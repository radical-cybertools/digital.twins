"""Main runtime for the DT framework

High level:
- Allows for user to build a graph of digital twin components (Utility Tasks, Agents, Investigators)
- The runtime then runs the graph.
- The runtime also translates the graph via its own data type resolver for the
in-situ flow via a system of queues.

"""

import asyncio
import logging
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import cast

try:
    from enum import StrEnum
except ImportError:
    from backports.strenum import StrEnum

from typing import Any, Callable, Optional

from radical.asyncflow import WorkflowEngine  # type: ignore

from .components import (
    NULL_DTYPE,
    TRUTHY,
    Barrier,
    DataType,
    JoinedTypedData,
    JoinDataType,
    ModelInvestigator,
    SciAgent,
    SharedSubtaskLabel,
    SplitTask,
    TypedData,
    UtilityTask,
    _TwinComponent,
)
from .streaming import CODEC_JSON, PubSubClient, PubSubConfig, check_codec
from .lru import LRUCache, freeze

logger = logging.getLogger(__name__)

# bounded wait for in-flight tasks to settle on stop()
STOP_TIMEOUT = 10.0

# How many recently submitted task uids a twin remembers.  This is an
# observation surface, not a ledger: `twin_list` carries it so an observer
# can say which twin a `task_status` notification belongs to, and one poll
# period's worth of submissions is all that is needed for that.  A uid the
# ring has dropped is simply unattributed.  asyncflow's uid counter is
# process-global and only `reset_uid_counter()` rewinds it (at backend
# shutdown), so within one host a uid never names two different twins.
TASK_UID_RING = 24

# The twin whose work the current asyncio task is doing.  asyncio copies the
# context into every task it creates, and asyncflow registers a component
# from a task of its own, so a runtime that stamps this once owns every uid
# assigned underneath it -- including the ones a user component submits from
# inside its own coroutine, which the runtime never sees.
_OWNER: ContextVar[Optional["DTRuntime"]] = ContextVar("dt_task_owner",
                                                      default=None)


def note_flow_task(fut: Any, owner: Optional["DTRuntime"] = None) -> Optional[str]:
    """Record the uid asyncflow assigned to `fut` against its owning twin.

    The uid is the one rhapsody publishes in `task_status`: asyncflow puts
    `task.NNNNNN` in the component description (`_assign_uid`) and the
    execution backend keeps it (`setdefault`), so joining on it is exact.

    Returns the uid when there was one.  A plain coroutine -- an inference
    task that is not a flow task -- has none and is skipped, and so is a
    future asyncflow has not stamped yet (`hook_engine` catches those).
    """

    who = owner or _OWNER.get()
    desc = getattr(fut, "task", None)
    uid = desc.get("uid") if isinstance(desc, dict) else None

    if who is None or not uid:
        return None

    who.note_task(uid)

    return uid


def hook_engine(flow: Any, owner: Optional["DTRuntime"] = None) -> None:
    """Capture every uid this engine assigns, at the moment it assigns it.

    asyncflow stamps the future from a task of its own, so the uid is not on
    it when a submitting call returns -- which is exactly when a twin would
    like to record it.  `_register_component` is where the uid is minted, so
    that is what this wraps, once per engine object; ownership comes from the
    context (see `_OWNER`), because one engine serves every twin of a
    session.  `owner` pins it for an engine driven from outside the runtime's
    own tasks (the ex-situ one, whose loop is ROSE's).

    In-package coupling to one asyncflow internal, deliberately: the
    alternative is a uid the service cannot know, and every honest
    alternative was tried first (see the README).
    """

    inner = getattr(flow, "_register_component", None)
    if inner is None or getattr(flow, "_dt_uid_hook", False):
        return

    def hooked(comp_fut, comp_type, comp_desc, *args, **kwargs):
        result = inner(comp_fut, comp_type, comp_desc, *args, **kwargs)
        try:
            uid = comp_desc.get("uid")
            who = _OWNER.get() or owner
            # blocks are not tasks and never appear in `task_status`
            if who is not None and isinstance(uid, str) and uid.startswith("task."):
                who.note_task(uid)
        except Exception as exc:                       # never break a submit
            logger.debug("uid capture failed: %s", exc)

        return result

    flow._register_component = hooked
    flow._dt_uid_hook = True


@dataclass(frozen=True)
class _InputBinding:
    """An external channel bound to an input dtype (see `add_input`)."""

    dtype: DataType
    channel: str
    codec: str


class RuntimeState(StrEnum):
    """Lifecycle of a twin runtime.

    `stopped` and `failed` are both terminal: a twin which fails tears
    itself down (see `_record_error`), it just reports the error rather
    than a clean stop.
    """

    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


# A special component that is called by the runtime for data join.
# Acts like a persistent utility task.
# It's main loop gets multiple streams...
class _JoinComponent(_TwinComponent):
    """Special component for joining multiple input streams into a single output.

    Should only be built by the runtime.

    The component registers a queue for each data type specified in ``join_dtype.dtypes``.
    Incoming :class:`TypedData` objects are queued via :meth:`update`.  Once items are
    present in all queues, :meth:`main_loop` gathers them, creates a
    :class:`JoinedTypedData` instance containing the list of results, and
    publishes it by calling the supplied ``submit_event_fn``.

    The component runs indefinitely until the surrounding runtime cancels it.

    Args:
        join_dtype: The combined data type that represents all input types.
        submit_event_fn: Function that receives the final :class:`JoinedTypedData`.

    Returns:
        None.
    """

    def __init__(self, join_dtype: JoinDataType, submit_event_fn: Callable) -> None:
        # FIXME(review): the depth-1 queues below plus the blocking `put` in
        # `update()` make a join a *non-local* operator.  `update` is awaited
        # from `_run_component`, which is gathered by `_dtype_consumer`, which
        # is awaited in `_launch_consumer`'s loop -- so while one input waits
        # for its partner, the whole consumer for that dtype is stalled,
        # including components which have nothing to do with the join.  The
        # existing `Barrier` deliberately does the opposite (unbounded output
        # queues, plus a soft mode).  Having two synchronisation primitives
        # with opposite back-pressure semantics and no stated distinction is
        # the actual problem; it needs a policy decision, not a patch.
        # Invisible in `08-data-join` because both sensors tick at 1 Hz.

        # need a queue for each input.
        self.input_queues: dict[DataType, asyncio.Queue] = {}
        self.submit_event_fn = submit_event_fn

        for dtype in join_dtype.dtypes:
            self.input_queues[dtype] = asyncio.Queue(1)  # only holds one item!

        self.out_dtype = join_dtype

    async def update(self, in_data: TypedData):
        # is the data type part of the ones registered?
        if in_data.dtype not in self.input_queues:
            raise ValueError(f"Received data with unexpected type: {in_data.dtype}!")

        # put the item on the queue - wait if busy
        await self.input_queues[in_data.dtype].put(in_data)

    async def main_loop(self):
        # simply wait on all queues, and then publish result
        while True:
            tk = []
            for t in self.input_queues:
                tk.append(self.input_queues[t].get())
            results = await asyncio.gather(*tk)
            out = JoinedTypedData(dtype=self.out_dtype, data=results)
            self.submit_event_fn(out)


