"""Unit tests for the `dt` plugin: policy, wire format, guards.

No ORBIT broker involved -- routes are exercised over Starlette's
`TestClient` (plugin route registration is dual), sessions and the
stream-broker supervisor directly.
"""

import asyncio
import uuid

from typing import Optional

import pytest

pytest.importorskip("radical.orbit")

from fastapi import FastAPI, HTTPException  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from digitaltwin.components import (  # noqa: E402
    TRUTHY,
    Barrier,
    DataType,
    JoinDataType,
    SplitTask,
    UtilityTask,
)
from digitaltwin.runtime import DTRuntime  # noqa: E402
from digitaltwin.service.plugin import UI_ASSETS, PluginDT  # noqa: E402
from digitaltwin.service.session import (  # noqa: E402
    ENV_DEFAULT_ENGINE,
    DTSession,
    TwinInstance,
)
from digitaltwin.service.wire import (  # noqa: E402
    MAX_PAYLOAD,
    Package,
    check_versions,
    decode,
    encode,
    encode_checked,
    version_stamp,
)


@pytest.fixture
def plugin():
    """A `PluginDT` on a bare app -- no broker, no engines."""

    return PluginDT(FastAPI())


@pytest.fixture
def client(plugin):
    return TestClient(plugin._app)


# ---------------------------------------------------------------------------
# session policy
# ---------------------------------------------------------------------------


def test_sessions_are_forced_persistent(plugin, client):
    """Whatever the client asks for, twins must outlive it."""

    for body in ({}, {"lifetime": "ephemeral"}, {"lifetime": "ttl", "ttl": 5}):
        sid = client.post("/dt/register_session", json=body).json()["sid"]
        record = plugin._records[sid]

        assert record.lifetime == "persistent"
        assert record.ttl is None


def test_sid_is_a_bearer_capability(plugin, client):
    """A reconnecting client is a different participant; it must still
    get its own twins back."""

    resp = client.post(
        "/dt/register_session", json={}, headers={"x-orbit-src": "client.1"}
    )
    sid = resp.json()["sid"]
    assert plugin._records[sid].owner == "client.1"

    again = client.post(
        "/dt/register_session", json={"sid": sid}, headers={"x-orbit-src": "client.2"}
    )

    assert again.status_code == 200
    assert again.json() == {"sid": sid, "reattached": True}


def test_register_session_rejects_a_bad_config(client):
    resp = client.post("/dt/register_session", json={"config": "nope"})

    assert resp.status_code == 400
    assert "config" in resp.text


def test_admin_sessions_reports_policy_and_broker(plugin, client):
    sid = client.post("/dt/register_session", json={}).json()["sid"]
    listing = client.get("/dt/admin/sessions").json()

    entry = next(s for s in listing["sessions"] if s["sid"] == sid)
    assert entry["lifetime"] == "persistent"
    assert entry["twins"] == []
    assert entry["engines"] == []

    # nothing needed the stream broker yet, so none was started
    assert listing["stream_broker"] == {
        "backend": "zmq",
        "addresses": None,
        "alive": False,
    }


# ---------------------------------------------------------------------------
# routes and validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("twin_id", ["", "with/slash", "with space", None, 42])
def test_twin_create_rejects_bad_ids(client, twin_id):
    """A twin id is a stream namespace: a separator would let two twins
    alias each other's topics."""

    sid = client.post("/dt/register_session", json={}).json()["sid"]
    resp = client.post(f"/dt/twin_create/{sid}", json={"twin_id": twin_id})

    assert resp.status_code == 400


def test_twin_call_rejects_unknown_verbs(client):
    sid = client.post("/dt/register_session", json={}).json()["sid"]
    resp = client.post(
        f"/dt/twin_call/{sid}/t1", json={"verb": "rm_rf", "payload": "", "client": {}}
    )

    assert resp.status_code == 400
    assert "unknown verb" in resp.text


def test_twin_call_rejects_version_skew(client):
    sid = client.post("/dt/register_session", json={}).json()["sid"]
    resp = client.post(
        f"/dt/twin_call/{sid}/t1",
        json={
            "verb": "start",
            "payload": "",
            "client": {"python": "2.7", "cloudpickle": "0.1"},
        },
    )

    assert resp.status_code == 400
    assert "version skew" in resp.text


def test_twin_close_is_idempotent_for_unknown_twins(client):
    sid = client.post("/dt/register_session", json={}).json()["sid"]
    resp = client.post(f"/dt/twin_close/{sid}/never-existed")

    assert resp.status_code == 200
    assert resp.json()["state"] == "closed"


def test_unknown_session_is_404(client):
    assert client.get("/dt/twin_list/session.nope").status_code == 404


def test_an_unknown_session_never_unpickles_the_payload(client):
    """Decoding is arbitrary code execution: an unroutable verb must be
    turned away before its payload reaches cloudpickle.

    The payload here is not decodable at all -- a 400 would mean the
    service tried."""

    resp = client.post(
        "/dt/twin_call/session.nope/t1",
        json={
            "verb": "start",
            "payload": "!! not base64 !!",
            "client": version_stamp(),
        },
    )

    assert resp.status_code == 404


async def test_a_call_on_a_closed_session_is_410():
    """Not a 500: a client racing its own `unregister_session` has
    simply outlived its session."""

    session = DTSession("s1")
    await session.close()

    with pytest.raises(HTTPException) as raised:
        await session.twin_call("t1", "start")

    assert raised.value.status_code == 410


async def test_a_malformed_call_is_a_client_error():
    """A hand-built payload with the wrong arity is a bad request, not a
    service fault."""

    session = DTSession("s1")
    session.twins["t1"] = _twin_with(_FakeFlow())

    with pytest.raises(HTTPException) as raised:
        await session.twin_call(
            "t1", "start", encode({"args": (1, 2, 3)}), version_stamp()
        )

    assert raised.value.status_code == 409
    assert "TypeError" in raised.value.detail


# ---------------------------------------------------------------------------
# wire format
# ---------------------------------------------------------------------------


def test_encode_roundtrip():
    payload = {"args": (1, "two", [3]), "kwargs": {"k": {"nested": True}}}

    assert decode(encode(payload)) == payload


def test_size_check_refuses_oversized_payloads():
    with pytest.raises(ValueError, match="frame cap"):
        encode_checked(bytearray(MAX_PAYLOAD), "test payload")


