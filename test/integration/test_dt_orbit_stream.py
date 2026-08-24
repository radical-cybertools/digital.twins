"""Integration tests for M3: the DT data plane on ORBIT eventing.

Against a `dt` deployment started with `DT_STREAM_BACKEND=orbit`: full
twins run, streams flow, twins tear down -- and no ZMQ broker exists
anywhere, which is the point of the milestone (plan risk R7).  The
subscriber the tests attach is itself an ORBIT participant, so even the
observation path opens no port.
"""

import asyncio
import os
import uuid

from pathlib import Path

import pytest

from digitaltwin.components import TRUTHY, TypedData
from digitaltwin.config import BACKEND_ORBIT
from digitaltwin.service import register_user_modules
from digitaltwin.streaming import connect_stream_client

import learner_components
import twin_components

from conftest import ORBIT_BROKER_URL
from test_dt_learner import await_learned, build_learner_twin, infer
from test_dt_service import await_state, broker_fds, build_pipeline
from twin_components import (
    ECHO_DTYPE,
    INFERENCE_DTYPE,
    SENSOR_DTYPE,
    OffsetModel,
)

pytestmark = pytest.mark.integration

register_user_modules([learner_components, twin_components])

COLLECT_TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def collect(twin, dtype, count, timeout=COLLECT_TIMEOUT):
    """Subscribe to one twin's stream and collect `count` messages.

    The subscriber joins the ORBIT star as an ordinary participant: no
    addresses, no ports, the same token as every other call.
    """

    client = await connect_stream_client(
        twin, backend=BACKEND_ORBIT, broker_url=ORBIT_BROKER_URL
    )
    queue: asyncio.Queue = asyncio.Queue()

    try:
        await client.subscribe_to_dtype(dtype, queue)
        return [
            (await asyncio.wait_for(queue.get(), timeout)).data
            for _ in range(count)
        ]
    finally:
        await client.close()


def child_pids(pid: int) -> list:
    """The child processes of `pid` (Linux only).

    An embedded DT stream broker is a spawned subprocess of the plugin
    host, so "no ZMQ broker was started" is literally "this process has
    no children".
    """

    if not Path("/proc/self/status").exists():
        pytest.skip("no /proc: cannot enumerate child processes")

    children = []

    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            status = Path(f"/proc/{entry}/status").read_text()
        except OSError:  # it exited under us
            continue

        for line in status.splitlines():
            if line.startswith("PPid:") and int(line.split()[1]) == pid:
                children.append(int(entry))
                break

    return children


# ---------------------------------------------------------------------------
# a full twin, no ZMQ anywhere
# ---------------------------------------------------------------------------

def test_a_full_twin_runs_on_the_orbit_data_plane(orbit_dt, twin_id):
    """sensor -> investigator -> sink, with every stream hop an event."""

    orbit_dt.create_twin(twin_id)
    build_pipeline(orbit_dt, twin_id, offset=500)
    assert orbit_dt.start(twin_id) == "running"

    seen = asyncio.run(collect(twin_id, ECHO_DTYPE, 3))
    assert len(seen) == 3
    assert all(500 <= value < 500 + 100_000 for value in seen), seen

    # the in-situ inference path is unaffected by the data plane choice
    answer = orbit_dt.get_inference(twin_id, TypedData(SENSOR_DTYPE, 5),
                                    INFERENCE_DTYPE, timeout=120)
    assert answer.data == 505

    assert orbit_dt.twin_close(twin_id) == "closed"
    assert orbit_dt.twin_list() == []


def test_no_zmq_stream_broker_is_started(orbit_dt, orbit_broker, twin_id):
    """R7 closed: the deployment owns no stream ports at all.

    The embedded ZMQ broker is a spawned subprocess of the plugin host,
    so the assertion is that the host has no children -- after a twin has
    actually run, which is when the ZMQ deployment would have started one.
    """

    orbit_dt.create_twin(twin_id)
    build_pipeline(orbit_dt, twin_id)
    orbit_dt.start(twin_id)

    assert asyncio.run(collect(twin_id, ECHO_DTYPE, 1))

    listing = orbit_dt.admin_sessions()
    assert listing["stream_broker"] == {"backend": "orbit"}

    assert child_pids(orbit_broker.pid) == [], (
        "the orbit data plane must not spawn a stream broker")

    orbit_dt.twin_close(twin_id)


def test_identical_dtype_labels_do_not_cross_subscribe(orbit_dt):
    """Namespacing isolation on the second backend: two twins, one label,
    one broker -- and now one shared event stream."""

    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    bands = {first: 1_000_000, second: 2_000_000}

    for twin, offset in bands.items():
        orbit_dt.create_twin(twin)
        build_pipeline(orbit_dt, twin, offset=offset)
        orbit_dt.start(twin)

    seen_first = asyncio.run(collect(first, ECHO_DTYPE, 3))
    seen_second = asyncio.run(collect(second, ECHO_DTYPE, 3))

    def in_band(values, base):
        return all(base <= v < base + 100_000 for v in values)

    assert in_band(seen_first, bands[first]), seen_first
    assert in_band(seen_second, bands[second]), seen_second

    # closing one leaves the other producing
    assert orbit_dt.twin_close(first) == "closed"
    assert asyncio.run(collect(second, ECHO_DTYPE, 2))
    assert orbit_dt.twin_close(second) == "closed"


