"""M0.7 -- the graph's input edge: external channels, shared by twins."""

import asyncio

import pytest

from digitaltwin import (
    CODEC_CLOUDPICKLE,
    CODEC_JSON,
    CODEC_RAW,
    NULL_DTYPE,
    ChannelPublisher,
    DTRuntime,
    DataType,
    PubSubConfig,
    UtilityTask,
)
from digitaltwin.streaming import decode_payload, encode_payload

SENSOR = DataType("sensor")
CHANNEL = "sensors/temperature"


class Sink(UtilityTask):
    def __init__(self, flow, received):
        super().__init__(flow)
        self.received = received

    async def main_loop(self, runtime, in_data):
        self.received.append(in_data.data)


async def _publisher(broker, channel=CHANNEL, codec=CODEC_JSON):
    """An external producer, as a demo script would open one."""

    config = PubSubConfig(None, *broker.get_connection_str())

    return await ChannelPublisher.open(channel, codec, config=config, timeout=10.0)


async def _twin(stream_clients, namespace, channel=CHANNEL, codec=CODEC_JSON):
    received: list = []

    runtime = DTRuntime(None, await stream_clients(namespace))
    runtime.add_input(SENSOR, channel, codec)
    runtime.add_task(Sink(None, received), SENSOR, NULL_DTYPE)
    runtime.start()

    return runtime, received


async def _wait_for(received, count, timeout=10.0):
    async def wait():
        while len(received) < count:
            await asyncio.sleep(0.05)

    await asyncio.wait_for(wait(), timeout)


async def test_two_twins_share_one_channel(broker, stream_clients, no_task_leaks):
    """The acceptance test for sharing: one external producer, one channel,
    two twins in two namespaces, and every message reaches both."""

    twin_a, received_a = await _twin(stream_clients, "twin-a")
    twin_b, received_b = await _twin(stream_clients, "twin-b")

    publisher = await _publisher(broker)
    await asyncio.sleep(0.3)  # let both subscriptions reach the broker

    try:
        for value in range(5):
            await publisher.publish({"value": value})

        await _wait_for(received_a, 5)
        await _wait_for(received_b, 5)

        expected = [{"value": value} for value in range(5)]
        assert received_a == expected
        assert received_b == expected

    finally:
        await publisher.close()
        await twin_a.stop()
        await twin_b.stop()


async def test_raw_channel_delivers_bytes(broker, stream_clients, no_task_leaks):
    twin, received = await _twin(stream_clients, "twin-a", codec=CODEC_RAW)

    publisher = await _publisher(broker, codec=CODEC_RAW)
    await asyncio.sleep(0.3)

    try:
        await publisher.publish(b"\x01\x02 not text")
        await _wait_for(received, 1)
        assert received == [b"\x01\x02 not text"]

    finally:
        await publisher.close()
        await twin.stop()


async def test_undecodable_payload_is_dropped(broker, stream_clients, no_task_leaks):
    """A producer which gets the codec wrong costs its own message, not the
    stream (the same contract malformed internal traffic gets)."""

    twin, received = await _twin(stream_clients, "twin-a")

    # same channel, but bytes which are not JSON
    garbage = await _publisher(broker, codec=CODEC_RAW)
    publisher = await _publisher(broker)
    await asyncio.sleep(0.3)

    try:
        await garbage.publish(b"\xff\xfe not json")
        await asyncio.sleep(0.2)
        assert received == []

        await publisher.publish({"value": 1})
        await _wait_for(received, 1)
        assert received == [{"value": 1}]

    finally:
        await garbage.close()
        await publisher.close()
        await twin.stop()


async def test_channels_and_codecs_are_validated(stream_clients):
    runtime = DTRuntime(None, await stream_clients("twin-a"))

    # a channel may not claim the twin-internal prefix, be empty, or carry
    # the topic terminator
    for channel in ("dt/twin-b/dtypes/sensor", "", "sensors/x\x00"):
        with pytest.raises(ValueError):
            runtime.add_input(SENSOR, channel)

    with pytest.raises(ValueError):
        runtime.add_input(SENSOR, CHANNEL, codec="yaml")

    assert runtime.inputs == []

    await runtime.stop()

    # and a stopped twin takes no new bindings
    with pytest.raises(RuntimeError):
        runtime.add_input(SENSOR, CHANNEL)


async def test_bindings_are_described(stream_clients):
    import json

    runtime = DTRuntime(None, await stream_clients("twin-a"))
    runtime.add_input(SENSOR, CHANNEL)
    runtime.add_input(SENSOR, CHANNEL)  # idempotent

    info = runtime.describe()
    assert json.loads(json.dumps(info)) == info
    assert info["inputs"] == [{"dtype": "sensor", "channel": CHANNEL, "codec": "json"}]

    # a bound dtype belongs to the graph even before a component consumes it
    assert "sensor" in info["dtypes"]
    assert CHANNEL in runtime.print_graph()

    await runtime.stop()


@pytest.mark.parametrize(
    "codec, message",
    [
        (CODEC_JSON, {"value": 1.5, "unit": "C"}),
        (CODEC_RAW, b"bytes"),
        (CODEC_CLOUDPICKLE, {"value": 1.5}),
    ],
)
def test_codecs_round_trip(codec, message):
    assert decode_payload(encode_payload(message, codec), codec) == message


def test_unknown_codec_is_refused():
    with pytest.raises(ValueError):
        encode_payload({}, "yaml")
    with pytest.raises(ValueError):
        decode_payload(b"{}", "yaml")


# -- a burst right after open() is not lost (#40) ------------------------------

async def test_burst_right_after_open_reaches_the_twin(broker, stream_clients,
                                                      no_task_leaks):
    """No settle sleep: `open()` waits until the twin's subscription has
    reached the publisher, so the first message already arrives."""

    twin, received = await _twin(stream_clients, "twin-a")
    publisher = await _publisher(broker)

    try:
        for value in range(3):
            await publisher.publish({"value": value})

        await _wait_for(received, 3)
        assert received == [{"value": value} for value in range(3)]

    finally:
        await publisher.close()
        await twin.stop()


async def test_open_without_subscriber_returns_after_ready_timeout(broker):
    config = PubSubConfig(None, *broker.get_connection_str())
    loop = asyncio.get_running_loop()

    t0 = loop.time()
    publisher = await ChannelPublisher.open("nobody/listens", config=config,
                                            timeout=10.0, ready_timeout=0.3)
    elapsed = loop.time() - t0

    try:
        assert 0.25 <= elapsed < 5.0
        await publisher.publish({"value": 1})     # still usable
    finally:
        await publisher.close()


async def test_ready_timeout_zero_skips_the_wait(broker):
    config = PubSubConfig(None, *broker.get_connection_str())
    loop = asyncio.get_running_loop()

    t0 = loop.time()
    publisher = await ChannelPublisher.open("nobody/listens", config=config,
                                            timeout=10.0, ready_timeout=0)
    try:
        assert loop.time() - t0 < 0.25
    finally:
        await publisher.close()