def test_size_check_passes_a_normal_payload():
    assert encode_checked({"args": (1, 2)}, "test payload")


def test_version_stamp_matches_itself():
    check_versions(version_stamp())


@pytest.mark.parametrize(
    "key, value",
    [
        ("python", "2.7"),
        ("cloudpickle", "0.1"),
        # by-reference pickling of component classes: any difference counts
        ("digitaltwin", version_stamp()["digitaltwin"] + ".dev1"),
    ],
)
def test_version_skew_is_rejected(key, value):
    with pytest.raises(ValueError, match=f"{key} version skew"):
        check_versions({**version_stamp(), key: value})


@pytest.mark.parametrize("missing", ["python", "cloudpickle", "digitaltwin"])
def test_a_missing_version_is_rejected(missing):
    stamp = {k: v for k, v in version_stamp().items() if k != missing}

    with pytest.raises(ValueError, match=f"did not report its {missing}"):
        check_versions(stamp)


def test_the_stamp_pins_digitaltwin_too():
    assert "digitaltwin" in version_stamp()


def test_the_package_version_is_looked_up_once(monkeypatch):
    from digitaltwin.service import wire

    calls = []
    real = wire.metadata.version

    def counting(name):
        if name == "digitaltwin":
            calls.append(name)
        return real(name)

    monkeypatch.setattr(wire.metadata, "version", counting)
    wire._dt_version.cache_clear()
    try:
        for _ in range(100):
            check_versions(version_stamp())
        assert calls == ["digitaltwin"]
    finally:
        wire._dt_version.cache_clear()


def test_package_instantiates_with_the_injected_engine():
    class Component:
        def __init__(self, flow, a, b=0):
            self.flow, self.a, self.b = flow, a, b

    component = Package(Component, (1,), {"b": 2}).instantiate("engine")

    assert (component.flow, component.a, component.b) == ("engine", 1, 2)


# ---------------------------------------------------------------------------
# the persistent-component guard
# ---------------------------------------------------------------------------


class _FakeFlow:
    """Just enough engine for `_instantiate` and teardown."""

    def __init__(self):
        self.registered = []
        self.backends = []
        self.is_shut_down = False

    def function_task(self, func):
        self.registered.append(func)
        return func

    def _attach_backend(self, backend):
        self.backends.append(backend)

    async def shutdown(self):
        # asyncflow's shutdown takes the attached backends down with it
        self.is_shut_down = True
        for backend in self.backends:
            await backend.shutdown()


class _FakeBackend:
    def __init__(self, name):
        self.name = name
        self.is_shut_down = False

    async def shutdown(self):
        self.is_shut_down = True


class _FakeEngineFactory:
    """Stands in for `WorkflowEngine` inside `_build_engine`."""

    @staticmethod
    async def create(backend=None):
        flow = _FakeFlow()
        flow.backends.append(backend)
        return flow


@pytest.fixture(autouse=True)
def _fake_engine(monkeypatch):
    monkeypatch.setattr(
        "digitaltwin.service.session.WorkflowEngine", _FakeEngineFactory
    )


class _Persistent(UtilityTask):
    def __init__(self, flow):
        super().__init__(flow)

        @flow.function_task
        async def body():
            return 1

        self.body = body


class _Plain(UtilityTask):
    pass


class _FakeStream:
    """Just enough stream client for a `DTRuntime` that never streams."""

    namespace = "twin"
    on_error = None


def _twin_with(flow):
    twin = TwinInstance("t1")
    twin.runtime = type("R", (), {"flow": flow})()

    return twin


def test_persistent_function_task_warns(caplog):
    flow = _FakeFlow()
    session = DTSession("s1")

    with caplog.at_level("WARNING"):
        session._instantiate(Package(_Persistent), _twin_with(flow), is_persistent=True)

    assert "registered 1 function_task" in caplog.text
    # the engine is handed back unpatched
    assert flow.function_task.__func__ is _FakeFlow.function_task


def test_non_persistent_function_task_is_fine(caplog):
    session = DTSession("s1")

    with caplog.at_level("WARNING"):
        session._instantiate(Package(_Persistent), _twin_with(_FakeFlow()))

    assert "function_task" not in caplog.text


def test_persistent_without_function_tasks_is_fine(caplog):
    session = DTSession("s1")

    with caplog.at_level("WARNING"):
        session._instantiate(
            Package(_Plain), _twin_with(_FakeFlow()), is_persistent=True
        )

    assert "function_task" not in caplog.text


def test_instantiate_rejects_a_non_package():
    with pytest.raises(ValueError, match="package"):
        DTSession("s1")._instantiate(_Plain, _twin_with(_FakeFlow()))


# ---------------------------------------------------------------------------
# engines
# ---------------------------------------------------------------------------


def _slow_build(session, delay: float, started: Optional[asyncio.Event] = None):
    """Stand in for a real (up to 150 s) backend build."""

    built = []

    async def build(name):
        if started is not None:
            started.set()
        await asyncio.sleep(delay)
        backend = _FakeBackend(name)
        built.append(backend)
        return backend

    session._create_backend = build

    return built


async def test_one_engine_is_shared_by_every_caller():
    session = DTSession("s1")
    built = _slow_build(session, 0.05)

    first, second = await asyncio.gather(session.engine(), session.engine())

    assert first is second
    assert len(built) == 1


async def test_an_engine_build_survives_a_cancelled_caller():
    """A twin whose initialization is cancelled halfway must not take the
    build with it -- that would strand a live backend nobody holds."""

    session = DTSession("s1")
    started = asyncio.Event()
    built = _slow_build(session, 0.2, started)

    caller = asyncio.create_task(session.engine())
    await started.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    flow = await session.engine()

    assert session._flow is flow
    assert built == [session._backends["inference"]]


async def test_an_engine_landing_after_close_disposes_of_itself():
    """Nothing will ever own it, so it must not outlive its own build."""

    session = DTSession("s1")
    built = _slow_build(session, 0.2)

    caller = asyncio.create_task(session.engine())
    await asyncio.sleep(0.05)

    await session.close()

    with pytest.raises((RuntimeError, asyncio.CancelledError)):
        await caller

    assert len(built) == 1
    assert built[0].is_shut_down
    assert session._flow is None


