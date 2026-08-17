"""Unit tests for the `dt` plugin: policy, wire format, guards.

No ORBIT broker involved -- routes are exercised over Starlette's
`TestClient` (plugin route registration is dual), sessions and the
stream-broker supervisor directly.
"""

import asyncio

from typing import Optional

import pytest

pytest.importorskip("radical.orbit")

from fastapi import FastAPI, HTTPException  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from digitaltwin.components import TRUTHY, DataType, UtilityTask  # noqa: E402
from digitaltwin.runtime import DTRuntime  # noqa: E402
from digitaltwin.service.plugin import UI_ASSETS, PluginDT  # noqa: E402
from digitaltwin.service.session import DTSession, TwinInstance  # noqa: E402
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

    resp = client.post("/dt/register_session", json={},
                       headers={"x-orbit-src": "client.1"})
    sid = resp.json()["sid"]
    assert plugin._records[sid].owner == "client.1"

    again = client.post("/dt/register_session", json={"sid": sid},
                        headers={"x-orbit-src": "client.2"})

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
        "backend": "zmq", "addresses": None, "alive": False}


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
    resp = client.post(f"/dt/twin_call/{sid}/t1",
                       json={"verb": "rm_rf", "payload": "", "client": {}})

    assert resp.status_code == 400
    assert "unknown verb" in resp.text