@dataclass
class _SharedStruct:
    """Private container for shared subtask state.

    Each label registered via :meth:`RuntimeAPI.register_shared_subtask` receives a
    :class:`_SharedStruct` instance.  It holds an :class:`asyncio.Lock` to
    protect concurrent access, an :class:`LRUCache` for memoising results, and an
    optional ``wrap_fn`` callable that performs the actual task execution while
    honouring the cache.

    Attributes:
        lock: Synchronisation primitive for the cache.
        cache: LRU cache used to store outstanding or completed futures.
        wrap_fn: The wrapped coroutine that implements the heavy work.
    """

    lock: asyncio.Lock
    cache: LRUCache
    wrap_fn: Optional[Callable] = None


@dataclass
class _AnnotatedComponent:
    """Metadata wrapper for a component used by :class:`DTRuntime`.

    The runtime decouples execution logic from component details by associating
    additional information such as input/output data types, runtime events, and
    subscriptions with each component.  The class also keeps track of child
    investigators, shared subtasks, and various control flags used during the
    workflow.

    The attributes mirror those required by :class:`RuntimeAPI` and enable
    dynamic behavior such as publishing new models, selecting investigative
    models, and registering shared tasks.
    """

    component: _TwinComponent
    input_dtype: DataType = NULL_DTYPE
    output_dtype: DataType = NULL_DTYPE
    is_persistent: bool = False
    subscriptions: dict[str, list[Callable]] = field(
        default_factory=lambda: defaultdict(list)
    )
    model_kwargs: dict[str, Any] = field(default_factory=dict)
    accuracy_kwargs: dict[str, Any] = field(default_factory=dict)
    inference_task: Optional[Callable] = None
    investigators: dict[int, "_AnnotatedComponent"] = field(default_factory=dict)
    model_select_task: Optional[Callable] = None

    model_select_args: tuple = tuple()
    model_select_kwargs: dict = field(default_factory=dict)

    has_published_model: asyncio.Event = field(default_factory=lambda: asyncio.Event())
    has_published_selector: asyncio.Event = field(
        default_factory=lambda: asyncio.Event()
    )
    model_publish_cb: Optional[Callable] = None
    split_outputs: tuple[DataType] = tuple([])  # type: ignore

    shared_tasks: dict[SharedSubtaskLabel, _SharedStruct] = field(default_factory=dict)