async def test_close_shuts_down_a_built_engine():
    session = DTSession("s1")
    built = _slow_build(session, 0)

    flow = await session.engine()
    await session.close()

    assert flow.is_shut_down
    assert built[0].is_shut_down
    assert session._flow is None


# ---------------------------------------------------------------------------
# the 'learning' role (M2)
# ---------------------------------------------------------------------------


def _dual(**endpoints: str) -> dict:
    return {
        "engines": {
            name: {"endpoint_name": endpoint} for name, endpoint in endpoints.items()
        }
    }


async def test_an_unconfigured_role_aliases_inference():
    """Adding `'learning'` must stay a config-only change: without one, a
    learner twin runs both halves on the one backend."""

    session = DTSession("s1", _dual(inference="ep1"))
    built = _slow_build(session, 0)

    assert await session.engine("learning") is await session.engine("inference")
    assert len(built) == 1
    assert sorted(session._backends) == ["inference"]


async def test_a_slow_learning_build_does_not_hold_up_inference():
    """Per-role build tasks and locks: a remote backend taking minutes
    must not serialize ahead of the backend a sibling twin needs."""

    session = DTSession("s1", _dual(inference="ep1", learning="hpc1"))
    delays = {"inference": 0.0, "learning": 5.0}

    async def build(name):
        await asyncio.sleep(delays[name])
        return _FakeBackend(name)

    session._create_backend = build

    slow = asyncio.create_task(session.engine("learning"))
    await asyncio.sleep(0.05)

    assert await asyncio.wait_for(session.engine("inference"), 1.0)

    slow.cancel()


async def test_a_learner_gets_the_learning_label():
    """Role injection, by subclass check -- there is no user-facing
    role selector in v1."""

    learn = pytest.importorskip("digitaltwin.learn")

    class _Learner(learn.StreamingLearnerInvestigator):
        def __init__(self, flow, learn_backend=None):
            self.flow, self.learn_backend = flow, learn_backend

    session = DTSession("s1", _dual(inference="ep1", learning="hpc1"))
    session._backends["learning"] = _FakeBackend("learning")

    twin = _twin_with(_FakeFlow())
    component = session._instantiate(Package(_Learner), twin)

    assert component.learn_backend == "learning"
    assert component.flow is twin.runtime.flow
    assert twin.engines == {"inference", "learning"}


async def test_a_plain_component_never_sees_a_second_role():
    session = DTSession("s1", _dual(inference="ep1", learning="hpc1"))
    session._backends["learning"] = _FakeBackend("learning")

    twin = _twin_with(_FakeFlow())
    session._instantiate(Package(_Plain), twin)

    assert twin.engines == {"inference"}


# ---------------------------------------------------------------------------
# R8: a lost endpoint is visible, not silent
# ---------------------------------------------------------------------------


def _running_twin(session, twin_id, *engines: str):
    twin = session.twins[twin_id] = TwinInstance(twin_id)
    twin.engines.update(engines)
    twin.runtime = DTRuntime(_FakeFlow(), _FakeStream())
    twin.runtime.start()

    return twin


async def test_a_lost_endpoint_fails_only_the_twins_that_used_it():
    session = DTSession("s1")
    session._endpoints = {"inference": "ep1", "learning": "hpc1"}

    learner = _running_twin(session, "learner", "learning")
    plain = _running_twin(session, "plain")

    assert session.endpoints_lost({"hpc1"}) == ("learner",)

    assert learner.state == "failed"
    assert learner.last_error == "engine endpoint lost: hpc1"

    # a session-shared engine the twin never bound to is not its problem
    assert plain.state == "running"
    assert plain.last_error is None


async def test_a_lost_endpoint_is_never_handed_out_again():
    """R8 is announced once, but the dead engine stays cached: a twin
    created afterwards must fail fast instead of binding it and
    stalling."""

    session = DTSession("s1", _dual(inference="ep1", learning="hpc1"))
    _slow_build(session, 0)

    flow = await session.engine("inference")
    await session.engine("learning")
    session._endpoints = {"inference": "ep1", "learning": "hpc1"}

    session.endpoints_lost({"hpc1"})

    with pytest.raises(RuntimeError, match="recreate the session"):
        await session.engine("learning")

    # the surviving role is still handed out
    assert await session.engine("inference") is flow


async def test_a_loss_before_the_build_is_remembered_too():
    """The engine need not have been built for its endpoint to be
    known: the configuration named it."""

    session = DTSession("s1", _dual(inference="ep1", learning="hpc1"))
    _slow_build(session, 0)

    session.endpoints_lost({"hpc1"})

    with pytest.raises(RuntimeError, match="recreate the session"):
        await session.engine("learning")


async def test_a_surviving_topology_change_fails_nothing():
    session = DTSession("s1")
    session._endpoints = {"inference": "ep1"}
    twin = _running_twin(session, "t1")

    assert session.endpoints_lost({"someone-else"}) == ()
    assert twin.state == "running"


async def test_the_plugin_routes_lost_participants_to_its_sessions(plugin):
    session = plugin._sessions["s1"] = DTSession("s1")
    session._endpoints = {"inference": "ep1"}
    twin = _running_twin(session, "t1")

    await plugin.on_topology_change(
        {
            "ep1": {"liveness": "lost"},
            "ep2": {"liveness": "present"},
        }
    )

    assert twin.state == "failed"
    assert twin.last_error == "engine endpoint lost: ep1"


async def test_a_suspect_participant_is_not_a_loss(plugin):
    """A transient blip reaches `suspect` at most and must never fail a
    twin -- the broker's grace timer decides."""

    session = plugin._sessions["s1"] = DTSession("s1")
    session._endpoints = {"inference": "ep1"}
    twin = _running_twin(session, "t1")

    await plugin.on_topology_change({"ep1": {"liveness": "suspect"}})

    assert twin.state == "running"


# ---------------------------------------------------------------------------
# the embedded stream broker and its supervisor
# ---------------------------------------------------------------------------


async def test_stream_broker_starts_on_loopback_once(plugin):
    """One broker per plugin, shared by every twin, bound to loopback."""

    try:
        first = await plugin.stream_addresses()
        second = await plugin.stream_addresses()

        assert first == second
        assert all(addr.startswith("tcp://127.0.0.1:") for addr in first)
        assert plugin._stream_broker.is_alive()

    finally:
        await plugin.shutdown()


