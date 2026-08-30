"""Twin components the integration tests ship to the service.

This module is cloudpickled by value (the service has no copy of it), so
it must stay importable on its own -- no test imports, no fixtures.
"""

import asyncio

from digitaltwin.components import (
    DataType,
    ModelInvestigator,
    TypedData,
    UtilityTask,
)

SENSOR_DTYPE = DataType("sensor")
INFERENCE_DTYPE = DataType("inference")
ECHO_DTYPE = DataType("echo")


class CountingSensor(UtilityTask):
    """Persistent source: publishes 0, 1, 2, ... into the twin's stream.

    Plain async code on the service loop with the injected stream client
    -- the persistent-component contract.
    """

    def __init__(self, flow, count: int = 10_000, interval: float = 0.2):
        super().__init__(flow)
        self.count = count
        self.interval = interval

    async def main_loop(self, runtime, in_data):
        for value in range(self.count):
            await asyncio.sleep(self.interval)
            await runtime.stream.publish(SENSOR_DTYPE, value)


class OffsetModel(ModelInvestigator):
    """Inference on the engine: `sensor value + offset`.

    Note the split: the *task* returns a plain value and the component
    wraps it in `TypedData`.  Task arguments keep full cloudpickle
    fidelity, but return values only survive the ORBIT rhapsody plugin
    when they are JSON-safe (or `bytes`) -- see README.
    """

    def __init__(self, flow, offset: int = 100):
        super().__init__(flow)
        self.offset = offset

        @flow.function_task
        async def compute(in_data: TypedData, offset: int = 0):
            return in_data.data + offset

        self.compute = compute

    async def main_loop(self, runtime):
        async def infer(in_data: TypedData, offset: int = 0):
            value = await self.compute(in_data, offset=offset)
            return TypedData(INFERENCE_DTYPE, value)

        runtime.set_inference_task(infer)
        runtime.publish_new_model({"offset": self.offset})


class SlowModel(ModelInvestigator):
    """Inference that never finishes in test time -- for the teardown
    path of a `twin_close` with a call in flight."""

    def __init__(self, flow, delay: float = 300.0):
        super().__init__(flow)
        self.delay = delay

    async def main_loop(self, runtime):
        async def infer(in_data: TypedData, **kwargs):
            await asyncio.sleep(self.delay)
            return TypedData(INFERENCE_DTYPE, in_data.data)

        runtime.set_inference_task(infer)
        runtime.publish_new_model({})


class SlowTaskModel(ModelInvestigator):
    """`SlowModel`, but the wait happens in a real backend task.

    Closing a twin mid-inference then has to walk the best-effort cancel
    of an in-flight *engine* call, not just of a local sleep.

    The delay is deliberately short: cancelling the local await does not
    reach into the endpoint (`stop` is best-effort by design), so the
    task really does keep running there, and a long one would hold a
    slot on the shared test endpoint for the rest of the suite.
    """

    def __init__(self, flow, delay: float = 15.0):
        super().__init__(flow)
        self.delay = delay

        @flow.function_task
        async def slow(seconds: float):
            await asyncio.sleep(seconds)
            return 1

        self.slow = slow

    async def main_loop(self, runtime):
        async def infer(in_data: TypedData, **kwargs):
            await self.slow(self.delay)
            return TypedData(INFERENCE_DTYPE, in_data.data)

        runtime.set_inference_task(infer)
        runtime.publish_new_model({})


class EchoSink(UtilityTask):
    """Terminal component: republishes what it receives, so a client can
    watch the pipeline over the twin's own (namespaced) stream."""

    async def main_loop(self, runtime, in_data):
        await runtime.stream.publish(ECHO_DTYPE, in_data.data)


class JoinSink(UtilityTask):
    """Terminal for a joined stream: republishes the member sum, so a
    client can watch complete join sets arrive over the twin's stream."""

    async def main_loop(self, runtime, in_data):
        await runtime.stream.publish(
            ECHO_DTYPE, sum(item.data for item in in_data.data))


class CrashingTask(UtilityTask):
    """Persistent component that dies -- the twin must land in `failed`
    with the reason visible in `twin_list`."""

    def __init__(self, flow, delay: float = 0.1):
        super().__init__(flow)
        self.delay = delay

    async def main_loop(self, runtime, in_data):
        await asyncio.sleep(self.delay)
        raise RuntimeError("component crashed on purpose")


class MisplacedFunctionTask(UtilityTask):
    """A persistent component written the *wrong* way: its body is a
    `function_task`, which would occupy a backend slot for the twin's
    lifetime.  The service warns about exactly this."""

    def __init__(self, flow):
        super().__init__(flow)

        @flow.function_task
        async def body():
            return 1

        self.body = body

    async def main_loop(self, runtime, in_data):
        await asyncio.sleep(3600)