def test_twin_call_rejects_version_skew(client):
    sid = client.post("/dt/register_session", json={}).json()["sid"]
    resp = client.post(
        f"/dt/twin_call/{sid}/t1",
        json={"verb": "start", "payload": "",
              "client": {"python": "2.7", "cloudpickle": "0.1"}},
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
        json={"verb": "start", "payload": "!! not base64 !!",
              "client": version_stamp()},
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
        await session.twin_call("t1", "start",
                                encode({"args": (1, 2, 3)}), version_stamp())

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


@pytest.mark.parametrize("key, value", [
    ("python", "2.7"),
    ("cloudpickle", "0.1"),
    # by-reference pickling of component classes: any difference counts
    ("digitaltwin", version_stamp()["digitaltwin"] + ".dev1"),
])
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
        self.is_shut_down = False

    def function_task(self, func):
        self.registered.append(func)
        return func

    async def shutdown(self):
        self.is_shut_down = True


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
        session._instantiate(Package(_Persistent), _twin_with(flow),
                             is_persistent=True)

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
        session._instantiate(Package(_Plain), _twin_with(_FakeFlow()),
                             is_persistent=True)

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
        flow = _FakeFlow()
        built.append(flow)
        return flow

    session._create_engine = build

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

    assert built == [flow]
    assert session._engines == {"task": flow}


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
    assert session._engines == {}


async def test_close_shuts_down_a_built_engine():
    session = DTSession("s1")
    _slow_build(session, 0)

    flow = await session.engine()
    await session.close()

    assert flow.is_shut_down
    assert session._engines == {}


# ---------------------------------------------------------------------------
# the 'exsitu' engine (M2)
# ---------------------------------------------------------------------------

def _dual(**endpoints: str) -> dict:
    return {"engines": {name: {"endpoint_name": endpoint}
                        for name, endpoint in endpoints.items()}}


async def test_an_unconfigured_engine_aliases_task():
    """Adding `'exsitu'` must stay a config-only change: without one, a
    learner twin runs both halves on the twin's own engine."""

    session = DTSession("s1", _dual(task="ep1"))
    built = _slow_build(session, 0)

    assert await session.engine("exsitu") is await session.engine("task")
    assert len(built) == 1
    assert sorted(session._engines) == ["task"]


async def test_a_slow_exsitu_build_does_not_hold_up_task():
    """Per-name build tasks and locks: a remote backend taking minutes
    must not serialize ahead of the engine a sibling twin needs."""

    session = DTSession("s1", _dual(task="ep1", exsitu="hpc1"))
    delays = {"task": 0.0, "exsitu": 5.0}

    async def build(name):
        await asyncio.sleep(delays[name])
        return _FakeFlow()

    session._create_engine = build

    slow = asyncio.create_task(session.engine("exsitu"))
    await asyncio.sleep(0.05)

    assert await asyncio.wait_for(session.engine("task"), 1.0)

    slow.cancel()


async def test_a_learner_gets_the_exsitu_engine():
    """Dual-engine injection, by subclass check -- there is no
    user-facing engine selector in v1."""

    learn = pytest.importorskip("digitaltwin.learn")

    class _Learner(learn.StreamingLearnerInvestigator):
        def __init__(self, flow, learn_flow=None):
            self.flow, self.learn_flow = flow, learn_flow

    session = DTSession("s1", _dual(task="ep1", exsitu="hpc1"))
    exsitu = session._engines["exsitu"] = _FakeFlow()

    twin = _twin_with(_FakeFlow())
    component = session._instantiate(Package(_Learner), twin)

    assert component.learn_flow is exsitu
    assert component.flow is twin.runtime.flow
    assert twin.engines == {"task", "exsitu"}


async def test_a_plain_component_never_sees_a_second_engine():
    session = DTSession("s1", _dual(task="ep1", exsitu="hpc1"))
    session._engines["exsitu"] = _FakeFlow()

    twin = _twin_with(_FakeFlow())
    session._instantiate(Package(_Plain), twin)

    assert twin.engines == {"task"}


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
    session._endpoints = {"task": "ep1", "exsitu": "hpc1"}

    learner = _running_twin(session, "learner", "exsitu")
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

    session = DTSession("s1", _dual(task="ep1", exsitu="hpc1"))
    _slow_build(session, 0)

    task_flow = await session.engine("task")
    await session.engine("exsitu")
    session._endpoints = {"task": "ep1", "exsitu": "hpc1"}

    session.endpoints_lost({"hpc1"})

    with pytest.raises(RuntimeError, match="recreate the session"):
        await session.engine("exsitu")

    # the surviving engine is still handed out
    assert await session.engine("task") is task_flow


async def test_a_loss_before_the_build_is_remembered_too():
    """The engine need not have been built for its endpoint to be
    known: the configuration named it."""

    session = DTSession("s1", _dual(task="ep1", exsitu="hpc1"))
    _slow_build(session, 0)

    session.endpoints_lost({"hpc1"})

    with pytest.raises(RuntimeError, match="recreate the session"):
        await session.engine("exsitu")


async def test_a_surviving_topology_change_fails_nothing():
    session = DTSession("s1")
    session._endpoints = {"task": "ep1"}
    twin = _running_twin(session, "t1")

    assert session.endpoints_lost({"someone-else"}) == ()
    assert twin.state == "running"


async def test_the_plugin_routes_lost_participants_to_its_sessions(plugin):
    session = plugin._sessions["s1"] = DTSession("s1")
    session._endpoints = {"task": "ep1"}
    twin = _running_twin(session, "t1")

    await plugin.on_topology_change({
        "ep1": {"liveness": "lost"},
        "ep2": {"liveness": "present"},
    })

    assert twin.state == "failed"
    assert twin.last_error == "engine endpoint lost: ep1"


async def test_a_suspect_participant_is_not_a_loss(plugin):
    """A transient blip reaches `suspect` at most and must never fail a
    twin -- the broker's grace timer decides."""

    session = plugin._sessions["s1"] = DTSession("s1")
    session._endpoints = {"task": "ep1"}
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

    metrics = {"rmse": {"value": 0.4, "threshold": 0.25, "operator": "<",
                        "should_stop": False, "windows": 3,
                        "history": [0.9, 0.6, 0.4]}}


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
    """The dashboard draws one lane per engine *role*; `None` for
    `'exsitu'` is the documented alias of `'task'`, not an omission."""

    single = DTSession("s1", _dual(task="ep1"))
    assert single.summary()["endpoints"] == {"task": "ep1", "exsitu": None}

    dual = DTSession("s2", _dual(task="ep1", exsitu="hpc1"))
    assert dual.summary()["endpoints"] == {"task": "ep1", "exsitu": "hpc1"}


def test_admin_sessions_carries_endpoints_and_metrics(client):
    sid = client.post("/dt/register_session",
                      json={"config": _dual(task="ep1")}).json()["sid"]
    entry = next(s for s in client.get("/dt/admin/sessions").json()["sessions"]
                 if s["sid"] == sid)

    assert entry["endpoints"] == {"task": "ep1", "exsitu": None}


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


@pytest.mark.parametrize("asset", ["dt_dash.js", "dt_sample.js",
                                   "dt_explorer.js"])
def test_the_ui_assets_are_served_as_javascript(client, asset):
    resp = client.get(f"/dt/ui/{asset}")

    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


@pytest.mark.parametrize("asset", [
    "passwd", "plugin.py", ".env",
    # a percent-encoded separator survives the route's `[^/]+` segment, so
    # the allow-list is what has to refuse it -- not the router
    "..%2f..%2fplugin.py", "%2e%2e%2f%2e%2e%2fplugin.py",
    "dt_dash.js%00.png",
])
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
