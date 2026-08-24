"""M0.3 -- persistent components publish through the injected stream client.

No `function_task` wrapping, no hand-built ZMQ client, no address in sight:
the component only ever touches `runtime.stream`.  A component which opens
its own client from `runtime.stream_config` instead leaks it -- `no_task_leaks`
catches that here.
"""

import asyncio

from digitaltwin import (
    NULL_DTYPE,
    TRUTHY,
    DTRuntime,
    DataType,
    ModelInvestigator,
    TypedData,
    UtilityTask,
)
from digitaltwin.streaming import PubSubClient

SENSOR = DataType("sensor")
INFERENCE = DataType("inference")


class Sensor(UtilityTask):
    async def main_loop(self, runtime, in_data):
        value = 0
        while True:
            await runtime.stream.publish(SENSOR, value)
            value += 1
            await asyncio.sleep(0.05)


class Doubler(ModelInvestigator):
    async def main_loop(self, runtime):
        async def inference(in_data, **model_kwargs):
            return TypedData(INFERENCE, in_data.data * 2)

        runtime.set_inference_task(inference)
        runtime.publish_new_model()


class Sink(UtilityTask):
    def __init__(self, flow, received):
        super().__init__(flow)
        self.received = received

    async def main_loop(self, runtime, in_data):
        self.received.append(in_data.data)


async def test_persistent_component_publishes_through_runtime_stream(
    stream_clients, no_task_leaks
):
    received: list[int] = []

    runtime = DTRuntime(None, await stream_clients("twin-a"))
    runtime.add_task(Sensor(None), TRUTHY, SENSOR, is_persistent=True)
    runtime.add_investigator(Doubler(None), SENSOR, INFERENCE)
    runtime.add_task(Sink(None, received), INFERENCE, NULL_DTYPE)

    runtime.start()

    async def wait_for_data():
        while len(received) < 3:
            await asyncio.sleep(0.05)

    await asyncio.wait_for(wait_for_data(), timeout=10.0)
    await runtime.stop()

    # the sensor counts up, the investigator doubles
    assert received[:3] == [received[0], received[0] + 2, received[0] + 4]
    assert all(value % 2 == 0 for value in received)


class ConfigProbe(UtilityTask):
    def __init__(self, flow, seen):
        super().__init__(flow)
        self.seen = seen

    async def main_loop(self, runtime, in_data):
        self.seen.append((runtime.stream_config, runtime.stream))


async def test_components_see_the_stream_config(stream_clients):
    """What a component gets handed: the live client for in-process use,
    and the same endpoint as plain data for anything that has to travel."""

    seen: list = []
    client = await stream_clients("twin-a")

    runtime = DTRuntime(None, client)
    runtime.add_task(ConfigProbe(None, seen), TRUTHY, NULL_DTYPE)
    runtime.start()

    await asyncio.sleep(0.1)
    assert seen == [(client.config, client)]
    assert runtime.stream_config == client.config

    await runtime.stop()


async def test_two_twins_on_one_broker_stay_separate(stream_clients, no_task_leaks):
    """Same component code, same dtype labels, two namespaces: the twins
    must not see each other's data."""

    received_a: list[int] = []
    received_b: list[int] = []

    twins = []
    for namespace, received in (("twin-a", received_a), ("twin-b", received_b)):
        runtime = DTRuntime(None, await stream_clients(namespace))
        runtime.add_task(Sensor(None), TRUTHY, SENSOR, is_persistent=True)
        runtime.add_task(Sink(None, received), SENSOR, NULL_DTYPE)
        runtime.start()
        twins.append(runtime)

    async def wait_for_data():
        while len(received_a) < 5 or len(received_b) < 5:
            await asyncio.sleep(0.05)

    try:
        await asyncio.wait_for(wait_for_data(), timeout=10.0)
    finally:
        for runtime in twins:
            await runtime.stop()

    # each twin sees exactly its own monotonic sensor sequence -- crosstalk
    # would show up as duplicated values
    for received in (received_a, received_b):
        assert received == sorted(set(received))

    # tearing one twin down does not disturb its sibling
    assert twins[0].last_error is None
    assert twins[1].last_error is None