async def test_supervisor_respawns_on_the_same_addresses(plugin, monkeypatch):
    """A silently dead stream broker would stall every twin's stream."""

    monkeypatch.setattr("digitaltwin.service.plugin.BROKER_WATCH_INTERVAL", 0.1)

    try:
        addrs = await plugin.stream_addresses()
        first_pid = plugin._stream_broker._proc.pid

        plugin._stream_broker._proc.kill()
        await asyncio.wait_for(_respawned(plugin, first_pid), 20)

        assert plugin._stream_broker.get_connection_str() == addrs
        assert plugin._stream_broker.is_alive()

    finally:
        await plugin.shutdown()


async def _respawned(plugin, old_pid):
    """Wait for a live successor.  Observed under the plugin's own lock,
    so a respawn in progress is never seen half-started."""

    while True:
        async with plugin._stream_lock:
            proc = plugin._stream_broker._proc
            if proc is not None and proc.pid != old_pid and proc.is_alive():
                return
        await asyncio.sleep(0.05)


async def test_shutdown_stops_the_broker_and_the_supervisor(plugin):
    await plugin.stream_addresses()
    broker, supervisor = plugin._stream_broker, plugin._supervisor

    await plugin.shutdown()

    assert not broker.is_alive()
    assert supervisor.done()
    assert plugin._stream_broker is None


# ---------------------------------------------------------------------------
# the observation surface the dashboard reads
# ---------------------------------------------------------------------------


class _Metered(UtilityTask):
    """A component reporting a convergence metric, the way a
    `StreamingLearnerInvestigator` does -- duck-typed, so this needs no
    ROSE."""

    metrics = {
        "rmse": {
            "value": 0.4,
            "threshold": 0.25,
            "operator": "<",
            "should_stop": False,
            "windows": 3,
            "history": [0.9, 0.6, 0.4],
        }
    }


async def test_a_twin_summary_carries_its_metrics():
    session = DTSession("s1")
    twin = _running_twin(session, "t1")
    twin.runtime.add_task(_Metered(_FakeFlow()), TRUTHY, DataType("x"))

    summary = twin.summary()

    assert summary["metrics"]["rmse"]["value"] == 0.4
    assert summary["metrics"]["rmse"]["component"] == "_Metered"

    await twin.close()
    # a closed twin has no graph left to ask
    assert twin.summary()["metrics"] == {}


async def test_a_twin_counts_the_verbs_it_answered():
    """The only trace a synchronous verb leaves: what the dashboard's
    client-ward arcs are inferred from."""

    session = DTSession("s1")
    twin = _running_twin(session, "t1")

    assert twin.summary()["calls"] == {}

    for _ in range(3):
        await session.twin_call("t1", "describe", stamp=version_stamp())

    assert twin.summary()["calls"] == {"describe": 3}

    await twin.close()


async def test_a_verb_that_failed_is_not_counted():
    """A round trip that was never answered is not one."""

    session = DTSession("s1")
    twin = _running_twin(session, "t1")
    await twin.runtime.stop()

    with pytest.raises(HTTPException) as raised:
        await session.twin_call("t1", "start", stamp=version_stamp())

    assert raised.value.status_code == 409
    assert "start" not in twin.summary()["calls"]

    await twin.close()


async def test_the_session_summary_names_the_engine_endpoints():
    """The dashboard draws one lane per *role*; `None` for
    `'learning'` is the documented alias of `'inference'`, not an
    omission."""

    single = DTSession("s1", _dual(inference="ep1"))
    assert single.summary()["endpoints"] == {"inference": "ep1", "learning": None}

    dual = DTSession("s2", _dual(inference="ep1", learning="hpc1"))
    assert dual.summary()["endpoints"] == {"inference": "ep1", "learning": "hpc1"}


def test_admin_sessions_carries_endpoints_and_metrics(client):
    sid = client.post(
        "/dt/register_session", json={"config": _dual(inference="ep1")}
    ).json()["sid"]
    entry = next(
        s
        for s in client.get("/dt/admin/sessions").json()["sessions"]
        if s["sid"] == sid
    )

    assert entry["endpoints"] == {"inference": "ep1", "learning": None}


# ---------------------------------------------------------------------------
# the dashboard's assets
# ---------------------------------------------------------------------------


def test_the_ui_route_serves_the_standalone_page(client):
    """Served by the plugin so a browser can reach a live broker
    same-origin: the gateway's CORS allow-list and the SameSite=Strict
    auth cookie rule out every other origin."""

    resp = client.get("/dt/ui")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "dt_dash.js" in resp.text


@pytest.mark.parametrize("asset", ["dt_dash.js", "dt_sample.js", "dt_explorer.js"])
def test_the_ui_assets_are_served_as_javascript(client, asset):
    resp = client.get(f"/dt/ui/{asset}")

    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


@pytest.mark.parametrize(
    "asset",
    [
        "passwd",
        "plugin.py",
        ".env",
        # a percent-encoded separator survives the route's `[^/]+` segment, so
        # the allow-list is what has to refuse it -- not the router
        "..%2f..%2fplugin.py",
        "%2e%2e%2f%2e%2e%2fplugin.py",
        "dt_dash.js%00.png",
    ],
)
def test_an_unlisted_ui_asset_is_404(client, asset):
    """An allow-list, not a directory walk: the asset name comes from the
    client."""

    resp = client.get(f"/dt/ui/{asset}")

    assert resp.status_code == 404
    assert "plugin" not in resp.text or "no such asset" in resp.text


def test_the_explorer_module_is_the_one_the_plugin_declares():
    """ORBIT reads `ui_module` off the class and serves its content at
    `/plugins/dt.js` -- so the path has to exist in the installed
    package."""

    from pathlib import Path

    module = Path(PluginDT.ui_module)

    assert module.is_file()
    assert module.name in UI_ASSETS
    assert "window.DTDash.mount" in module.read_text()


# ---------------------------------------------------------------------------
# pool-backed roles (dispatcher pools)
# ---------------------------------------------------------------------------


