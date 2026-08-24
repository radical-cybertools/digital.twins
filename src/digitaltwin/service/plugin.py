"""The `dt` ORBIT plugin: digital twins as a long-running service.

Hosted on a standalone broker by default (`--plugins default,dt`);
endpoint hosting works the same way.  The plugin owns

- the session policy: sessions are forced `persistent` (twins survive
  disappearing clients, without timeout) and the sid acts as a bearer
  capability, so a reconnecting client reattaches by sid alone;
- the embedded DT stream broker: one supervised subprocess shared by
  every session, respawned on the addresses it reported;
- the wire: one graph verb per `twin_call`, cloudpickle-base64 payloads
  with a version stamp, and `twin_list` as the only observation path.

**Data plane (risk R7)**: `DT_STREAM_BACKEND` picks the transport.

- `orbit` puts the twins' streams inside the same token-authenticated
  WebSocket star as the control plane, and the embedded ZMQ broker is
  then never started -- no DT-owned ports exist at all.  This is what
  closes R7, and it is what a production deployment selects.
- `zmq` (the default) runs the embedded stream broker, and *binds
  loopback*.  Its payloads are cloudpickled, so anyone who can reach its
  ports executes code in every subscriber.  A non-loopback bind needs an
  explicit `DT_STREAM_PUB_ADDR` / `DT_STREAM_SUB_ADDR` configuration
  *and* a firewalled/private network.
"""

import asyncio
import logging
import os
import time

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from radical.orbit.errors import http_exception
from radical.orbit.plugin_base import Plugin
from starlette.requests import Request
from starlette.responses import Response

from ..config import (
    BACKEND_ORBIT,
    BACKEND_ZMQ,
    embedded_stream_addresses,
    stream_backend,
)
from ..streaming import (
    CLIENT_CONNECT_TIMEOUT,
    PubSubClient,
    ZMQ_BrokerProcess,
    connect_stream_client,
)
from .client import DTClient
from .session import VERBS, DTSession

log = logging.getLogger("radical.orbit")

# route templates -- single-sourced between registration and the client
ROUTE_TWIN_CREATE = "twin_create/{sid}"
ROUTE_TWIN_LIST = "twin_list/{sid}"
ROUTE_TWIN_CLOSE = "twin_close/{sid}/{twin_id}"
ROUTE_TWIN_CALL = "twin_call/{sid}/{twin_id}"
ROUTE_ADMIN_SESSIONS = "admin/sessions"
ROUTE_UI = "ui"
ROUTE_UI_ASSET = "ui/{asset}"

# The dashboard.  `dt_explorer.js` is the ORBIT Explorer's UI module (see
# `ui_module`); `index.html` is the standalone host, which the plugin
# serves so that a browser can reach a live broker *same-origin* -- the
# gateway's CORS allow-list and the `SameSite=Strict` auth cookie rule out
# every other origin.  An allow-list, not a directory walk: `{asset}` is a
# client-supplied path segment.
UI_DIR = Path(__file__).parent / "ui"
UI_ASSETS = {
    "index.html": "text/html; charset=utf-8",
    "dt_dash.js": "application/javascript",
    "dt_sample.js": "application/javascript",
    "dt_explorer.js": "application/javascript",
}

# how often the supervisor checks that the stream broker is still alive
BROKER_WATCH_INTERVAL = 5.0

# plugin-level ORBIT broker URL for the engines' OrbitExecutionBackend;
# unset lets ORBIT resolve it (env / ~/.radical/orbit), as does the token
ENV_BROKER_URL = "DT_ORBIT_BROKER_URL"


