"""M0.1 -- teardown: terminal/idempotent stop, failure routing, no leaks."""

import asyncio

import pytest

from digitaltwin import (
    NULL_DTYPE,
    TRUTHY,
    Barrier,
    DTRuntime,
    DataType,
    RuntimeState,
    UtilityTask,
)
from digitaltwin.runtime import STOP_TIMEOUT

TICK = DataType("tick")

# DTRuntime never calls into the engine itself -- components do.  The unit
# tests use components which do not submit any work, so no engine is needed.
NO_FLOW = None


class Forever(UtilityTask):
    """A persistent component that never returns."""

    async def main_loop(self, runtime, in_data):
        while True:
            await asyncio.sleep(0.01)


class SlowToCancel(UtilityTask):
    """A component that does not settle when cancelled -- stop() must
    abandon it instead of waiting for it."""

    def __init__(self, flow, release: asyncio.Event):
        super().__init__(flow)
        self.release = release

    async def main_loop(self, runtime, in_data):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await self.release.wait()


class Boom(UtilityTask):
    async def main_loop(self, runtime, in_data):
        raise ValueError("component exploded")


class BoomOnCue(UtilityTask):
    """A component which fails only once the test says so -- long enough
    for its siblings to have proven that they were running."""

    def __init__(self, flow, cue: asyncio.Event, error="component exploded"):
        super().__init__(flow)
        self.cue = cue
        self.error = error

    async def main_loop(self, runtime, in_data):
        await self.cue.wait()
        raise ValueError(self.error)


class BoomOnCancel(UtilityTask):
    """A component which fails *while being torn down*: its cancellation
    handler raises something that is not a CancelledError."""

    async def main_loop(self, runtime, in_data):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise ValueError("component exploded on cancel")


class Publisher(UtilityTask):
    """A persistent component publishing on the twin's stream, recording
    what it published so a test can watch it stop."""

    def __init__(self, flow, published: list):
        super().__init__(flow)
        self.published = published

    async def main_loop(self, runtime, in_data):
        while True:
            await runtime.stream.publish(TICK, len(self.published))
            self.published.append(len(self.published))
            await asyncio.sleep(0.01)


async def torn_down(runtime: DTRuntime, timeout: float = 5.0):
    """Await the teardown the twin started on its own.

    `_stop_task` is the handle a scheduled teardown leaves behind -- the
    failure path cannot hand a caller anything else, since it is reached
    from synchronous done-callbacks.
    """

    async def wait():
        while runtime._stop_task is None:
            await asyncio.sleep(0.01)
        await asyncio.shield(runtime._stop_task)

    await asyncio.wait_for(wait(), timeout=timeout)


def assert_stream_is_closed(client):
    """The leak assertion the explicit-stop tests use."""

    assert client.subscriptions == set()
    assert client._backend.pub_soc is None
    assert client._backend.sub_soc is None
    assert client._backend._ctx.closed


async def test_stop_is_terminal_and_idempotent(stream_clients):
    runtime = DTRuntime(NO_FLOW, await stream_clients("twin-a"))
    runtime.add_task(Forever(NO_FLOW), TRUTHY, TICK, is_persistent=True)

    assert runtime.state is RuntimeState.READY
    runtime.start()
    assert runtime.state is RuntimeState.RUNNING

    await asyncio.sleep(0.1)
    await runtime.stop()
    assert runtime.state is RuntimeState.STOPPED

    await runtime.stop()  # idempotent
    assert runtime.state is RuntimeState.STOPPED

    with pytest.raises(RuntimeError):
        runtime.start()


async def test_stop_cancels_tasks_and_tears_down_the_stream(
    stream_clients, no_task_leaks
):
    client = await stream_clients("twin-a")
    runtime = DTRuntime(NO_FLOW, client)

    barrier = Barrier("b")
    barrier.add_dtype(TICK)
    runtime.add_barrier(barrier)

    runtime.add_task(Forever(NO_FLOW), TRUTHY, TICK, is_persistent=True)
    runtime.start()

    # the persistent component subscribed the runtime to its output dtype
    await asyncio.sleep(0.3)
    assert runtime.running_tasks
    assert TICK in client.subscriptions

    await runtime.stop()

    # no lingering tasks, subscriptions, sockets or contexts
    assert runtime.running_tasks == set()
    assert_stream_is_closed(client)


