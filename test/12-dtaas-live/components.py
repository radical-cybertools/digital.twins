"""The plain twin: sensor -> model -> sink.

Paced for narration rather than for throughput.  Everything here is
cloudpickled by value and instantiated inside the plugin host, so this
module must stay importable on its own.
"""

import asyncio

from digitaltwin.components import ModelInvestigator, TypedData, UtilityTask

from dtypes import INFERENCE_DTYPE, SENSOR_DTYPE

# slow enough to talk over, long enough to outlast the whole narration
TICK = 2.5
READINGS = 400


class PacedSensor(UtilityTask):
    """A persistent component, running inline on the service loop.

    It publishes through `runtime.stream` -- the twin's own client, which
    the runtime injected.  Not `stream_config`: that is for code running
    somewhere else, and opening a second client from in here would leak
    one per twin inside a broker that runs for days.
    """

    async def main_loop(self, runtime, in_data):
        for value in range(READINGS):
            await runtime.stream.publish(SENSOR_DTYPE, value)
            await asyncio.sleep(TICK)


class RampModel(ModelInvestigator):
    """No learning -- inference whose answer moves as the model is
    republished, so the sink's output visibly changes mid-demo.

    `compute` runs on the rhapsody endpoint; the `TypedData` wrapping
    happens here, in the service.  Task return values have to be
    JSON-safe or bytes to survive ORBIT's rhapsody plugin, so the task
    returns a plain number.
    """

    def __init__(self, flow, *args, **kwargs):
        super().__init__(flow)
        self.flow = flow

        @self.flow.function_task
        async def compute(in_data: TypedData, gain=1):
            return gain * in_data.data

        self.compute = compute

    async def main_loop(self, runtime):
        async def do_inference(in_data: TypedData, gain=1):
            answer = await self.compute(in_data, gain=gain)
            return TypedData(INFERENCE_DTYPE, answer)

        runtime.set_inference_task(do_inference)

        gain = 2
        while True:
            runtime.publish_new_model({"gain": gain})
            gain += 1
            await asyncio.sleep(20.0)


class EchoSink(UtilityTask):
    """Prints, and *publishes*.

    The runtime hands a component's answer to the next component on that
    dtype over an in-process queue and drops it if nobody is registered.
    Anything outside the service -- the dashboard included -- only sees a
    result because a component chose to publish it.
    """

    async def main_loop(self, runtime, in_data):
        print(f"    [twin] inference -> {in_data.data}", flush=True)
        await runtime.stream.publish(INFERENCE_DTYPE, in_data.data)
