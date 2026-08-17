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

# every field the renderer reads off a twin summary
TWIN_KEYS = {"twin_id", "state", "last_error", "age", "metrics"}
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
    """The poll response, verbatim -- including the engine endpoints the
    lanes are drawn from and the data plane's backend badge."""

    snapshots = [f["data"] for f in recording["frames"]
                 if f["kind"] == "snapshot"]

    assert all("sessions" in s and "stream_broker" in s for s in snapshots)
    assert {s["stream_broker"]["backend"] for s in snapshots} <= {"zmq", "orbit"}

    sessions = [s for snap in snapshots for s in snap["sessions"]]
    assert sessions

    for session in sessions:
        assert {"sid", "age", "engines", "endpoints", "twins"} <= set(session)
        assert set(session["endpoints"]) == {"task", "exsitu"}
        for twin in session["twins"]:
            assert TWIN_KEYS <= set(twin)


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
        assert {"endpoint", "plugin", "topic", "data"} <= set(event)

    assert len({e["endpoint"] for e in tasks}) == 2, "both role lanes"
    states = {e["data"]["state"] for e in tasks}
    assert "RUNNING" in states and states & {"DONE", "COMPLETED"}
    assert all(e["data"]["uid"] for e in tasks)


def test_the_page_and_the_plugin_ship_the_same_assets():
    """Whatever the standalone page loads, the plugin must be able to
    serve -- the live mode only works same-origin."""

    pytest.importorskip("radical.orbit")
    from digitaltwin.service.plugin import UI_ASSETS

    page = (UI / "index.html").read_text()
    for asset in re.findall(r'<script src="([^"]+)">', page):
        assert asset in UI_ASSETS

    for asset in UI_ASSETS:
        assert (UI / asset).exists()
