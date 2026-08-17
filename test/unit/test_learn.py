"""M2 -- `StreamingLearnerInvestigator`: wiring, propagation, teardown.

Against a real (local, thread-backed) engine: ROSE typechecks its
`WorkflowEngine` argument, so there is no useful fake to substitute.
"""

import asyncio
import logging

from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("rose")

from radical.asyncflow import WorkflowEngine  # noqa: E402
from rhapsody.backends import ConcurrentExecutionBackend  # noqa: E402

from digitaltwin import (  # noqa: E402
    TRUTHY,
    DTRuntime,
    DataType,
    RuntimeState,
    TypedData,
    UtilityTask,
)
from digitaltwin.learn import StreamingLearnerInvestigator  # noqa: E402

X = DataType("x")
Y = DataType("y")

SLOPE = 10.0
BATCH = 4


@pytest.fixture
async def engines():
    """Factory for local engines, all shut down with the test.

    Threads, not processes: the learner's tasks are closures, and a
    process pool would have to pickle them.
    """

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


@pytest.fixture
async def flow(engines):
    """The twin's `'task'` engine."""

    return await engines()


class Counter(UtilityTask):
    """Persistent source: 0, 1, 2, ... into the twin's stream."""

    async def main_loop(self, runtime, in_data):
        for value in range(1000):
            await asyncio.sleep(0.05)
            await runtime.stream.publish(X, float(value))


class LinearLearner(StreamingLearnerInvestigator):
    """Fits `y = slope * x` on each window; serves `slope * x`."""

    def __init__(self, flow, learn_flow=None):
        super().__init__(flow, learn_flow, batch_size=BATCH, max_wait=5.0)

        latest: dict = {}
        self.learner.on_state_update(latest.__setitem__)

        @self.learner.training_task(as_executable=False)
        async def training(window, *args):
            xs = [float(x) for x in window]
            den = sum(x * x for x in xs) or 1.0
            return {"slope": sum(SLOPE * x * x for x in xs) / den}

        @self.learner.active_learn_task(as_executable=False)
        async def active_learn(model, *args):
            return len(model)

        @self.learner.as_stop_criterion(
            metric_name="fit_error", threshold=1e-6, operator="<",
            as_executable=False)
        async def criterion(*args, model=latest):
            return (model.get("slope", 0.0) - SLOPE) ** 2

        @flow.function_task
        async def predict(in_data, slope=0.0):
            return slope * in_data.data

        async def infer(in_data, slope=0.0):
            return TypedData(Y, await predict(in_data, slope=slope))

        self.inference_task = infer

    def bootstrap_model(self):
        return {"slope": 0.0}, {}


async def _twin(flow, stream, learn_flow=None):
    """A started twin: counter -> learner."""

    runtime = DTRuntime(flow, stream)
    learner = LinearLearner(flow, learn_flow)

    runtime.add_task(Counter(flow), TRUTHY, X, is_persistent=True)
    runtime.add_investigator(learner, X, Y)
    runtime.start()

    return runtime, learner


async def _await_learned(runtime, timeout=30.0):
    """Poll inference until a learned model is being served."""

    deadline = asyncio.get_running_loop().time() + timeout

    while True:
        answer = await runtime.get_inference(TypedData(X, 3.0), Y)
        if answer.data:
            return answer.data
        if asyncio.get_running_loop().time() > deadline:
            pytest.fail(f"no model published: {runtime.state} {runtime.last_error}")
        await asyncio.sleep(0.25)


# ---------------------------------------------------------------------------
# the wiring
# ---------------------------------------------------------------------------

async def test_a_published_model_changes_the_next_prediction(flow,
                                                             stream_clients):
    runtime, _ = await _twin(flow, await stream_clients("twin-learn"))

    try:
        # the bootstrap model, published before any input -- without it
        # inference would block on `has_published_model` and the stream
        # that feeds the learner would never get past the first item
        first = await runtime.get_inference(TypedData(X, 3.0), Y)
        assert first.data == 0.0

        assert await _await_learned(runtime) == pytest.approx(3.0 * SLOPE)
        assert runtime.state is RuntimeState.RUNNING

    finally:
        await runtime.stop()


async def test_the_learner_uses_the_engine_it_was_given(flow, engines):
    """Dual-engine: the learner's tasks go to `learn_flow`, the
    inference task stays on `flow`."""

    exsitu = await engines()
    learner = LinearLearner(flow, learn_flow=exsitu)

    assert learner.learn_flow is exsitu
    assert learner.learner.asyncflow is exsitu
    assert learner.flow is flow


async def test_the_criterion_state_shows_up_in_the_twins_metrics(
        flow, stream_clients):
    """Per window, the learner mirrors its criterion into `metrics`, and
    the runtime collects it for `twin_list` -- the only observation
    mechanism v1 has, so convergence has to ride on it."""

    runtime, learner = await _twin(flow, await stream_clients("twin-metrics"))

    try:
        await _await_learned(runtime)

        assert learner.windows >= 1
        metric = learner.metrics["fit_error"]

        assert metric["threshold"] == 1e-6
        assert metric["operator"] == "<"
        assert metric["should_stop"] is True
        assert metric["windows"] == learner.windows
        assert metric["history"][-1] == metric["value"]
        # filtered: the model itself never travels in a metric
        assert set(metric) == {"value", "threshold", "operator",
                               "should_stop", "windows", "history"}

        collected = runtime.metrics()
        assert collected["fit_error"]["component"] == "LinearLearner"
        assert collected["fit_error"]["value"] == metric["value"]

    finally:
        await runtime.stop()