async def test_stop_abandons_tasks_that_ignore_cancellation(
    stream_clients, no_task_leaks
):
    release = asyncio.Event()
    runtime = DTRuntime(NO_FLOW, await stream_clients("twin-a"))
    runtime.add_task(SlowToCancel(NO_FLOW, release), TRUTHY, TICK, is_persistent=True)
    runtime.start()
    await asyncio.sleep(0.1)

    # bounded: stop returns even though the component does not settle
    await asyncio.wait_for(runtime.stop(timeout=0.2), timeout=2.0)
    assert runtime.state is RuntimeState.STOPPED

    # the abandoned task is no longer owned by the runtime
    assert runtime.running_tasks == set()

    release.set()
    await asyncio.sleep(0.05)


async def test_concurrent_stop_joins_one_teardown(stream_clients, no_task_leaks):
    client = await stream_clients("twin-a")
    runtime = DTRuntime(NO_FLOW, client)
    runtime.add_task(Forever(NO_FLOW), TRUTHY, TICK, is_persistent=True)
    runtime.start()
    await asyncio.sleep(0.1)

    await asyncio.gather(runtime.stop(), runtime.stop(), runtime.stop())

    # every caller returned only after the one teardown finished
    assert runtime.state is RuntimeState.STOPPED
    assert runtime.running_tasks == set()
    assert client._backend._ctx.closed


async def test_graph_cannot_be_changed_after_stop(stream_clients):
    runtime = DTRuntime(NO_FLOW, await stream_clients("twin-a"))
    runtime.start()
    await runtime.stop()

    with pytest.raises(RuntimeError):
        runtime.add_task(Forever(NO_FLOW), TRUTHY, TICK, is_persistent=True)
    with pytest.raises(RuntimeError):
        runtime.add_investigator(Forever(NO_FLOW), TICK, NULL_DTYPE)
    with pytest.raises(RuntimeError):
        runtime.add_agent(Forever(NO_FLOW), TICK, NULL_DTYPE)
    with pytest.raises(RuntimeError):
        runtime.add_barrier(Barrier("b"))


async def test_stream_failure_fails_the_twin(stream_clients, no_task_leaks):
    """The out-of-band door: a failure only the host can see.  `on_error`
    arrives synchronously, from the done-callback of the backend's receive
    loop -- teardown can only be scheduled from there, never awaited."""

    client = await stream_clients("twin-a")
    runtime = DTRuntime(NO_FLOW, client)
    runtime.add_task(Forever(NO_FLOW), TRUTHY, TICK, is_persistent=True)
    runtime.start()
    await asyncio.sleep(0.1)

    # what a dead receive loop reports
    client._backend._report_error(RuntimeError("stream receive loop exited"))

    assert runtime.state is RuntimeState.FAILED
    assert runtime.last_error == "RuntimeError: stream receive loop exited"

    # ... and the twin took itself down over it
    await torn_down(runtime)
    assert runtime.state is RuntimeState.FAILED
    assert runtime.running_tasks == set()
    assert_stream_is_closed(client)

    with pytest.raises(RuntimeError):
        runtime.start()

    await runtime.stop()


async def test_component_failure_tears_the_twin_down(stream_clients, no_task_leaks):
    """A component failure stops the twin: same teardown as `stop()`, but
    it ends in `failed` with the error, not in `stopped`."""

    cue = asyncio.Event()
    client = await stream_clients("twin-a")
    runtime = DTRuntime(NO_FLOW, client)

    barrier = Barrier("b")
    barrier.add_dtype(TICK)
    runtime.add_barrier(barrier)

    runtime.add_task(Forever(NO_FLOW), TRUTHY, TICK, is_persistent=True)
    runtime.add_task(BoomOnCue(NO_FLOW, cue), TRUTHY, NULL_DTYPE)
    runtime.start()

    # the twin is up: tasks running, subscribed to its own output dtype
    await asyncio.sleep(0.3)
    assert runtime.running_tasks
    assert TICK in client.subscriptions

    cue.set()
    await torn_down(runtime)

    assert runtime.state is RuntimeState.FAILED
    assert runtime.last_error == "ValueError: component exploded"

    # nothing of the twin is left running or open
    assert runtime.running_tasks == set()
    assert_stream_is_closed(client)

    # and it starts no further work
    assert runtime._to_asyncio_task(asyncio.sleep, 0) is None
    assert runtime.running_tasks == set()


