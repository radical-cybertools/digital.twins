"""The per-message path: skipped answers nobody takes, inline ON_INPUT.

By default every streamed input runs the investigator's in-situ inference.
An investigator that sets `infer_without_consumer = False` (the streaming
learner does) runs it only if its answer has a taker (an `ON_OUTPUT`
subscriber, or something consuming the output dtype), or for the first
input after each published model or inference task; `get_inference` always
runs it.  An `ON_INPUT` callback subscribed with
`inline=True` is awaited in place, before the inference, and its failure
fails the twin as a task's would.
"""

import asyncio

import pytest

from digitaltwin import (
    NULL_DTYPE,
    TRUTHY,
    DTRuntime,
    DataType,
    ModelInvestigator,
    RuntimeAPI,
    RuntimeState,
    TypedData,
    UtilityTask,
)

SENSOR = DataType("mp-sensor")
OUT = DataType("mp-out")


class Sensor(UtilityTask):
    async def main_loop(self, runtime, in_data):
        value = 0
        while True:
            await runtime.stream.publish(SENSOR, value)
            value += 1
            await asyncio.sleep(0.02)


class Counting(ModelInvestigator):
    """Counts its inferences and its ON_INPUT calls, in call order."""

    def __init__(self, inline=False, on_output=False, fail_on=None, skip=False):
        super().__init__(None)
        self.inline, self.on_output, self.fail_on = inline, on_output, fail_on
        if skip:
            self.infer_without_consumer = False
        self.inferred, self.seen, self.outputs, self.order = [], [], [], []

    async def publish(self, runtime):
        runtime.publish_new_model()

    async def main_loop(self, runtime):
        async def inference(in_data, **model_kwargs):
            if model_kwargs.get("bad"):
                raise RuntimeError("model rejected")
            self.inferred.append(in_data.data)
            self.order.append(("infer", in_data.data))
            return TypedData(OUT, in_data.data)

        async def on_input(in_data):
            if in_data.data == self.fail_on:
                raise RuntimeError("on_input failed")
            self.seen.append(in_data.data)
            self.order.append(("input", in_data.data))

        async def on_output(answer):
            self.outputs.append(answer.data)

        runtime.set_inference_task(inference)
        runtime.subscribe_to_topic(RuntimeAPI.ON_INPUT, on_input, inline=self.inline)
        if self.on_output:
            runtime.subscribe_to_topic(RuntimeAPI.ON_OUTPUT, on_output)
        await self.publish(runtime)


class Sink(UtilityTask):
    def __init__(self, received):
        super().__init__(None)
        self.received = received

    async def main_loop(self, runtime, in_data):
        self.received.append(in_data.data)


async def until(cond, timeout=10.0):
    async def poll():
        while not cond():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(poll(), timeout)


async def run_twin(stream_clients, inv, sink=None, until_seen=5):
    runtime = DTRuntime(None, await stream_clients("mp"))
    runtime.add_task(Sensor(None), TRUTHY, SENSOR, is_persistent=True)
    runtime.add_investigator(inv, SENSOR, OUT)
    if sink is not None:
        runtime.add_task(sink, OUT, NULL_DTYPE)
    runtime.start()
    try:
        await until(lambda: len(inv.seen) >= until_seen)
        await asyncio.sleep(0.1)
    finally:
        await runtime.stop()
    return runtime


async def test_default_infers_every_input(stream_clients, no_task_leaks):
    inv = Counting()
    await run_twin(stream_clients, inv)
    assert len(inv.inferred) >= 5


def test_streaming_learner_skips_unconsumed():
    learn = pytest.importorskip("digitaltwin.learn", exc_type=ImportError)
    assert learn.StreamingLearnerInvestigator.infer_without_consumer is False


async def test_unconsumed_streamed_answer_is_not_inferred(stream_clients, no_task_leaks):
    inv = Counting(skip=True)
    await run_twin(stream_clients, inv)
    assert len(inv.seen) >= 5          # the investigator still sees every input
    assert len(inv.inferred) == 1      # one probe of the one published model


class LatePublish(Counting):
    """Publishes only after the first input has arrived (and waits for it)."""

    async def publish(self, runtime):
        await until(lambda: len(self.seen) >= 1)
        await asyncio.sleep(0.2)
        runtime.publish_new_model()