async def test_a_twin_without_a_learner_reports_no_metrics(flow,
                                                           stream_clients):
    runtime = DTRuntime(flow, await stream_clients("twin-nometrics"))
    runtime.add_task(Counter(flow), TRUTHY, X, is_persistent=True)

    assert runtime.metrics() == {}

    await runtime.stop()


async def test_an_absent_exsitu_engine_falls_back_to_the_twins(flow):
    learner = LinearLearner(flow)

    assert learner.learn_flow is flow
    assert learner.learner.asyncflow is flow


# ---------------------------------------------------------------------------
# lifetime
# ---------------------------------------------------------------------------

async def test_stop_winds_the_learner_down(flow, stream_clients,
                                           no_task_leaks):
    """The learner's lifetime is the twin's: `stop()` leaves no loop, no
    task and no error behind."""

    runtime, learner = await _twin(flow, await stream_clients("twin-stop"))
    await _await_learned(runtime)

    await runtime.stop()

    assert learner.learner.is_stopped
    assert learner._finished.is_set()
    assert runtime.state is RuntimeState.STOPPED
    assert runtime.last_error is None


async def test_stop_before_start_does_not_wait_for_the_learner(flow,
                                                               stream_clients):
    """A twin torn down before its learner ever ran must not sit out the
    stop hook's timeout."""

    runtime = DTRuntime(flow, await stream_clients("twin-idle"))
    runtime.add_investigator(LinearLearner(flow), X, Y)

    loop = asyncio.get_running_loop()
    t0 = loop.time()
    await runtime.stop()

    assert loop.time() - t0 < 2.0


async def test_a_missing_inference_task_is_a_clear_error(flow,
                                                         stream_clients):
    class NoInference(StreamingLearnerInvestigator):
        pass

    runtime = DTRuntime(flow, await stream_clients("twin-broken"))
    runtime.add_investigator(NoInference(flow), X, Y)
    runtime.start()

    try:
        await asyncio.sleep(0.2)
        assert runtime.state is RuntimeState.FAILED
        assert "inference_task" in runtime.last_error

    finally:
        await runtime.stop()


# ---------------------------------------------------------------------------
# the remote-executability guard
# ---------------------------------------------------------------------------

class Shelling(LinearLearner):
    """A learner left on ROSE's executable default."""

    def __init__(self, flow, learn_flow=None):
        super().__init__(flow, learn_flow)

        @self.learner.training_task
        async def training(window, *args, task_description={"shell": True}):
            return "/bin/true"


async def test_executable_learner_tasks_warn(flow, engines, stream_clients,
                                             caplog):
    """ROSE's default is a shell command with local paths, which cannot
    reach a remote 'exsitu' endpoint."""

    runtime = DTRuntime(flow, await stream_clients("twin-shell"))
    runtime.add_investigator(Shelling(flow, await engines()), X, Y)

    with caplog.at_level(logging.WARNING):
        runtime.start()
        await asyncio.sleep(0.2)

    assert "as executable task(s)" in caplog.text
    assert "training" in caplog.text

    await runtime.stop()


async def test_a_purely_local_learner_does_not_warn(flow, stream_clients,
                                                    caplog):
    """One engine for both halves is the local case, where a shell
    command with local paths is a perfectly good task."""

    runtime = DTRuntime(flow, await stream_clients("twin-local"))
    runtime.add_investigator(Shelling(flow), X, Y)

    with caplog.at_level(logging.WARNING):
        runtime.start()
        await asyncio.sleep(0.2)

    assert "as executable task(s)" not in caplog.text

    await runtime.stop()


# ---------------------------------------------------------------------------
# a published model the inference task cannot take
# ---------------------------------------------------------------------------

async def test_a_model_the_inference_task_rejects_is_named(flow,
                                                           stream_clients):
    """A learner publishes whatever its training task returned, so a key
    the inference task does not accept is an easy mistake -- and it must
    not surface as a bare `TypeError` from a call the user never wrote."""

    class Mismatched(LinearLearner):
        def published_model(self, state):
            return {"nonesuch": 1}, {}

    runtime = DTRuntime(flow, await stream_clients("twin-mismatch"))
    runtime.add_task(Counter(flow), TRUTHY, X, is_persistent=True)
    runtime.add_investigator(Mismatched(flow), X, Y)
    runtime.start()

    try:
        for _ in range(120):
            await asyncio.sleep(0.25)
            if runtime.state is RuntimeState.FAILED:
                break

        assert runtime.state is RuntimeState.FAILED
        assert "published model keys do not match" in runtime.last_error
        assert "nonesuch" in runtime.last_error

    finally:
        await runtime.stop()


async def test_the_task_bodys_own_TypeError_is_left_alone(flow,
                                                          stream_clients):
    class Exploding(LinearLearner):
        def __init__(self, flow, learn_flow=None):
            super().__init__(flow, learn_flow)

            async def infer(in_data, slope=0.0):
                raise TypeError("the body's own complaint")

            self.inference_task = infer

    runtime = DTRuntime(flow, await stream_clients("twin-boom"))
    runtime.add_investigator(Exploding(flow), X, Y)
    runtime.start()

    try:
        with pytest.raises(TypeError, match="the body's own complaint"):
            await runtime.get_inference(TypedData(X, 1.0), Y)

    finally:
        await runtime.stop()
