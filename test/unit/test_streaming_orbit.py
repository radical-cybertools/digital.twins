"""M3 -- the ORBIT-backed pubsub backend.

Everything here runs against a loopback stand-in for ORBIT's event
router: an in-process registry with the two properties the backend
actually depends on -- events reach *every* matching subscriber
including the sender (the DT case: a twin's runtime subscribes to the
dtypes its own components publish), and callbacks arrive on a foreign
thread, not on the host loop.

The live-broker coverage is in `test/integration/test_dt_orbit_stream.py`.
"""

import asyncio
import threading

from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("radical.orbit")

from digitaltwin import DataType, PubSubClient  # noqa: E402
from digitaltwin.streaming_orbit import (  # noqa: E402
    FRAME_OVERHEAD,
    INBOX_SIZE,
    PAYLOAD_KEY,
    STREAM_PLUGIN,
    OrbitPubSubBackend,
)

SENSOR = DataType("sensor")

# 64 KiB envelope headroom + 1 KiB of payload: enough to test the ceiling
# without pickling megabytes
SMALL_FRAME_CAP = 64 * 1024 + 1024


# ---------------------------------------------------------------------------
# the loopback stand-in
# ---------------------------------------------------------------------------

class LoopbackBroker:
    """ORBIT's event router, in process.

    Exact-match subscriptions, fan-out to every matching participant with
    no exclusion of the sender, and delivery on a dedicated thread -- the
    three behaviours the backend is written against.
    """

    def __init__(self):
        self.subscriptions: list[tuple] = []  # (runtime, plugin, topic)
        self.published: list[tuple] = []      # (src, plugin, topic, data)
        self.registered: dict[str, "LoopbackRuntime"] = {}

        # stands in for the runtime's own 'orbit-callbacks' thread
        self._pool = ThreadPoolExecutor(1, thread_name_prefix="loopback-cb")

    def runtime(self, name: str, registers: bool = True) -> "LoopbackRuntime":
        return LoopbackRuntime(self, name, registers)

    def publish(self, src, plugin, topic, data) -> None:
        self.published.append((src, plugin, topic, data))

        for runtime, sub_plugin, sub_topic in list(self.subscriptions):
            if (sub_plugin, sub_topic) == (plugin, topic):
                self._pool.submit(runtime.deliver, src, plugin, topic, data)

    def drop(self, runtime) -> None:
        self.subscriptions = [s for s in self.subscriptions if s[0] is not runtime]
        self.registered.pop(runtime.name, None)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)

    def topics(self) -> list[str]:
        return [topic for _, _, topic in self.subscriptions]


class LoopbackRuntime:
    """The slice of `EndpointRuntime` the backend uses."""

    def __init__(self, broker: LoopbackBroker, name: str, registers: bool):
        self._broker = broker
        self._registers = registers
        self._frame_cap = SMALL_FRAME_CAP

        self.name = name
        self.broker_url = "loopback://broker"
        self.started = False
        self.stopped = False
        self.callbacks: dict[tuple, list] = {}

    # -- lifecycle
    def start(self, wait=True, timeout=None):
        self.started = True
        if self._registers:
            self._broker.registered[self.name] = self

    def wait_registered(self, timeout=0):
        return self.name in self._broker.registered

    def stop(self):
        self.stopped = True
        self._broker.drop(self)

    # -- eventing
    def register_callback(self, endpoint_id=None, plugin_name=None, topic=None,
                          callback=None, with_meta=False):
        self.callbacks.setdefault((plugin_name, topic), []).append(callback)
        self._broker.subscriptions.append((self, plugin_name, topic))

    def unregister_callback(self, endpoint_id=None, plugin_name=None,
                            topic=None, callback=None):
        key = (plugin_name, topic)
        self.callbacks[key] = [
            cb for cb in self.callbacks.get(key, []) if cb is not callback
        ]
        entry = (self, plugin_name, topic)
        if entry in self._broker.subscriptions:
            self._broker.subscriptions.remove(entry)

    def send_notification(self, plugin_name, topic, data):
        self._broker.publish(self.name, plugin_name, topic, data)

    def deliver(self, src, plugin, topic, data):
        """Runs on the broker's callback thread, never on the host loop."""

        for callback in list(self.callbacks.get((plugin, topic), [])):
            callback(src, plugin, topic, data)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def loopback():
    broker = LoopbackBroker()
    try:
        yield broker
    finally:
        broker.shutdown()