# ---------------------------------------------------------------------------
# the M2 learner path, on the new data plane
# ---------------------------------------------------------------------------

def test_a_learner_twin_learns_off_the_orbit_stream(orbit_dt, twin_id):
    """The ex-situ learner is fed from the twin's input stream, so it is
    the component that depends most on the data plane.

    One backend here: `'learning'` aliases `'inference'` when it is not
    configured, and which endpoint the learner tasks land on is M2's
    question, not this one.
    """

    build_learner_twin(orbit_dt, twin_id)

    bootstrap = infer(orbit_dt, twin_id)
    learned = await_learned(orbit_dt, twin_id)

    assert learned != bootstrap, (bootstrap, learned)
    assert orbit_dt.twin_close(twin_id) == "closed"


# ---------------------------------------------------------------------------
# teardown
# ---------------------------------------------------------------------------

def test_twin_churn_leaks_no_participants(orbit_dt, orbit_broker):
    """Every twin brings its own participant connection up and takes it
    down again -- churn must not accumulate sockets or threads."""

    def cycle():
        twin = str(uuid.uuid4())
        orbit_dt.create_twin(twin)
        build_pipeline(orbit_dt, twin)
        orbit_dt.start(twin)
        await_state(orbit_dt, twin, "running")
        orbit_dt.twin_close(twin)

    cycle()  # the first cycle pays the engine startup
    before = broker_fds(orbit_broker.pid)

    for _ in range(4):
        cycle()

    assert orbit_dt.twin_list() == []
    assert child_pids(orbit_broker.pid) == []

    after = broker_fds(orbit_broker.pid)
    assert after <= before + 8, f"broker fds {before} -> {after}"


def test_an_oversized_payload_is_a_clear_error(orbit_dt, twin_id):
    """The 4 MiB frame cap surfaces as a refusal, not as a stream that
    quietly drops every large sample."""

    orbit_dt.create_twin(twin_id)
    orbit_dt.add_investigator(twin_id, orbit_dt.package(OffsetModel, offset=1),
                              SENSOR_DTYPE, INFERENCE_DTYPE)
    orbit_dt.start(twin_id)

    async def publish_a_huge_sample():
        client = await connect_stream_client(
            twin_id, backend=BACKEND_ORBIT, broker_url=ORBIT_BROKER_URL
        )
        try:
            with pytest.raises(ValueError, match="byte ceiling"):
                await client.publish(SENSOR_DTYPE,
                                     b"x" * (client._backend.payload_cap() + 1))

            # ... and a payload that fits still goes through
            await client.publish(SENSOR_DTYPE, 1)
        finally:
            await client.close()

    asyncio.run(publish_a_huge_sample())

    # the twin survived the refusal and is still serving
    assert orbit_dt.twin(twin_id)["state"] == "running"
    assert orbit_dt.get_inference(twin_id, TypedData(SENSOR_DTYPE, 1),
                                  INFERENCE_DTYPE, timeout=120).data == 2


def test_a_twin_whose_stream_is_a_participant_reports_the_backend(orbit_dt):
    """The admin listing names the data plane -- an operator must be able
    to tell which one a deployment is running."""

    assert orbit_dt.admin_sessions()["stream_broker"]["backend"] == BACKEND_ORBIT


def test_the_endpoint_hosted_dt_smoke_still_holds(orbit_dt, twin_id):
    """A twin that never streams must still come up and go away cleanly
    on the orbit backend (the stream client is built regardless)."""

    orbit_dt.create_twin(twin_id)
    orbit_dt.add_investigator(twin_id, orbit_dt.package(OffsetModel, offset=1),
                              SENSOR_DTYPE, INFERENCE_DTYPE)
    assert orbit_dt.start(twin_id) == "running"
    assert orbit_dt.twin_close(twin_id) == "closed"
    assert orbit_dt.twin_list() == []


def test_a_persistent_component_publishes_through_the_injected_client(
    orbit_dt, twin_id
):
    """The persistent-component contract is untouched by M3: the twin's
    sensor publishes through `RuntimeAPI.stream`, knowing nothing about
    the transport underneath it."""

    orbit_dt.create_twin(twin_id)
    orbit_dt.add_task(twin_id, orbit_dt.package(twin_components.CountingSensor),
                      TRUTHY, SENSOR_DTYPE, is_persistent=True)
    orbit_dt.start(twin_id)

    seen = asyncio.run(collect(twin_id, SENSOR_DTYPE, 3))
    assert seen == sorted(seen), seen

    orbit_dt.twin_close(twin_id)
