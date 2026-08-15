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

**Binding policy (risk R7)**: the stream broker binds loopback by
default.  Its payloads are cloudpickled, so anyone who can reach its
ports executes code in every subscriber.  A non-loopback bind needs an
explicit `DT_STREAM_PUB_ADDR` / `DT_STREAM_SUB_ADDR` configuration *and*
a firewalled/private network.
"""

import asyncio
import logging
import os
import time

from typing import Any, Optional

from fastapi import FastAPI
from radical.orbit.errors import http_exception
from radical.orbit.plugin_base import Plugin
from starlette.requests import Request

from ..config import embedded_stream_addresses
from ..streaming import ZMQ_BrokerProcess
from .client import DTClient
from .session import VERBS, DTSession

log = logging.getLogger("radical.orbit")

# route templates -- single-sourced between registration and the client
ROUTE_TWIN_CREATE = "twin_create/{sid}"
ROUTE_TWIN_LIST = "twin_list/{sid}"
ROUTE_TWIN_CLOSE = "twin_close/{sid}/{twin_id}"
ROUTE_TWIN_CALL = "twin_call/{sid}/{twin_id}"
ROUTE_ADMIN_SESSIONS = "admin/sessions"

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

    def __init__(self, app: FastAPI, instance_name: str = "dt"):
        super().__init__(app, instance_name)

        self.broker_url: Optional[str] = os.environ.get(ENV_BROKER_URL) or None

        # the embedded DT stream broker, shared plugin-wide and started on
        # first need (see `stream_addresses`)
        self._stream_broker: Optional[ZMQ_BrokerProcess] = None
        self._stream_addrs: Optional[tuple[str, str]] = None
        self._stream_lock = asyncio.Lock()
        self._supervisor: Optional[asyncio.Task] = None

        self.add_route_post(ROUTE_TWIN_CREATE, self.twin_create)
        self.add_route_get(ROUTE_TWIN_LIST, self.twin_list)
        self.add_route_post(ROUTE_TWIN_CLOSE, self.twin_close)
        self.add_route_post(ROUTE_TWIN_CALL, self.twin_call)
        self.add_route_get(ROUTE_ADMIN_SESSIONS, self.admin_sessions)

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

            {"engines": {"task":   {"endpoint_name": "ep1",
                                    "backends": ["concurrent"]},
                         "exsitu": {"endpoint_name": "hpc1",
                                    "backends": ["concurrent"]}}}

        `'exsitu'` is optional: unconfigured, it aliases `'task'`.
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

        return {
            "sessions": sessions,
            "stream_broker": {
                "addresses": self._stream_addrs,
                "alive": bool(self._stream_broker and self._stream_broker.is_alive()),
            },
        }

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
        Twins on surviving engines are untouched, and the client's
        recovery is the ordinary one: close and recreate.
        """

        await super().on_topology_change(participants)

        lost = {
            name
            for name, info in (participants or {}).items()
            if (info or {}).get("liveness") == "lost"
        }
        if not lost:
            return

        for sid, session in self._sessions.items():
            if not isinstance(session, DTSession):
                continue

            failed = session.endpoints_lost(lost)
            if failed:
                log.warning(
                    "[dt] session %s: endpoint(s) %s lost -- twins failed: %s",
                    sid, ", ".join(sorted(lost)), ", ".join(failed),
                )

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
