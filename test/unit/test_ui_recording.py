"""The bundled dashboard recording, against the schema its reader expects.

`dt_dash.js` documents the recording format and consumes it; this is the
other half of that contract -- a Python check that the sample shipped in
the package still parses, still carries both frame kinds, and still uses
the field names the renderer reads.  It is what keeps a change on one side
from silently breaking the other.

The sample is a `.js` file assigning one JSON object, not a `.json` one:
a classic `<script src>` loads from `file://` where `fetch()` does not,
which is what lets the standalone page self-demo with nothing running.
"""

import json
import re

from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[2] / "src/digitaltwin/service/ui"
ASSIGNMENT = "window.DT_SAMPLE ="

SCHEMA = "dt-dash-recording/1"

# `PubSubClient.TOPIC_TERMINATOR`, spelled out here so a change to it has
# to be made twice -- the JS strips exactly this character
TOPIC_TERMINATOR = "\x00"

# every field the renderer reads off a twin summary
TWIN_KEYS = {"twin_id", "state", "last_error", "age", "metrics", "calls",
             "tasks"}
METRIC_KEYS = {"value", "threshold", "operator", "should_stop", "windows",
               "history", "component"}


@pytest.fixture(scope="module")
def recording() -> dict:
    text = (UI / "dt_sample.js").read_text()
    assert ASSIGNMENT in text, "the sample must assign window.DT_SAMPLE"

    return json.loads(text.split(ASSIGNMENT, 1)[1].strip().rstrip(";"))


def test_the_renderer_and_the_sample_agree_on_the_schema(recording):
    """One version string, in both languages."""

    js = (UI / "dt_dash.js").read_text()
    declared = re.search(r"SCHEMA\s*=\s*'([^']+)'", js)

    assert declared and declared.group(1) == SCHEMA
    assert recording["schema"] == SCHEMA


def test_the_envelope_carries_its_provenance(recording):
    assert recording["broker"]
    assert recording["recorded"].endswith("Z")
    assert recording["duration"] > 30, "a demo shorter than this shows nothing"
    assert recording["frames"]


def test_frames_are_ordered_and_of_the_two_known_kinds(recording):
    kinds = {}
    last = -1.0

    for frame in recording["frames"]:
        assert frame["t"] >= last, "frames must be ordered by t"
        last = frame["t"]
        assert set(frame) == {"t", "kind", "data"}
        kinds[frame["kind"]] = kinds.get(frame["kind"], 0) + 1

    assert set(kinds) == {"snapshot", "event"}
    assert kinds["snapshot"] > 30 and kinds["event"] > 30


def test_snapshots_are_admin_sessions_responses(recording):
    """The poll response -- including the engine endpoints the lanes are
    drawn from and the data plane's backend badge.  The bundled sample was
    captured against the M3 data plane, which is the deployment a
    production service runs (risk R7)."""

    snapshots = [f["data"] for f in recording["frames"]
                 if f["kind"] == "snapshot"]

    assert all("sessions" in s and "stream_broker" in s for s in snapshots)
    assert {s["stream_broker"]["backend"] for s in snapshots} == {"orbit"}

    sessions = [s for snap in snapshots for s in snap["sessions"]]
    assert sessions

    for session in sessions:
        assert {"sid", "age", "engines", "endpoints", "twins"} <= set(session)
        assert set(session["endpoints"]) == {"inference", "learning"}
        for twin in session["twins"]:
            assert TWIN_KEYS <= set(twin)


def test_the_client_calls_are_counted(recording):
    """The only record a synchronous verb leaves behind, and the source of
    the two client-ward arcs: a count that goes up."""

    counts = []

    for frame in recording["frames"]:
        if frame["kind"] != "snapshot":
            continue
        for session in frame["data"]["sessions"]:
            for twin in session["twins"]:
                calls = twin["calls"]
                assert all(isinstance(n, int) for n in calls.values())
                if "get_inference" in calls:
                    counts.append(calls["get_inference"])

    assert counts, "no twin was ever asked for an inference"
    assert max(counts) > min(counts), "the count never moved: no arc"
    # the verbs that built the twin are counted too
    verbs = {verb for frame in recording["frames"]
             if frame["kind"] == "snapshot"
             for s in frame["data"]["sessions"] for t in s["twins"]
             for verb in t["calls"]}
    assert {"add_task", "start", "get_inference"} <= verbs


