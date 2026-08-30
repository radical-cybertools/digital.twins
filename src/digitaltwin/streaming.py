# src/digitaltwin/streaming.py
"""Streaming facilities for the digital-twin runtime.

The digital twin framework itself has an abstract :class:`PubSubClient` that
translates DT terms into basic topics that a PubSubBackend can use.

The PubSubBackend is the actual implementation of a PubSub transport. This
distinction places the PubSubBackend outside of the DT architecture
intentionally.

Typical usage is::

    backend = ZMQ_PS_Client("tcp://127.0.0.1:5000", "tcp://127.0.0.1:5001")
    await backend.connect()
    ps = PubSubClient(backend)
    await ps.subscribe_to_dtype(DataType("hello"), queue)
    await ps.publish(DataType("hello"), "world")

The client accepts an arbitrary backend; the default is the abstract
:class:`PubSubBackend`.
"""

from __future__ import annotations

import asyncio
import contextlib

import json
import logging
import multiprocessing
import uuid

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional

import cloudpickle
import zmq
import zmq.asyncio

from zmq.utils.monitor import recv_monitor_message

from .components import DataType, TypedData
from .config import (
    BACKEND_ORBIT,
    RANDOM_PUB_ADDR,
    RANDOM_SUB_ADDR,
    stream_addresses,
    stream_backend,
)

logger = logging.getLogger(__name__)

# Payload codecs for external channels.  A channel is shared with
# producers which are not part of this framework, so what goes on the wire
# is a deployment decision, not ours: plain instruments and scripts speak
# `json`, `raw` hands bytes through untouched, and `cloudpickle` is only
# for producers inside the same trust domain (it executes what it decodes,
# see the binding policy in the README).
CODEC_JSON = "json"
CODEC_RAW = "raw"
CODEC_CLOUDPICKLE = "cloudpickle"

_CODECS: dict[str, tuple[Callable, Callable]] = {
    CODEC_JSON: (
        lambda message: json.dumps(message).encode("utf-8"),
        lambda payload: json.loads(payload.decode("utf-8")),
    ),
    CODEC_RAW: (bytes, lambda payload: payload),
    CODEC_CLOUDPICKLE: (cloudpickle.dumps, cloudpickle.loads),
}


def check_codec(codec: str):
    """Reject an unknown codec name, at registration rather than on the
    first message."""

    if codec not in _CODECS:
        raise ValueError(
            f"unknown stream codec: {codec!r}" f" (known: {', '.join(sorted(_CODECS))})"
        )


def encode_payload(message, codec: str) -> bytes:
    check_codec(codec)

    return _CODECS[codec][0](message)


def decode_payload(payload: bytes, codec: str):
    check_codec(codec)

    return _CODECS[codec][1](payload)


# bounded waits: no teardown path may hang the host event loop
BROKER_START_TIMEOUT = 30.0
BROKER_STOP_TIMEOUT = 5.0

# bounded connect: a client which cannot reach the broker must fail, not
# wait forever (the service turns that failure into a twin state)
CLIENT_CONNECT_TIMEOUT = 30.0