@pytest.fixture
async def orbit_backends(loopback, monkeypatch):
    """Factory for connected `OrbitPubSubBackend`s on the loopback broker.

    The runtime class is patched, so the backends take the *owned*
    connection path -- the one a twin uses, and the one whose teardown
    the leak assertions are about.  Everything handed out is closed with
    the test.
    """

    monkeypatch.setattr(
        "digitaltwin.streaming_orbit.EndpointRuntime",
        lambda broker_url=None, name=None: loopback.runtime(name),
    )

    backends = []

    async def make(**kwargs):
        backend = OrbitPubSubBackend(**kwargs)
        backends.append(backend)
        await backend.connect(timeout=5)
        return backend

    try:
        yield make
    finally:
        for backend in backends:
            await backend.close()


@pytest.fixture
def orbit_clients(orbit_backends):
    """Factory for namespaced `PubSubClient`s on the loopback broker."""

    async def make(namespace: str):
        return PubSubClient(await orbit_backends(), namespace)

    return make


async def drain(queue: asyncio.Queue, timeout=5.0):
    return await asyncio.wait_for(queue.get(), timeout)


# ---------------------------------------------------------------------------
# delivery
# ---------------------------------------------------------------------------

async def test_a_twin_receives_what_it_publishes(orbit_clients):
    """The DT case: one client both publishes and subscribes.

    Persistent components publish through the twin's stream client and
    the twin's own runtime consumes those dtypes -- so the backend must
    get its own events back, off the broker.
    """

    twin = await orbit_clients("twin-a")
    queue: asyncio.Queue = asyncio.Queue()

    await twin.subscribe_to_dtype(SENSOR, queue)
    await twin.publish(SENSOR, {"value": 42})

    received = await drain(queue)
    assert received.dtype == SENSOR
    assert received.data == {"value": 42}


async def test_delivery_crosses_from_the_callback_thread(orbit_clients):
    """Callbacks arrive on ORBIT's thread; subscribers run on the loop."""

    twin = await orbit_clients("twin-a")
    seen: list = []

    async def record(message):
        seen.append((message, threading.current_thread()))

    await twin._backend.subscribe(twin.topic(SENSOR), record)
    await twin.publish(SENSOR, "hello")

    for _ in range(100):
        if seen:
            break
        await asyncio.sleep(0.02)

    assert seen, "message never reached the host loop"
    assert seen[0] == ("hello", threading.current_thread())


async def test_identical_dtype_labels_do_not_cross_subscribe(orbit_clients):
    """The multi-tenancy target, on the orbit backend: same dtype label,
    two namespaces, one broker -- no crosstalk."""

    twin_a = await orbit_clients("twin-a")
    twin_b = await orbit_clients("twin-b")

    queue_a: asyncio.Queue = asyncio.Queue()
    queue_b: asyncio.Queue = asyncio.Queue()

    await twin_a.subscribe_to_dtype(SENSOR, queue_a)
    await twin_b.subscribe_to_dtype(SENSOR, queue_b)

    for i in range(3):
        await twin_a.publish(SENSOR, f"a-{i}")

    assert (await drain(queue_a)).data == "a-0"

    await asyncio.sleep(0.2)
    assert queue_b.empty()

    # ... and the other direction, so this is isolation and not silence
    await twin_b.publish(SENSOR, "b-0")
    assert (await drain(queue_b)).data == "b-0"


