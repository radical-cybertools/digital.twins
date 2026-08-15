"""Integration tests for M2: ex-situ learning on a second endpoint.

Covers the DTaaS plan's M2 item 11 against a live stack with *distinct*
`'task'` and `'exsitu'` endpoints: a twin whose
`StreamingLearnerInvestigator` retrains on streamed windows ex-situ
while serving inference in-situ, a model update actually propagating to
the next prediction, and (risk R8) an endpoint loss failing exactly the
twins that used it.
"""

import time
import uuid

import pytest

from digitaltwin.components import TRUTHY, TypedData

from digitaltwin.service import register_user_modules

import learner_components
import twin_components

from conftest import (
    DOOMED_ENDPOINT,
    ENGINES_DOOMED,
    ENGINES_DUAL,
    EXSITU_ENDPOINT,
    TASK_ENDPOINT,
    _terminate,
)
from learner_components import (
    INFERENCE_DTYPE,
    SENSOR_DTYPE,
    SLOPE,
    LinearLearner,
)
from test_dt_service import await_state
from twin_components import CountingSensor, OffsetModel

pytestmark = pytest.mark.integration

register_user_modules([learner_components, twin_components])

# the learner needs a few windows off the sensor stream, and each window
# is a round trip to a second endpoint
LEARN_TIMEOUT = 120.0
INFER_TIMEOUT = 120.0

# the broker's suspect -> lost grace is 10 s by default
LOST_TIMEOUT = 120.0

PROBE = 3.0


def build_learner_twin(dt, twin, interval: float = 0.2):
    """sensor -> streaming learner, the standard dual-engine test twin."""

    dt.create_twin(twin)
    dt.add_task(twin, dt.package(CountingSensor, interval=interval),
                TRUTHY, SENSOR_DTYPE, is_persistent=True)
    dt.add_investigator(twin, dt.package(LinearLearner), SENSOR_DTYPE,
                        INFERENCE_DTYPE)
    dt.start(twin)


def infer(dt, twin, value=PROBE):
    """One inference through the twin, as the plain dict the task built."""

    answer = dt.get_inference(twin, TypedData(SENSOR_DTYPE, value),
                              INFERENCE_DTYPE, timeout=INFER_TIMEOUT)

    return answer.data


def await_learned(dt, twin, timeout=LEARN_TIMEOUT):
    """Poll inference until the published model is no longer the
    bootstrap one -- the twin has to *serve* the update, not merely
    compute it."""

    deadline = time.time() + timeout

    while True:
        answer = infer(dt, twin)
        if answer["value"]:
            return answer
        if time.time() > deadline:
            pytest.fail(f"twin {twin} never published a learned model: "
                        f"{dt.twin(twin)}")
        time.sleep(1)


# ---------------------------------------------------------------------------
# two engines, two endpoints
# ---------------------------------------------------------------------------

def test_learned_model_propagates_across_two_endpoints(
    dt_client, task_endpoint, exsitu_endpoint, twin_id
):
    """The M2 acceptance test.

    One stream feeds both halves of the twin: the learner retrains on
    windows of it via the `'exsitu'` endpoint, the inference task serves
    it from the `'task'` endpoint, and a published model changes what
    the *next* prediction answers.
    """

    dt = dt_client(ENGINES_DUAL)
    build_learner_twin(dt, twin_id)

    # the bootstrap model: published up front, or the first input would
    # deadlock on `has_published_model` and nothing would ever be learned
    before = infer(dt, twin_id)
    assert before["value"] == 0.0
    assert before["served_by"] == TASK_ENDPOINT

    after = await_learned(dt, twin_id)

    # the same request, a different answer -- only the model changed
    assert after["value"] == pytest.approx(SLOPE * PROBE)

    # and the two halves really did run on different endpoints
    assert after["served_by"] == TASK_ENDPOINT
    assert after["trained_on"] == EXSITU_ENDPOINT

    session = next(s for s in dt.admin_sessions()["sessions"]
                   if s["sid"] == dt.sid)
    assert session["engines"] == ["exsitu", "task"]


def test_a_learner_twin_stops_cleanly(dt_client, task_endpoint,
                                      exsitu_endpoint, twin_id):
    """The learner's lifetime is the twin's.

    `stop` is terminal and must not hang on a learner parked in a
    window, and the twin must not land in `failed` on the way out.
    """

    dt = dt_client(ENGINES_DUAL)
    build_learner_twin(dt, twin_id)
    await_learned(dt, twin_id)

    t0 = time.time()
    assert dt.stop(twin_id) == "stopped"
    assert time.time() - t0 < 60, "stop waited for the learner"

    assert dt.twin(twin_id)["last_error"] is None
    assert dt.twin_close(twin_id) == "closed"


def test_an_unconfigured_exsitu_engine_aliases_task(dt, task_endpoint,
                                                    twin_id):
    """Adding `'exsitu'` is a config-only change: a single-endpoint
    deployment keeps working, with one engine serving both roles."""

    build_learner_twin(dt, twin_id)

    answer = await_learned(dt, twin_id)
    assert answer["served_by"] == TASK_ENDPOINT
    assert answer["trained_on"] == TASK_ENDPOINT

    session = next(s for s in dt.admin_sessions()["sessions"]
                   if s["sid"] == dt.sid)
    assert session["engines"] == ["task"]


# ---------------------------------------------------------------------------
# R8: a lost endpoint is visible, not silent
# ---------------------------------------------------------------------------

def test_a_lost_endpoint_fails_only_the_twins_that_used_it(
    dt_client, task_endpoint, doomed_endpoint, twin_id
):
    """Killing the ex-situ endpoint strands the learner twin -- which
    must show up as `failed` with a readable reason, while its
    task-only sibling keeps serving."""

    dt = dt_client(ENGINES_DOOMED)

    plain = str(uuid.uuid4())
    dt.create_twin(plain)
    dt.add_investigator(plain, dt.package(OffsetModel, offset=7),
                        SENSOR_DTYPE, INFERENCE_DTYPE)
    dt.start(plain)

    build_learner_twin(dt, twin_id)
    await_learned(dt, twin_id)

    _terminate(doomed_endpoint)

    entry = await_state(dt, twin_id, "failed", timeout=LOST_TIMEOUT)
    assert entry["last_error"] == f"engine endpoint lost: {DOOMED_ENDPOINT}"

    # the sibling never touched that engine
    sibling = dt.twin(plain)
    assert sibling["state"] == "running", sibling
    assert sibling["last_error"] is None

    answer = dt.get_inference(plain, TypedData(SENSOR_DTYPE, 5),
                              INFERENCE_DTYPE, timeout=INFER_TIMEOUT)
    assert answer.data == 12
