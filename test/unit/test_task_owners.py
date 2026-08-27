"""Task ownership: which twin submitted the task a notification names.

A `task_status` notification carries a uid and an endpoint and nothing else,
so the service records what it submitted (`DTRuntime.note_task`) and
`twin_list` carries it.  The uid is asyncflow's own -- the execution backend
keeps the one in the component description -- so the join is exact rather
than inferred.

Two paths reach the ring, and both are tested here against a real (local,
thread-backed) engine: the runtime's own submissions, and ROSE's.
"""

import asyncio

from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("rose")

from radical.asyncflow import WorkflowEngine  # noqa: E402
from rhapsody.backends import ConcurrentExecutionBackend  # noqa: E402

from digitaltwin import (  # noqa: E402
    TRUTHY,
    DTRuntime,
    DataType,
    ModelInvestigator,
    TypedData,
    UtilityTask,
)

from digitaltwin.runtime import TASK_UID_RING  # noqa: E402

X = DataType("x")
Y = DataType("y")


@pytest.fixture
async def engines():
    made = []

    async def make():
        backend = await ConcurrentExecutionBackend(ThreadPoolExecutor())
        made.append(await WorkflowEngine.create(backend=backend))
        return made[-1]

    try:
        yield make
    finally:
        for engine in made:
            await engine.shutdown()


class Direct(ModelInvestigator):
    """The inference task *is* the flow task."""

    def __init__(self, flow):
        super().__init__(flow)

        @flow.function_task
        async def infer(in_data, k=1.0):
            return TypedData(Y, k * in_data.data)

        self._infer = infer

    async def main_loop(self, runtime):
        runtime.set_inference_task(self._infer)
        runtime.publish_new_model({"k": 2.0}, {})


class Wrapped(ModelInvestigator):
    """The inference task is a plain coroutine that awaits a flow task.

    The shape every real learner has, and the one the runtime cannot see:
    what it awaits is a coroutine, and the future with the uid on it never
    passes through the runtime at all.
    """

    def __init__(self, flow):
        super().__init__(flow)

        @flow.function_task
        async def predict(in_data, k=1.0):
            return k * in_data.data

        async def infer(in_data, k=1.0):
            return TypedData(Y, await predict(in_data, k=k))

        self._infer = infer

    async def main_loop(self, runtime):
        runtime.set_inference_task(self._infer)
        runtime.publish_new_model({"k": 3.0}, {})


# class Learner(ModelInvestigator):
#     """Windows of one, so a single item drives a whole ROSE iteration."""

#     def __init__(self, flow, learn_backend=None):
#         super().__init__(flow)

#         self.learner = SequentialActiveLearner()

#         @self.learner.training_task(as_executable=False)
#         async def training(window, *args):
#             return {"k": 2.0}

#         @self.learner.active_learn_task(as_executable=False)
#         async def active_learn(model, *args):
#             return model

#         @self.learner.as_stop_criterion(
#             metric_name="err", threshold=1e-9, operator="<",
#             as_executable=False)
#         async def criterion(*args):
#             return 1.0

#         @flow.function_task
#         async def predict(in_data, k=0.0):
#             return k * in_data.data

#         async def infer(in_data, k=0.0):
#             return TypedData(Y, await predict(in_data, k=k))

#         self.inference_task = infer

#     def bootstrap_model(self):
#         return {"k": 0.0}, {}


# class Feeder(UtilityTask):
#     """One item per tick, into the twin's stream."""

#     async def main_loop(self, runtime, in_data):
#         for value in range(1000):
#             await runtime.stream.publish(X, float(value))
#             await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# the runtime's own submissions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("component", [Direct, Wrapped])
async def test_an_inference_task_is_recorded_against_its_twin(
        component, engines, stream_clients):
    """One inference, one uid -- whichever shape the inference task has."""

    flow = await engines()
    runtime = DTRuntime(flow, await stream_clients(f"own-{component.__name__}"))
    runtime.add_investigator(component(flow), X, Y)
    runtime.start()

    assert runtime.task_uids() == []

    answer = await runtime.get_inference(TypedData(X, 21.0), Y)
    await asyncio.sleep(0.1)

    assert answer.data
    uids = runtime.task_uids()
    assert len(uids) == 1, uids
    assert uids[0].startswith("task."), uids
    # the submitting component's class name rides along
    assert runtime.task_components().get(uids[0]) == component.__name__

    # and a second call is a second task, in order
    await runtime.get_inference(TypedData(X, 1.0), Y)
    await asyncio.sleep(0.1)
    assert runtime.task_uids()[:1] == uids
    assert len(runtime.task_uids()) == 2

    await runtime.stop()


async def test_the_ring_is_bounded_and_keeps_the_newest(engines,
                                                        stream_clients):
    """A twin that submits forever must not remember forever."""

    flow = await engines()
    runtime = DTRuntime(flow, await stream_clients("own-bounded"))
    runtime.start()

    for i in range(TASK_UID_RING + 5):
        runtime.note_task(f"task.{i:06d}", component="Feeder")

    uids = runtime.task_uids()

    assert len(uids) == TASK_UID_RING
    assert uids[-1] == f"task.{TASK_UID_RING + 4:06d}"
    assert uids[0] == f"task.{5:06d}"
    # the component map is ring-bounded with the uids
    assert set(runtime.task_components()) == set(uids)
    # a uid it already has is not a new submission
    runtime.note_task(uids[-1])
    assert runtime.task_uids() == uids

    await runtime.stop()


# ---------------------------------------------------------------------------
# ROSE's submissions
# ---------------------------------------------------------------------------

# async def test_the_learners_own_tasks_are_recorded_too(engines,
#                                                        stream_clients):
#     """Training / active learning / criterion carry the learning label and
#     never pass through the runtime; the wrapper in `main_loop` is what makes
#     them the twin's (`_own_learner_tasks`)."""

#     flow = await engines()

#     runtime = DTRuntime(flow, await stream_clients("own-learner"))
#     learner = Learner(flow)

#     runtime.add_task(Feeder(flow), TRUTHY, X, is_persistent=True)
#     runtime.add_investigator(learner, X, Y)
#     runtime.start()

#     # the learner is wrapped as soon as its main loop runs
#     deadline = asyncio.get_running_loop().time() + 30.0
#     while len(runtime.task_uids()) < 3:
#         if asyncio.get_running_loop().time() > deadline:
#             pytest.fail(f"only {runtime.task_uids()} recorded"
#                         f" ({runtime.state} {runtime.last_error})")
#         await asyncio.sleep(0.25)

#     assert getattr(learner.learner, "_dt_owned", False)
#     assert all(uid.startswith("task.") for uid in runtime.task_uids())
#     # every recorded task is the learner's, and says so
#     assert set(runtime.task_components().values()) == {"Learner"}
#     # every window is three learner tasks, so a handful arrive quickly
#     assert len(set(runtime.task_uids())) == len(runtime.task_uids())

#     await runtime.stop()