class PubSubBackend(ABC):
    """The transport seam: everything above this is transport-agnostic.

    A backend delivers to per-topic subscriber callbacks from a single
    receive loop it owns.  That loop, the subscriber registry and the
    closed/running state are the same in every backend, so they live
    here; a subclass supplies `connect`, `publish`, `subscribe`,
    `unsubscribe`, `close` and a `_run()` body.
    """

    label = "generic"

    # names this backend in a PubSubConfig: what has to reopen the
    # endpoint.  Every backend declares its own.
    kind = "generic"

    # the addresses another process would connect to.  Part of the backend
    # interface because a PubSubConfig is built from them.
    pub_addr: Optional[str] = None
    sub_addr: Optional[str] = None

    def __init__(self):
        # asynchronous failures (a dead receive loop above all) are reported
        # here -- see PubSubClient.on_error.  A silently stalled stream is
        # the failure mode this exists to prevent.
        self.on_error: Optional[Callable[[BaseException], None]] = None

        # topic -> subscriber callbacks.  Delivery is filtered by exact
        # topic lookup, whatever the transport matched on the wire.
        self.topics: dict[str, list[Callable]] = {}

        # topics whose payload the transport hands over untouched:
        # something above the seam owns their wire format (see the codecs)
        self.raw_topics: set[str] = set()

        self._task: Optional[asyncio.Task] = None
        self._closed = False
        self.is_running = asyncio.Event()

    def _report_error(self, exc: BaseException):
        logger.error("stream backend failed: %s", exc, exc_info=exc)

        if self.on_error is not None:
            self.on_error(exc)

    def _check_open(self):
        if self._closed:
            raise RuntimeError("stream client is closed")

    async def _await_running(self, what: str):
        """Callers which arrive before `connect()` finished are made to
        wait rather than to lose their message.

        The re-check afterwards matters: a client closed while somebody
        was waiting here must produce the ordinary closed-client error,
        not an attribute error somewhere in a half-dismantled backend.
        """

        if not self.is_running.is_set():
            logger.warning("requesting %s before connecting to broker. Waiting",
                           what)
            await self.is_running.wait()
            self._check_open()

    def _stop_running(self):
        """Mark the backend disconnected, waking anyone parked in
        `_await_running` on the way.

        A waiter is otherwise stranded: it parked on a connect that has
        now been abandoned, and a plain `clear()` would leave it waiting
        for one that will never arrive.  `set()` resolves the waiters'
        futures immediately and the `clear()` right after does not
        un-resolve them, so they wake into `_check_open` and get the
        ordinary closed-client error.
        """

        self.is_running.set()
        self.is_running.clear()

    def _start_receiving(self):
        """Arm the supervised receive loop.  Called at the end of connect."""

        self._task = asyncio.create_task(self._run())
        self._task.add_done_callback(self._run_done)

    async def _dispatch(self, topic: str, message):
        """Hand one decoded message to the topic's subscribers.

        One failing subscriber must not starve its siblings
        (`CancelledError` is not an `Exception`: close() still wins).
        """

        for task in self.topics.get(topic, []):
            try:
                await task(message)
            except Exception:
                logger.exception("subscriber failed on topic %r", topic)

    async def _cancel_receiving(self):
        """Cancel and await the receive loop.  Part of every close()."""

        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _run_done(self, task: asyncio.Task):
        """The receive loop only ends on close().  Any other exit means the
        twin stopped receiving -- report it instead of stalling silently."""

        if self._closed or task.cancelled():
            return

        exc = task.exception() or RuntimeError("stream receive loop exited")
        self._report_error(exc)

    async def _run(self):
        """Receive loop: decode frames and `_dispatch` them.  Runs until
        cancelled by close()."""

        raise NotImplementedError

    @abstractmethod
    async def connect(self, *args: Any, **kwargs: Any) -> None:
        """Connect the backend to the message broker.

        Args:
            *args (Any): Positional arguments specific to the backend.
            **kwargs (Any): Keyword arguments specific to the backend.
        """

    @abstractmethod
    async def publish(self, topic, message, raw=False, **kwargs):
        """Publish `message` on `topic`.

        `raw` means the payload is already bytes and something above the
        seam owns its wire format: hand it over untouched.  Channels use
        that (see the codecs); twin-internal traffic does not, and the
        backend serializes it however it likes.
        """

    @abstractmethod
    async def subscribe(self, topic, callback, raw=False, **kwargs):
        """Deliver messages published on `topic` to `callback`.

        With `raw`, the callback receives the payload bytes as they
        arrived, undecoded.
        """

    @abstractmethod
    def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from *topic*."""
        pass

    @abstractmethod
    async def close(self):
        """Release all resources.  Idempotent."""
        pass

    def __str__(self):
        return f"{self.kind}"


# ---------------------------------------------------------------------------
# ZMQ broker and client
# ---------------------------------------------------------------------------
class ZMQ_Broker:
    """XSUB/XPUB proxy.  `run()` blocks -- it is meant to own its process.

    Addresses default to a random port on loopback (see `config`); the
    actually bound addresses are available from `get_connection_str()`
    once `bind()` ran.
    """

    def __init__(
        self, publish_addr: Optional[str] = None, subscribe_addr: Optional[str] = None
    ):
        self.publish_addr = publish_addr or RANDOM_PUB_ADDR
        self.subscribe_addr = subscribe_addr or RANDOM_SUB_ADDR

        self.ctx: Optional[zmq.Context] = None
        self.pub_recv: Optional[zmq.Socket] = None
        self.sub_send: Optional[zmq.Socket] = None

    def bind(self) -> tuple[str, str]:
        """Create the sockets and bind them.  Returns the bound addresses.

        Must run in the process that will run the proxy -- a ZMQ context
        does not survive a fork/spawn.

        Raises:
            zmq.ZMQError
                If binding to the provided addresses fails.
        """

        self.ctx = zmq.Context()
        self.pub_recv = self.ctx.socket(zmq.XSUB)
        self.sub_send = self.ctx.socket(zmq.XPUB)

        self.pub_recv.bind(self.publish_addr)
        self.sub_send.bind(self.subscribe_addr)

        # resolve wildcard ports to what the OS actually handed out
        self.publish_addr = self.pub_recv.getsockopt_string(zmq.LAST_ENDPOINT)
        self.subscribe_addr = self.sub_send.getsockopt_string(zmq.LAST_ENDPOINT)

        return self.get_connection_str()

    def run(self):
        if self.ctx is None:
            self.bind()

        try:
            zmq.proxy(self.pub_recv, self.sub_send)
        except zmq.ContextTerminated:
            pass
        finally:
            self.pub_recv.close(linger=0)
            self.sub_send.close(linger=0)
            self.ctx.term()

    def get_connection_str(self) -> tuple[str, str]:
        return self.publish_addr, self.subscribe_addr


def _broker_main(publish_addr, subscribe_addr, conn):
    """Entry point of the broker subprocess (must be importable for spawn)."""

    broker = ZMQ_Broker(publish_addr, subscribe_addr)
    conn.send(broker.bind())
    conn.close()
    broker.run()


class ZMQ_BrokerProcess:
    """A `ZMQ_Broker` embedded as a spawn-context subprocess.

    The subprocess boundary is the stop path: `zmq.proxy()` has none of
    its own.  The child binds (random port by default), reports the bound
    addresses back to the parent, and is stopped by terminate/join.
    """

    def __init__(
        self, publish_addr: Optional[str] = None, subscribe_addr: Optional[str] = None
    ):
        self._addrs = (
            publish_addr or RANDOM_PUB_ADDR,
            subscribe_addr or RANDOM_SUB_ADDR,
        )
        self._proc: Optional[multiprocessing.process.BaseProcess] = None

        # serializes start/stop: concurrent starts must not spawn two
        # brokers, and must not observe a half-started one
        self._lock = asyncio.Lock()

        self.publish_addr: Optional[str] = None
        self.subscribe_addr: Optional[str] = None

    async def start(self, timeout: float = BROKER_START_TIMEOUT) -> tuple[str, str]:
        """Spawn the broker and return its bound (publish, subscribe) pair."""

        async with self._lock:
            if self._proc is not None:
                return self.get_connection_str()

            # spawn + pipe read are blocking: keep them off the event loop
            addrs = await asyncio.to_thread(self._start, timeout)
            self.publish_addr, self.subscribe_addr = addrs
            logger.info("stream broker at %s / %s", *addrs)

            return addrs

    async def stop(self, timeout: float = BROKER_STOP_TIMEOUT):
        """Terminate the broker subprocess.  Idempotent."""

        async with self._lock:
            if self._proc is None:
                return

            await asyncio.to_thread(self._stop, timeout)
            self.publish_addr = self.subscribe_addr = None

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    def get_connection_str(self) -> tuple[str, str]:
        return self.publish_addr, self.subscribe_addr

    def _start(self, timeout):
        ctx = multiprocessing.get_context("spawn")
        recv_conn, send_conn = ctx.Pipe(duplex=False)

        self._proc = ctx.Process(
            target=_broker_main, args=(*self._addrs, send_conn), daemon=True
        )
        try:
            self._proc.start()
            send_conn.close()  # only the child keeps the write end

            if not recv_conn.poll(timeout):
                raise TimeoutError(f"stream broker did not bind within {timeout}s")

            return recv_conn.recv()

        except BaseException:
            self._stop(BROKER_STOP_TIMEOUT)
            raise

        finally:
            recv_conn.close()

    def _stop(self, timeout):
        proc, self._proc = self._proc, None

        if proc.pid is not None:  # None if start() itself failed
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout)

            if proc.is_alive():
                logger.warning("stream broker ignored terminate -- killing")
                proc.kill()
                proc.join(timeout)

        proc.close()


class ZMQ_PS_Client(PubSubBackend):
    """Pub/Sub client that talks to a ZMQ broker.

    The client manages a pair of asynchronous sockets (PUB/SUB) and
    keeps a mapping from topics to user callbacks.
    """

    label: str = "local"

    # names this backend in a PubSubConfig (see `PubSubBackend.kind`).  Without
    # it the class inherits "generic", and every config which travels to
    # another process names a backend nothing can reopen.
    kind = "zmq"

    def __init__(
        self, pub_addr: Optional[str] = None, sub_addr: Optional[str] = None
    ) -> None:
        super().__init__()
        self.pub_addr = pub_addr
        self.sub_addr = sub_addr

        self._ctx = zmq.asyncio.Context()
        self.pub_soc: Optional[zmq.asyncio.Socket] = (
            self._ctx.socket(zmq.PUB) if pub_addr is not None else None
        )
        self.sub_soc: Optional[zmq.asyncio.Socket] = (
            self._ctx.socket(zmq.SUB) if sub_addr is not None else None
        )


    async def _connect_socket(self, sock, addr):
        """Connect `sock` and wait until the connection is established.

        The monitor is attached *before* connecting: it only reports events
        which happen after it was attached.
        """

        monitor = sock.get_monitor_socket()
        try:
            sock.connect(addr)
            while True:
                event = await recv_monitor_message(monitor)
                if event["event"] == zmq.EVENT_CONNECTED:
                    return
        finally:
            # also runs on cancellation.  disable_monitor() only detaches
            # the socket -- leaving it open would block ctx.term()
            sock.disable_monitor()
            monitor.close(linger=0)

    async def connect(self, timeout: Optional[float] = CLIENT_CONNECT_TIMEOUT):
        """Connect the sockets, bounded by `timeout` (None waits forever).

        On timeout the half-connected client is closed before the error
        propagates -- an unreachable broker must not leak sockets, and it
        must not park a caller (the service turns the error into a failed
        twin instead).
        """

        self._check_open()

        try:
            async with asyncio.timeout(timeout):
                if self.sub_soc is not None:
                    logger.info("Waiting to connect to ZMQ broker...")
                    await self._connect_socket(self.sub_soc, self.sub_addr)

                if self.pub_soc is not None:
                    await self._connect_socket(self.pub_soc, self.pub_addr)

        except TimeoutError:
            addrs = f"{self.sub_addr} / {self.pub_addr}"
            await self.close()
            raise TimeoutError(
                f"stream broker at {addrs} did not accept a connection"
                f" within {timeout}s"
            ) from None

        except BaseException:
            await self.close()
            raise

        if self.sub_soc is not None:
            self._start_receiving()

        self.is_running.set()

    async def publish(self, topic, message, raw=False):
        """Publish *message* under *topic*.

        The method waits for the socket to be in a running state if the
        connection has not yet finished.
        """
        self._check_open()
        if self.pub_soc is None:
            raise ValueError("Publishing endpoint not connected")

        await self._await_running("publish")

        topic_b = topic.encode("utf-8")
        message_b = message if raw else cloudpickle.dumps(message)
        await self.pub_soc.send_multipart([topic_b, message_b])

    async def subscribe(self, topic, callback, raw=False, **backend_params):
        """Subscribe *callback* to *topic*.

        If *topic* is new a subscription is created, otherwise the
        callback is appended to the existing topic list.
        """
        self._check_open()
        if self.sub_soc is None:
            raise ValueError("Subscribe endpoint not connected")

        await self._await_running("subscribe")

        self.sub_soc.setsockopt(zmq.SUBSCRIBE, topic.encode("utf-8"))

        self.topics.setdefault(topic, []).append(callback)
        if raw:
            self.raw_topics.add(topic)

    def unsubscribe(self, topic):
        if self._closed or self.sub_soc is None:
            return

        if topic in self.topics:
            self.sub_soc.setsockopt(zmq.UNSUBSCRIBE, topic.encode("utf-8"))
            del self.topics[topic]
            self.raw_topics.discard(topic)

    async def close(self):
        """Cancel the receive loop, close all sockets, terminate the context.

        Idempotent.
        """

        if self._closed:
            return
        self._closed = True

        try:
            await self._cancel_receiving()
        finally:
            # the guard above makes close() a one-shot, so the sockets and
            # the context have to go even if the await was cancelled
            self.topics.clear()
            self.raw_topics.clear()

            for sock in (self.pub_soc, self.sub_soc):
                if sock is not None:
                    sock.close(linger=0)
            self.pub_soc = self.sub_soc = None

            # all sockets are closed, so this returns immediately
            self._ctx.term()
            self._stop_running()

    async def _run(self):
        """Receive loop.  A single bad payload or a raising callback must
        not take the stream down -- it is dropped and logged."""

        while True:
            frames = await self.sub_soc.recv_multipart()

            try:
                topic, message = frames
                item = topic.decode("utf-8")
                data = (
                    message if item in self.raw_topics else cloudpickle.loads(message)
                )
            except Exception:
                logger.exception("dropping malformed message: %r", frames[:1])
                continue

            await self._dispatch(item, data)


# The pubsub client abstracts away the specifics of the pub / sub
# implementation. It rather adds the DataType wrapper / connects with the
# runtime


class PubSubClient:
    """Namespaced, dtype-aware view on a pubsub backend.

    Topics are `dt/<namespace>/dtypes/<dtype label>`.  The namespace keeps
    twins that use identical dtype labels apart on a shared broker, so one
    client per twin is required (also because `subscribe_to_dtype` holds
    one queue per dtype).
    """

    # ZMQ SUBSCRIBE is prefix matching: the terminator keeps a label from
    # matching every label it is a prefix of.  Hygiene, not correctness --
    # delivery is filtered by exact topic lookup.  A control character is
    # used because a dtype label may contain any printable character.
    TOPIC_TERMINATOR = "\x00"

    # twin-internal traffic lives under this prefix; external channels are
    # deliberately outside it, and may not claim it
    TOPIC_PREFIX = "dt/"

    # For now, only support one backend. Future TODO: Add support for multiple backends

    def __init__(self, backend: PubSubBackend, namespace: str):
        # a namespace carrying a separator would let two twins alias each
        # other's topics -- the one thing the namespace exists to prevent
        if not namespace or "/" in namespace or self.TOPIC_TERMINATOR in namespace:
            raise ValueError(f"invalid stream namespace: {namespace!r}")

        self._backend = backend
        self.namespace = namespace

        # so I don't repeat
        self.subscriptions: set[DataType] = set()

        # external channels bound to a dtype: (channel, dtype)
        self.channels: set[tuple[str, DataType]] = set()

    @property
    def on_error(self) -> Optional[Callable[[BaseException], None]]:
        """Hook for asynchronous stream failures (see `PubSubBackend`)."""

        return self._backend.on_error

    @on_error.setter
    def on_error(self, callback: Optional[Callable[[BaseException], None]]):
        self._backend.on_error = callback

    @property
    def config(self) -> "PubSubConfig":
        """This client's endpoint as plain, shippable data."""

        return PubSubConfig(
            namespace=self.namespace,
            pub_addr=self._backend.pub_addr,
            sub_addr=self._backend.sub_addr,
            kind=self._backend.kind,
            broker_url=getattr(self._backend, "broker_url", None),
        )

    def topic(self, dtype: DataType) -> str:
        """Topic carrying this twin's internal traffic for `dtype`."""

        return (
            f"{self.TOPIC_PREFIX}{self.namespace}/dtypes/{dtype.name}"
            f"{self.TOPIC_TERMINATOR}"
        )

    @classmethod
    def check_channel(cls, channel: str):
        """Reject a channel name which is not usable as an external topic.

        A channel goes on the wire verbatim, which is what makes it
        shareable.  It may therefore not claim the prefix under which twins
        publish their internal traffic, and it may not carry the topic
        terminator.
        """

        if not channel:
            raise ValueError("a channel name is required")

        if channel.startswith(cls.TOPIC_PREFIX):
            raise ValueError(
                f"channel {channel!r} collides with twin-internal topics"
                f" ({cls.TOPIC_PREFIX}...): pick a name outside that prefix"
            )

        if cls.TOPIC_TERMINATOR in channel:
            raise ValueError(f"channel {channel!r} contains a topic terminator")

    async def subscribe_to_channel(
        self,
        channel: str,
        dtype: DataType,
        queue: asyncio.Queue,
        codec: str = CODEC_JSON,
        backend_params=None,
    ):
        """Feed an external channel into `dtype`.

        The topic is used verbatim, without this twin's namespace: the
        channel is shared, so every twin which binds it receives every
        message on it, and the producers are outside the framework
        entirely.  Payloads are decoded per `codec`; an undecodable one is
        dropped and logged rather than taking the stream down with it.
        """

        if backend_params is None:
            backend_params = {}

        self.check_channel(channel)
        check_codec(codec)

        if (channel, dtype) in self.channels:
            return
        self.channels.add((channel, dtype))

        async def receive_data(payload):
            try:
                message = decode_payload(payload, codec)
            except Exception:
                logger.exception(
                    "dropping undecodable %s payload on channel %r", codec, channel
                )
                return

            await queue.put(TypedData(dtype, message))

        await self._backend.subscribe(
            topic=channel, callback=receive_data, raw=True, **backend_params
        )

    def unsubscribe_channel(self, channel: str, dtype: DataType):
        if (channel, dtype) not in self.channels:
            return
        self.channels.discard((channel, dtype))

        self._backend.unsubscribe(channel)

    # for runtime use only!!!
    async def subscribe_to_dtype(
        self,
        dtype: DataType,
        queue: asyncio.Queue[TypedData],
        backend_params: dict[str, Any] | None = None,
    ) -> None:
        """For runtime use only!!! Subscribe *queue* to all messages of *dtype*.

        The subscription creates a topic like
        ``runtime/dtypes/<dtype_label>`` and pushes received payloads
        wrapped in :class:`TypedData` onto *queue*.
        """
        if dtype in self.subscriptions:
            return

        if backend_params is None:
            backend_params = {}

        self.subscriptions.add(dtype)

        # add message to queue
        async def receive_data(message: Any) -> None:
            td = TypedData(dtype, message)
            await queue.put(td)

        logger.debug(f"SUB: {self.topic(dtype)}")
        await self._backend.subscribe(
            topic=self.topic(dtype), callback=receive_data, **backend_params
        )

    def unsubscribe_dtype(self, dtype: DataType):
        if dtype not in self.subscriptions:
            return
        self.subscriptions.discard(dtype)

        self._backend.unsubscribe(self.topic(dtype))

    async def publish(self, dtype: DataType, message, backend_params=None):
        # Convert dtype to a topic
        if backend_params is None:
            backend_params = {}
        await self._backend.publish(
            topic=self.topic(dtype), message=message, **backend_params
        )

    async def close(self):
        """Drop all subscriptions and close the backend.  Idempotent.

        The client owns its backend: one client per twin, torn down with it.
        """

        for dtype in list(self.subscriptions):
            self.unsubscribe_dtype(dtype)

        for channel, dtype in list(self.channels):
            self.unsubscribe_channel(channel, dtype)

        await self._backend.close()


