#
# This test is the exact same as the standalone API tests but "servicified" with ORBIT.
# This test creates a all comprehensive digital twin, with model investigators,
# agents, data joins, splits, barriers, inputs, etc.... Every abstraction and
# feature that the DT framework provides. If these tests don't work, then user
# code relying on the DT framework won't work either.
#
# The API tests cover the standalone version. This now covers the "as-a-service"
# version. The components for this test are on-purposely soft linked to the API
# tests, as the user code shouldn't have to change at all whether running as a
# service or standalone.


import json
import sys
import time

from pathlib import Path

import pytest

from digitaltwin.components import TRUTHY, Barrier

# the linked api_test modules import each other by their own names
# (`from dtypes import ...`); appended, so this directory's conftest wins
sys.path.append(str(Path(__file__).resolve().parent.parent / "api_test"))

from api_dtypes import *  # noqa: E402,F403
from api_sensors import (  # noqa: E402
    Fast4_Sensor,
    Persist_Sensor,
    Fast_Sensor,
    Slow4_Sensor,
    Slow_Sensor,
    Fast2_Sensor,
    Slow2_Sensor,
    Fast3_Sensor,
    Slow3_Sensor,
    Rand_Sensor,
)
from api_components import (  # noqa: E402
    AgentTest,
    FlipAgent,
    InvestigatorTest,
    SplitTest,
)
from digitaltwin.service import register_user_modules  # noqa: E402

import api_components  # noqa: E402
import api_dtypes  # noqa: E402
import api_sensors  # noqa: E402

pytestmark = pytest.mark.integration

register_user_modules([api_dtypes, api_sensors, api_components])


def setup(dt, twin):
    """The api_test graph, built through the service verbs."""

    dt.create_twin(twin)

    # create the persistent sensor tasks
    persist_sensor = dt.package(Persist_Sensor)
    fast_sensor = dt.package(Fast_Sensor)
    slow_sensor = dt.package(Slow_Sensor)
    fast2_sensor = dt.package(Fast2_Sensor)
    slow2_sensor = dt.package(Slow2_Sensor)
    fast3_sensor = dt.package(Fast3_Sensor)
    slow3_sensor = dt.package(Slow3_Sensor)
    fast4_sensor = dt.package(Fast4_Sensor)
    slow4_sensor = dt.package(Slow4_Sensor)
    rand_sensor = dt.package(Rand_Sensor)

    # the graph opens at its input edge: bind the external sensor's channel
    dt.add_input(twin, INPUT_SENSOR_DTYPE, INPUT_CHANNEL)

    # persistent utility tasks: driven by TRUTHY, publish on their own dtype
    dt.add_task(twin, persist_sensor, TRUTHY, PERSIST_SENSOR_DTYPE, is_persistent=True)
    dt.add_task(twin, fast_sensor, TRUTHY, FAST_SENSOR_DTYPE, is_persistent=True)
    dt.add_task(twin, slow_sensor, TRUTHY, SLOW_SENSOR_DTYPE, is_persistent=True)
    dt.add_task(twin, fast2_sensor, TRUTHY, FAST2_SENSOR_DTYPE, is_persistent=True)
    dt.add_task(twin, slow2_sensor, TRUTHY, SLOW2_SENSOR_DTYPE, is_persistent=True)
    dt.add_task(twin, fast3_sensor, TRUTHY, FAST3_SENSOR_DTYPE, is_persistent=True)
    dt.add_task(twin, slow3_sensor, TRUTHY, SLOW3_SENSOR_DTYPE, is_persistent=True)
    dt.add_task(twin, fast4_sensor, TRUTHY, FAST4_SENSOR_DTYPE, is_persistent=True)
    dt.add_task(twin, slow4_sensor, TRUTHY, SLOW4_SENSOR_DTYPE, is_persistent=True)
    dt.add_task(twin, rand_sensor, TRUTHY, RAND_SENSOR_DTYPE, is_persistent=True)

    # add investigators
    investigator = dt.package(InvestigatorTest)
    dt.add_investigator(
        twin, investigator, PERSIST_SENSOR_DTYPE, INVESTIGATOR_OUT_DTYPE
    )

    # add the science agent: its two LetterInvestigators answer with their
    # own AGENT_OUT_DTYPE, kept distinct from TestInvestigator's output.

    flip_agent = dt.package(FlipAgent)
    dt.add_agent(twin, flip_agent, FLIP_AGENT_IN, FLIP_AGENT_OUT)

    # AgentTest depends on FlipAgent. TODO: Make all agent loops only start after start()
    agent = dt.package(AgentTest)
    dt.add_agent(twin, agent, INPUT_SENSOR_DTYPE, AGENT_OUT_DTYPE)

    # Add barriers
    hard_only = Barrier("HARD_ONLY")
    hard_only.add_dtype(FAST_SENSOR_DTYPE)
    hard_only.add_dtype(SLOW_SENSOR_DTYPE)

    fast_soft = Barrier("FAST SOFT")  # tests Windowing
    fast2_window = fast_soft.add_dtype(FAST2_SENSOR_DTYPE, hard=False)
    fast_soft.add_dtype(SLOW2_SENSOR_DTYPE)

    slow_soft = Barrier("SLOW SOFT")  # tests replication
    slow_soft.add_dtype(FAST3_SENSOR_DTYPE)
    slow3_window = slow_soft.add_dtype(SLOW3_SENSOR_DTYPE, hard=False)

    soft_only = Barrier("SOFT ONLY", hard=False)
    fast4_window = soft_only.add_dtype(FAST4_SENSOR_DTYPE)
    slow4_window = soft_only.add_dtype(SLOW4_SENSOR_DTYPE)

    # add each to runtime.
    dt.add_barrier(twin, hard_only)
    dt.add_barrier(twin, fast_soft)
    dt.add_barrier(twin, slow_soft)
    dt.add_barrier(twin, soft_only)

    # Add a data join
    dt.add_data_join(twin, DATA_JOIN)

    # add data split
    st = dt.package(SplitTest)
    dt.add_data_split_task(twin, st, RAND_SENSOR_DTYPE, [POS_NUM, NEG_NUM])

    return fast2_window, slow3_window, fast4_window, slow4_window


# what a graph *is*, as opposed to what its loops have done so far: through
# the service the agents' and investigators' main loops start when they are
# added, so by the time `describe` answers they may have published a model
# and started their investigators -- the standalone snapshot predates that
RUNTIME_FIELDS = ("model_published", "model_keys", "investigators")


def _structure(graph: dict) -> dict:
    graph = {k: v for k, v in graph.items() if k != "namespace"}
    graph["components"] = [
        {k: v for k, v in c.items() if k not in RUNTIME_FIELDS}
        for c in graph["components"]
    ]
    return graph


def test_setup(dt, twin_id):
    """The whole api_test graph registers through the service and has the
    same structure as the standalone one -- barriers and split included --
    and it then runs without an error."""

    setup(dt, twin_id)

    expected = Path(__file__).resolve().parent / "expected_graph.json"
    answer = json.loads(expected.read_text())

    assert _structure(answer) == _structure(dt.describe(twin_id))

    assert dt.start(twin_id) == "running"
    time.sleep(5)
    assert dt.twin(twin_id)["last_error"] is None
    dt.stop(twin_id)