async def test_an_out_of_band_failure_tears_the_twin_down(
    stream_clients, no_task_leaks
):
    """A failure the runtime cannot see by itself, handed in from outside
    and synchronously -- what the service's `fail()` door reports when an
    engine endpoint is lost under a twin (R8).  Same funnel, same
    teardown: the twin is down when it says `failed`."""

    client = await stream_clients("twin-a")
    runtime = DTRuntime(NO_FLOW, client)
    runtime.add_task(Forever(NO_FLOW), TRUTHY, TICK, is_persistent=True)
    runtime.start()

    await asyncio.sleep(0.1)
    assert runtime.running_tasks

    runtime._record_error(RuntimeError("engine endpoint lost: hpc1"))

    assert runtime.state is RuntimeState.FAILED
    assert runtime.last_error == "RuntimeError: engine endpoint lost: hpc1"

    await torn_down(runtime)
    assert runtime.state is RuntimeState.FAILED
    assert runtime.running_tasks == set()
    assert_stream_is_closed(client)


async def test_a_failure_stops_the_other_components(stream_clients, no_task_leaks):
    """The failure stops the *twin*, not just the component which broke:
    a persistent publisher which was happily publishing goes quiet."""

    published: list[int] = []
    cue = asyncio.Event()
    client = await stream_clients("twin-a")
    runtime = DTRuntime(NO_FLOW, client)

    runtime.add_task(Publisher(NO_FLOW, published), TRUTHY, TICK, is_persistent=True)
    runtime.add_task(BoomOnCue(NO_FLOW, cue), TRUTHY, NULL_DTYPE)
    runtime.start()

    async def wait_for_data():
        while len(published) < 3:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait_for_data(), timeout=10.0)

    cue.set()
    await torn_down(runtime)

    # whatever it had published by then, it publishes nothing more
    quiet_at = len(published)
    await asyncio.sleep(0.2)

    assert published == list(range(quiet_at))
    assert runtime.state is RuntimeState.FAILED
    assert runtime.running_tasks == set()
    assert_stream_is_closed(client)


async def test_stop_after_a_failure_is_a_bounded_no_op(stream_clients, no_task_leaks):
    """`TwinInstance.close()` calls `stop()` on whatever it holds.  On an
    already torn-down twin that returns promptly, does not raise, and
    leaves the failure standing: the error is the more useful fact."""

    client = await stream_clients("twin-a")
    runtime = DTRuntime(NO_FLOW, client)
    runtime.add_task(Boom(NO_FLOW), TRUTHY, NULL_DTYPE)
    runtime.start()

    await torn_down(runtime)
    teardown = runtime._stop_task

    await asyncio.wait_for(runtime.stop(), timeout=2.0)
    await asyncio.wait_for(runtime.stop(timeout=0.1), timeout=2.0)

    # no second teardown, no state change, no clobbered error
    assert runtime._stop_task is teardown
    assert runtime.state is RuntimeState.FAILED
    assert runtime.last_error == "ValueError: component exploded"
    assert runtime.running_tasks == set()
    assert_stream_is_closed(client)

    with pytest.raises(RuntimeError):
        runtime.start()


async def test_stop_during_a_failure_teardown_joins_it(stream_clients, no_task_leaks):
    """The race `TwinInstance.close()` can lose: a component fails while a
    client is calling `stop()`.  One teardown, and the failure wins the
    state -- `stop()` never gets to flip it to `stopped`."""

    client = await stream_clients("twin-a")
    runtime = DTRuntime(NO_FLOW, client)
    runtime.add_task(Forever(NO_FLOW), TRUTHY, TICK, is_persistent=True)
    runtime.add_task(Boom(NO_FLOW), TRUTHY, NULL_DTYPE)
    runtime.start()

    # the failure is already scheduled, its teardown has not run yet
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert runtime.state is RuntimeState.FAILED

    teardown = runtime._stop_task
    await runtime.stop()

    assert runtime._stop_task is teardown
    assert runtime.state is RuntimeState.FAILED
    assert runtime.last_error == "ValueError: component exploded"
    assert runtime.running_tasks == set()
    assert_stream_is_closed(client)