async def test_input_before_the_first_publish_probes_once(stream_clients, no_task_leaks):
    inv = LatePublish(skip=True)
    await run_twin(stream_clients, inv, until_seen=8)
    assert len(inv.inferred) == 1


class Republish(Counting):
    """Publishes the same dict object again after changing it in place."""

    async def publish(self, runtime):
        self.model = {"version": 1}
        runtime.publish_new_model(self.model)
        await until(lambda: len(self.inferred) >= 1)
        await until(lambda: len(self.seen) >= len(self.inferred) + 2)
        self.model["version"] = 2
        runtime.publish_new_model(self.model)


async def test_republished_dict_is_probed_again(stream_clients, no_task_leaks):
    inv = Republish(skip=True)
    await run_twin(stream_clients, inv, until_seen=10)
    assert len(inv.inferred) == 2


class BadModelLater(Counting):
    """Publishes a model the inference task rejects, after a good one."""

    async def publish(self, runtime):
        runtime.publish_new_model()
        await until(lambda: len(self.inferred) >= 1)
        runtime.publish_new_model({"bad": True})


async def test_rejected_model_fails_the_twin_on_the_next_input(stream_clients, no_task_leaks):
    inv = BadModelLater(skip=True)
    runtime = DTRuntime(None, await stream_clients("mp-bad"))
    runtime.add_task(Sensor(None), TRUTHY, SENSOR, is_persistent=True)
    runtime.add_investigator(inv, SENSOR, OUT)
    runtime.start()
    try:
        await until(lambda: runtime.state is RuntimeState.FAILED)
        assert "model rejected" in str(runtime.last_error)
    finally:
        await runtime.stop()


async def test_consumed_output_dtype_is_inferred(stream_clients, no_task_leaks):
    received: list = []
    inv = Counting(skip=True)
    await run_twin(stream_clients, inv, sink=Sink(received))
    assert inv.inferred and received
    assert received == inv.inferred[:len(received)]


async def test_on_output_subscriber_is_a_taker(stream_clients, no_task_leaks):
    inv = Counting(on_output=True, skip=True)
    await run_twin(stream_clients, inv)
    assert inv.inferred
    await until(lambda: len(inv.outputs) >= 1)


async def test_get_inference_always_infers(stream_clients, no_task_leaks):
    inv = Counting(skip=True)
    runtime = DTRuntime(None, await stream_clients("mp-direct"))
    runtime.add_investigator(inv, SENSOR, OUT)
    runtime.start()
    try:
        await until(lambda: inv.inferred or runtime.state is RuntimeState.RUNNING)
        answer = None
        for _ in range(200):
            answer = await runtime.get_inference(TypedData(SENSOR, 7), OUT)
            if answer.dtype != NULL_DTYPE:
                break
            await asyncio.sleep(0.02)
        assert answer.data == 7
        assert 7 in inv.inferred
    finally:
        await runtime.stop()


async def test_inline_on_input_runs_before_the_inference(stream_clients, no_task_leaks):
    inv = Counting(inline=True)
    await run_twin(stream_clients, inv)
    # per input: the callback first, then the inference, never interleaved
    for value in inv.inferred:
        assert inv.order.index(("input", value)) < inv.order.index(("infer", value))


async def test_inline_failure_fails_the_twin(stream_clients, no_task_leaks):
    inv = Counting(inline=True, fail_on=2)
    runtime = DTRuntime(None, await stream_clients("mp-fail"))
    runtime.add_task(Sensor(None), TRUTHY, SENSOR, is_persistent=True)
    runtime.add_investigator(inv, SENSOR, OUT)
    runtime.start()
    try:
        await until(lambda: runtime.state is RuntimeState.FAILED)
        assert "on_input failed" in str(runtime.last_error)
    finally:
        await runtime.stop()


async def test_inline_is_for_on_input_only(stream_clients):
    runtime = DTRuntime(None, await stream_clients("mp-api"))
    runtime.add_investigator(Counting(), SENSOR, OUT)
    api = runtime._api(runtime.components[SENSOR][0])
    try:
        with pytest.raises(ValueError):
            api.subscribe_to_topic(RuntimeAPI.ON_OUTPUT, lambda answer: None, inline=True)
    finally:
        await runtime.stop()
