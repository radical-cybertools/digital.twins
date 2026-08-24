"""Ex-situ learning: a ROSE streaming learner inside a twin component.

`StreamingLearnerInvestigator` packages the wiring `test/rose_streaming`
spells out by hand -- a `StreamingActiveLearner` fed from `ON_INPUT`, a
bootstrap model published up front, `on_model_ready ->
publish_new_model`, and a learner whose lifetime is the twin's.

It is also the marker for **role injection**: the learner's training /
active-learning / criterion tasks carry the `'learning'` backend label
(typically remote HPC hardware) while inference rides the default
`'inference'` backend of the same engine.  The service detects this
class by subclass check and passes the label as `learn_backend`; locally
the caller passes it (or nothing -- every task then rides the one
backend, which is what a single-endpoint deployment does).

A subclass provides its learner tasks and its inference task::

    class Fit(StreamingLearnerInvestigator):

        def __init__(self, flow, learn_backend=None):
            super().__init__(flow, learn_backend, batch_size=8)

            # learning role: the label is injected on registration.
            # as_executable=False makes these cloudpickled function
            # tasks, which is what lets them run on an endpoint that
            # shares no filesystem with the service
            @self.learner.training_task(as_executable=False)
            async def training(window, *args):
                return {'slope': fit(window)}

            ...

            # inference role, on the default backend
            @flow.function_task
            async def predict(in_data, slope=0.0):
                return in_data.data * slope

            self.inference_task = ...

A criterion task takes no dependency from ROSE's streaming loop, so
whatever it scores has to travel *with* it -- the usual pattern is a
dict mirroring the learner's state, captured by value.  Mind the cost:
that mirror is re-cloudpickled with the criterion on every window and
retains every state key ever registered, so a model approaching the
~2 MiB return budget crosses the wire twice per window.  Keep bulk
artifacts out of learner state and stage them instead.

This module needs ROSE (`pip install .[learn]`); nothing else in the
package imports it.
"""

import asyncio
import contextlib
import logging
import math

from typing import Any, Callable, Optional

from radical.asyncflow import WorkflowEngine  # type: ignore
from rose.al.streaming_learner import StreamingActiveLearner  # type: ignore

from .components import ModelInvestigator, TypedData
from .runtime import RuntimeAPI, hook_engine, note_flow_task

logger = logging.getLogger(__name__)

# how long twin teardown lets the learner leave its current window before
# the runtime cancels it outright
LEARNER_STOP_TIMEOUT = 5.0

# the three ROSE task slots a streaming learner drives
LEARNER_TASKS = ("training", "active_learn", "criterion")

# ROSE's own per-window bookkeeping -- state, but not model parameters
_ROSE_STATE_KEYS = ("window_size",)

# how much of the criterion's metric history travels in `metrics`.  A
# days-long twin accumulates one value per window forever; the dashboard
# only ever draws a sparkline of the recent tail, and it keeps 24 points
# (`SPARK_MAX` in `service/ui/dt_dash.js`) -- so sending more is paying
# for something nothing reads.
METRIC_HISTORY = 24


