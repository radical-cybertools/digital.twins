"""Integration tests for the `dt` plugin against a live ORBIT stack.

Covers the DTaaS plan's M1 item 9: two concurrent twins in one session,
independent teardown, twin churn with a leak assertion, `twin_close`
with an inference in flight, client disconnect -> reattach by sid,
idempotent retries, and a component crash surfacing as `failed` plus a
last error through `twin_list`.
"""

import asyncio
import os
import threading
import time
import uuid

from pathlib import Path

import pytest

from radical.orbit import EndpointRuntime

from digitaltwin.components import NULL_DTYPE, TRUTHY, TypedData
from digitaltwin.service import register_user_modules
from digitaltwin.streaming import connect_stream_client

import twin_components

from conftest import ENGINES, LOGS
from twin_components import (
    ECHO_DTYPE,
    INFERENCE_DTYPE,
    SENSOR_DTYPE,
    CountingSensor,
    CrashingTask,
    EchoSink,
    MisplacedFunctionTask,
    OffsetModel,
    SlowModel,
    SlowTaskModel,
)

pytestmark = pytest.mark.integration

register_user_modules([twin_components])

POLL_TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def build_pipeline(dt, twin, offset=100):
    """sensor -> investigator -> echo sink, the standard test twin."""

    dt.add_task(twin, dt.package(CountingSensor), TRUTHY, SENSOR_DTYPE,
                is_persistent=True)
    dt.add_investigator(twin, dt.package(OffsetModel, offset=offset),
                        SENSOR_DTYPE, INFERENCE_DTYPE)
    dt.add_task(twin, dt.package(EchoSink), INFERENCE_DTYPE, NULL_DTYPE)


def await_state(dt, twin, *states, timeout=POLL_TIMEOUT):
    """Poll `twin_list` -- the only observation mechanism in v1."""

    deadline = time.time() + timeout

    while True:
        entry = dt.twin(twin)
        if entry["state"] in states:
            return entry
        if time.time() > deadline:
            pytest.fail(f"twin {twin} stuck in {entry['state']}: {entry}")
        time.sleep(0.25)


def stream_addresses(dt):
    """The service's embedded stream broker, from the admin listing."""

    addrs = dt.admin_sessions()["stream_broker"]["addresses"]
    assert addrs, "the service reports no stream broker"

    return addrs


async def collect(dt, twin, dtype, count, timeout=POLL_TIMEOUT):
    """Subscribe to one twin's stream and collect `count` messages.

    Loopback only -- the service and the tests share a host here.
    """

    pub_addr, sub_addr = stream_addresses(dt)
    client = await connect_stream_client(twin, pub_addr, sub_addr)
    queue: asyncio.Queue = asyncio.Queue()

    try:
        await client.subscribe_to_dtype(dtype, queue)
        return [
            (await asyncio.wait_for(queue.get(), timeout)).data
            for _ in range(count)
        ]
    finally:
        await client.close()


def broker_fds(pid):
    """Open file descriptors of *the* broker under test (Linux only).

    The pid comes from the fixture: counting descriptors of whatever
    process on the host happens to look like a broker would make the
    leak assertion meaningless.
    """

    fds = Path(f"/proc/{pid}/fd")
    if not Path("/proc/self/fd").exists():
        pytest.skip("no /proc: cannot count descriptors")

    try:
        return len(os.listdir(fds))
    except OSError as exc:
        pytest.fail(f"cannot read {fds} of the broker under test: {exc}")


# ---------------------------------------------------------------------------
# the happy path
# ---------------------------------------------------------------------------

def test_inference_roundtrip(dt, twin_id):
    """A twin computes on the endpoint and answers a client's query."""

    dt.create_twin(twin_id)
    dt.add_investigator(twin_id, dt.package(OffsetModel, offset=7),
                        SENSOR_DTYPE, INFERENCE_DTYPE)
    assert dt.start(twin_id) == "running"

    answer = dt.get_inference(twin_id, TypedData(SENSOR_DTYPE, 5),
                              INFERENCE_DTYPE, timeout=120)

    assert isinstance(answer, TypedData)
    assert answer.data == 12

    graph = dt.describe(twin_id)
    assert graph["namespace"] == twin_id
    assert graph["state"] == "running"


