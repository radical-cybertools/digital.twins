"""The per-message path: skipped answers nobody takes, inline ON_INPUT.

A streamed input runs the investigator's in-situ inference only if its
answer has a taker (an `ON_OUTPUT` subscriber, or something consuming the
output dtype), if it is the first input after a published model, or if the
investigator opts out (`infer_without_consumer`); `get_inference` always
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

    def __init__(self, inline=False, on_output=False, fail_on=None):
        super().__init__(None)
        self.inline, self.on_output, self.fail_on = inline, on_output, fail_on
        self.inferred, self.seen, self.outputs, self.order = [], [], [], []

    async def main_loop(self, runtime):
        async def inference(in_data, **model_kwargs):
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
        runtime.publish_new_model()


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


async def test_unconsumed_streamed_answer_is_not_inferred(stream_clients, no_task_leaks):
    inv = Counting()
    await run_twin(stream_clients, inv)
    assert len(inv.seen) >= 5          # the investigator still sees every input
    assert len(inv.inferred) == 1      # one probe of the one published model


async def test_consumed_output_dtype_is_inferred(stream_clients, no_task_leaks):
    received: list = []
    inv = Counting()
    await run_twin(stream_clients, inv, sink=Sink(received))
    assert inv.inferred and received
    assert received == inv.inferred[:len(received)]


async def test_on_output_subscriber_is_a_taker(stream_clients, no_task_leaks):
    inv = Counting(on_output=True)
    await run_twin(stream_clients, inv)
    assert inv.inferred
    await until(lambda: len(inv.outputs) >= 1)


async def test_infer_without_consumer_opts_out(stream_clients, no_task_leaks):
    inv = Counting()
    inv.infer_without_consumer = True
    await run_twin(stream_clients, inv)
    assert inv.inferred


async def test_get_inference_always_infers(stream_clients, no_task_leaks):
    inv = Counting()
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
    inv.infer_without_consumer = True
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