def _number(value: Any) -> Optional[float]:
    """A JSON-safe float, or `None` -- a criterion may not have run yet.

    Six *significant* figures, not six decimal places: a criterion
    threshold of 1e-8 is an ordinary target, and rounding it by decimals
    would put 0.0 on the wire.  Infinities and NaN are dropped rather
    than emitted, because neither survives JSON.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None

    number = float(f"{value:.6g}")

    return number if math.isfinite(number) else None



class StreamingLearnerInvestigator(ModelInvestigator):
    """A `ModelInvestigator` with a ROSE `StreamingActiveLearner` inside.

    Every item the twin routes to this investigator is fed to the learner
    (`ON_INPUT`) *and* served by the inference task, so one stream drives
    both retraining and prediction.  Each window of `batch_size` items (or
    `max_wait` seconds' worth) runs one training / active-learning /
    criterion iteration under the `'learning'` label; a met criterion is a
    publish gate, not a terminator -- it swaps the model the in-situ
    inference task runs with.
    """

    def __init__(
        self,
        flow: WorkflowEngine,
        learn_backend: Optional[str] = None,
        batch_size: int = 5,
        max_wait: Optional[float] = 2.0,
        conflate: bool = True,
    ):
        super().__init__(flow)

        # One engine, two roles.  `learn_backend` is the name of the
        # 'learning' backend the service injects; the learner's tasks
        # carry it as their asyncflow routing label.  Without one (local
        # use, or a deployment that configured no 'learning' backend) the
        # label is omitted and every task rides the default backend.
        self.learn_backend = learn_backend

        # conflate: a stream faster than the learner drops its backlog
        # rather than growing it -- a days-long twin must not queue days
        # of sensor data
        self.learner = StreamingActiveLearner(
            flow,
            batch_size=batch_size,
            max_wait=max_wait,
            conflate=conflate,
        )

        # The routing label rides ROSE's own registration seam: every
        # learner task passes `_register_task`, which forwards
        # `decor_kwargs` into `asyncflow.function_task`.  Injected there
        # rather than via an engine proxy -- ROSE type-checks the engine
        # argument, a wrapper object does not pass.
        if learn_backend is not None:
            inner_register = self.learner._register_task

            def labeled(task_obj, *args, **kwargs):
                decor = task_obj.setdefault("decor_kwargs", {})
                decor.setdefault("backend", learn_backend)
                return inner_register(task_obj, *args, **kwargs)

            self.learner._register_task = labeled

        # set by the subclass; the in-situ half of the pair
        self.inference_task: Optional[Callable] = None

        # Read-only observation surface, refreshed once per window and
        # carried by `twin_list` (see `_record_metrics`).  Nothing in the
        # framework reads these -- they exist so an operator can see a
        # learner converging without a second channel.
        self.metrics: dict = {}
        self.windows: int = 0

        self._started = False
        self._finished = asyncio.Event()

    # -- what subclasses shape ----------------------------------------------

    def bootstrap_model(self) -> tuple[dict, dict]:
        """The model published before any training has happened.

        Inference gates on a published model, so a learner that published
        only from `on_model_ready` would deadlock its twin on the very
        first input -- and nothing would ever reach the learner, since the
        stream feeds it through that same input.  Override to bootstrap
        with something better than the inference task's own defaults.
        """

        return {}, {}

    def published_model(self, state: Any) -> tuple[dict, dict]:
        """`(model_kwargs, accuracy_kwargs)` for a criterion-met window.

        Whatever the learner's tasks registered as state becomes the model
        -- a training task returning a dict has every key of it registered
        -- and those kwargs are what the inference task is called with.
        ROSE's own per-window bookkeeping is dropped.
        """

        model = {
            key: value
            for key, value in state.state.items()
            if key not in _ROSE_STATE_KEYS
        }

        return model, {"metric": state.metric_value}

    def on_window(self, state: Any) -> None:
        """Called once per learning window.  Default: one log line."""

        logger.info(
            "window %s (%s items): %s=%s published=%s",
            state.iteration,
            state.window_size,
            state.metric_name,
            state.metric_value,
            state.should_stop,
        )

    # -- the wiring ---------------------------------------------------------

    async def main_loop(self, runtime: RuntimeAPI):
        if self.inference_task is None:
            raise ValueError(
                f"{type(self).__name__} must set self.inference_task -- the"
                " inference, on the twin's default backend"
            )

        self._warn_local_learner_tasks()
        self._own_learner_tasks(runtime)

        runtime.set_inference_task(self.inference_task)
        runtime.subscribe_to_topic(RuntimeAPI.ON_INPUT, self._feed)
        runtime.publish_new_model(*self.bootstrap_model())

        # criterion met => this model is worth serving.  In streaming mode
        # the criterion is a publish gate and the loop keeps running.
        self.learner.on_model_ready(
            lambda state: runtime.publish_new_model(*self.published_model(state))
        )

        self._started = True

        try:
            async for state in self.learner.start():
                self._record_metrics(state)
                self.on_window(state)

        finally:
            # the failure path too: no learner outlives its twin
            self.learner.stop()
            self._finished.set()

    def _own_learner_tasks(self, runtime: RuntimeAPI) -> None:
        """Record the ex-situ tasks as this twin's, as ROSE submits them.

        Every training / active-learning / criterion task goes out through
        `Learner._register_task`, which returns the asyncflow future -- so an
        instance-attribute wrapper here sees all three without ROSE knowing.
        The engine is hooked as well, because the uid is minted a tick after
        the future is handed back; the wrapper's own reading catches the case
        where the hook cannot (an engine ROSE replaced), and both write to the
        same bounded ring, which ignores a uid it already has.

        Best-effort by construction: a ROSE that stops routing through
        `_register_task` loses the attribution, not the learning.
        """

        owner = getattr(runtime, "_runtime", None)
        if owner is None:
            return

        hook_engine(self.flow, owner)

        inner = getattr(self.learner, "_register_task", None)
        if inner is None or getattr(self.learner, "_dt_owned", False):
            return

        def registered(*args, **kwargs):
            future = inner(*args, **kwargs)
            try:
                note_flow_task(future, owner, type(self).__name__)
            except Exception as exc:
                logger.debug("learner uid capture failed: %s", exc)

            return future

        self.learner._register_task = registered
        self.learner._dt_owned = True

    def _record_metrics(self, state: Any) -> None:
        """Mirror the window's criterion state into `self.metrics`.

        A filtered, JSON-safe view -- the value, the target it is compared
        against, the operator doing the comparing and whether this window
        met it -- and never the model, which can be megabytes.  This is
        what `twin_list` and `admin/sessions` carry per twin.
        """

        self.windows = state.iteration + 1
        name = state.metric_name
        if not name:
            return

        window = (state.metric_history or [])[-METRIC_HISTORY:]
        history = [value for value in map(_number, window)
                   if value is not None]

        self.metrics = {
            name: {
                "value": _number(state.metric_value),
                "threshold": _number(state.metric_threshold),
                # '' for a standard metric, whose operator ROSE knows
                # itself; the consumer then falls back on `should_stop`
                "operator": (self.learner.criterion_function
                             or {}).get("operator") or None,
                "should_stop": bool(state.should_stop),
                "windows": self.windows,
                "history": history,
            }
        }

    async def _feed(self, in_data: TypedData) -> None:
        """`ON_INPUT`: everything the twin sees also feeds the learner."""

        await self.learner.feed(in_data.data)

    async def _on_stop(self) -> None:
        """Wind the learner down before the runtime cancels the main loop.

        `learner.stop()` unblocks the window collector, so the loop leaves
        its `async for` at a *window boundary* and ROSE's generator runs
        its own cleanup.  Cancellation alone would mostly work -- the
        consumer is usually suspended in `__anext__`, so the generator's
        `finally` does run -- but three things only this buys:

        - it does not kill an in-flight `await train_task` on a *shared*
          engine, which a cancellation mid-window would;
        - ROSE catches `Exception`, not `CancelledError`, so a cancelled
          loop records `stop_reason='stream_exhausted'` to its trackers;
        - it does not rely on async-generator GC finalization, which is
          not something to lean on after days of running.

        Bounded: a learner parked in a remote training task is cancelled
        with everything else, a moment later.
        """

        if not self._started:
            return

        self.learner.stop()

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._finished.wait(), LEARNER_STOP_TIMEOUT)

    def _warn_local_learner_tasks(self) -> None:
        """Warn about learner tasks that cannot leave this host.

        ROSE registers tasks as *executables* by default: the task body
        returns a command line, which only runs where that command exists
        under that path.  The `'learning'` backend points at other hardware,
        so learner tasks belong on the cloudpickle path -- registered with
        `as_executable=False` they travel as function tasks, and the
        backend's Python-version guard covers the rest.

        Only when there *is* a separate learning backend: a learner
        running both halves on one backend is the local case, where a
        shell command with local paths is a perfectly good task.
        """

        if self.learn_backend is None:
            return

        local = [
            name
            for name in LEARNER_TASKS
            if (getattr(self.learner, f"{name}_function", None) or {}).get(
                "as_executable"
            )
        ]

        if local:
            logger.warning(
                "%s registered %s as executable task(s): a shell command with"
                " local paths does not survive a remote 'learning' endpoint."
                " Register them with as_executable=False.",
                type(self).__name__,
                ", ".join(local),
            )
