import asyncio
import json
import time

from digitaltwin import NULL_DTYPE

from digitaltwin.runtime import DTRuntime
from digitaltwin.streaming import connect_stream_client
from digitaltwin.components import TRUTHY

from dtypes import *
from sensors import (
    N_ITERS,
    Persist_Sensor,
    Fast_Sensor,
    Slow_Sensor,
    Fast2_Sensor,
    Slow2_Sensor,
    Fast3_Sensor,
    Slow3_Sensor,
    Rand_Sensor,
)
from monitor import MonitorTask
from components import UPDATE_EVERY, AgentTest, FlipAgent, InvestigatorTest

import logging

logger = logging.getLogger(__name__)

# put it all together
#
#   input_sensor channel --> INPUT_SENSOR_DTYPE
#   Persist_Sensor, Fast_Sensor, Slow_Sensor, Fast2_Sensor, Slow2_Sensor,
#   Fast3_Sensor, Slow3_Sensor, Rand_Sensor --> their own dtypes
#
# Nothing consumes these dtypes yet - this just proves persistence and the
# input binding both work end-to-end.
#
# The input sensor is external: run `python -c "import asyncio;
# from sensors import input_sensor; asyncio.run(input_sensor())"` in its
# own terminal once the broker is up.


async def setup(stream_clients):
    flow = None

    # create the twin's namespaced stream client
    pubsub_client = await stream_clients()

    runtime = DTRuntime(flow, pubsub_client)

    # create the persistent sensor tasks
    persist_sensor = Persist_Sensor(flow)
    fast_sensor = Fast_Sensor(flow)
    slow_sensor = Slow_Sensor(flow)
    fast2_sensor = Fast2_Sensor(flow)
    slow2_sensor = Slow2_Sensor(flow)
    fast3_sensor = Fast3_Sensor(flow)
    slow3_sensor = Slow3_Sensor(flow)
    rand_sensor = Rand_Sensor(flow)

    # the graph opens at its input edge: bind the external sensor's channel
    runtime.add_input(INPUT_SENSOR_DTYPE, INPUT_CHANNEL)

    # persistent utility tasks: driven by TRUTHY, publish on their own dtype
    runtime.add_task(persist_sensor, TRUTHY, PERSIST_SENSOR_DTYPE, is_persistent=True)
    runtime.add_task(fast_sensor, TRUTHY, FAST_SENSOR_DTYPE, is_persistent=True)
    runtime.add_task(slow_sensor, TRUTHY, SLOW_SENSOR_DTYPE, is_persistent=True)
    runtime.add_task(fast2_sensor, TRUTHY, FAST2_SENSOR_DTYPE, is_persistent=True)
    runtime.add_task(slow2_sensor, TRUTHY, SLOW2_SENSOR_DTYPE, is_persistent=True)
    runtime.add_task(fast3_sensor, TRUTHY, FAST3_SENSOR_DTYPE, is_persistent=True)
    runtime.add_task(slow3_sensor, TRUTHY, SLOW3_SENSOR_DTYPE, is_persistent=True)
    runtime.add_task(rand_sensor, TRUTHY, RAND_SENSOR_DTYPE, is_persistent=True)

    # add investigators
    investigator = InvestigatorTest()
    runtime.add_investigator(investigator, PERSIST_SENSOR_DTYPE, INVESTIGATOR_OUT_DTYPE)

    # add the science agent: its two LetterInvestigators answer with their
    # own AGENT_OUT_DTYPE, kept distinct from TestInvestigator's output.

    flip_agent = FlipAgent()
    runtime.add_agent(flip_agent, FLIP_AGENT_IN, FLIP_AGENT_OUT)

    # AgentTest depends on FlipAgent. TODO: Make all agent loops only start after start()
    agent = AgentTest()
    runtime.add_agent(agent, INPUT_SENSOR_DTYPE, AGENT_OUT_DTYPE)

    # Add a data join
    runtime.add_data_join(DATA_JOIN)

    return runtime


async def test_setup(stream_clients, no_task_leaks, input_sensor_task):

    runtime = await setup(stream_clients)

    with open("expected_graph.json", "w") as f:
        json.dump(runtime.describe(), f, indent=4)
        # answer = json.load(f)

    # assert answer == runtime.describe()

    runtime.start()

    # # let it run
    await asyncio.sleep(5)
    await runtime.stop()
    print("Stopped")


async def test_run(stream_clients, no_task_leaks, input_sensor_task):
    print("Start test run")
    runtime = await setup(stream_clients)

    # monitor tasks for the test
    input_monitor = MonitorTask(POST_INPUT)
    persist_monitor = MonitorTask(POST_PERSIST_SENSOR)

    out_monitor = MonitorTask(NULL_DTYPE)

    start_time = time.monotonic()

    # Monitor input and persist task
    runtime.add_task(input_monitor, INPUT_SENSOR_DTYPE, POST_INPUT)
    runtime.add_task(persist_monitor, PERSIST_SENSOR_DTYPE, POST_PERSIST_SENSOR)
    runtime.add_task(out_monitor, DATA_JOIN, NULL_DTYPE)

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

    # check data split
