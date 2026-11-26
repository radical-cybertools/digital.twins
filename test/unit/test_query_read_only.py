"""A query is not an observation: `get_inference` answers, but fires no
ON_INPUT, so it trains nothing.  Streamed inputs still do."""

import asyncio

from radical.doppelganger import (
    CODEC_JSON,
    NULL_DTYPE,
    ChannelPublisher,
    DTRuntime,
    DataType,
    ModelInvestigator,
    PubSubConfig,
    RuntimeAPI,
    SciAgent,
    TypedData,
    UtilityTask,
)

X = DataType("ro-in")
Y = DataType("ro-out")
CHANNEL = "sensors/read-only"


class Inv(ModelInvestigator):
    def __init__(self, flow, seen):
        super().__init__(flow)
        self.seen = seen

    async def main_loop(self, runtime):
        async def infer(in_data, k=1.0):
            return TypedData(Y, k * in_data.data["value"])

        async def observe(in_data):
            self.seen.append(("investigator", in_data.data["value"]))

        runtime.set_inference_task(infer)
        runtime.subscribe_to_topic(RuntimeAPI.ON_INPUT, observe)
        runtime.publish_new_model({"k": 2.0}, {})


class Agent(SciAgent):
    def __init__(self, flow, seen):
        super().__init__(flow)
        self.seen = seen
        self.inv = Inv(flow, seen)

    async def main_loop(self, runtime):
        async def observe(in_data):
            self.seen.append(("agent", in_data.data["value"]))

        runtime.subscribe_to_topic(RuntimeAPI.ON_INPUT, observe, inline=True)
        runtime.start_investigator(self.inv)

        async def select(in_data, i_id=0):
            return i_id, {"k": 2.0}

        runtime.set_model_selection_task(select)
        runtime.update_model_selector(i_id=self.inv.get_id())


class Sink(UtilityTask):
    def __init__(self, flow, received):
        super().__init__(flow)
        self.received = received

    async def main_loop(self, runtime, in_data):
        self.received.append(in_data.data)


async def _wait_for(items, count, timeout=10.0):
    async def wait():
        while len(items) < count:
            await asyncio.sleep(0.05)

    await asyncio.wait_for(wait(), timeout)


async def test_queries_feed_no_investigator(broker, stream_clients, no_task_leaks):
    seen: list = []
    received: list = []

    runtime = DTRuntime(None, await stream_clients("read-only"))
    runtime.add_input(X, CHANNEL, CODEC_JSON)
    runtime.add_agent(Agent(None, seen), X, Y)
    runtime.add_task(Sink(None, received), Y, NULL_DTYPE)
    runtime.start()

    config = PubSubConfig(None, *broker.get_connection_str())
    publisher = await ChannelPublisher.open(CHANNEL, CODEC_JSON, config=config, timeout=10.0)
    await asyncio.sleep(0.3)  # let the subscription reach the broker

    try:
        for value in (1, 2, 3):
            await publisher.publish({"value": value})
        await _wait_for(received, 3)

        for value in (10, 20):
            answer = await runtime.get_inference(TypedData(X, {"value": value}), Y)
            assert answer.data == 2.0 * value
        await asyncio.sleep(0.3)  # an ON_INPUT task would have run by now

        assert sorted(v for who, v in seen if who == "agent") == [1, 2, 3]
        assert sorted(v for who, v in seen if who == "investigator") == [1, 2, 3]
    finally:
        await publisher.close()
        await runtime.stop()