def test_a_failed_twin_is_reaped_by_the_client(recording):
    """The service keeps a failed twin listed; closing it is the client's
    job, and the demo does it so the card goes away."""

    seen_failed, still_there = set(), set()

    for frame in recording["frames"]:
        if frame["kind"] != "snapshot":
            continue
        present = {t["twin_id"] for s in frame["data"]["sessions"]
                   for t in s["twins"]}
        for s in frame["data"]["sessions"]:
            for t in s["twins"]:
                if t["state"] == "failed":
                    seen_failed.add(t["twin_id"])
        still_there = present

    assert seen_failed, "the demo never fails a twin"
    assert not (seen_failed & still_there), "a failed twin was never reaped"


def test_the_demo_shows_the_states_worth_showing(recording):
    """A sample that never fails a twin, never closes one and never
    converges a criterion would not exercise the renderer."""

    states, errors, metrics = set(), [], []
    counts = []

    for frame in recording["frames"]:
        if frame["kind"] != "snapshot":
            continue
        twins = [t for s in frame["data"]["sessions"] for t in s["twins"]]
        counts.append(len(twins))
        for twin in twins:
            states.add(twin["state"])
            if twin["last_error"]:
                errors.append(twin["last_error"])
            metrics.extend(twin["metrics"].values())

    assert {"running", "failed"} <= states
    assert errors
    assert max(counts) > min(counts), "no twin ever came or went"

    assert metrics
    for metric in metrics:
        assert METRIC_KEYS >= set(metric)
        assert isinstance(metric["should_stop"], bool)
        assert isinstance(metric["history"], list)
    # a criterion that never meets its target shows no convergence
    assert any(m["should_stop"] for m in metrics)


def test_events_are_sse_notifications_the_lanes_can_place(recording):
    """The gateway's inner notification envelope: the endpoint names the
    role lane, and rhapsody's task states drive the tiles."""

    events = [f["data"] for f in recording["frames"] if f["kind"] == "event"]
    tasks = [e for e in events if e["topic"] == "task_status"]

    assert tasks
    for event in events:
        assert {"plugin", "topic", "data"} <= set(event)
    for event in tasks:
        # a task's endpoint is what picks its role lane
        assert event["endpoint"]
        # the tiles read these two and a recording keeps nothing else
        assert set(event["data"]) == {"uid", "state"}

    assert len({e["endpoint"] for e in tasks}) == 2, "both role lanes"
    states = {e["data"]["state"] for e in tasks}
    assert "RUNNING" in states and states & {"DONE", "COMPLETED"}
    assert all(e["data"]["uid"] for e in tasks)


def test_the_tasks_in_the_sample_are_attributable_to_their_twins(recording):
    """Exact task attribution, which is the whole point of the twins' own
    `tasks` field: every uid a notification carries should be one some twin
    said it submitted.

    The map is cumulative and the uid ring is repeated by every poll, so a
    recording carries each uid once (see `captureFrame`); a handful of
    unresolved uids at the very start is the join race, not a failure -- the
    first tasks are submitted before the first poll that could report them.
    """

    owners: dict = {}
    seen: list = []

    for frame in recording["frames"]:
        if frame["kind"] == "snapshot":
            for session in frame["data"]["sessions"]:
                for twin in session["twins"]:
                    assert isinstance(twin["tasks"], list)
                    for uid in twin["tasks"]:
                        assert isinstance(uid, str) and uid
                        # a uid belongs to exactly one twin, ever
                        assert owners.setdefault(uid, twin["twin_id"]) \
                            == twin["twin_id"]
                        seen.append(uid)
            continue

        event = frame["data"]
        if event.get("topic") == "task_status":
            payload = [event["data"]]
        elif event.get("topic") == "task_status_batch":
            payload = event["data"]["tasks"]
        else:
            continue

        for task in payload:
            if task.get("uid"):
                seen.append(task["uid"])

    # each uid written once, not once per poll: the ring is repetitive and a
    # recording that kept every repeat would be mostly uids
    assert len(seen) > len(owners), "the sample carries no task events"
    assert len(owners) > 50, "too few attributed tasks to demonstrate anything"

    uids = {t["uid"] for f in recording["frames"] if f["kind"] == "event"
            for t in ([f["data"]["data"]]
                      if f["data"].get("topic") == "task_status"
                      else f["data"]["data"].get("tasks", [])
                      if f["data"].get("topic") == "task_status_batch" else [])
            if t.get("uid")}

    resolved = [uid for uid in uids if uid in owners]
    rate = len(resolved) / len(uids)

    assert rate > 0.9, f"only {rate:.0%} of task uids resolve to a twin"