class _FakePoolBackend:
    """Signature-faithful stand-in: the pool path checks the constructor's
    parameters before using them."""

    captured: dict = {}

    def __init__(
        self,
        broker_url=None,
        endpoint_name=None,
        backends=None,
        name=None,
        participant_name=None,
        plugin_name="rhapsody",
        pool=None,
        session_kwargs=None,
        batch_window=0,
    ):
        type(self).captured = dict(
            endpoint_name=endpoint_name,
            name=name,
            participant_name=participant_name,
            plugin_name=plugin_name,
            pool=pool,
            session_kwargs=session_kwargs,
        )
        self._endpoint_name = endpoint_name or "broker"

    def __await__(self):
        async def _self():
            return self

        return _self().__await__()


class _FakeOldBackend:
    """A backend from before pool support -- no `pool` parameter."""

    def __init__(
        self,
        broker_url=None,
        endpoint_name=None,
        backends=None,
        name=None,
        batch_window=0,
    ):
        pass


async def test_a_pool_backed_role_targets_the_dispatcher(monkeypatch):
    """`pool` in a role's config routes it at the task dispatcher: one
    dispatcher session per DT session (keyed by the DT sid), the
    session-level pool configs declared with it."""

    import digitaltwin.service.session as session_mod

    session = DTSession("s1")
    session.config = {
        "pools": [{"name": "exsitu", "endpoint_name": "hpc1"}],
        "engines": {
            "inference": {"endpoint_name": "ep1"},
            "learning": {"pool": "exsitu"},
        },
    }
    monkeypatch.setattr(session_mod, "OrbitExecutionBackend", _FakePoolBackend)

    await session._create_backend("learning")

    got = _FakePoolBackend.captured
    assert got["plugin_name"] == "task_dispatcher"
    assert got["pool"] == "exsitu"
    assert got["session_kwargs"]["sid"] == "s1"
    assert got["session_kwargs"]["pools"] == [
        {"name": "exsitu", "endpoint_name": "hpc1"}
    ]
    # the role records its pool, not an endpoint -- the R8 opt-out
    assert session._endpoints["learning"] == "pool:exsitu"


async def test_a_pool_needs_a_pool_capable_backend(monkeypatch):
    import digitaltwin.service.session as session_mod

    session = DTSession("s1")
    session.config = {"engines": {"learning": {"pool": "exsitu"}}}
    monkeypatch.setattr(session_mod, "OrbitExecutionBackend", _FakeOldBackend)

    with pytest.raises(RuntimeError, match="no pool support"):
        await session._create_backend("learning")


async def test_endpoint_loss_spares_pool_backed_roles():
    """Losing an endpoint requeues a pool's tasks inside the dispatcher;
    only endpoint-bound roles fail their twins (R8)."""

    session = DTSession("s1")
    session.config = {"engines": {"learning": {"pool": "exsitu"}}}
    session._endpoints["learning"] = "pool:exsitu"

    assert session.endpoints_lost({"hpc1", "exsitu", "pool"}) == ()
    assert not session._lost


# ---------------------------------------------------------------------------
# graph verbs: external inputs and joins (#30)
# ---------------------------------------------------------------------------


class _BindingStream(_FakeStream):
    """A `_FakeStream` that also accepts channel subscriptions."""

    def __init__(self):
        self.subscribed = []

    async def subscribe_to_channel(self, channel, dtype, queue, codec):
        self.subscribed.append((channel, dtype, codec))


async def test_add_input_binds_a_channel_through_the_verb():
    """`add_input` carries data only -- dtype, channel, codec -- and the
    binding lands in the runtime exactly as a direct call would leave it."""

    session = DTSession("s1")
    twin = _running_twin(session, "t1")
    twin.runtime.streamer = _BindingStream()

    x = DataType("x")
    await session.twin_call(
        "t1", "add_input", encode({"args": (x, "lab/raw")}), version_stamp()
    )

    binding = twin.runtime.inputs[0]
    assert (binding.dtype, binding.channel, binding.codec) == (x, "lab/raw", "json")
    # the verb answered, so the subscription is already live -- no settling
    assert twin.runtime.streamer.subscribed == [("lab/raw", x, "json")]
    assert twin.summary()["calls"] == {"add_input": 1}

    await twin.close()


async def test_add_input_rejects_a_bad_channel_as_client_error():
    """The runtime's own refusal (reserved prefix) surfaces as a 409,
    the same contract every other graph verb has."""

    session = DTSession("s1")
    twin = _running_twin(session, "t1")
    twin.runtime.streamer = _BindingStream()

    with pytest.raises(HTTPException) as raised:
        await session.twin_call(
            "t1",
            "add_input",
            encode({"args": (DataType("x"), "dt/oops")}),
            version_stamp(),
        )

    assert raised.value.status_code == 409
    assert twin.runtime.inputs == []

    await twin.close()


async def test_add_data_join_registers_through_the_verb():
    """One joined dtype, consumable downstream like any other."""

    session = DTSession("s1")
    twin = _running_twin(session, "t1")

    a, b = DataType("a"), DataType("b")
    joined = JoinDataType([a, b])
    await session.twin_call(
        "t1", "add_data_join", encode({"args": (joined,)}), version_stamp()
    )

    assert joined in twin.runtime.join_components
    assert twin.summary()["calls"] == {"add_data_join": 1}

    await twin.close()


async def test_add_input_refuses_a_codec_change_on_a_bound_channel():
    """The stream client dedupes on (channel, dtype): a re-bind with a
    different codec would be recorded yet never applied, so it is
    refused instead of silently decoding with the old codec forever."""

    session = DTSession("s1")
    twin = _running_twin(session, "t1")
    twin.runtime.streamer = _BindingStream()

    x = DataType("x")
    await session.twin_call(
        "t1", "add_input", encode({"args": (x, "lab/raw")}), version_stamp()
    )

    # the identical re-bind is an idempotent no-op
    await session.twin_call(
        "t1", "add_input", encode({"args": (x, "lab/raw")}), version_stamp()
    )
    assert len(twin.runtime.inputs) == 1

    with pytest.raises(HTTPException) as raised:
        await session.twin_call(
            "t1", "add_input", encode({"args": (x, "lab/raw", "raw")}), version_stamp()
        )

    assert raised.value.status_code == 409
    assert "codec" in raised.value.detail
    assert len(twin.runtime.inputs) == 1

    await twin.close()


# -- engine-side telemetry and workflow scopes (#36) ---------------------------


