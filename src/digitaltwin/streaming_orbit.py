"""The DT data plane on ORBIT eventing (DTaaS plan M3, risk R7).

A second `PubSubBackend` behind the M0 seam.  Nothing above the seam
changes: `PubSubClient` still hands topics down and gets decoded messages
back, and a persistent component still publishes through
`RuntimeAPI.stream`.  What changes is where the bytes travel.

Why this exists
---------------
The ZMQ backend's payloads are cloudpickled and its XSUB/XPUB ports carry
no authentication: anyone who can reach them executes code in every
subscriber.  This backend moves exactly the same payloads inside ORBIT's
token-authenticated WebSocket star, so the data plane is no weaker than
the control plane and the deployment opens no DT-owned ports at all.
The payloads are *still* cloudpickle -- the win is the trust boundary
around them, which is the same one that already accepts client-shipped
component classes (plan risk R4).

How it maps
-----------
- **Publish** is `EndpointRuntime.send_notification(plugin, topic,
  data)`: a plain sync, non-blocking call that emits one `event` frame.
  The DT topic (`dt/<namespace>/dtypes/<label>`) becomes the ORBIT
  `topic` verbatim; `plugin` is the fixed `dt_stream` namespace, which
  keeps DT traffic out of every other subscriber's match set.  The
  cloudpickled message rides as `bytes` in the event's `data` dict.
- **Subscribe** is `EndpointRuntime.register_callback(plugin_name=...,
  topic=...)`, one registration per DT topic.  ORBIT matches topics by
  exact equality (there are no wildcards), which is exactly what DT
  needs: the broker then filters on the wire and only matching frames
  cross the socket.
- **Connection ownership**: one `EndpointRuntime` per backend instance,
  i.e. one per twin, created in `connect()` and stopped in `close()` --
  the same pattern (and the same loopback wrinkle: the service connects
  to the broker that hosts it) as rhapsody's `OrbitExecutionBackend`.  A
  runtime can also be injected, in which case the backend uses it and
  does not own its lifetime.

Semantics
---------
At-most-once with bounded queues at every hop, which is the DT conflation
contract -- so nothing above adds a second one.  There are *three* such
queues on the path, and only two of them drop the oldest:

1. the broker's per-subscriber out-queue (drop-oldest),
2. the receiving runtime's `CallbackDispatcher` (drop-*newest*: a full
   queue refuses the arriving frame).  It is ORBIT's, not ours, and its
   losses are counted in `runtime._cb.dropped` -- logged here at close
   when nonzero, because otherwise they would only ever be a warning in
   somebody else's log,
3. the inbox this module puts between that dispatcher thread and the
   host loop (drop-oldest).

Losses are observable as gaps in the broker-assigned `seq`; the `replay`
plugin would give late joiners history and is deliberately not integrated
in v1.
"""

import asyncio
import contextlib
import logging
import uuid

from typing import Callable, Optional

import cloudpickle

from radical.orbit import EndpointRuntime  # type: ignore
from radical.orbit.protocol import FRAME_CAP  # type: ignore

from .streaming import CLIENT_CONNECT_TIMEOUT, PubSubBackend

logger = logging.getLogger(__name__)

# the ORBIT `plugin` field of every DT stream event: one namespace for
# the whole data plane.  It is a free string on the wire -- a bare
# participant does not have to host a plugin of that name to use it.
STREAM_PLUGIN = "dt_stream"

# the cloudpickled message rides under this key of the event data dict
PAYLOAD_KEY = "p"

# headroom for the msgpack envelope (topic, ids, participant name) on top
# of the payload.  Generous: the check exists to produce a clear error,
# not to squeeze the last kilobyte out of a frame.
FRAME_OVERHEAD = 64 * 1024

# bounded handoff from the runtime's callback thread to the host loop.
# Drop-oldest, matching the broker's own per-subscriber queues.
INBOX_SIZE = 1024