async def test_a_failure_after_stop_keeps_the_twin_stopped(stream_clients):
    """The mirror-image rule: a twin which was stopped cleanly stays
    `stopped`, and only keeps the error for inspection."""

    runtime = DTRuntime(NO_FLOW, await stream_clients("twin-a"))
    runtime.start()
    await runtime.stop()

    runtime._record_error(RuntimeError("late arrival"))

    assert runtime.state is RuntimeState.STOPPED
    assert runtime.last_error == "RuntimeError: late arrival"


async def test_simultaneous_failures_run_one_teardown(stream_clients, no_task_leaks):
    """Two components failing in the same loop iteration, and a third
    failing *inside* the teardown (its cancellation handler raises): one
    teardown, no crash, and the first error is the one reported."""

    client = await stream_clients("twin-a")
    runtime = DTRuntime(NO_FLOW, client)

    scheduled = []
    start_teardown = runtime._start_teardown

    def spy(timeout):
        scheduled.append(timeout)
        return start_teardown(timeout)

    runtime._start_teardown = spy

    cue = asyncio.Event()
    cue.set()
    runtime.add_task(BoomOnCue(NO_FLOW, cue, "first"), TRUTHY, NULL_DTYPE)
    runtime.add_task(BoomOnCue(NO_FLOW, cue, "second"), TRUTHY, NULL_DTYPE)
    runtime.add_task(BoomOnCancel(NO_FLOW), TRUTHY, NULL_DTYPE)
    runtime.start()

    await torn_down(runtime)

    # one teardown, on the default budget
    assert scheduled == [STOP_TIMEOUT]
    assert runtime.state is RuntimeState.FAILED
    assert runtime.last_error == "ValueError: first"
    assert runtime.running_tasks == set()
    assert_stream_is_closed(client)

    await runtime.stop()
    assert runtime.last_error == "ValueError: first"


async def test_stopped_runtime_starts_no_new_work(stream_clients):
    runtime = DTRuntime(NO_FLOW, await stream_clients("twin-a"))
    runtime.start()
    await runtime.stop()

    assert runtime._to_asyncio_task(asyncio.sleep, 0) is None
    assert runtime.running_tasks == set()


async def test_describe_is_serializable(stream_clients):
    import json

    runtime = DTRuntime(NO_FLOW, await stream_clients("twin-a"))
    inference = DataType("inference")

    runtime.add_task(Forever(NO_FLOW), TRUTHY, TICK, is_persistent=True)
    runtime.add_task(Forever(NO_FLOW), inference, NULL_DTYPE)

    barrier = Barrier("b", hard=False)
    barrier.add_dtype(TICK)
    runtime.add_barrier(barrier)

    info = runtime.describe()
    assert json.loads(json.dumps(info)) == info

    assert info["namespace"] == "twin-a"
    assert info["state"] == "ready"
    assert info["last_error"] is None
    assert sorted(info["dtypes"]) == ["NULL", "TRUE", "inference", "tick"]
    assert info["barriers"] == {"tick": [{"name": "b", "hard": False}]}
    assert info["components"] == [
        {
            "component": "Forever",
            "kind": "utility",
            "input_dtype": "TRUE",
            "output_dtype": "tick",
            "is_persistent": True,
            "is_join": False,
            "is_split": False,
            "split_outputs": [],
        },
        {
            "component": "Forever",
            "kind": "utility",
            "input_dtype": "inference",
            "output_dtype": "NULL",
            "is_persistent": False,
            "is_join": False,
            "is_split": False,
            "split_outputs": [],
        },
    ]

    # print_graph is a rendering of describe()
    assert "Forever" in runtime.print_graph()

    await runtime.stop()