def test_the_stream_events_are_real_and_attributable(recording):
    """The M3 data plane's own traffic, as the twins actually published it.

    Each pulse is drawn from its topic alone -- which names the twin and
    the dtype -- so a topic that does not resolve to a twin in the same
    recording would draw a pulse on nothing.
    """

    streams = [f["data"] for f in recording["frames"]
               if f["kind"] == "event" and f["data"]["plugin"] == "dt_stream"]

    assert len(streams) > 50, "an orbit-backend capture carries stream traffic"

    twins = {t["twin_id"] for f in recording["frames"]
             if f["kind"] == "snapshot"
             for s in f["data"]["sessions"] for t in s["twins"]}
    hit, labels = set(), set()

    for event in streams:
        assert event["topic"].startswith("dt/")
        # `PubSubClient.topic()`: dt/<namespace>/dtypes/<label> + terminator
        namespace, sep, label = event["topic"][3:].partition("/dtypes/")
        assert sep and label.endswith(TOPIC_TERMINATOR)
        assert namespace in twins
        hit.add(namespace)
        labels.add(label.rstrip(TOPIC_TERMINATOR))
        # neither the cloudpickled payload nor the publisher's participant
        # name is carried: the topic is what draws the pulse
        assert event["data"] == {}
        assert "endpoint" not in event

    assert len(hit) > 1, "pulses on one twin only would not show the fan-out"
    assert len(labels) > 1, "more than one dtype should be flowing"


def test_the_topic_the_dashboard_parses_is_the_one_the_client_builds():
    """The cross-language contract behind every pulse: `applyStream` splits
    the topic on `/` and strips the terminator, and this is the code that
    produces it.  A change to either side has to fail here."""

    streaming = pytest.importorskip("digitaltwin.streaming")
    from digitaltwin.components import DataType

    client = streaming.PubSubClient.__new__(streaming.PubSubClient)
    client.namespace = "11111111-2222-3333-4444-555555555555"
    topic = streaming.PubSubClient.topic(client, DataType("sensor"))

    parts = topic.split("/")

    assert parts[0] == "dt"
    assert parts[1] == client.namespace
    assert parts[2] == "dtypes"
    assert parts[3].rstrip(TOPIC_TERMINATOR) == "sensor"
    assert TOPIC_TERMINATOR == streaming.PubSubClient.TOPIC_TERMINATOR


def test_the_page_and_the_plugin_ship_the_same_assets():
    """Whatever the standalone page loads, the plugin must be able to
    serve -- the live mode only works same-origin."""

    pytest.importorskip("radical.orbit")
    from digitaltwin.service.plugin import UI_ASSETS

    page = (UI / "index.html").read_text()
    # the page loads its scripts with a `?v=` cache-buster; the plugin routes
    # on the path and never sees it, so the query comes off before the check
    scripts = re.findall(r'<script src="([^"?]+)(\?[^"]*)?">', page)
    assert scripts, "the page loads no scripts at all"

    for asset, _query in scripts:
        assert asset in UI_ASSETS

    for asset in UI_ASSETS:
        assert (UI / asset).exists()

    # and the buster has to name the version the dashboard reports, or it
    # stops busting the moment someone edits the dashboard
    version = re.search(r"const VERSION\s*=\s*'([^']+)'",
                        (UI / "dt_dash.js").read_text()).group(1)
    for _asset, query in scripts:
        assert query == f"?v={version}", "index.html cache-buster is stale"