@pytest.mark.parametrize(
    "telemetry", ["on", {}, {"checkpoint_path": 3}, {"checkpoint_interval": 0}]
)
def test_register_session_rejects_a_bad_telemetry_block(client, telemetry):
    resp = client.post(
        "/dt/register_session", json={"config": {"telemetry": telemetry}}
    )

    assert resp.status_code == 400
    assert "telemetry" in resp.text


def test_register_session_accepts_a_telemetry_block(client):
    resp = client.post(
        "/dt/register_session",
        json={"config": {"telemetry": {"checkpoint_path": "/tmp/t"}}},
    )

    assert resp.status_code == 200


def test_twin_create_rejects_a_bad_workflow_scope(client):
    sid = client.post("/dt/register_session", json={}).json()["sid"]
    resp = client.post(
        f"/dt/twin_create/{sid}",
        json={"twin_id": str(uuid.uuid4()), "config": {"workflow_scope": 3}},
    )

    assert resp.status_code == 400
    assert "workflow_scope" in resp.text


async def test_a_failed_telemetry_start_shuts_the_engine_down(monkeypatch):
    session = DTSession("s1", {"telemetry": {"checkpoint_path": "/x"}})
    _slow_build(session, 0)
    stopped = []

    async def start_telemetry(self, **kwargs):
        raise RuntimeError("no such directory")

    async def shutdown_engine(flow):
        stopped.append(flow)

    monkeypatch.setattr(_FakeFlow, "start_telemetry", start_telemetry, raising=False)
    session._shutdown_engine = shutdown_engine

    with pytest.raises(RuntimeError, match="no such directory"):
        await session.engine()

    assert len(stopped) == 1


# -- barriers and split tasks through the verbs (#30) --------------------------

A, B, C = DataType("a"), DataType("b"), DataType("c")


def _call(*args):
    return encode({"args": list(args), "kwargs": {}})


def test_add_barrier_sends_the_spec_not_the_barrier():
    """A client-built barrier travels as name, hardness and per-dtype
    flags; the asyncio primitives it holds stay behind."""

    from digitaltwin.service.client import DTClient

    sent = []
    client = DTClient.__new__(DTClient)
    client._verb = lambda twin, verb, *args, **kw: (
        sent.append((verb, args)) or {"state": "ready"}
    )

    barrier = Barrier("AB", hard=False)
    barrier.add_dtype(A, hard=True)
    barrier.add_dtype(B)

    assert client.add_barrier("t1", barrier) == "ready"
    assert sent == [("add_barrier", ("AB", False, [(A, True), (B, False)]))]


async def test_add_barrier_verb_builds_the_same_barrier_service_side():
    session = DTSession("s1")
    twin = _running_twin(session, "t1")

    await session.twin_call(
        "t1",
        "add_barrier",
        _call("AB", True, [(A, True), (B, False)]),
        stamp=version_stamp(),
    )

    barrier = twin.runtime.barriers[A][0]
    assert twin.runtime.barriers[B] == [barrier]
    assert barrier.name == "AB"
    assert barrier.is_hard_barrier is True
    assert barrier.dtypes == {A: True, B: False}

    await twin.close()


class _Split(SplitTask):
    async def main_loop(self, runtime, in_data):
        return None, None


async def test_add_data_split_task_verb_registers_the_split():
    session = DTSession("s1")
    twin = _running_twin(session, "t1")

    await session.twin_call(
        "t1",
        "add_data_split_task",
        _call(Package(_Split), A, (B, C)),
        stamp=version_stamp(),
    )

    (split,) = twin.runtime.components[A]
    assert isinstance(split.component, _Split)
    assert tuple(split.split_outputs) == (B, C)

    await twin.close()


def test_add_barrier_refuses_a_subclass():
    from digitaltwin.service.client import DTClient

    class Custom(Barrier):
        pass

    client = DTClient.__new__(DTClient)

    with pytest.raises(TypeError, match="plain Barrier"):
        client.add_barrier("t1", Custom("AB"))


async def test_a_barrier_cannot_follow_a_soft_one_or_repeat(stream_clients):
    runtime = DTRuntime(None, await stream_clients("barriers"))

    first = Barrier("AB", hard=False)
    first.add_dtype(A)
    runtime.add_barrier(first)

    second = Barrier("CD")
    second.add_dtype(A)
    with pytest.raises(ValueError, match="cannot follow"):
        runtime.add_barrier(second)

    with pytest.raises(ValueError, match="no dtypes"):
        runtime.add_barrier(Barrier("EF"))

    await runtime.stop()


async def test_add_data_split_task_needs_a_split_task(stream_clients):
    runtime = DTRuntime(None, await stream_clients("splits"))

    with pytest.raises(AssertionError):
        runtime.add_data_split_task(_Persistent(_FakeFlow()), A, (B,))

    await runtime.stop()


# -- default engine (#27) -----------------------------------------------------

_DUAL = {
    "engines": {"inference": {"endpoint_name": "a"}, "learning": {"endpoint_name": "b"}}
}


def test_default_engine_is_inference_without_config(monkeypatch):
    monkeypatch.delenv(ENV_DEFAULT_ENGINE, raising=False)

    assert DTSession("s1", _DUAL).default_engine() == "inference"


def test_default_engine_config_beats_environment(monkeypatch):
    monkeypatch.setenv(ENV_DEFAULT_ENGINE, "inference")
    session = DTSession("s1", {**_DUAL, "default_engine": "learning"})

    assert session.default_engine() == "learning"


def test_default_engine_from_environment(monkeypatch):
    monkeypatch.setenv(ENV_DEFAULT_ENGINE, "learning")

    assert DTSession("s1", _DUAL).default_engine() == "learning"


def test_default_engine_unconfigured_role_aliases_inference(monkeypatch):
    monkeypatch.setenv(ENV_DEFAULT_ENGINE, "learning")

    assert DTSession("s1").default_engine() == "inference"


def test_register_session_rejects_a_bad_deployment_default(client, monkeypatch):
    monkeypatch.setenv(ENV_DEFAULT_ENGINE, "gpu")

    resp = client.post("/dt/register_session", json={})

    assert resp.status_code == 400
    assert "default_engine" in resp.text