def test_two_twins_one_session_are_independent(dt):
    """Two twins, identical dtype labels, one session.

    Their streams must not cross (topic namespacing), and closing one
    must leave the other running.
    """

    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    bands = {first: 1_000_000, second: 2_000_000}

    for twin, offset in bands.items():
        dt.create_twin(twin)
        build_pipeline(dt, twin, offset=offset)
        dt.start(twin)

    seen_first = asyncio.run(collect(dt, first, ECHO_DTYPE, 3))
    seen_second = asyncio.run(collect(dt, second, ECHO_DTYPE, 3))

    # same dtype label, different namespace: no cross-subscription
    def in_band(values, base):
        return all(base <= v < base + 100_000 for v in values)

    assert in_band(seen_first, bands[first]), seen_first
    assert in_band(seen_second, bands[second]), seen_second

    assert dt.twin_close(first) == "closed"

    # the sibling is untouched and still producing
    assert dt.twin(second)["state"] == "running"
    assert asyncio.run(collect(dt, second, ECHO_DTYPE, 2))

    assert {t["twin_id"] for t in dt.twin_list()} == {second}


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------

def test_twin_churn_leaks_nothing(dt, broker_pid):
    """Create/close cycles must not accumulate twins, engines or fds."""

    def cycle():
        twin = str(uuid.uuid4())
        dt.create_twin(twin)
        build_pipeline(dt, twin)
        dt.start(twin)
        await_state(dt, twin, "running")
        dt.twin_close(twin)

    cycle()  # first cycle pays the engine + stream broker startup
    before = broker_fds(broker_pid)

    for _ in range(4):
        cycle()

    assert dt.twin_list() == []

    session = next(s for s in dt.admin_sessions()["sessions"]
                   if s["sid"] == dt.sid)
    # one engine per session, never one per twin
    assert session["engines"] == ["learning"]
    assert session["twins"] == []

    after = broker_fds(broker_pid)
    assert after <= before + 8, f"broker fds {before} -> {after}"


@pytest.mark.parametrize("model", [SlowModel, SlowTaskModel],
                         ids=["local-wait", "backend-task"])
def test_twin_close_with_inference_in_flight(dt, twin_id, model):
    """A `twin_close` must not be held up by -- nor strand -- a call in
    flight; the caller gets a prompt, clear error.

    Twice over: once where the inference waits in the service, and once
    where it waits on a real task running on the endpoint.
    """

    dt.create_twin(twin_id)
    dt.add_investigator(twin_id, dt.package(model), SENSOR_DTYPE,
                        INFERENCE_DTYPE)
    dt.start(twin_id)

    failure = {}
    started = threading.Event()

    def infer():
        started.set()
        try:
            dt.get_inference(twin_id, TypedData(SENSOR_DTYPE, 1),
                             INFERENCE_DTYPE, timeout=300)
            failure["result"] = "returned unexpectedly"
        except Exception as exc:
            failure["error"] = str(exc)

    caller = threading.Thread(target=infer, daemon=True)
    caller.start()
    started.wait(5)
    time.sleep(2)  # let the inference reach the runtime

    t0 = time.time()
    assert dt.twin_close(twin_id) == "closed"
    assert time.time() - t0 < 30, "twin_close waited for the inference"

    caller.join(30)
    assert not caller.is_alive()
    assert "error" in failure, failure
    assert "closed" in failure["error"], failure


def test_idempotent_retries(dt, twin_id):
    """The bearer-sid retry path: every verb a client may resend twice."""

    dt.create_twin(twin_id)
    # same uuid again: a no-op reporting current state, not a second twin
    dt.create_twin(twin_id)
    assert len(dt.twin_list()) == 1

    dt.add_investigator(twin_id, dt.package(OffsetModel), SENSOR_DTYPE,
                        INFERENCE_DTYPE)

    assert dt.start(twin_id) == "running"
    assert dt.start(twin_id) == "running"

    assert dt.stop(twin_id) == "stopped"
    assert dt.stop(twin_id) == "stopped"

    assert dt.twin_close(twin_id) == "closed"
    assert dt.twin_close(twin_id) == "closed"
    assert dt.twin_list() == []


def test_start_after_stop_is_an_error(dt, twin_id):
    """`stop` is terminal in v1."""

    dt.create_twin(twin_id)
    dt.start(twin_id)
    dt.stop(twin_id)

    with pytest.raises(RuntimeError, match="terminal"):
        dt.start(twin_id)


def test_graph_verb_after_stop_is_a_clear_error(dt, twin_id):
    """The runtime refuses graph changes on a stopped twin; the service
    turns that into a 409 the client can read."""

    dt.create_twin(twin_id)
    dt.stop(twin_id)

    with pytest.raises(RuntimeError, match="graph cannot be changed"):
        dt.add_investigator(twin_id, dt.package(OffsetModel), SENSOR_DTYPE,
                            INFERENCE_DTYPE)


def test_component_crash_surfaces_as_failed(dt, twin_id):
    """A dying component lands in the twin state, not in the log."""

    dt.create_twin(twin_id)
    dt.add_task(twin_id, dt.package(CrashingTask), TRUTHY, NULL_DTYPE,
                is_persistent=True)
    dt.start(twin_id)

    entry = await_state(dt, twin_id, "failed")
    assert "component crashed on purpose" in entry["last_error"]


