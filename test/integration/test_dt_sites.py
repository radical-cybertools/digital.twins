"""Named engines: one twin's components on several endpoints ("sites").

Three rhapsody endpoints stand in for three sites, each tagging the tasks
it runs with its own name (`DT_TEST_ENDPOINT_TAG`), so a placement can be
read back from the answer.
"""

import uuid

import pytest

from digitaltwin.components import DataType, TypedData
from digitaltwin.service import register_user_modules

import twin_components

from conftest import (
    DOOMED_ENDPOINT,
    EXSITU_ENDPOINT,
    TASK_ENDPOINT,
    _terminate,
    engines,
)
from test_dt_service import await_state
from twin_components import SiteModel

pytestmark = pytest.mark.integration

register_user_modules([twin_components])

INFER_TIMEOUT = 120.0
LOST_TIMEOUT = 120.0  # the broker's suspect -> lost grace is 10 s

SITES = engines(inference=TASK_ENDPOINT, site_b=EXSITU_ENDPOINT, site_c=DOOMED_ENDPOINT)

PROBES = {
    name: (DataType(f"probe_{name}"), DataType(f"where_{name}"))
    for name in ("a", "b", "c")
}


def _probe(dt, twin, name):
    probe, where = PROBES[name]
    answer = dt.get_inference(twin, TypedData(probe, 1), where, timeout=INFER_TIMEOUT)
    return answer.data


def _site_twin(dt, *, b="site_b", c=None):
    """Three investigators: default engine, placed with `engine=`, and
    labelled by the component itself."""

    twin = str(uuid.uuid4())
    dt.create_twin(twin)
    probe, where = PROBES["a"]
    dt.add_investigator(twin, dt.package(SiteModel, where), probe, where)
    if b is not None:
        probe, where = PROBES["b"]
        dt.add_investigator(twin, dt.package(SiteModel, where), probe, where, engine=b)
    if c is not None:
        probe, where = PROBES["c"]
        dt.add_investigator(twin, dt.package(SiteModel, where, site=c), probe, where)
    dt.start(twin)
    return twin


def test_components_run_where_they_are_placed(
    dt_client, inference_endpoint, learning_endpoint, doomed_endpoint
):
    dt = dt_client(SITES)
    twin = _site_twin(dt, c="site_c")

    assert _probe(dt, twin, "a") == TASK_ENDPOINT
    assert _probe(dt, twin, "b") == EXSITU_ENDPOINT
    assert _probe(dt, twin, "c") == DOOMED_ENDPOINT

    session = next(s for s in dt.admin_sessions()["sessions"] if s["sid"] == dt.sid)
    assert session["endpoints"]["site_b"] == EXSITU_ENDPOINT
    assert session["endpoints"]["site_c"] == DOOMED_ENDPOINT

    # explicit placement never aliases
    probe, where = PROBES["b"]
    with pytest.raises(Exception, match="not configured"):
        dt.add_investigator(
            twin, dt.package(SiteModel, where), probe, where, engine="nowhere"
        )


def test_losing_a_site_fails_only_the_twin_placed_there(
    dt_client, inference_endpoint, learning_endpoint, doomed_endpoint
):
    dt = dt_client(SITES)
    placed = _site_twin(dt, c="site_c")
    elsewhere = _site_twin(dt)

    assert _probe(dt, placed, "c") == DOOMED_ENDPOINT
    _terminate(doomed_endpoint)

    entry = await_state(dt, placed, "failed", timeout=LOST_TIMEOUT)
    assert entry["last_error"] == f"engine endpoint lost: {DOOMED_ENDPOINT}"

    sibling = dt.twin(elsewhere)
    assert sibling["state"] == "running", sibling
    assert _probe(dt, elsewhere, "b") == EXSITU_ENDPOINT

    # a new twin that does not use the lost site still starts; placing a
    # component there is refused
    later = _site_twin(dt)
    assert _probe(dt, later, "a") == TASK_ENDPOINT

    probe, where = PROBES["c"]
    with pytest.raises(Exception, match="endpoint was lost"):
        dt.add_investigator(
            later, dt.package(SiteModel, where), probe, where, engine="site_c"
        )