class PluginDT(Plugin):
    """Digital-twin plugin for ORBIT.

    - POST `/dt/register_session`            -- open (or reattach to) a session
    - POST `/dt/twin_create/{sid}`           -- register a twin, init in background
    - GET  `/dt/twin_list/{sid}`             -- states of all twins in a session
    - POST `/dt/twin_close/{sid}/{twin_id}`  -- stop and forget one twin
    - POST `/dt/twin_call/{sid}/{twin_id}`   -- exactly one graph verb
    - GET  `/dt/admin/sessions`              -- every session, twin and error
    - GET  `/dt/ui`, `/dt/ui/{asset}`        -- the live dashboard

    Every call is short except `get_inference`.  No notifications, no
    request ids: `twin_list` polling is the observation mechanism.
    """

    plugin_name = "dt"
    session_class = DTSession
    client_class = DTClient
    version = "0.1.0"

    ui_config = {
        "icon": "🪞",
        "title": "Digital Twins",
        "description": "Host long-running digital twins (in-situ inference).",
    }

    # The Explorer's per-plugin JS module, served by the gateway at
    # `/plugins/dt.js`.  Honoured for broker-hosted plugins only
    # (`BrokerPluginHost.get_ui_modules` is its single reader), which is
    # this plugin's default deployment; endpoint-hosted, the Explorer falls
    # back on `ui_config` above and the dashboard is reached at
    # `{namespace}/ui` instead.
    ui_module = str(UI_DIR / "dt_explorer.js")

    def __init__(self, app: FastAPI, instance_name: str = "dt"):
        super().__init__(app, instance_name)

        self.broker_url: Optional[str] = os.environ.get(ENV_BROKER_URL) or None

        # which transport carries the twins' streams.  Resolved once, at
        # plugin construction: a deployment decision, not a per-twin one.
        self.stream_backend: str = stream_backend()

        # the embedded DT stream broker, shared plugin-wide and started on
        # first need (see `stream_addresses`).  Never started at all under
        # the 'orbit' backend -- that is the point of it.
        self._stream_broker: Optional[ZMQ_BrokerProcess] = None
        self._stream_addrs: Optional[tuple[str, str]] = None
        self._stream_lock = asyncio.Lock()
        self._supervisor: Optional[asyncio.Task] = None

        self.add_route_post(ROUTE_TWIN_CREATE, self.twin_create)
        self.add_route_get(ROUTE_TWIN_LIST, self.twin_list)
        self.add_route_post(ROUTE_TWIN_CLOSE, self.twin_close)
        self.add_route_post(ROUTE_TWIN_CALL, self.twin_call)
        self.add_route_get(ROUTE_ADMIN_SESSIONS, self.admin_sessions)
        self.add_route_get(ROUTE_UI, self.ui_index)
        self.add_route_get(ROUTE_UI_ASSET, self.ui_asset)

        # the page references its script relative to itself, and a browser
        # at `{namespace}/ui` (no trailing slash) resolves that against the
        # *parent* -- so the assets answer there as well, and both spellings
        # of the page work
        for asset in UI_ASSETS:
            if asset != "index.html":
                self.add_route_get(asset, self._root_asset(asset))

    # -- session policy -----------------------------------------------------

    def _normalize_session_policy(self, data: dict) -> tuple:
        """Force `persistent`.

        Twins run for days and clients attach opportunistically; a session
        that expires under an absent client would take its twins with it.
        Teardown is explicit only (`unregister_session`).
        """

        forced = dict(data or {})
        forced["lifetime"] = "persistent"
        forced.pop("ttl", None)

        return super()._normalize_session_policy(forced)

    def _check_owner(self, sid: str, owner: Optional[str]) -> None:
        """The sid is a bearer capability: any holder may reattach.

        A client that reconnects comes back as a *different* participant,
        so the owner check would lock it out of its own twins.  This is
        acceptable inside ORBIT's single-token trust domain, and the
        recorded owner stays visible in `admin/sessions`.
        """

    async def register_session(self, request: Request) -> dict:
        """Open or reattach to a session.

        Body (all optional): `{"sid": str, "config": {...}}`.  `config`
        carries the engine configuration and applies at create time only:

            {"engines": {"inference": {"endpoint_name": "ep1",
                                    "backends": ["concurrent"]},
                         "learning":  {"endpoint_name": "hpc1",
                                    "backends": ["concurrent"]}}}

        `'learning'` is optional: unconfigured, it aliases `'inference'`.

        A role may name a dispatcher-managed pool instead of an endpoint
        (`{"pool": "exsitu"}`), with the pool configs declared once at the
        session level (`"pools": [<PoolConfig>, ...]` -- the task
        dispatcher's own schema).  Pool-backed roles run on the pool's
        pilots, survive single-endpoint loss (tasks requeue; keep them
        idempotent), and share one dispatcher session per DT session.
        """

        self._ensure_cleanup_task()

        data = await _body(request)
        config = data.get("config")
        if config is not None and not isinstance(config, dict):
            raise http_exception(ValueError("'config' must be an object"))

        owner = self._request_owner(request)
        sid, lifetime, ttl = self._normalize_session_policy(data)

        if sid is not None and sid in self._sessions:
            self._check_owner(sid, owner)
            self._check_policy_conflict(sid, lifetime, ttl)
            self._touch(sid)
            log.info("[dt] reattached session %s", sid)
            return {"sid": sid, "reattached": True}

        sid = await self._open_session(sid, lifetime, ttl, owner)
        session = self._sessions[sid]
        session.config = config or {}

        return {"sid": sid, "reattached": False}

    # -- routes -------------------------------------------------------------

    async def twin_create(self, request: Request) -> dict:
        """Register a twin; engine and stream come up in the background.

        Body: `{"twin_id": <client-supplied uuid>, "config": {...}}`.
        The client-supplied id is what makes a retry idempotent, and it
        doubles as the twin's stream namespace -- hence globally unique
        across sessions, not just within one.
        """

        sid = request.path_params["sid"]
        data = await _body(request)

        twin_id = _twin_id(data.get("twin_id"))

        # Scan-then-insert is race-free only because nothing awaits
        # between this check and the insertion in `DTSession.twin_create`
        # -- keep both halves synchronous with respect to each other.
        owner = self._twin_owner(twin_id)
        if owner not in (None, sid):
            raise http_exception(
                ValueError(f"twin id {twin_id} is already used by session {owner}")
            )

        config = data.get("config")
        if config is not None and not isinstance(config, dict):
            raise http_exception(ValueError("'config' must be an object"))

        return await self._forward(
            sid, DTSession.twin_create, twin_id=twin_id, config=config
        )

    async def twin_list(self, request: Request) -> dict:
        return await self._forward(request.path_params["sid"], DTSession.twin_list)

    async def twin_close(self, request: Request) -> dict:
        return await self._forward(
            request.path_params["sid"],
            DTSession.twin_close,
            twin_id=request.path_params["twin_id"],
        )

    async def twin_call(self, request: Request) -> dict:
        """Apply one graph verb.

        Body: `{"verb": str, "payload": <b64 cloudpickle of
        {"args": [...], "kwargs": {...}}>, "client": {"python":…,
        "cloudpickle":…, "digitaltwin":…}}`.
        """

        sid = request.path_params["sid"]
        twin_id = request.path_params["twin_id"]
        data = await _body(request)

        verb = data.get("verb")
        if verb not in VERBS:
            raise http_exception(
                ValueError(f"unknown verb {verb!r}; expected one of {', '.join(VERBS)}")
            )

        # The payload stays a blob here: unpickling is arbitrary code
        # execution, so it happens only after `_forward` has established
        # that this sid names a live session (404 / 410 otherwise).
        return await self._forward(
            sid,
            DTSession.twin_call,
            twin_id=twin_id,
            verb=verb,
            payload=data.get("payload"),
            stamp=data.get("client"),
        )

    async def admin_sessions(self, request: Request) -> dict:
        """Every session with its owner, age, twins, states and errors.

        The single admin route: immortal sessions leak by design, so they
        have to be discoverable.  Teardown then uses the ordinary
        `twin_close` / `unregister_session` routes with a sid from here.
        """

        now = time.time()
        sessions = []

        for sid, session in self._sessions.items():
            record = self._records.get(sid)
            entry = {
                "owner": record.owner if record else None,
                "lifetime": record.lifetime if record else None,
                "idle": round(now - record.last_access, 3) if record else None,
            }
            if isinstance(session, DTSession):
                entry.update(session.summary())
            else:
                entry["sid"] = sid
            sessions.append(entry)

        return {"sessions": sessions, "stream_broker": self.stream_summary()}

    # -- the dashboard ------------------------------------------------------

    async def ui_index(self, request: Request) -> Response:
        """The standalone dashboard page, same-origin with the broker."""

        return self._ui_asset("index.html")

    async def ui_asset(self, request: Request) -> Response:
        """One dashboard asset, from the allow-list."""

        return self._ui_asset(request.path_params["asset"])

    def _root_asset(self, asset: str):
        """The same assets, next to `ui` instead of under it (see routes).

        The name is bound per route: the broker-hosted dispatch hands a
        request shim, so the handler must not introspect the request.
        """

        async def handler(request: Request) -> Response:
            return self._ui_asset(asset)

        return handler

    @staticmethod
    def _ui_asset(asset: str) -> Response:
        """A `Response`, not a dict -- which every dispatch path handles.

        Checked, because it is the only route in this plugin that does not
        return JSON: all three normalize on `status_code` and forward the
        raw body.  `Plugin._wrap_handler` for the ASGI/Explorer path,
        `BrokerPluginHost.handle_request` for a broker-hosted call
        (`Broker._dispatch_to_host` then packs `bytes(result.body)` into
        the wire response), and `EndpointRuntime._dispatch_served` for an
        endpoint-hosted one.
        """

        media = UI_ASSETS.get(asset)
        if media is None:
            raise http_exception(FileNotFoundError(f"no such asset: {asset}"))

        try:
            body = (UI_DIR / asset).read_bytes()
        except OSError as exc:
            raise http_exception(FileNotFoundError(str(exc))) from exc

        # read per request rather than cached: these are a handful of KiB,
        # asked for once per page load, and editing one should not need a
        # broker restart (the gateway's own `ui_module` cache does)
        return Response(body, media_type=media,
                        headers={"cache-control": "no-store"})

    # -- observability ------------------------------------------------------

    async def on_topology_change(self, participants: dict) -> None:
        """Mark twins failed when an engine's endpoint is lost (risk R8).

        `OrbitExecutionBackend` has no reconnect and components bind their
        engine at construction, so a twin whose endpoint went away is
        stranded and cannot be healed in v1.  What it must not be is
        *silent*: on a days-long twin an endpoint loss would otherwise
        show up as inference calls that simply never return.  So this maps
        the lost participants onto the sessions' engine endpoints and
        turns the affected twins into `failed` + a reason in `twin_list`.
        Twins on surviving engines are untouched.  Recovery is the
        client's, and it is the *session* that has to go: engines are
        session-shared and one of them is dead, so a twin created
        afterwards would inherit it.  `unregister_session`, then build
        the session and its twins again.
        """

        await super().on_topology_change(participants)

        lost = {
            name
            for name, info in (participants or {}).items()
            if (info or {}).get("liveness") == "lost"
        }
        if not lost:
            return

        for sid, session in list(self._sessions.items()):
            if not isinstance(session, DTSession):
                continue

            # one session's bookkeeping must not cost the others their
            # notification -- this is the only announcement they get
            try:
                failed = session.endpoints_lost(lost)
            except Exception:
                log.exception("[dt] session %s: endpoint loss handling", sid)
                continue

            if failed:
                log.warning(
                    "[dt] session %s: endpoint(s) %s lost -- twins failed: %s",
                    sid, ", ".join(sorted(lost)), ", ".join(failed),
                )

    # -- the data plane -----------------------------------------------------

    async def connect_stream(
        self, namespace: str, timeout: Optional[float] = CLIENT_CONNECT_TIMEOUT
    ) -> PubSubClient:
        """A connected, namespaced stream client on the selected backend.

        The single place where the plugin's transport choice is applied.
        The `orbit` branch never touches `stream_addresses`, which is what
        keeps the embedded ZMQ broker from being started in a deployment
        that asked for the token-authenticated data plane.
        """

        if self.stream_backend == BACKEND_ORBIT:
            return await connect_stream_client(
                namespace,
                timeout=timeout,
                backend=BACKEND_ORBIT,
                broker_url=self.broker_url,
            )

        pub_addr, sub_addr = await self.stream_addresses()

        # named explicitly: the choice was resolved once at construction,
        # and re-reading the environment per twin could contradict it
        return await connect_stream_client(
            namespace, pub_addr, sub_addr, timeout, backend=BACKEND_ZMQ
        )

    def stream_summary(self) -> dict:
        """The data plane's entry in `admin/sessions`."""

        if self.stream_backend == BACKEND_ORBIT:
            # no addresses and nothing to supervise: the streams ride the
            # ORBIT connection the control plane already has
            return {"backend": BACKEND_ORBIT}

        return {
            "backend": self.stream_backend,
            "addresses": self._stream_addrs,
            "alive": bool(self._stream_broker and self._stream_broker.is_alive()),
        }

    # -- embedded stream broker --------------------------------------------

    async def stream_addresses(self) -> tuple[str, str]:
        """The DT stream broker's `(publish, subscribe)` addresses.

        Starts the broker on first need and arms the supervisor.  One
        broker per plugin, shared by every session and twin -- topic
        namespacing (the twin id) keeps them apart.
        """

        async with self._stream_lock:
            if self._stream_broker is None:
                self._stream_broker = ZMQ_BrokerProcess(*embedded_stream_addresses())
                self._stream_addrs = await self._stream_broker.start()
                log.info("[dt] stream broker at %s / %s", *self._stream_addrs)

            if self._supervisor is None:
                self._supervisor = asyncio.create_task(self._supervise())

            return self._stream_addrs

    async def _supervise(self) -> None:
        """Respawn the stream broker if it dies.

        On the *reported* addresses, not the configured ones: those are
        wildcards by default, and clients have already connected to the
        concrete ports.  ZMQ reconnects them on its own, so a respawn is
        invisible above this line -- whereas a silently dead broker would
        stall every stream on a days-long twin.
        """

        while True:
            try:
                await asyncio.sleep(BROKER_WATCH_INTERVAL)

                async with self._stream_lock:
                    if self._stream_broker is None or self._stream_broker.is_alive():
                        continue

                    log.warning("[dt] stream broker died -- respawning on %s / %s",
                                *self._stream_addrs)
                    await self._stream_broker.stop()
                    self._stream_broker = ZMQ_BrokerProcess(*self._stream_addrs)
                    self._stream_addrs = await self._stream_broker.start()

            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("[dt] stream broker supervision failed")

    # -- teardown -----------------------------------------------------------

    async def shutdown(self) -> None:
        """Host-shutdown path: supervisor, then sessions, then the broker."""

        supervisor, self._supervisor = self._supervisor, None
        if supervisor is not None:
            supervisor.cancel()
            try:
                await supervisor
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("[dt] stream broker supervisor teardown")

        await super().shutdown()

        broker, self._stream_broker = self._stream_broker, None
        if broker is not None:
            await broker.stop()
        self._stream_addrs = None

    # -- internals ----------------------------------------------------------

    def _twin_owner(self, twin_id: str) -> Optional[str]:
        """The sid currently holding `twin_id`, if any.

        Twin ids are globally unique because the stream broker is shared
        plugin-wide; derived by scan so there is no registry to keep in
        sync with session and twin teardown.
        """

        for sid, session in self._sessions.items():
            if isinstance(session, DTSession) and twin_id in session.twins:
                return sid
        return None


async def _body(request: Request) -> dict:
    """Best-effort JSON body as a dict (missing / malformed -> empty)."""

    try:
        data = await request.json()
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _twin_id(twin_id: Any) -> str:
    """Validate a client-supplied twin id.

    It becomes the twin's stream namespace, where a separator would let
    two twins alias each other's topics.
    """

    if not isinstance(twin_id, str) or not twin_id or len(twin_id) > 128:
        raise http_exception(ValueError("'twin_id' must be a non-empty string"))

    if any(c in twin_id for c in "/\x00 "):
        raise http_exception(
            ValueError(f"invalid twin id {twin_id!r}: no '/', spaces or NULs")
        )

    return twin_id