class OrbitPubSubBackend(PubSubBackend):
    """A `PubSubBackend` over ORBIT eventing.

    Args:
        broker_url: the ORBIT broker; `None` uses ORBIT's own resolution
            (`RADICAL_ORBIT_BROKER_URL`, then `~/.radical/orbit`), as does
            the token.
        runtime: an already-started `EndpointRuntime` to ride on.  The
            backend then does *not* own it and will not stop it.
        name: the participant name; defaults to a unique one, because two
            participants may not register under the same name.
    """

    label = "orbit"

    # names this backend in a PubSubConfig (see PubSubBackend.kind)
    kind = "orbit"

    def __init__(
        self,
        broker_url: Optional[str] = None,
        runtime: Optional[EndpointRuntime] = None,
        name: Optional[str] = None,
    ):
        super().__init__()

        self.broker_url = broker_url
        self.name = name or f"{STREAM_PLUGIN}.{uuid.uuid4().hex[:8]}"

        self._runtime = runtime
        # an injected runtime is somebody else's to stop
        self._owns_runtime = runtime is None

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._inbox: Optional[asyncio.Queue] = None
        self.dropped = 0

    # -- lifecycle ----------------------------------------------------------

    async def connect(self, timeout: Optional[float] = CLIENT_CONNECT_TIMEOUT):
        """Bring the participant connection up, bounded by `timeout`.

        A runtime which cannot reach its broker must fail here -- the
        service turns that into a failed twin.  It must not come up half
        connected and deliver nothing.
        """

        self._check_open()

        self._loop = asyncio.get_running_loop()
        self._inbox = asyncio.Queue(INBOX_SIZE)

        try:
            if self._owns_runtime:
                # start() is blocking and joins threads: off the loop
                self._runtime = await asyncio.to_thread(self._start_runtime, timeout)

        except BaseException:
            await self.close()
            raise

        self._start_receiving()
        self.is_running.set()

    def _start_runtime(self, timeout: Optional[float]) -> EndpointRuntime:
        """Build and register the participant.  Runs in a worker thread."""

        logger.info("connecting stream participant %s", self.name)

        # role: the default 'consumer' says nothing in a topology view.
        # This participant is a twin's data plane.
        runtime = EndpointRuntime(broker_url=self.broker_url, name=self.name,
                                  role="stream")

        try:
            runtime.start(wait=True, timeout=timeout)

            # start() returns *silently* when it merely timed out, so the
            # registration has to be checked explicitly -- otherwise an
            # unreachable broker would surface much later, as a stream
            # that never delivers
            if not runtime.wait_registered(timeout=0):
                raise TimeoutError(
                    f"ORBIT broker at {runtime.broker_url} did not register"
                    f" {self.name} within {timeout}s"
                )

        except BaseException:
            # the runtime's threads and its socket are live from start();
            # a caller that never reaches close() would keep them alive
            runtime.stop()
            raise

        return runtime

    async def close(self):
        """Cancel the receive loop, drop every subscription, stop the
        participant.  Idempotent."""

        if self._closed:
            return
        self._closed = True

        try:
            await self._cancel_receiving()

        finally:
            # the guard above makes close() a one-shot, so the connection
            # has to go even if the await was cancelled
            runtime, self._runtime = self._runtime, None

            try:
                for topic in list(self.topics):
                    self._unregister(runtime, topic)
                self.topics.clear()

                self._report_losses(runtime)

                if runtime is not None and self._owns_runtime:
                    # blocking: closes the socket and joins three threads
                    await asyncio.to_thread(runtime.stop)

            finally:
                self._stop_running()
                self._inbox = None
                self._loop = None

    def _report_losses(self, runtime: Optional[EndpointRuntime]) -> None:
        """Account for both queues that dropped on the way in.

        The dispatcher's counter is ORBIT's and drops the *newest* frame;
        ours is the inbox and drops the oldest.  Neither is an error --
        the data plane is specified to conflate -- but a twin that lost
        samples should not have to be inferred from `seq` gaps.
        """

        cb_dropped = getattr(getattr(runtime, "_cb", None), "dropped", 0) or 0

        if self.dropped or cb_dropped:
            logger.warning(
                "%s dropped %d message(s) at the inbox and %d at the ORBIT"
                " callback queue", self.name, self.dropped, cb_dropped,
            )

    # -- pubsub -------------------------------------------------------------

    async def publish(self, topic, message, raw=False, **backend_params):
        """Emit one event frame carrying the message.

        `raw` means the payload is already bytes whose format something
        above the seam owns (an external channel and its codec): it goes
        on the wire untouched.  Twin-internal traffic is cloudpickled
        here.

        Oversized payloads raise: ORBIT drops a frame over the cap with a
        log line and no exception, and a data plane that silently swallows
        every large sample is worse than one that refuses it.
        """

        self._check_open()
        await self._await_running("publish")

        payload = bytes(message) if raw else cloudpickle.dumps(message)
        cap = self.payload_cap()

        if len(payload) > cap:
            raise ValueError(
                f"stream payload for {topic!r} is {len(payload)} bytes, over"
                f" the {cap} byte ceiling (ORBIT's {self.frame_cap()} byte"
                f" frame cap, less envelope overhead)"
            )

        self._runtime.send_notification(STREAM_PLUGIN, topic,
                                        {PAYLOAD_KEY: payload})

    async def subscribe(self, topic, callback: Callable, raw=False, **backend_params):
        """Register `callback` for `topic`, subscribing on first use.

        With `raw`, the topic's payloads reach their subscribers as the
        bytes that arrived: an external channel decodes them itself.
        """

        self._check_open()
        await self._await_running("subscribe")

        if raw:
            self.raw_topics.add(topic)

        callbacks = self.topics.setdefault(topic, [])
        callbacks.append(callback)

        # one ORBIT registration per topic, however many local subscribers
        # it feeds -- a second one would deliver every frame twice
        if len(callbacks) == 1:
            self._runtime.register_callback(
                plugin_name=STREAM_PLUGIN, topic=topic, callback=self._on_event
            )

    def unsubscribe(self, topic):
        if self._closed:
            return

        if self.topics.pop(topic, None) is not None:
            self._unregister(self._runtime, topic)

    def _unregister(self, runtime: Optional[EndpointRuntime], topic: str):
        if runtime is None:
            return

        runtime.unregister_callback(
            plugin_name=STREAM_PLUGIN, topic=topic, callback=self._on_event
        )

    # -- frame cap ----------------------------------------------------------

    def frame_cap(self) -> int:
        """The effective ORBIT frame cap of this participant.

        Read off the runtime when there is one: a deployment may tune it,
        and the module default would then be wrong in either direction.

        `_frame_cap` is private, and reaching into it is the wart here --
        `EndpointRuntime` should expose it (upstream follow-up).  Until it
        does, the `getattr` fallback keeps this correct against a runtime
        that does not have the attribute at all.
        """

        cap = getattr(self._runtime, "_frame_cap", None)

        return cap if isinstance(cap, int) and cap > 0 else FRAME_CAP

    def payload_cap(self) -> int:
        """The largest cloudpickled message that fits in one frame."""

        return self.frame_cap() - FRAME_OVERHEAD

    # -- receiving ----------------------------------------------------------

    def _on_event(self, endpoint, plugin, topic, data):
        """ORBIT event callback.  Runs on the runtime's callback thread.

        That thread is shared by every callback of this runtime and its
        queue is bounded, so this returns immediately: the frame is handed
        to the host loop and decoded there.
        """

        loop = self._loop

        if loop is None or loop.is_closed():
            return

        try:
            loop.call_soon_threadsafe(self._enqueue, topic, data)
        except RuntimeError:  # the loop closed under us
            pass

    def _enqueue(self, topic, data):
        """Queue one frame for the receive loop.  Runs on the host loop.

        Drop-oldest when the host loop falls behind: the same discipline
        the broker applies to its own per-subscriber queues, and the
        conflation semantics the DT data plane is specified with.
        """

        inbox = self._inbox
        if inbox is None:
            return

        if inbox.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                inbox.get_nowait()

            self.dropped += 1
            if self.dropped % INBOX_SIZE == 1:
                logger.warning(
                    "stream inbox of %s is full: %d message(s) dropped",
                    self.name, self.dropped,
                )

        inbox.put_nowait((topic, data))

    async def _run(self):
        """Receive loop.  A single bad payload or a raising callback must
        not take the stream down -- it is dropped and logged."""

        while True:
            topic, data = await self._inbox.get()

            try:
                payload = data[PAYLOAD_KEY]
                message = (
                    payload
                    if topic in self.raw_topics
                    else cloudpickle.loads(payload)
                )
            except Exception:
                logger.exception("dropping malformed message on topic %r", topic)
                continue

            await self._dispatch(topic, message)
