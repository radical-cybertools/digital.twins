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


import asyncio
import json
import os
import time

from digitaltwin import NULL_DTYPE

from digitaltwin.runtime import DTRuntime
from digitaltwin.components import TRUTHY

from api_dtypes import *
from api_sensors import (
    N_ITERS,
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
from api_monitor import MonitorTask
from api_components import (
    UPDATE_EVERY,
    AgentTest,
    FlipAgent,
    InvestigatorTest,
    SplitTest,
)
from digitaltwin.components import Barrier
from digitaltwin.service import register_user_modules

import api_dtypes
import api_sensors
import api_monitor
import api_components

register_user_modules([api_dtypes, api_sensors, api_monitor, api_components])

from conftest import (
    EXSITU_ENDPOINT,
    TASK_ENDPOINT,
)


async def setup(dt, twin):

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
    dt.add_investigator(twin, flip_agent, FLIP_AGENT_IN, FLIP_AGENT_OUT)

    # AgentTest depends on FlipAgent. TODO: Make all agent loops only start after start()
    agent = dt.package(AgentTest)
    dt.add_investigator(twin, agent, INPUT_SENSOR_DTYPE, AGENT_OUT_DTYPE)

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
    dt.add_barrier(twin, DATA_JOIN)

    # add data split
    st = dt.package(SplitTest)
    dt.add_data_split_task(twin, st, RAND_SENSOR_DTYPE, [POS_NUM, NEG_NUM])

    return dt, fast2_window, slow3_window, fast4_window, slow4_window


async def test_setup(dt, twin_id):

    dt.create_twin(twin_id)
    await setup(dt, twin_id)

    if os.path.exists("expected_graph.json"):
        with open("expected_graph.json", "r") as f:
            # json.dump(runtime.describe(), f, indent=4)
            answer = json.load(f)
    else:
        with open("test/integration/expected_graph.json", "r") as f:
            # json.dump(runtime.describe(), f, indent=4)
            answer = json.load(f)

    assert answer == dt.describe(twin_id)

    dt.start(twin_id)

    # # let it run
    await asyncio.sleep(5)
    await dt.stop(twin_id)
    print("Stopped")


async def skip_test_run(stream_clients, no_task_leaks, input_sensor_task):
    print("Start test run")
    runtime, fast2_w, slow3_w, fast4_w, slow4_w = await setup(stream_clients)

    # monitor tasks for the test
    input_monitor = MonitorTask(POST_INPUT)
    persist_monitor = MonitorTask(POST_PERSIST_SENSOR)

    out_monitor = MonitorTask(NULL_DTYPE)

    pos_monitor = MonitorTask(NULL_DTYPE)
    neg_monitor = MonitorTask(NULL_DTYPE)

    # Outputs
    output = {
        FAST_SENSOR_DTYPE: MonitorTask(NULL_DTYPE, mark_time=True),
        SLOW_SENSOR_DTYPE: MonitorTask(NULL_DTYPE, mark_time=True),
        fast2_w: MonitorTask(NULL_DTYPE, mark_time=True),
        SLOW2_SENSOR_DTYPE: MonitorTask(NULL_DTYPE, mark_time=True),
        FAST3_SENSOR_DTYPE: MonitorTask(NULL_DTYPE, mark_time=True),
        slow3_w: MonitorTask(NULL_DTYPE, mark_time=True),
        fast4_w: MonitorTask(NULL_DTYPE, mark_time=True),
        slow4_w: MonitorTask(NULL_DTYPE, mark_time=True),
    }

    for dtype, task in output.items():
        runtime.add_task(task, dtype, NULL_DTYPE)

    start_time = time.monotonic()

    # Monitor input and persist task
    runtime.add_task(input_monitor, INPUT_SENSOR_DTYPE, POST_INPUT)
    runtime.add_task(persist_monitor, PERSIST_SENSOR_DTYPE, POST_PERSIST_SENSOR)
    runtime.add_task(out_monitor, DATA_JOIN, NULL_DTYPE)
    runtime.add_task(pos_monitor, POS_NUM, NULL_DTYPE)
    runtime.add_task(neg_monitor, NEG_NUM, NULL_DTYPE)

    runtime.start()

    # # let it run
    await asyncio.sleep(20)
    await runtime.stop()

    # should be done.
    stop_time = time.monotonic()

    # Check 1:  is input ordered?

    # check output
    assert len(input_monitor.output) == N_ITERS

    prev_time = start_time
    for entry in input_monitor.output:
        # early to late
        assert entry.data["sensor_time"] > prev_time

    assert input_monitor.output[-1].data["sensor_time"] < stop_time

    # Check two:
    # Are all the events from the persistent task there?
    assert len(persist_monitor.output) == N_ITERS

    prev_time = start_time
    for entry in persist_monitor.output:
        # early to late
        assert entry.data["sensor_time"] > prev_time

    assert persist_monitor.output[-1].data["sensor_time"] < stop_time

    # Great... Now, add an investigator and an agent.

    # check output from join.
    assert len(out_monitor.output) == N_ITERS
    i_counter = 0
    for entry in out_monitor.output:
        i_entry = entry.data[0]
        a_entry = entry.data[1]

        assert i_entry.dtype == INVESTIGATOR_OUT_DTYPE
        assert a_entry.dtype == AGENT_OUT_DTYPE

        # the values should match.
        assert i_entry.data["dat"]["sensor"] == a_entry.data["dat"]["sensor"]

        # check investigator and auto update
        assert i_entry.data["dat"]["sensor"] == i_counter

        # the next one triggers the version update
        assert i_entry.data["version"] == (i_counter // UPDATE_EVERY) + 1

        # check agent with model updates + investigators
        print(
            a_entry.data["letters"],
            i_counter,
            a_entry.data["version"],
            a_entry.data["fcount"],
            a_entry.data["fcount_out"],
            a_entry.data["out_count"],
            a_entry.data["flip"].get("swap", ""),
            a_entry.data["flip"].get("version", 0),
            a_entry.data["flip"].get("fcount", 0),
            a_entry.data["flip"].get("fcount_out", 0),
            a_entry.data["flip"].get("out_count", 0),
        )
        assert a_entry.data["letters"].islower() == (i_counter // UPDATE_EVERY) % 2

        double_up = UPDATE_EVERY * 2

        assert a_entry.data["fcount"] == (i_counter // double_up) * UPDATE_EVERY
        assert a_entry.data["fcount_out"] == a_entry.data["fcount"]
        assert a_entry.data["out_count"] == a_entry.data["version"]

        check = ((i_counter // UPDATE_EVERY) - 1) * UPDATE_EVERY

        if check < 0:
            check = 0
        assert a_entry.data["version"] == check

        # check inter-agent inference

        i_counter += 1

        flip = a_entry.data["flip"]
        assert a_entry.data["letters"].isupper() == flip["swap"].isupper()
        assert flip["fcount"] == flip["fcount_out"]
        assert flip["fcount"] == flip["out_count"]
        assert flip["version"] == flip["fcount"]
        assert flip["version"] == a_entry.data["fcount"]

    assert len(out_monitor.output) == N_ITERS

    # check barriers
    print("Barrier check ===")

    # HARD.

    fast_out = output[FAST_SENSOR_DTYPE].output
    slow_out = output[SLOW_SENSOR_DTYPE].output

    assert len(fast_out) == len(slow_out) and len(slow_out) == N_ITERS
    sorted_recvs = {}
    for fast_item, slow_item in zip(fast_out, slow_out):
        print(
            fast_item["data"].data["sensor"],
            fast_item["data"].data["sensor_time"],
            fast_item["recv_time"],
            "|",
            slow_item["data"].data["sensor"],
            slow_item["data"].data["sensor_time"],
            slow_item["recv_time"],
        )

        # sort by recv time.
        sorted_recvs[fast_item["recv_time"]] = "FAST"
        sorted_recvs[slow_item["recv_time"]] = "SLOW"

        assert fast_item["data"].data["sensor"] == slow_item["data"].data["sensor"]

    sorted_recvs = dict(sorted(sorted_recvs.items(), key=lambda item: item[0]))
    assert len(sorted_recvs) == 2 * N_ITERS

    saw_slow = 0
    saw_fast = 0
    for i in sorted_recvs.values():
        if saw_slow == 1 and saw_fast == 1:
            saw_slow = 0
            saw_fast = 0

        if i == "SLOW" and saw_slow == 0:
            saw_slow = 1
        elif i == "FAST" and saw_fast == 0:
            saw_fast = 1
        else:
            # Failed order test!
            raise ValueError("Failed barrier ordering test!")

    # Now, check fast_soft

    print("FAST SOFT check")

    fast_out = output[fast2_w].output
    slow_out = output[SLOW2_SENSOR_DTYPE].output
    sorted_recvs = {}

    for fast_item, slow_item in zip(fast_out, slow_out):
        # get fast window
        print(
            fast_item["data"].data,
            fast_item["recv_time"],
            slow_item["data"].data["sensor"],
            slow_item["data"].data["sensor_time"],
            slow_item["recv_time"],
        )

        # sort by recv time.
        for i in fast_item["data"].data:
            val = i["sensor"]
            t = i["sensor_time"]

            sorted_recvs[t] = {"val": val, "type": "FAST"}

        val = slow_item["data"].data["sensor"]
        sorted_recvs[slow_item["data"].data["sensor_time"]] = {
            "val": val,
            "type": "SLOW",
        }

    sorted_recvs = dict(sorted(sorted_recvs.items(), key=lambda item: item[0]))

    # simulate expected:

    # simply check if each count up....
    prev_slow = None
    prev_fast = None

    # first is slow, sneak ahead to fast!

    for i in list(sorted_recvs.values()):
        if i["type"] == "SLOW" and prev_slow is None:
            assert i["val"] == 0
            prev_slow = 0
            continue
        elif i["type"] == "SLOW":
            assert i["val"] == prev_slow + 1
            prev_slow = i["val"]
            continue

        if i["type"] == "FAST" and prev_fast is None:
            assert i["val"] == 0
            prev_fast = 0
            continue
        elif i["type"] == "FAST":
            assert i["val"] == (prev_fast + 1) or i["val"] == prev_fast
            prev_fast = i["val"]
            continue

        assert False

    # check the opposite, hard on fast, soft on slow

    print("SLOW SOFT check")

    fast_out = output[FAST3_SENSOR_DTYPE].output
    slow_out = output[slow3_w].output
    sorted_recvs = {}

    for fast_item, slow_item in zip(fast_out, slow_out):
        # get fast window
        print(
            fast_item["data"].data["sensor"],
            fast_item["data"].data["sensor_time"],
            fast_item["recv_time"],
            slow_item["data"].data,
            slow_item["recv_time"],
        )

        # sort by recv time.
        assert len(slow_item["data"].data) == 1
        val = slow_item["data"].data[0]["sensor"]

        sorted_recvs[slow_item["recv_time"]] = {"val": val, "type": "SLOW"}

        val = fast_item["data"].data["sensor"]
        sorted_recvs[fast_item["recv_time"]] = {
            "val": val,
            "type": "FAST",
        }

    sorted_recvs = dict(sorted(sorted_recvs.items(), key=lambda item: item[0]))

    assert len(sorted_recvs) == N_ITERS * 2

    # simulate expected:

    prev_type = "SLOW"
    prev_slow = 0
    counter = 0
    for i in sorted_recvs.values():
        if i["type"] == "FAST":
            assert prev_type == "SLOW"
            prev_type = "FAST"
            continue

        if i["type"] == "SLOW":
            assert prev_type == "FAST"
            assert i["val"] >= prev_slow
            prev_slow = i["val"]
            prev_type = "SLOW"
            continue

        assert False

    # check soft only

    print("SOFT ONLY check")

    fast_out = output[fast4_w].output
    slow_out = output[slow4_w].output
    sorted_recvs = {}

    for fast_item, slow_item in zip(fast_out, slow_out):
        # get fast window
        print(
            fast_item["data"].data,
            fast_item["recv_time"],
            slow_item["data"].data,
            slow_item["recv_time"],
        )

        # sort by recv time.
        assert len(slow_item["data"].data) == 1
        sorted_recvs[slow_item["recv_time"]] = {
            "val": slow_item["data"].data[0]["sensor"],
            "type": "SLOW",
        }

        assert len(fast_item["data"].data) == 1
        sorted_recvs[fast_item["recv_time"]] = {
            "val": fast_item["data"].data[0]["sensor"],
            "type": "FAST",
        }

    sorted_recvs = dict(sorted(sorted_recvs.items(), key=lambda item: item[0]))

    # simulate expected:

    prev_type = "SLOW"
    prev_slow = 0
    counter = 0
    for i in sorted_recvs.values():
        if i["type"] == "FAST":
            assert prev_type == "SLOW"
            prev_type = "FAST"
            continue

        if i["type"] == "SLOW":
            assert prev_type == "FAST"
            assert i["val"] >= prev_slow
            prev_slow = i["val"]
            prev_type = "SLOW"
            continue

        assert False

    # check data split
    print("Check data split")

    assert len(pos_monitor.output) == len(neg_monitor.output)
    # check vals
    for p, n in zip(pos_monitor.output, neg_monitor.output):
        assert p.data["sensor"] >= 0 and p.data["sensor"] % 2 == 0
        assert n.data["sensor"] < 0 and n.data["sensor"] % 2 == 1
        print(p.data["sensor"], n.data["sensor"])

    # done!