class RuntimeAPI:
    """External API that components can use to interact with the Digital-Twin
    runtime. What a twin component sees of its runtime.

    ``RuntimeAPI`` exposes methods for:
    * Subscribing to runtime events (inputs, outputs, model publishes, etc.).
    * Publishing a freshly trained model and notifying observers.
    * Registering an inference callback used by investigators.
    * Managing investigators and model selectors in ``SciAgent`` instances.
    * Handling shared sub-task memoisation for agents.

    The class stores a reference to its annotated component and keeps track of
    background tasks that are spawned when publishing callbacks.
    """

    ON_INPUT = "runtime/ON_INPUT"
    ON_OUTPUT = "runtime/ON_OUTPUT"
    ON_MODEL_PUBLISH = "runtime/ON_PUBLISH"
    ON_FILTERED_INPUT = "runtime/ON_FILTER_INPUT"
    ON_FILTERED_OUTPUT = "runtime/ON_FILTER_OUTPUT"

    def __init__(self, runtime: "DTRuntime", ant: _AnnotatedComponent):
        """Create the runtime API facade for a component.

        Args:
            runtime: The DTRuntime.
            ant: The annotated component that this API will control.
        """
        self._runtime = runtime
        self._ant = ant
        self._internal_add_investigator: Optional[Callable] = None

        if isinstance(self._ant.component, SplitTask):
            self.cmp_type = f"SPLIT"
        elif isinstance(self._ant.component, UtilityTask):
            self.cmp_type = (
                f"UTILITY-{'persist' if self._ant.is_persistent else 'regular'}"
            )
        elif isinstance(self._ant.component, ModelInvestigator):
            self.cmp_type = f"INVESTIGATOR"
        elif isinstance(self._ant.component, SciAgent):
            self.cmp_type = f"AGENT"
        elif isinstance(self._ant.component, _JoinComponent):
            self.cmp_type = f"JOIN"
        else:
            raise ValueError("Unknown component type!")

    @property
    def stream(self) -> PubSubClient:
        """The twin's namespaced, connected stream client.

        Persistent components publish their output through it (the runtime
        subscribes to that dtype and feeds the graph with it).  Components
        never build their own transport clients and never see addresses.

        This is the in-process convenience: the same endpoint `stream_config`
        describes, already open.  Code which does not run on the host loop
        needs the config instead -- see below.
        """

        return self._runtime.streamer

    @property
    def stream_config(self) -> PubSubConfig:
        """The twin's stream endpoint as plain data.

        Ship *this* to code which runs outside the host process (a task in
        another process or on another host) and let it open its own client:
        the live client above holds sockets, a receive loop and subscriber
        queues, none of which can travel.
        """

        return self._runtime.stream_config

    def subscribe_to_topic(self, topic: str, task: Callable) -> None:
        """Register a callback under a specific runtime event.

        The callback will be invoked whenever the component receives an event
        from the runtime.

        Supported events:
            * :pyattr:`ON_INPUT` - send all input received by the agent.
            * :pyattr:`ON_OUTPUT` - send all output emitted by the agent.
            * :pyattr:`ON_MODEL_PUBLISH` - for agents when an investigator
              publishes a model.
            * :pyattr:`ON_FILTERED_INPUT` - invoke only for selected
              investigators.
            * :pyattr:`ON_FILTERED_OUTPUT` - invoke only for selected
              investigators.

        Args:
            topic: Name of the runtime event.
            task: Callback to register.
        """

        assert self.cmp_type in ["INVESTIGATOR", "AGENT"]
        self._ant.subscriptions[topic].append(task)

    def publish_new_model(self, model_kwargs=None, acc_kwargs=None) -> None:
        """Publish a newly trained model from an agent.

        The method stores the provided ``model_kwargs`` and ``acc_kwargs`` on the
        annotated component, sets an internal event to signal that a model has
        been published, and optionally triggers a callback if one is defined.

        Args:
            model_kwargs: Keyword arguments describing the model.
            acc_kwargs: Keyword arguments describing accuracy or evaluation.
        """

        assert self.cmp_type in ["INVESTIGATOR"]

        # `None` is the "caller passed nothing" sentinel, not a value the
        # rest of the runtime can hold: `_run_component` splats these into
        # the inference task, and `**None` raises.  Normalised here, the
        # same way the callback below already normalises them.
        self._ant.model_kwargs = model_kwargs or {}
        self._ant.accuracy_kwargs = acc_kwargs or {}
        self._ant.has_published_model.set()
        if self._ant.model_publish_cb is not None:
            self._runtime._to_asyncio_task(
                self._ant.model_publish_cb,
                self._ant.component,
                model_kwargs if model_kwargs else {},
                acc_kwargs if acc_kwargs else {},
            )

    def set_inference_task(self, task: Callable) -> None:
        """Associate an inference callback with an investigator.

        The callback is stored on the annotated component and will be invoked
        when the investigator receives input data.

        Args:
            task: Callable that implements the inference logic.
        """

        assert self.cmp_type in ["INVESTIGATOR"]
        self._ant.inference_task = task

    def start_investigator(self, investigator: ModelInvestigator):
        """Begin monitoring an investigator from a ``SciAgent``.

        The investigator is wrapped in an :class:`_AnnotatedComponent` and
        added to the agent's investigator registry.  A background task running
        ``investigator.main_loop`` is scheduled to execute the investigation
        logic.

        Args:
            investigator: The investigator component to start.
        """

        assert self.cmp_type in ["AGENT"]
        if self._internal_add_investigator is None:
            raise ValueError("Only can start an investigator inside a SciAgent")

        count = len(self._ant.investigators)

        new = _AnnotatedComponent(
            investigator,
            input_dtype=self._ant.input_dtype,
            output_dtype=self._ant.output_dtype,
            is_persistent=False,
        )
        assert isinstance(self._ant.component, SciAgent)
        new.model_publish_cb = self._ant.component.model_publish_cb
        investigator.runtime_id = count
        self._ant.investigators[count] = new
        self._internal_add_investigator(new)  # calls the loop

    # receives TypedData. Outputs investigator ID.
    def set_model_selection_task(self, task: Callable) -> None:
        """Set the model-selection callback used by a ``SciAgent``.

        The callback chooses an investigator ID or tuple of (ID, kwargs) based on
        input data.

        Args:
            task: Callable that returns selected investigator information.
        """

        assert self.cmp_type in ["AGENT"]
        self._ant.model_select_task = task

    def update_model_selector(self, *args, **kwargs) -> None:
        """Publish arguments for a model-selection call.

        The ``SciAgent`` uses these arguments to invoke :meth:`model_select_task`.

        Args:
            *args: Positional arguments for the selector.
            **kwargs: Keyword arguments for the selector.
        """

        assert self.cmp_type in ["AGENT"]
        self._ant.model_select_args = args
        self._ant.model_select_kwargs = kwargs
        self._ant.has_published_selector.set()

    # the learner can request inference from other agents --- is blocking
    async def get_inference(
        self, input_d: TypedData, output_dtype: DataType
    ) -> TypedData:
        """Request inference from another agent.

        The runtime forwards the request to the appropriate registered agent
        component.  The call is awaited and the resulting :class:`TypedData`
        instance is returned.

        Args:
            input_d: Input data to forward.
            output_dtype: Desired output data type.

        Returns:
            ``TypedData`` produced by the requested agent.
        """

        assert self.cmp_type not in ["JOIN"]
        return await self._runtime._internal_agent_inference(input_d, output_dtype)

    # for shared SIMs in the agent.
    def register_shared_subtask(
        self, label: SharedSubtaskLabel, task: Callable, lru_size: int = 128
    ):
        """Register a memoised sub-task that can be shared across investigators.

        The shared task is wrapped to keep a per-label LRU cache.  The wrapper
        ensures that concurrent invocations wait for the same cache entry and
        results are returned from the cache when available.

        Args:
            label: Unique identifier for the shared task.
            task: The coroutine function to execute.
            lru_size: Maximum number of cached results.

        Returns:
            Wrapped coroutine that implements cache logic.
        """

        assert self.cmp_type in ["AGENT"]
        logger.info(f"Register shared subtask with label {label}. LRU size: {lru_size}")

        # FIXME(review): one open defect in the memoisation below:
        #
        #  * registration copies the label into `self._ant.investigators` as
        #    they stand *now*; an investigator started afterwards silently has
        #    no such label.  `11-shared-sim` happens to start its two first.
        #
        # Two others -- a lock held forever after cancellation, and failed or
        # cancelled futures staying cached (issue #12) -- are fixed below; the
        # frozen-arguments one was fixed upstream in 97c96b4/8487a4b: the key
        # is now the only thing frozen.

        async def wrapper(*args, **kwargs):
            # task must be awaitable
            return await task(*args, **kwargs)

        cache = LRUCache(lru_size)
        lock = asyncio.Lock()
        self._ant.shared_tasks[label] = _SharedStruct(lock=lock, cache=cache)

        async def fetch_wrapper(*args, **kwargs):
            key = freeze((args, tuple(sorted(kwargs.items()))))
            struct = self._ant.shared_tasks[label]

            async with struct.lock:
                if await struct.cache.exists(key):
                    logger.info(
                        f"Computation of {label} {key if len(str(key)) < 20 else ''} saved. Return future."
                    )
                    fut = await struct.cache.fetch_item(key)
                else:
                    logger.info(
                        f"Begin compute of {label} {key if len(str(key)) < 20 else ''}. Return future."
                    )
                    fut = asyncio.ensure_future(wrapper(*args, **kwargs))

                    # only a future that completed is worth keeping: one that
                    # raised or was cancelled would replay its failure to every
                    # later caller, so it leaves the cache the moment it ends
                    def evict_on_failure(f, key=key, struct=struct):
                        if f.cancelled() or f.exception() is not None:
                            struct.cache.drop(key, f)

                    fut.add_done_callback(evict_on_failure)
                    await struct.cache.put_item(key, fut)

            # shielded: a cancelled caller must not cancel the shared future
            # under the other waiters
            return await asyncio.shield(fut)

        # store wrapped function
        self._ant.shared_tasks[label].wrap_fn = fetch_wrapper

        # add to investigators
        for inv_ant in self._ant.investigators.values():
            inv_ant.shared_tasks[label] = self._ant.shared_tasks[label]

        return fetch_wrapper

    async def call_shared_subtask(self, label: SharedSubtaskLabel, *args, **kwargs):
        """Invoke a previously-registered shared sub-task.

        The method forwards the call to the cached wrapper stored during
        registration.

        Args:
            label: The shared task identifier.
            *args, **kwargs: Arguments for the wrapped task.

        Returns:
            Result of the underlying coroutine.
        """

        assert self.cmp_type in ["AGENT", "INVESTIGATOR"]

        # uses the shared_tasks dict in the annotated component
        # reference was copied to investigator by agent
        if label not in self._ant.shared_tasks:
            raise ValueError(
                f"Unknown shared task label: {label}. Expected: {list(self._ant.shared_tasks.keys())}"
            )
        assert self._ant.shared_tasks[label].wrap_fn is not None
        return await self._ant.shared_tasks[label].wrap_fn(*args, **kwargs)  # type: ignore

    def get_shared_subtask(self, label: SharedSubtaskLabel):
        """Retrieve the wrapped callable for a registered shared sub-task.

        The returned callable can be invoked directly and will honour the LRU
        cache.

        Args:
            label: The shared task identifier.

        Returns:
            Wrapped coroutine implementing the cached logic.
        """

        assert self.cmp_type in ["AGENT", "INVESTIGATOR"]

        # uses the shared_tasks dict in the annotated component
        # reference was copied to investigator by agent.
        #
        # Simply returns the callable.
        if label not in self._ant.shared_tasks:
            raise ValueError(
                f"Unknown shared task label: {label}. Expected: {list(self._ant.shared_tasks.keys())}"
            )
        assert self._ant.shared_tasks[label].wrap_fn is not None

        return self._ant.shared_tasks[label].wrap_fn