def test_unknown_twin_and_verb_are_rejected(dt):
    with pytest.raises(RuntimeError, match="unknown twin"):
        dt.start("no-such-twin")


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------

def test_client_disconnect_then_reattach_by_sid(stack, twin_id):
    """Twins survive their client, and the sid gets them back."""

    first = EndpointRuntime(broker_url=stack)
    first.start(wait=True)
    dt = first.get_plugin("broker", "dt", config=ENGINES)
    sid = dt.sid

    dt.create_twin(twin_id)
    build_pipeline(dt, twin_id)
    dt.start(twin_id)

    # the client goes away entirely -- it comes back as a different
    # participant, which is exactly what the bearer sid is for
    first.stop()
    time.sleep(2)

    runtime = EndpointRuntime(broker_url=stack)
    runtime.start(wait=True)
    try:
        again = runtime.get_plugin("broker", "dt", sid=sid)
        assert again.sid == sid

        entry = again.twin(twin_id)
        assert entry["state"] == "running"

        # and it is still doing work
        assert asyncio.run(collect(again, twin_id, ECHO_DTYPE, 2))

        again.twin_close(twin_id)
        again.unregister_session()
    finally:
        runtime.stop()


def test_admin_sessions_lists_twins_and_errors(dt, twin_id):
    dt.create_twin(twin_id)
    dt.add_task(twin_id, dt.package(CrashingTask), TRUTHY, NULL_DTYPE,
                is_persistent=True)
    dt.start(twin_id)
    await_state(dt, twin_id, "failed")

    listing = dt.admin_sessions()
    session = next(s for s in listing["sessions"] if s["sid"] == dt.sid)

    assert session["lifetime"] == "persistent"  # forced by the plugin
    assert session["age"] >= 0
    assert "owner" in session

    twin = next(t for t in session["twins"] if t["twin_id"] == twin_id)
    assert twin["state"] == "failed"
    assert "component crashed on purpose" in twin["last_error"]

    assert listing["stream_broker"]["alive"] is True


def test_twin_ids_are_globally_unique(dt, runtime, twin_id):
    """Twin ids namespace a plugin-wide stream broker, so a second
    session may not reuse a live one."""

    dt.create_twin(twin_id)

    other = runtime.get_plugin("broker", "dt", config=ENGINES)
    try:
        with pytest.raises(RuntimeError, match="already used"):
            other.create_twin(twin_id)
    finally:
        other.unregister_session()


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def test_persistent_function_task_warns(dt, twin_id):
    """The service-side guard for the actual migration mistake."""

    dt.create_twin(twin_id)
    dt.add_task(twin_id, dt.package(MisplacedFunctionTask), TRUTHY,
                NULL_DTYPE, is_persistent=True)

    # scoped to this twin: the log accumulates across the whole session,
    # so an unscoped match would pass on a previous test's warning
    warnings = [line for line in (LOGS / "broker.log").read_text().splitlines()
                if twin_id in line and "function_task" in line]

    assert len(warnings) == 1, warnings
    assert "MisplacedFunctionTask registered 1 function_task" in warnings[0]


def test_version_skew_is_rejected(dt, twin_id):
    """A payload from a skewed interpreter must not reach cloudpickle."""

    dt.create_twin(twin_id)

    resp = dt._request(
        "POST",
        dt._url(f"twin_call/{dt.sid}/{twin_id}"),
        json={"verb": "start", "payload": "", "client": {
            "python": "2.7", "cloudpickle": "0.1"}},
    )

    assert resp.status_code == 400, resp.text
    assert "version skew" in resp.text


# ---------------------------------------------------------------------------
# endpoint-hosted deployment
# ---------------------------------------------------------------------------

def test_endpoint_hosted_smoke(dt_endpoint, inference_endpoint, runtime):
    """The endpoint-hosted mode must not silently rot.

    Create / list / close only -- `get_inference` is the one verb the
    30 s relay backstop can cut short until P0 lands.
    """

    dt = runtime.get_plugin(dt_endpoint, "dt", config=ENGINES)
    twin = str(uuid.uuid4())

    try:
        dt.create_twin(twin)
        assert [t["twin_id"] for t in dt.twin_list()] == [twin]

        dt.add_investigator(twin, dt.package(OffsetModel), SENSOR_DTYPE,
                            INFERENCE_DTYPE)
        assert dt.start(twin) == "running"

        assert dt.twin_close(twin) == "closed"
        assert dt.twin_list() == []

    finally:
        dt.unregister_session()