@pytest.mark.parametrize("value", ["gpu", None, ""])
def test_register_session_rejects_a_bad_default_engine(client, value):
    resp = client.post(
        "/dt/register_session", json={"config": {"default_engine": value}}
    )

    assert resp.status_code == 400
    assert "default_engine" in resp.text


async def test_a_loss_during_init_fails_a_twin_on_the_default_role():
    """With 'learning' as the default, a twin depends on that endpoint
    from its first task on: losing it while the twin initializes must
    fail the twin, and it must not come up `ready` afterwards (R8)."""

    session = DTSession(
        "s1", {**_dual(inference="ep1", learning="hpc1"), "default_engine": "learning"}
    )
    started = asyncio.Event()
    _slow_build(session, 0.2, started)

    class _Plugin:
        async def connect_stream(self, twin_id, timeout):
            stream = _FakeStream()

            async def close():
                stream.closed = True

            stream.close = close
            return stream

    session._plugin = _Plugin()
    twin = session.twins["t1"] = TwinInstance("t1")

    init = asyncio.create_task(session._init_twin(twin))
    await started.wait()
    assert session.endpoints_lost({"hpc1"}) == ("t1",)
    await init

    assert twin.state == "failed"
    assert twin.runtime is None
    assert "hpc1" in twin.last_error


async def test_default_engine_moves_the_engines_default_backend():
    session = DTSession(
        "s1", {**_dual(inference="ep1", learning="hpc1"), "default_engine": "learning"}
    )
    _slow_build(session, 0)

    flow = await session.engine("learning")

    assert flow._default_backend_name == "learning"
    await session.close()


async def test_a_twin_is_bound_only_to_the_default_role():
    """R8: a twin on the 'learning' default does not use the inference
    endpoint, so losing that endpoint must not fail it."""

    session = DTSession(
        "s1", {**_dual(inference="ep1", learning="hpc1"), "default_engine": "learning"}
    )
    _slow_build(session, 0)

    class _Plugin:
        async def connect_stream(self, twin_id, timeout):
            return _FakeStream()

    session._plugin = _Plugin()
    twin = session.twins["t1"] = TwinInstance("t1")
    await session._init_twin(twin)

    assert twin.engines == {"learning"}
    assert session.endpoints_lost({"ep1"}) == ()
    await session.close()


def test_the_first_failure_of_a_twin_is_kept():
    twin = TwinInstance("t1")

    twin.fail("engine endpoint lost: hpc1")
    twin.fail("timed out")

    assert twin.last_error == "engine endpoint lost: hpc1"


# -- named engines: components on several sites --------------------------------


class _LabelFlow(_FakeFlow):
    """Records the keyword arguments of every task decorator."""

    def __init__(self):
        super().__init__()
        self.labels = []

    def _record(self, kind, *args, **kwargs):
        self.labels.append((kind, kwargs.get("backend")))
        return args[0] if args else (lambda func: func)

    def function_task(self, *args, **kwargs):
        return self._record("function", *args, **kwargs)

    def executable_task(self, *args, **kwargs):
        return self._record("executable", *args, **kwargs)

    def prompt_task(self, *args, **kwargs):
        return self._record("prompt", *args, **kwargs)


class _ThreeKinds(UtilityTask):
    """One task of each decorator kind, bare and called forms."""

    def __init__(self, flow):
        super().__init__(flow)

        @flow.function_task
        async def a():
            return 1

        @flow.executable_task()
        async def b():
            return "true"

        @flow.prompt_task
        async def c():
            return "hi"


class _Labelled(UtilityTask):
    """Builds two 'investigators' and places one itself, as an agent does."""

    def __init__(self, flow, site="site_c"):
        super().__init__(flow)

        @flow.function_task
        async def local():
            return 1

        @flow.function_task(backend=site)
        async def remote():
            return 2


class _BrokenAfterLabel(UtilityTask):
    def __init__(self, flow):
        super().__init__(flow)

        @flow.function_task(backend="site_c")
        async def remote():
            return 2

        raise RuntimeError("component construction failed")


def _sites(**extra):
    config = _dual(inference="ep1", site_b="ep2", site_c="ep3")
    config.update(extra)
    session = DTSession("s1", config)
    for name in ("inference", "site_b", "site_c"):
        session._backends[name] = _FakeBackend(name)
    return session


def test_engine_places_every_task_the_component_registers():
    session = _sites()
    twin = _twin_with(_LabelFlow())

    session._instantiate(Package(_ThreeKinds), twin, engine="site_b")

    assert twin.runtime.flow.labels == [
        ("function", "site_b"),
        ("executable", "site_b"),
        ("prompt", "site_b"),
    ]
    assert twin.engines == {"inference", "site_b"}


def test_without_engine_tasks_stay_unlabelled():
    session = _sites()
    twin = _twin_with(_LabelFlow())

    session._instantiate(Package(_ThreeKinds), twin)

    assert [label for _, label in twin.runtime.flow.labels] == [None] * 3
    assert twin.engines == {"inference"}


def test_a_tasks_own_label_is_kept_checked_and_bound():
    session = _sites()
    twin = _twin_with(_LabelFlow())

    session._instantiate(Package(_Labelled), twin, engine="site_b")

    assert twin.runtime.flow.labels == [("function", "site_b"), ("function", "site_c")]
    assert twin.engines == {"inference", "site_b", "site_c"}


def test_an_unconfigured_label_is_refused_and_binds_nothing():
    session = _sites()
    twin = _twin_with(_LabelFlow())

    with pytest.raises(ValueError, match="not configured"):
        session._instantiate(Package(_Labelled, kwargs={"site": "nowhere"}), twin)

    assert twin.engines == {"inference"}


def test_a_failed_component_binds_nothing():
    session = _sites()
    twin = _twin_with(_LabelFlow())

    with pytest.raises(RuntimeError, match="construction failed"):
        session._instantiate(Package(_BrokenAfterLabel), twin, engine="site_b")

    assert twin.engines == {"inference"}
    # the engine is handed back unpatched
    assert twin.runtime.flow.function_task.__func__ is _LabelFlow.function_task


def test_engine_on_a_verb_is_checked_first():
    session = _sites()

    session._check_engine("site_b")
    session._check_engine("inference")
    session._check_engine(None)

    with pytest.raises(ValueError, match="not configured"):
        session._check_engine("nowhere")
    # explicit placement never aliases: an unconfigured role is refused
    with pytest.raises(ValueError, match="not configured"):
        session._check_engine("learning")
    with pytest.raises(ValueError, match="must be a name"):
        session._check_engine("")