class DTRuntime:
    """Workflow builder and dynamic manager.

    The :class:`DTRuntime` orchestrates the execution of Digital Twin
    components.  It keeps an adjacency list of components per input data type,
    queues for data distribution, and supports special operators such as JOINs,
    SPLITs, and Barriers for synchronizing event order.

    Typical usage example:

    .. code-block:: python

        flow = WorkflowEngine()
        streamer = PubSubClient()
        dt = DTRuntime(flow, streamer)
        dt.add_task(...)      # register UtilityTask or SplitTask
        dt.add_investigator(...)   # register investigator edges
        dt.add_agent(...)          # register SciAgent edges
        dt.start()                 # enable processing

    All public methods are documented below.
    """

    def __init__(self, flow: WorkflowEngine, streamer: PubSubClient) -> None:
        """Create a runtime from the provided workflow engine and PubSub
        client.

        Args:
            flow: Instance of :class:`radical.asyncflow.WorkflowEngine`
                used to schedule and block tasks.
            streamer: Backend pub/sub client used to forward messages between
                components.
        """

        super().__init__()

        self.flow = flow
        self.streamer = streamer

        # A digital twin workflow has nodes and edges:
        #  - nodes: the actual DTypes
        #  - edges: Investigators, Utility Tasks

        self.dtype_queues: dict[DataType, asyncio.Queue] = {}

        # the tasks (edges). Defined by the input data type
        self.components: dict[DataType, list[_AnnotatedComponent]] = defaultdict(list)

        # list of barriers: order of PRODUCE --> CONSUME
        self.barriers: dict[DataType, list[Barrier]] = defaultdict(list)

        # the graph's input edge: external channels feeding a dtype
        self.inputs: list[_InputBinding] = []

        # join registry so that there are no duplicates
        self.join_components: dict[JoinDataType, _JoinComponent] = {}

        self.running_tasks: set[asyncio.Task] = set()

        self.is_start = asyncio.Event()

        self.state = RuntimeState.READY
        self.last_error: Optional[str] = None

        # the one teardown, whichever door started it: stop() or a failure.
        # Its presence is also what closes the twin for new work.
        self._stop_task: Optional[asyncio.Task] = None

        # Task ownership, for anything watching from outside: the uids this
        # twin most recently submitted (see `TASK_UID_RING`).  A submission
        # overwrites the oldest, which is also what makes it self-healing --
        # nothing has to be cleaned up, and a twin that stops submitting
        # stops appearing in new notifications.
        self._task_uids: deque[str] = deque(maxlen=TASK_UID_RING)
        self._task_seen: set[str] = set()

        hook_engine(flow)

        # a stalled stream is a twin failure, not a log line
        streamer.on_error = self._record_error

    def note_task(self, uid: str) -> None:
        """Record a task uid as this twin's.  Idempotent and bounded."""

        if uid in self._task_seen:
            return

        if len(self._task_uids) == self._task_uids.maxlen:
            self._task_seen.discard(self._task_uids[0])

        self._task_uids.append(uid)
        self._task_seen.add(uid)

    def task_uids(self) -> list[str]:
        """The uids this twin submitted most recently, oldest first."""

        return list(self._task_uids)

    @property
    def stream_config(self) -> PubSubConfig:
        """This twin's stream endpoint as plain data (see `PubSubConfig`).

        Derived from the injected client, so it cannot go stale.
        """

        return self.streamer.config

    async def _call_await(self, func, *args, **kwargs) -> None:
        """Await a given coroutine function.

        The helper wraps an awaitable in a non-blocking fashion but still keeps
        stack traces intact.

        Args:
            func: Coroutine function to await.
            *args, **kwargs: Arguments for ``func``.
        """

        await func(*args, **kwargs)

    def start(self) -> None:
        """Signal that the runtime is ready and allow queued components to
        begin processing.

        The method simply fires an internal event that other coroutine
        functions wait on before executing.
        """
        if self.state is RuntimeState.STOPPED:
            raise RuntimeError("stop() is terminal - this twin cannot be restarted")

        if self.state is RuntimeState.FAILED:
            raise RuntimeError(
                f"twin has failed and cannot be started: {self.last_error}"
            )

        self.state = RuntimeState.RUNNING
        self.is_start.set()

    async def stop(self, timeout: float = STOP_TIMEOUT):
        """Tear this twin down.  Terminal, idempotent, per-twin.

        Idempotent by joining: concurrent and repeated calls await the one
        teardown, so `stop()` only ever returns once the twin is down.

        Cancels every task the runtime owns (component main loops,
        callbacks, dtype consumers, barrier loops), then drops the twin's
        stream subscriptions and closes its stream client.  The execution
        engine is shared and never touched here.

        In-flight backend tasks: cancelling the task that awaits one
        propagates the cancellation into the backend call, which is a
        best-effort cancel.  Whatever has not settled after `timeout` is
        abandoned with a warning -- stop() never waits unboundedly.

        On a twin which already failed this is a bounded no-op: the
        failure tore the twin down on its own, so stop() joins *that*
        teardown (on its budget, not this `timeout`) and leaves the twin
        `failed` -- the error is the more useful fact to report, and
        `last_error` survives.
        """

        if self._stop_task is None:
            # flip the state before scheduling: no new work from here on
            self.state = RuntimeState.STOPPED
            self._stop_task = self._start_teardown(timeout)

        # every caller joins the one teardown; a cancelled caller does not
        # abort it (stop is terminal)
        logger.info("Shutting down runtime....")
        await asyncio.shield(self._stop_task)

    def _start_teardown(self, timeout: float) -> asyncio.Task:
        """Schedule the one teardown and return its handle.

        Deliberately *not* through `_to_asyncio_task`: teardown cancels
        everything in `running_tasks`, so a teardown registered there
        would cancel itself on its first await.

        The handle is what makes teardown joinable (`stop()`) and
        observable; the done-callback is what keeps it quiet when nobody
        joins it, which is the case whenever a failure started it.
        """

        task = asyncio.ensure_future(self._teardown(timeout))
        task.add_done_callback(self._teardown_done)

        return task

    def _teardown_done(self, task: asyncio.Task):
        """Consume the teardown's outcome: nothing awaits the teardown a
        failure started, and an unretrieved exception would surface as
        loop noise long after the fact.  It is logged, not recorded -- a
        mishap while cleaning up must not overwrite the cause."""

        if task.cancelled():
            return

        exc = task.exception()
        if exc is not None:
            logger.error("twin teardown failed: %s", exc, exc_info=exc)

    async def _teardown(self, timeout: float):
        await self._quiesce(timeout)

        tasks, self.running_tasks = self.running_tasks, set()
        for task in tasks:
            task.cancel()

        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            if pending:
                logger.warning(
                    "abandoning %d task(s) which ignored cancellation: %s",
                    len(pending),
                    ", ".join(str(task.get_coro()) for task in pending),
                )

        try:
            await asyncio.wait_for(self.streamer.close(), timeout)
        except asyncio.TimeoutError:
            logger.warning("stream client did not close within %ss", timeout)
        except Exception as exc:
            self._record_error(exc)

    async def _quiesce(self, timeout: float):
        """Let components wind down their own machinery before cancellation.

        One shared budget, spent *concurrently*: two learners waiting five
        seconds each must not add up to ten.  Whoever ignores the budget
        is cancelled like everything else a moment later.
        """

        async def wind_down(component: _TwinComponent):
            try:
                await component._on_stop()
            except Exception as exc:
                self._record_error(exc)

        hooks = [wind_down(ant.component) for ant in self._annotated()]
        if not hooks:
            return

        try:
            async with asyncio.timeout(timeout):
                await asyncio.gather(*hooks)

        except TimeoutError:
            logger.warning("component teardown exceeded %ss", timeout)

    def _annotated(self):
        """Every component in the graph, child investigators included."""

        for ants in list(self.components.values()):
            for ant in ants:
                yield ant
                yield from ant.investigators.values()

    async def _owned(self, func, *args, **kwargs):
        """Run a component's coroutine as this twin's work.

        The stamp lives in the task's own context, so it reaches every task
        created underneath -- asyncflow's registration among them -- and no
        sibling twin's.
        """

        _OWNER.set(self)

        return await func(*args, **kwargs)

    def _to_asyncio_task(self, func, *args, **kwargs) -> Optional[asyncio.Task]:
        """Schedule a coroutine as an :class:`asyncio.Task` and track its
        completion.

        The method creates a background :class:`asyncio.Task` and registers a
        ``done`` callback to automatically propagate exceptions and to remove
        the finished task from the internal tracker.

        Args:
            func: Coroutine function to run.
            *args, **kwargs: Arguments to ``func``.
        """
        # a twin which is being torn down starts no new work: a task
        # registered after teardown swapped `running_tasks` out would never
        # be cancelled by anyone
        if self._stop_task is not None or self.state is RuntimeState.FAILED:
            logger.debug("twin is %s - not running %s", self.state, func)
            return None

        task = asyncio.create_task(self._owned(func, *args, **kwargs))
        self.running_tasks.add(task)
        task.add_done_callback(self._task_done)

        return task

    def _task_done(self, task: asyncio.Task):
        """Done callback for all runtime tasks: cancellation-safe, and it
        routes component failures into the twin state instead of dumping
        them into the event loop's exception handler."""

        self.running_tasks.discard(task)

        if task.cancelled():
            return

        exc = task.exception()
        if exc is not None:
            self._record_error(exc)

    def fail(self, error: str):
        """Route an out-of-band failure into the twin state.

        Component failures arrive through the done-callbacks; this is the
        door for the ones only the host can see -- a lost engine endpoint
        (R8) strands every component bound to that engine, but nothing
        inside the runtime notices.
        """

        self._record_error(error)

    def _record_error(self, exc: BaseException | str):
        """Route a failure into the twin state, and stop the twin.

        A component failure is a twin failure: the other components have
        lost the graph they were part of, so the twin is torn down exactly
        as `stop()` would tear it down -- but it ends up `failed`, with
        `last_error`, rather than `stopped`.

        Called from several doors, all of them synchronous and all of them
        on the host loop: task done-callbacks, the teardown itself, and
        `PubSubClient.on_error` (the stream backends report from the
        done-callback of their receive loop; a backend whose events arrive
        on a foreign thread hands them over with `call_soon_threadsafe`
        first).  Teardown is therefore *scheduled*, never awaited here.

        Re-entrant by construction: the first failure owns the report and
        the teardown, and everything after it is fallout -- teardown
        cancelling the failure's siblings, a stop hook tripping over a
        half-dead component -- which is logged and dropped.
        """

        error = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
        logger.error(
            "twin component failed: %s",
            error,
            exc_info=exc if isinstance(exc, BaseException) else None,
        )

        if self.state is RuntimeState.FAILED:
            # the cause is already recorded, and its teardown is running
            return

        self.last_error = error

        # a stopped twin stays stopped, but keeps the error for inspection
        if self.state is RuntimeState.STOPPED:
            return

        self.state = RuntimeState.FAILED

        if self._stop_task is None:
            self._stop_task = self._start_teardown(STOP_TIMEOUT)

    def _api(self, ant: _AnnotatedComponent) -> RuntimeAPI:
        return RuntimeAPI(self, ant)

    def _check_mutable(self):
        # both terminal states are terminal for the graph as well
        if self.state in (RuntimeState.STOPPED, RuntimeState.FAILED):
            raise RuntimeError(f"twin is {self.state} - its graph cannot be changed")

    def _ensure_dtype_queue(self, dtype: DataType) -> asyncio.Queue:
        """The queue feeding the components registered for `dtype`, with
        its consumer task running."""

        if dtype not in self.dtype_queues:
            logger.info(f"Create listener for: {dtype}")
            self.dtype_queues[dtype] = asyncio.Queue()
            self._to_asyncio_task(self._launch_consumer, dtype)

        return self.dtype_queues[dtype]

    def add_input(self, dtype: DataType, channel: str, codec: str = CODEC_JSON):
        """Open the graph at its input edge: bind an external channel.

        Sensors and other producers live outside the framework.  They
        publish to a shared channel, this binds that channel to an input
        dtype, and from there the data flows exactly like traffic a
        component produced.  The channel topic is shared verbatim, so any
        number of twins may bind the same one and each of them receives
        every message on it.

        `codec` decodes the payloads: `json` for the plain scripts and
        instruments which are the normal producers, `raw` for bytes, and
        `cloudpickle` only for producers inside the same trust domain
        (see the binding policy in the README).

        Internal producers keep their own path: a persistent component
        publishes through `RuntimeAPI.stream`.
        """

        self._check_mutable()

        PubSubClient.check_channel(channel)
        check_codec(codec)

        binding = _InputBinding(dtype, channel, codec)
        if binding in self.inputs:
            return
        self.inputs.append(binding)

        # subscribe now, so nothing published before start() is lost: the
        # queue buffers it and the consumers wait for start anyway
        logger.info(f"Bind channel {channel!r} ({codec}) to dtype: {dtype}")
        self._to_asyncio_task(
            self.streamer.subscribe_to_channel,
            channel,
            dtype,
            self._ensure_dtype_queue(dtype),
            codec,
        )

    def add_task(
        self,
        task: UtilityTask,
        input_dtype: DataType,
        output_dtype: DataType,
        is_persistent: bool = False,
    ) -> None:
        """Register a utility task in the runtime.

        A :class:`UtilityTask` produces an output :class:`TypedData` given an input
        instance.  If persistent, its mainloop will run detached and output TypedData is
        expected to be published via the PubSubClient.

        Args:
            task: UtilityTask instance.
            input_dtype: Data type that the task consumes.
            output_dtype: Desired output data type.
            is_persistent: Persistence flag for the task.
        """
        self._check_mutable()

        assert isinstance(task, UtilityTask)

        ant_comp = _AnnotatedComponent(task, input_dtype, output_dtype, is_persistent)

        # Add component to edge dict
        self.components[input_dtype].append(ant_comp)

        # is input_dtype TRUTHY? If so, run it!
        if input_dtype == TRUTHY:
            logger.debug("Added task with input of TRUTHY... Running.")
            true_data = TypedData(TRUTHY, True)
            # call as a block so it receives Ctrl-C
            self._to_asyncio_task(self._run_component, ant_comp, true_data)

    def add_investigator(
        self,
        investigator: ModelInvestigator,
        input_dtype: DataType,
        output_dtype: DataType,
        *args,
        **kwargs,
    ):
        """Register a model investigator.


        A model investigator's main loop will be started immediately.
        The model investigator's inference task will be called for in-situ
        inference.

        Args:
            investigator: Investigator to add.
            input_dtype: Input data type consumed.
            output_dtype: Output data type produced.
            *args, **kwargs: Additional keyword arguments for ``investigator.main_loop``.
        """
        self._check_mutable()
        assert input_dtype != TRUTHY

        # check: is there already an investigator or agent assigned to this
        # input output pair?
        for r in self.components.get(input_dtype, []):
            if r.output_dtype == output_dtype and (
                isinstance(r.component, (ModelInvestigator, SciAgent))
            ):
                raise ValueError(
                    f"Error: investigator or agent already exists with {input_dtype}-->{output_dtype} mapping"
                )

        ant_comp = _AnnotatedComponent(investigator, input_dtype, output_dtype, False)

        # Add component to edge dict
        self.components[input_dtype].append(ant_comp)

        # start up its main loop
        rt = self._api(ant_comp)
        self._to_asyncio_task(investigator.main_loop, rt, *args, **kwargs)

    def _internal_add_investigator(self, ant: _AnnotatedComponent) -> None:
        """Internal helper to add an investigator to the runtime.

        The method subscribes investigators to relevant dtype topics and
        schedules their main loops for execution.

        Args:
            ant: Annotated component representing the investigator.
        """

        # subscribe to model publishes
        # start up its main loop
        rt = self._api(ant)
        self._to_asyncio_task(ant.component.main_loop, rt)

    def add_agent(
        self,
        agent: SciAgent,
        input_dtype: DataType,
        output_dtype: DataType,
        *args,
        **kwargs,
    ):
        """Register a science agent.

        A science agent's main loop will be run right away. The model selection
        task will be called for in-situ inference.

        Args:
            agent: ``SciAgent`` instance.
            input_dtype: Data type consumed.
            output_dtype: Data type produced.
            *args, **kwargs: Additional arguments for ``agent.main_loop``.
        """
        self._check_mutable()
        assert input_dtype != TRUTHY

        # check: is there already an investigator or agent assigned to this
        # input output pair?
        for r in self.components.get(input_dtype, []):
            if r.output_dtype == output_dtype and (
                isinstance(r.component, (ModelInvestigator, SciAgent))
            ):
                raise ValueError(
                    f"Error: investigator or agent already exists with {input_dtype}-->{output_dtype} mapping"
                )

        ant_comp = _AnnotatedComponent(agent, input_dtype, output_dtype, False)
        # logger.debug(f"Add: {ant_comp}")
        # Add component to edge dict
        self.components[input_dtype].append(ant_comp)

        # start up its main loop. Agents get a patched start_investigator
        rt = self._api(ant_comp)
        rt._internal_add_investigator = self._internal_add_investigator
        self._to_asyncio_task(agent.main_loop, rt, *args, **kwargs)

    async def get_inference(
        self, in_data: TypedData, output_dtype: DataType
    ) -> TypedData:
        """Run one inference through the graph and return its result.

        The out-of-graph entry point (the service exposes it as a verb);
        components use `RuntimeAPI.get_inference`, which is the same path.
        `NULL_DTYPE` comes back when no component serves the requested
        input -> output mapping.
        """

        answer = await self._internal_agent_inference(in_data, output_dtype)

        return answer if answer is not None else TypedData(NULL_DTYPE, None)

    # agent-to-agent inference communication
    async def _internal_agent_inference(self, in_data: TypedData, req_dtype: DataType):
        """Forward agent-to-agent inference requests.

        The method looks up agents registered for the input ``dtype`` and
        requests inference. Bypasses queues, runs in a blocking manner.

        Args:
            in_data: Input data.
            req_dtype: Desired output data type.

        Returns:
            ``TypedData``
        """

        for component in self.components.get(in_data.dtype, []):
            if component.output_dtype == req_dtype and component.is_persistent is False:
                # check if agent or investigator
                answer = await self._run_component(
                    component, in_data, skip_queue_out=True
                )
                if answer is None:
                    return TypedData(NULL_DTYPE, None)
                return answer

    # add a barrier
    def add_barrier(self, barrier: Barrier) -> None:
        """Register a synchronization barrier.

        A :class:`Barrier` can span multiple data types.  The method schedules
        consumers that route data from the previous barrier to the next one.

        Args:
            barrier: :class:`Barrier` instance to add.
        """
        self._check_mutable()

        # a barrier spans across multiple dtypes.... add in the order that
        # follows.
        for dtype in barrier.dtypes:
            self.barriers[dtype].append(barrier)
            if len(self.barriers[dtype]) > 1:
                # NOT the first barrier
                self._to_asyncio_task(
                    self._barrier_consumer, dtype, self.barriers[dtype][-2], barrier
                )

        self._to_asyncio_task(barrier.run)

        # I need a consumer per dtype per barrier.

    async def _barrier_consumer(
        self, dtype, get_barrier: Barrier, put_barrier: Barrier
    ) -> None:
        """Consume data from one barrier and forward it to the next.

        The consumer continuously waits for data matching ``dtype`` on
        ``get_barrier`` and forwards it to ``put_barrier``.

        Args:
            dtype: Data type routed through the barriers.
            get_barrier: Barrier that provides data.
            put_barrier: Barrier that consumes data.
        """

        while True:
            val = await get_barrier.get(dtype)
            logger.debug(
                f"Barrier receive from {get_barrier}:{dtype}. Put to {put_barrier}"
            )
            await put_barrier.put(val)

    # add a data join
    def add_data_join(self, join_dtype: JoinDataType):
        """Create a data-join component that waits on all input streams.

        The data join task will produce data tagged with the given join dtype.

        Args:
            join_dtype: Combined data type representing the join.
        """

        self._check_mutable()
        if join_dtype in self.join_components:
            raise ValueError("Data join already exists for that type")

        cmp = _JoinComponent(join_dtype, self._put_to_dtype_queue)
        self.join_components[join_dtype] = cmp

        # add to component registry
        for dtype in join_dtype.dtypes:
            # component handles its own output
            ant_comp = _AnnotatedComponent(cmp, dtype, join_dtype)
            self.components[dtype].append(ant_comp)

        # start main loop
        self._to_asyncio_task(self.join_components[join_dtype].main_loop)

    # add a data split task - just about the same as a utility task

    def add_data_split_task(
        self, task: SplitTask, input_dtype: DataType, output_dtypes: tuple[DataType]
    ):
        """Register a split task that forwards a single input into multiple
        output data types.

        Args:
            task: Split task instance.
            input_dtype: Input data type consumed.
            output_dtypes: Tuple of output data types produced.
        """

        self._check_mutable()
        assert input_dtype != TRUTHY

        ant_comp = _AnnotatedComponent(task, input_dtype, NULL_DTYPE, False)
        ant_comp.split_outputs = tuple(output_dtypes)  # type: ignore
        self.components[input_dtype].append(ant_comp)

    async def _run_component(
        self, ant: _AnnotatedComponent, in_data: TypedData, skip_queue_out: bool = False
    ):
        """Execute a component's main loop / its inference tasks.

        This is the meat and potatoes of the runtime, running each component and
        calling necessary subscriptions.

        Args:
            ant: Annotated component to run.
            in_data: Input :class:`TypedData` instance.
            skip_queue_out: Flag indicating whether to skip enqueuing the
                output for the consumer.

        Returns:
            Final ``TypedData`` produced, or ``None`` for special cases (e.g.
            joins and persistent utility tasks.)
        """

        # Every task submitted under this call is this twin's, including the
        # ones a component submits from inside its own coroutine.  Stamped
        # here as well as in `_owned` because a client's `get_inference`
        # arrives on a request handler's context, not on one of ours.
        _OWNER.set(self)

        await self.is_start.wait()
        logger.info(f"Online run: {type(ant.component).__name__}.")

        assert ant.input_dtype == TRUTHY or ant.input_dtype == in_data.dtype

        # is the component a data JOIN?
        # special handling
        if isinstance(ant.component, _JoinComponent):
            await ant.component.update(in_data)
            return  # NULL_VAL.. Output done by component directly

        for cb in ant.subscriptions[RuntimeAPI.ON_INPUT]:
            logger.info(f"Fire ON_INPUT on {cb}")
            self._to_asyncio_task(self._call_await, cb, in_data)

        # and child investigators
        for investigator in ant.investigators.values():
            for cb in investigator.subscriptions[RuntimeAPI.ON_INPUT]:
                logger.info(f"Fire ON_INPUT on {cb}")
                self._to_asyncio_task(self._call_await, cb, in_data)

        # run the main loop directly
        if isinstance(ant.component, UtilityTask):
            if ant.is_persistent:
                # is persistent, so subscribe to its output
                if (
                    ant.output_dtype in self.components
                    or ant.output_dtype in self.barriers
                ):
                    logger.info(f"Subscribe to dtype: {ant.output_dtype}")
                    await self.streamer.subscribe_to_dtype(
                        ant.output_dtype, self._ensure_dtype_queue(ant.output_dtype)
                    )
                # else: output is null.

                # run mainloop as async task
                rt = self._api(ant)
                logger.info(f"Run {type(ant.component).__name__} main loop")
                self._to_asyncio_task(ant.component.main_loop, rt, in_data)
                return

            rt = self._api(ant)
            logger.info(f"Run {type(ant.component).__name__} main loop")
            answer = await ant.component.main_loop(rt, in_data)

            # for split tasks, treat the answer differently
            # splits also don't support an output callback
            if isinstance(ant.component, SplitTask):
                # do checks
                if answer is None:
                    raise ValueError("Answer is None!")

                l_answer = cast(tuple[TypedData], answer)  # type: ignore

                if ant.split_outputs is None or len(l_answer) != len(ant.split_outputs):
                    raise ValueError("Unexpected outputs returned by SplitTask")

                for i in range(len(l_answer)):
                    if (
                        l_answer[i] is not None
                        and l_answer[i].dtype != ant.split_outputs[i]
                    ):
                        raise ValueError("Unexpected outputs returned by SplitTask")

                # checks done, send out. None acts as a blank
                for part in l_answer:
                    if part is None:
                        continue
                    self._put_to_dtype_queue(part)
                return

            if answer is None:
                # no downstream tasks. End
                return
            assert isinstance(answer, TypedData)

            if answer.dtype == NULL_DTYPE:
                return

            if answer.dtype != ant.output_dtype:
                raise ValueError(
                    f"Utility Task {ant.component} did not return the correct dtype. Expected: {ant.output_dtype}"
                )

        # item is an investigator - run its inference
        elif isinstance(ant.component, ModelInvestigator):
            # wait until there is an inference task
            await ant.has_published_model.wait()
            assert ant.inference_task is not None

            logger.debug(f"Run {type(ant.component).__name__} inference task")
            answer = await self._infer(ant, in_data, ant.model_kwargs)
            if answer is None:
                return
            assert isinstance(answer, TypedData)
            if answer.dtype != ant.output_dtype:
                raise ValueError(
                    f"Model Investigator {ant.component} returned {answer.dtype} dtype. Expected: {ant.output_dtype}"
                )
            assert isinstance(answer, TypedData)

        else:
            assert isinstance(ant.component, SciAgent)
            # run a science agent. Call its decision task
            await ant.has_published_selector.wait()
            assert ant.model_select_task is not None
            logger.debug(f"Run {type(ant.component).__name__} selection task")

            selecting = ant.model_select_task(
                in_data, *ant.model_select_args, **ant.model_select_kwargs
            )
            note_flow_task(selecting)
            answer_ms = await selecting

            # answer is an investigator id.
            if isinstance(answer_ms, tuple) and len(answer_ms) == 2:
                i_select, model_kwargs = answer_ms
            else:
                i_select = answer_ms
                model_kwargs = None

            if i_select not in ant.investigators:
                logger.warning("Model selector pointed to non-existent investigator!")
                return

            logger.debug(f"Model selector responded with: {i_select}")
            i_select = ant.investigators[i_select]

            if model_kwargs is None:
                model_kwargs = i_select.model_kwargs

            # now, run the inference of the provided investigator
            for cb in i_select.subscriptions[RuntimeAPI.ON_FILTERED_INPUT]:
                logger.info(f"Fire ON_FILTERED_INPUT on {cb}")
                self._to_asyncio_task(self._call_await, cb, in_data)

            await i_select.has_published_model.wait()
            answer = await self._infer(i_select, in_data, model_kwargs)

            for cb in i_select.subscriptions[RuntimeAPI.ON_FILTERED_OUTPUT]:
                self._to_asyncio_task(self._call_await, cb, answer)

        if ant.output_dtype == NULL_DTYPE:
            return
        assert isinstance(answer, TypedData) and answer.dtype is not NULL_DTYPE

        for cb in ant.subscriptions[RuntimeAPI.ON_OUTPUT]:
            self._to_asyncio_task(self._call_await, cb, answer)

        # alert child investigators
        for investigator in ant.investigators.values():
            for cb in investigator.subscriptions[RuntimeAPI.ON_OUTPUT]:
                self._to_asyncio_task(self._call_await, cb, in_data)

        if not skip_queue_out:
            self._put_to_dtype_queue(answer)

        return answer

    async def _infer(
        self, ant: _AnnotatedComponent, in_data: TypedData, model_kwargs: dict
    ):
        """Run an investigator's inference task with its published model.

        A published model is just kwargs, so publishing a key the
        inference task does not accept fails as a `TypeError` deep inside
        a call the user never wrote -- and for a learner that publishes
        whatever its training task returned, that is an easy mistake to
        make.  Name it instead.

        Only the *call* is rewritten: a `TypeError` raised inside the task
        body has its own frame in the traceback and is left alone.
        """

        try:
            # the future first, so the task it stands for is recorded as this
            # twin's before anyone can hear about it (`note_flow_task`); a
            # plain coroutine has no uid and is simply skipped
            pending = ant.inference_task(in_data, **model_kwargs)
            note_flow_task(pending)

            return await pending

        except TypeError as exc:
            traceback = exc.__traceback__
            if traceback is None or traceback.tb_next is not None:
                raise

            raise TypeError(
                f"published model keys do not match the inference task"
                f" signature of {type(ant.component).__name__}: published"
                f" {sorted(model_kwargs)} -- {exc}"
            ) from exc

    ## flow.block
    async def _dtype_consumer(self, input_data: TypedData) -> None:
        """Consume data for a given :class:`DataType`.

        The method launches all components registered for the specific data
        type concurrently, waiting for all to complete before returning.

        Args:
            input_data: Incoming :class:`TypedData` instance.

        Returns:
            None. All component loops are executed concurrently.
        """

        tasks = []
        for task in self.components[input_data.dtype]:
            tasks.append(self._run_component(task, input_data))

        await asyncio.gather(*tasks)

    def _put_to_dtype_queue(self, t_data: TypedData) -> None:
        """Enqueue a :class:`TypedData` instance for later consumption.

        If a queue already exists for the data type, the instance is queued.
        Otherwise, a new queue is created and a consumer task is scheduled to process the data.

        Args:
            t_data: Typed data to enqueue.
        """

        if t_data.dtype == NULL_DTYPE:
            return

        # nothing registered for it, and nothing consuming it: drop it
        if (
            t_data.dtype not in self.dtype_queues
            and t_data.dtype not in self.components
        ):
            return

        logger.info(f"Enqueue: {t_data.dtype}")
        self._ensure_dtype_queue(t_data.dtype).put_nowait(t_data)

    async def _launch_b_consumer(
        self, dtype: DataType, creation: asyncio.Event
    ) -> None:
        """Background consumer that waits for barrier creation and processes data.

        The coroutine continuously pulls data from the last barrier for ``dtype`` and
        forwards it to the generic dtype consumer.

        Args:
            dtype: Data type to consume.
            creation: Event fired when the barrier is ready.
        """

        await creation.wait()
        while True:
            t_data = await self.barriers[dtype][-1].get(dtype)
            logger.info(
                f"Final dequeue from barrier ({self.barriers[dtype][-1]}): {t_data.dtype}"
            )
            await self._dtype_consumer(t_data)

    async def _launch_consumer(self, dtype: DataType) -> None:
        """Consume data from the local queue and route it to barriers or consumers.

        The coroutine pulls typed data from the internal queue, passes it to the
        first barrier if present, or directly to the dtype consumer.

        Args:
            dtype: Data type to consume.
        """

        barrier_creation = asyncio.Event()
        self._to_asyncio_task(self._launch_b_consumer, dtype, barrier_creation)
        while True:

            # is input queue available?
            t_data = await self.dtype_queues[dtype].get()
            if len(self.barriers[dtype]) > 0:
                logger.info(
                    f"Dequeue and place to barrier ({self.barriers[dtype][0]}): {t_data.dtype}"
                )
                barrier_creation.set()
                await self.barriers[dtype][0].put(t_data)
            else:
                # process!
                logger.info(f"Dequeue: {t_data.dtype}")
                await self._dtype_consumer(t_data)

    def describe(self) -> dict:
        """Serializable summary of the twin: graph, dtypes, state.

        Introspection only, but this is the format that goes on the wire --
        `print_graph()` is just a rendering of it.
        """

        def kind_of(component) -> str:
            if isinstance(component, _JoinComponent):
                return "join"
            if isinstance(component, SplitTask):
                return "split"
            if isinstance(component, SciAgent):
                return "agent"
            if isinstance(component, ModelInvestigator):
                return "investigator"
            return "utility"

        def described(ant: _AnnotatedComponent) -> dict:
            entry = {
                "component": type(ant.component).__name__,
                "kind": kind_of(ant.component),
                "input_dtype": ant.input_dtype.name,
                "output_dtype": ant.output_dtype.name,
                "is_persistent": ant.is_persistent,
            }
            if ant.investigators:
                entry["investigators"] = [
                    described(inv) for inv in ant.investigators.values()
                ]

            # what an observer can know about an investigator's model
            # without shipping the model: whether one has been published,
            # and the names of its parameters
            if entry["kind"] == "investigator":
                entry["model_published"] = ant.has_published_model.is_set()
                entry["model_keys"] = sorted(ant.model_kwargs or {})

            entry["is_join"] = isinstance(ant.component, _JoinComponent)
            entry["is_split"] = isinstance(ant.component, SplitTask)
            entry["split_outputs"] = [f.name for f in ant.split_outputs]
            return entry

        components = [
            described(ant) for ants in self.components.values() for ant in ants
        ]

        inputs = [
            {
                "dtype": binding.dtype.name,
                "channel": binding.channel,
                "codec": binding.codec,
            }
            for binding in self.inputs
        ]

        return {
            "namespace": self.streamer.namespace,
            "state": str(self.state),
            "last_error": self.last_error,
            "inputs": inputs,
            "components": components,
            "dtypes": sorted(
                {entry["input_dtype"] for entry in components}
                | {entry["output_dtype"] for entry in components}
                | {entry["dtype"] for entry in inputs}
            ),
            # per dtype, the ordered chain of barriers it passes through
            "barriers": {
                dtype.name: [
                    {"name": barrier.name, "hard": barrier.dtypes[dtype]}
                    for barrier in chain
                ]
                for dtype, chain in self.barriers.items()
            },
        }

    def metrics(self) -> dict:
        """Convergence metrics the graph's components report, by name.

        Duck-typed on purpose: a `StreamingLearnerInvestigator` refreshes a
        filtered `metrics` dict once per learning window, and this collects
        whatever component carries one -- so the runtime never has to know
        about ROSE.  A metric name two components both track is qualified
        with the second one's class.
        """

        collected: dict = {}

        for ant in self._annotated():
            reported = getattr(ant.component, "metrics", None)
            if not isinstance(reported, dict):
                continue

            component = type(ant.component).__name__
            for name, entry in reported.items():
                if not isinstance(entry, dict):
                    continue
                key = name if name not in collected else f"{component}.{name}"
                collected[key] = {**entry, "component": component}

        return collected

    def print_graph(self) -> str:
        """Human-readable rendering of `describe()`."""

        info = self.describe()

        by_input: dict[str, list[dict]] = defaultdict(list)
        for entry in info["components"]:
            by_input[entry["input_dtype"]].append(entry)

        lines = ["=" * 30, f"Digital Twin Flow: {info['namespace']} [{info['state']}]"]

        for binding in info["inputs"]:
            lines.append(
                f"CHANNEL: {binding['channel']} ({binding['codec']})"
                f" --> {binding['dtype']}"
            )

        for input_dtype, entries in by_input.items():
            lines.append(f"IN: {input_dtype}")
            for entry in entries:
                if entry["is_join"]:
                    lines.append(f"\t{entry['output_dtype']}")
                    continue
                if entry["is_split"]:
                    lines.append(f"\tSPLIT: {entry['component']}")
                    for i in entry["split_outputs"]:
                        lines.append(f"\t\t{i}")
                    continue
                lines.append(
                    f"\t{entry['output_dtype']}: {entry['component']}"
                    f" ({entry['is_persistent']})"
                )

        lines.append("BARRIERS: ")
        for dtype, chain in info["barriers"].items():
            hops = "".join(
                f"{barrier['name']}{'' if barrier['hard'] else ']W'} --> "
                for barrier in chain
            )
            lines.append(f"\t {dtype} --> {hops}")

        lines.append("=" * 30)

        out = "\n".join(lines)
        print(f"\n{out}\n")

        return out