async def test_unsubscribe_stops_delivery_and_the_subscription(
    orbit_clients, loopback
):
    twin = await orbit_clients("twin-a")
    queue: asyncio.Queue = asyncio.Queue()

    await twin.subscribe_to_dtype(SENSOR, queue)
    assert loopback.topics() == [twin.topic(SENSOR)]

    await twin.publish(SENSOR, "first")
    assert (await drain(queue)).data == "first"

    twin.unsubscribe_dtype(SENSOR)
    assert SENSOR not in twin.subscriptions
    assert loopback.topics() == []

    await twin.publish(SENSOR, "second")
    await asyncio.sleep(0.2)
    assert queue.empty()

    # re-subscription is possible after unsubscribe
    await twin.subscribe_to_dtype(SENSOR, queue)
    await twin.publish(SENSOR, "third")
    assert (await drain(queue)).data == "third"


async def test_one_wire_subscription_per_topic(orbit_backends, loopback):
    """Two local subscribers on one topic must not double every frame."""

    backend = await orbit_backends()
    seen: list = []

    async def record(message):
        seen.append(message)

    await backend.subscribe("dt/twin-a/dtypes/sensor", record)
    await backend.subscribe("dt/twin-a/dtypes/sensor", record)

    assert loopback.topics() == ["dt/twin-a/dtypes/sensor"]

    await backend.publish("dt/twin-a/dtypes/sensor", "once")

    for _ in range(100):
        if len(seen) == 2:
            break
        await asyncio.sleep(0.02)

    assert seen == ["once", "once"], "one frame, both subscribers, once each"


async def test_events_use_one_plugin_namespace(orbit_backends, loopback):
    """DT traffic stays under `dt_stream`, so no other subscriber on the
    broker ever has to match it."""

    backend = await orbit_backends()
    await backend.publish("dt/twin-a/dtypes/sensor", "x")

    _, plugin, topic, data = loopback.published[0]
    assert plugin == STREAM_PLUGIN
    assert topic == "dt/twin-a/dtypes/sensor"
    assert isinstance(data[PAYLOAD_KEY], bytes)


# ---------------------------------------------------------------------------
# the frame cap
# ---------------------------------------------------------------------------

async def test_oversized_payload_is_refused_at_publish(orbit_backends):
    """ORBIT drops an oversized frame with a log line and no exception,
    so the ceiling has to be enforced here."""

    backend = await orbit_backends()
    cap = backend.payload_cap()
    assert cap == SMALL_FRAME_CAP - FRAME_OVERHEAD

    with pytest.raises(ValueError, match="over the .* byte ceiling"):
        await backend.publish("dt/twin-a/dtypes/sensor", b"x" * (cap + 1))

    # ... and the backend is still usable afterwards
    await backend.publish("dt/twin-a/dtypes/sensor", "small")


async def test_frame_cap_follows_the_runtime(orbit_backends, loopback):
    """A deployment may tune the cap; the module default would then be
    wrong in either direction."""

    backend = await orbit_backends()
    assert backend.frame_cap() == SMALL_FRAME_CAP

    backend._runtime._frame_cap = 8 * 1024 * 1024
    assert backend.frame_cap() == 8 * 1024 * 1024


# ---------------------------------------------------------------------------
# resilience
# ---------------------------------------------------------------------------

async def test_receive_loop_survives_bad_payloads_and_callbacks(orbit_backends):
    backend = await orbit_backends()
    queue: asyncio.Queue = asyncio.Queue()

    async def raises(message):
        raise ValueError("bad callback")

    async def record(message):
        await queue.put(message)

    topic = "dt/twin-a/dtypes/sensor"
    await backend.subscribe(topic, raises)
    await backend.subscribe(topic, record)

    # a frame with no payload where one belongs
    backend._enqueue(topic, {"nothing": "here"})

    # the raising callback fires on this one, the queue still gets it
    await backend.publish(topic, "good")

    assert await drain(queue) == "good"
    assert not backend._task.done()


async def test_inbox_drops_the_oldest_when_the_loop_falls_behind(orbit_backends):
    """Bounded drop-oldest, like the broker's own subscriber queues -- a
    stalled host loop must cost messages, not memory."""

    backend = await orbit_backends()
    topic = "dt/twin-a/dtypes/sensor"

    for i in range(INBOX_SIZE + 10):
        backend._enqueue(topic, {PAYLOAD_KEY: str(i).encode()})

    assert backend._inbox.qsize() == INBOX_SIZE
    assert backend.dropped == 10

    # the oldest went, the newest stayed
    _, first = backend._inbox.get_nowait()
    assert first[PAYLOAD_KEY] == b"10"