def test_a_lost_engine_is_refused_by_every_labelling_path():
    session = _sites()
    session._endpoints = {"inference": "ep1", "site_b": "ep2", "site_c": "ep3"}
    session.endpoints_lost({"ep3"})

    with pytest.raises(RuntimeError, match="endpoint was lost"):
        session._check_engine("site_c")

    twin = _twin_with(_LabelFlow())
    with pytest.raises(RuntimeError, match="endpoint was lost"):
        session._instantiate(Package(_Labelled), twin)


async def test_the_engine_kwarg_is_consumed_not_forwarded():
    session = _sites()
    seen = {}

    class _Runtime:
        flow = _LabelFlow()

        def add_investigator(self, component, *args, **kwargs):
            seen.update(kwargs)

    twin = TwinInstance("t1")
    twin.runtime = _Runtime()

    await session._verb_add_investigator(
        twin, Package(_ThreeKinds), "in", "out", engine="site_b", knob=1
    )

    assert seen == {"knob": 1}
    assert twin.engines == {"inference", "site_b"}


def test_a_placed_learner_gets_its_learner_label():
    learn = pytest.importorskip("digitaltwin.learn")

    class _Learner(learn.StreamingLearnerInvestigator):
        def __init__(self, flow, learn_backend=None):
            self.flow, self.learn_backend = flow, learn_backend

    # no 'learning' engine: the placed one, unless that is the default
    session = _sites()
    twin = _twin_with(_LabelFlow())
    placed = session._instantiate(Package(_Learner), twin, engine="site_b")
    assert placed.learn_backend == "site_b"
    assert twin.engines == {"inference", "site_b"}

    local = session._instantiate(
        Package(_Learner), _twin_with(_LabelFlow()), engine="inference"
    )
    assert local.learn_backend is None

    # a 'learning' engine wins, and a lost one is refused
    session = DTSession("s2", _dual(inference="ep1", learning="hpc1", site_b="ep2"))
    for name in ("inference", "learning", "site_b"):
        session._backends[name] = _FakeBackend(name)
    twin = _twin_with(_LabelFlow())
    learner = session._instantiate(Package(_Learner), twin, engine="site_b")
    assert learner.learn_backend == "learning"
    assert twin.engines == {"inference", "learning", "site_b"}

    session._endpoints = {"learning": "hpc1"}
    session.endpoints_lost({"hpc1"})
    with pytest.raises(RuntimeError, match="endpoint was lost"):
        session._instantiate(Package(_Learner), _twin_with(_LabelFlow()))


def test_the_session_summary_lists_every_engine():
    session = DTSession("s1", _dual(inference="ep1", site_b="ep2"))

    assert session.summary()["endpoints"] == {
        "inference": "ep1",
        "learning": None,
        "site_b": "ep2",
    }


def _init_plugin():
    class _Plugin:
        async def connect_stream(self, twin_id, timeout):
            return _FakeStream()

    return _Plugin()


async def test_a_lost_extra_engine_does_not_block_new_twins():
    session = DTSession("s1", _dual(inference="ep1", site_b="ep2"))
    _slow_build(session, 0)
    session._plugin = _init_plugin()

    session.endpoints_lost({"ep2"})

    twin = session.twins["t1"] = TwinInstance("t1")
    await session._init_twin(twin)

    assert twin.runtime is not None
    assert sorted(session._backends) == ["inference"]
    with pytest.raises(RuntimeError, match="endpoint was lost"):
        session._check_engine("site_b")
    await session.close()


async def test_a_lost_default_engine_still_fails_new_twins():
    session = DTSession(
        "s1", {**_dual(inference="ep1", site_b="ep2"), "default_engine": "site_b"}
    )
    _slow_build(session, 0)
    session._plugin = _init_plugin()

    session.endpoints_lost({"ep2"})

    twin = session.twins["t1"] = TwinInstance("t1")
    await session._init_twin(twin)

    assert twin.state == "failed"
    assert "recreate the session" in twin.last_error
    await session.close()


def test_register_session_accepts_named_engines(client):
    resp = client.post(
        "/dt/register_session",
        json={
            "config": {
                **_dual(inference="ep1", site_b="ep2"),
                "default_engine": "site_b",
            }
        },
    )

    assert resp.status_code == 200


@pytest.mark.parametrize(
    "engines, match",
    [
        ({"site-b": {"endpoint_name": "ep2"}}, "identifier"),
        ({"site_b": "ep2"}, "object"),
        ({"site_b": {"backends": ["concurrent"]}}, "endpoint_name"),
        (["inference"], "'engines' must be an object"),
    ],
)
def test_register_session_rejects_bad_engines(client, engines, match):
    resp = client.post("/dt/register_session", json={"config": {"engines": engines}})

    assert resp.status_code == 400
    assert match in resp.text


def test_a_learning_engine_may_still_auto_select(client):
    resp = client.post(
        "/dt/register_session",
        json={"config": {"engines": {"learning": {"backends": ["concurrent"]}}}},
    )

    assert resp.status_code == 200


def test_default_engine_must_be_a_role_or_configured(client):
    resp = client.post(
        "/dt/register_session",
        json={"config": {**_dual(inference="ep1"), "default_engine": "site_b"}},
    )

    assert resp.status_code == 400
    assert "default_engine" in resp.text


def test_the_deployment_default_stays_a_role(client, monkeypatch):
    monkeypatch.setenv(ENV_DEFAULT_ENGINE, "site_b")

    resp = client.post(
        "/dt/register_session", json={"config": _dual(inference="ep1", site_b="ep2")}
    )

    assert resp.status_code == 400


def test_a_reattach_ignores_the_engines_config(client):
    sid = client.post("/dt/register_session", json={}).json()["sid"]
    resp = client.post(
        "/dt/register_session", json={"sid": sid, "config": {"engines": {"site-b": {}}}}
    )

    assert resp.status_code == 200
    assert resp.json()["reattached"] is True


def test_the_client_sends_engine_only_when_set():
    from digitaltwin.service.client import _placed

    assert _placed(None) == {}
    assert _placed("site_b") == {"engine": "site_b"}