@dataclass(frozen=True)
class PubSubConfig:
    """A twin's stream endpoint as plain data: what to open, and where.

    A live `PubSubClient` cannot travel -- it owns sockets, a receive loop
    and subscriber queues, all of which are process-local.  Code which
    runs outside the host process (a task in another process, or on
    another host) therefore receives this description instead, ships it
    along as pickle or JSON, and opens its own client with `connect()`.

    Shipping it off-host implies the broker is reachable from there.  For
    the `zmq` backend that means the broker was bound to a non-loopback
    address on a private, firewalled network -- the default loopback bind
    is deliberately not reachable from another host (see the binding
    policy in the README).

    `kind` names the backend which has to open the endpoint; a backend
    declares its own (`PubSubBackend.kind`).  It stays a plain string so a
    further backend needs no change here.

    The address fields belong to the `zmq` kind; `broker_url` to the
    `orbit` kind (`None` uses ORBIT's own resolution, and the auth token
    is deliberately not part of the config -- it is resolved locally).
    """

    namespace: Optional[str] = None
    pub_addr: Optional[str] = None
    sub_addr: Optional[str] = None
    kind: str = ZMQ_PS_Client.kind
    broker_url: Optional[str] = None

    @classmethod
    def resolve(
        cls,
        namespace: Optional[str] = None,
        pub_addr: Optional[str] = None,
        sub_addr: Optional[str] = None,
    ) -> "PubSubConfig":
        """Describe the configured broker: explicit addresses, else the
        environment, else the loopback defaults (see `config`)."""

        return cls(namespace, *stream_addresses(pub_addr, sub_addr))

    async def connect_backend(self, timeout: Optional[float] = None) -> PubSubBackend:
        """Open the transport alone, without namespace semantics.

        What an external producer needs (see `ChannelPublisher`): a channel
        is shared, so it belongs to no twin's namespace.

        Bounded by `timeout` (None waits forever).  A backend which fails
        to connect is closed before the error propagates, so an unreachable
        broker leaks neither sockets nor a context.
        """

        if self.kind == BACKEND_ORBIT:
            # imported here: `radical.orbit` is the optional 'service'
            # extra, and a plain ZMQ install must not need it
            from .streaming_orbit import OrbitPubSubBackend

            # named after the twin it serves, so a topology view can match
            # the participant to a dashboard card.  A short random suffix
            # keeps two clients on one namespace apart (the twin's own,
            # plus any consumer which opened the twin's config).
            name = None
            if self.namespace:
                name = (f"dt_stream.{self.namespace.split('-')[0]}"
                        f".{uuid.uuid4().hex[:4]}")

            backend = OrbitPubSubBackend(self.broker_url, name=name)

        elif self.kind == ZMQ_PS_Client.kind:
            backend = ZMQ_PS_Client(self.pub_addr, self.sub_addr)

        else:
            raise ValueError(
                f"cannot open a {self.kind!r} stream endpoint here:"
                f" no backend of that kind is available"
            )

        await backend.connect(timeout)

        return backend

    async def connect(self, timeout: Optional[float] = None) -> PubSubClient:
        """Open a connected, namespaced client for this endpoint."""

        if self.namespace is None:
            raise ValueError("backend is None!")

        return PubSubClient(await self.connect_backend(timeout), self.namespace)