async def test_unexpected_receive_loop_exit_is_reported(orbit_backends):
    backend = await orbit_backends()
    seen: list[BaseException] = []

    backend.on_error = seen.append

    ended = asyncio.create_task(asyncio.sleep(0))
    await ended
    backend._run_done(ended)

    assert len(seen) == 1
    assert isinstance(seen[0], RuntimeError)

    # ... but the loop ending as part of close() is not an error
    await backend.close()
    backend._run_done(ended)
    assert len(seen) == 1


# ---------------------------------------------------------------------------
# connection ownership and teardown
# ---------------------------------------------------------------------------

async def test_close_stops_the_participant_and_leaks_nothing(
    orbit_backends, loopback, no_task_leaks
):
    backend = await orbit_backends()
    runtime = backend._runtime

    await backend.subscribe("dt/twin-a/dtypes/sensor", lambda m: None)
    await backend.close()

    assert runtime.stopped
    assert backend.topics == {}
    assert loopback.subscriptions == []
    assert backend._task is None
    assert backend._inbox is None

    # idempotent, and a closed backend refuses further use
    await backend.close()
    with pytest.raises(RuntimeError):
        await backend.publish("dt/twin-a/dtypes/sensor", "nope")


async def test_an_injected_runtime_is_not_stopped(loopback, no_task_leaks):
    """A shared connection is the caller's to end, not the backend's."""

    runtime = loopback.runtime("shared")
    runtime.start()

    backend = OrbitPubSubBackend(runtime=runtime)
    await backend.connect(timeout=5)

    await backend.subscribe("dt/twin-a/dtypes/sensor", lambda m: None)
    await backend.close()

    assert not runtime.stopped
    # but its subscriptions are gone -- they were the backend's
    assert loopback.subscriptions == []


async def test_a_runtime_which_cannot_register_is_not_left_behind(
    loopback, monkeypatch, no_task_leaks
):
    """An unreachable broker must fail `connect`, not come up half
    connected and deliver nothing -- and must not leak its threads."""

    made = []

    def build(broker_url=None, name=None):
        runtime = loopback.runtime(name, registers=False)
        made.append(runtime)
        return runtime

    monkeypatch.setattr("digitaltwin.streaming_orbit.EndpointRuntime", build)

    backend = OrbitPubSubBackend()

    with pytest.raises(TimeoutError, match="did not register"):
        await backend.connect(timeout=0.1)

    assert made[0].stopped
    assert backend._runtime is None
    assert backend._task is None


@pytest.mark.parametrize("verb", ["publish", "subscribe"])
async def test_a_waiter_parked_before_connect_is_woken_by_close(verb):
    """A caller which arrives before `connect()` parks until the backend
    is running.  If the connect is abandoned instead, that waiter must
    get the ordinary closed-client error -- not wait for a connection
    that will never come.
    """

    backend = OrbitPubSubBackend()
    topic = "dt/twin-a/dtypes/sensor"

    call = {
        "publish": lambda: backend.publish(topic, "parked"),
        "subscribe": lambda: backend.subscribe(topic, lambda m: None),
    }[verb]

    parked = asyncio.create_task(call())
    await asyncio.sleep(0.05)
    assert not parked.done(), "the caller should be waiting for connect"

    await backend.close()

    with pytest.raises(RuntimeError, match="closed"):
        await asyncio.wait_for(parked, 5)


async def test_participant_names_are_unique():
    """Two participants may not register under one name."""

    first = OrbitPubSubBackend()
    second = OrbitPubSubBackend()

    assert first.name != second.name
    assert first.name.startswith(f"{STREAM_PLUGIN}.")

    # ... unless the caller insists
    assert OrbitPubSubBackend(name="fixed").name == "fixed"