class ChannelPublisher:
    """Publishes to a shared channel from outside the framework.

    Sensors and instruments are external entities: they are not twin
    components, they outlive and precede any twin, and one channel of
    theirs feeds however many twins bind it.  Such a producer needs a
    broker, a channel name and a codec, and nothing else from this package
    -- no namespace (a channel has none) and no runtime.
    """

    def __init__(self, backend: PubSubBackend, channel: str, codec: str = CODEC_JSON):
        PubSubClient.check_channel(channel)
        check_codec(codec)

        self._backend = backend
        self.channel = channel
        self.codec = codec

    @classmethod
    async def open(
        cls,
        channel: str,
        codec: str = CODEC_JSON,
        config: Optional[PubSubConfig] = None,
        timeout: Optional[float] = CLIENT_CONNECT_TIMEOUT,
    ) -> "ChannelPublisher":
        """Connect to a broker and publish to `channel` on it.

        `config` defaults to the configured broker (environment, else the
        loopback defaults); its namespace, if it has one, is ignored.

        The connect is bounded by `timeout` -- an external producer
        pointed at an unreachable broker should fail fast, not hang.
        """

        config = config or PubSubConfig.resolve()

        return cls(await config.connect_backend(timeout), channel, codec)

    async def publish(self, message):
        """Publish one codec-encoded message on the channel."""

        await self._backend.publish(
            topic=self.channel,
            message=encode_payload(message, self.codec),
            raw=True,
        )

    async def close(self):
        await self._backend.close()


async def connect_stream_client(
    namespace: str,
    pub_addr: Optional[str] = None,
    sub_addr: Optional[str] = None,
    timeout: Optional[float] = CLIENT_CONNECT_TIMEOUT,
    *,
    backend: Optional[str] = None,
    broker_url: Optional[str] = None,
) -> PubSubClient:
    """Build and connect a namespaced stream client from configuration.

    `backend` selects the transport (`zmq` / `orbit`); unset, it comes
    from `DT_STREAM_BACKEND` (see `config.stream_backend`).  The address
    arguments belong to the ZMQ backend and `broker_url` to the ORBIT one
    -- each is ignored by the other, and both default to their own
    resolution.

    The connect is bounded by `timeout` in either case.
    """

    name = stream_backend(backend)

    if name == BACKEND_ORBIT:
        cfg = PubSubConfig(namespace, kind=BACKEND_ORBIT, broker_url=broker_url)
    else:
        cfg = PubSubConfig.resolve(namespace, pub_addr, sub_addr)

    return await cfg.connect(timeout)
