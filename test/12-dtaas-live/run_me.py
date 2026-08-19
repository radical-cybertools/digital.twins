"""The live DTaaS demo, paced for narration.

Two phases, because the point of phase two is that phase one's process is
gone:

    python run_me.py                    # build and start two twins, then exit
    python run_me.py --attach <sid>     # come back to them, then tear down

Each step waits for Enter so the pacing is yours.  Set DEMO_STEP to a
number of seconds to make it run itself instead.

Environment:

    RADICAL_ORBIT_BROKER_URL   wss://radical.3:8000
    DT_SERVICE_HOST            participant hosting the `dt` plugin (default 'broker')
    DT_TASK_ENDPOINT           endpoint for in-situ compute
    DT_EXSITU_ENDPOINT         endpoint for the learner's training windows
"""

import argparse
import json
import logging
import os
import sys
import time

from radical.orbit import EndpointRuntime

from digitaltwin.components import NULL_DTYPE, TRUTHY, TypedData
from digitaltwin.service import register_user_modules

from dtypes import INFERENCE_DTYPE, SENSOR_DTYPE
from components import EchoSink, PacedSensor, RampModel
from learner import DriftingLearner

# the service has no copy of this directory -- ship it by value
import components
import dtypes
import learner

register_user_modules([dtypes, components, learner])

DT_HOST = os.environ.get("DT_SERVICE_HOST", "broker")
TASK_EP = os.environ.get("DT_TASK_ENDPOINT") or None
EXSITU_EP = os.environ.get("DT_EXSITU_ENDPOINT") or TASK_EP

# Two engines, named by role and pinned to hardware.  'exsitu' is what
# makes the learner's training a separate lane in the dashboard rather
# than an alias of 'task'.
ENGINES = {
    "engines": {
        "task": {"endpoint_name": TASK_EP, "backends": ["concurrent"]},
        "exsitu": {"endpoint_name": EXSITU_EP, "backends": ["concurrent"]},
    }
}

PACE = os.environ.get("DEMO_STEP", "manual")


def step(title: str, note: str = "") -> None:
    """Announce the next beat and hold until the narrator is ready."""

    print(f"\n\033[1m{'=' * 70}\n{title}\033[0m")
    if note:
        print(f"{note}\n")

    if PACE == "manual":
        try:
            input("  [Enter] ")
        except EOFError:
            pass
    else:
        time.sleep(float(PACE))


def show(label: str, obj) -> None:
    print(f"  {label}:")
    for line in json.dumps(obj, indent=2).splitlines():
        print(f"    {line}")


def build(dt):
    """Phase one: two twins on one session, then walk away."""

    step("1.  A session on the service",
         f"  sid {dt.sid}\n"
         "  The sid is the bearer capability: whoever holds it owns these\n"
         "  twins.  Nothing else about this client is remembered.")

    # -- twin A: plain in-situ inference -----------------------------------

    step("2.  Create a twin",
         "  `create_twin` is the one asynchronous verb -- it returns as soon\n"
         "  as the twin is registered, and the helper polls until it is ready.\n"
         "  Watch a card appear in the broker lane: initializing, then ready.")
    twin_a = dt.create_twin()
    print(f"  twin A: {twin_a}")

    step("3.  Ship the graph",
         "  The service has none of this code.  What goes over the wire is\n"
         "  the component *classes*, cloudpickled by value, plus their\n"
         "  constructor arguments -- the service instantiates them with the\n"
         "  session's engine injected as `flow`.")
    dt.add_task(twin_a, dt.package(PacedSensor), TRUTHY, SENSOR_DTYPE,
                is_persistent=True)
    dt.add_investigator(twin_a, dt.package(RampModel), SENSOR_DTYPE,
                        INFERENCE_DTYPE)
    dt.add_task(twin_a, dt.package(EchoSink), INFERENCE_DTYPE, NULL_DTYPE)
    show("graph", dt.describe(twin_a))

    step("4.  Start it",
         "  Readings every 2.5s.  In the dashboard: a sensor tile appears\n"
         "  under the twin, arcs run client -> broker, and the inference\n"
         "  task shows up as a tile on the HPC task lane -- that compute is\n"
         "  running on a rhapsody endpoint, not in the broker.")
    dt.start(twin_a)

    # -- the client asks directly ------------------------------------------

    step("5.  Ask the twin a question",
         "  `get_inference` is the one path that answers the caller\n"
         "  directly.  Everything else the twin produces goes to the next\n"
         "  component over an in-process queue -- and is dropped if nobody\n"
         "  is registered for it.")
    answer = dt.get_inference(twin_a, TypedData(SENSOR_DTYPE, 21),
                              INFERENCE_DTYPE)
    print(f"  21 -> {answer.data}")

    # -- twin B: the dual-engine learner -----------------------------------

    step("6.  A second twin, learning ex-situ",
         "  Same session, same stream shape, but this one retrains on\n"
         "  windows of its input via a *second* engine on a second endpoint.\n"
         "  The convergence bar on its card is the ROSE stop criterion:\n"
         "  fit_error against a threshold, updated per window.")
    twin_b = dt.create_twin()
    dt.add_task(twin_b, dt.package(PacedSensor), TRUTHY, SENSOR_DTYPE,
                is_persistent=True)
    dt.add_investigator(twin_b, dt.package(DriftingLearner), SENSOR_DTYPE,
                        INFERENCE_DTYPE)
    dt.add_task(twin_b, dt.package(EchoSink), INFERENCE_DTYPE, NULL_DTYPE)
    dt.start(twin_b)
    print(f"  twin B: {twin_b}")

    step("7.  The operator's view",
         "  `admin_sessions` is how an orphaned session is found: owner,\n"
         "  age, twins, states, last errors, and the hardware behind each\n"
         "  engine role.")
    show("sessions", dt.admin_sessions())

    step("8.  Now the client goes away",
         "  This process is about to exit.  The twins do not stop, and\n"
         "  nothing times them out -- a twin may run for days while clients\n"
         "  come and go.  Keep watching the dashboard.")

    print("\n  reattach with:\n")
    print(f"      python run_me.py --attach {dt.sid}\n")

    return dt.sid


def attach(dt):
    """Phase two: the client is a different process now."""

    step("9.  Back, with nothing but the sid",
         "  A new process, no memory of the twins, holding one string.")
    for entry in dt.twin_list():
        print(f"  {entry['twin_id'][:8]}  {entry['state']:<10}"
              f"  metrics={list((entry.get('metrics') or {}).keys())}")

    step("10.  Tear them down",
         "  `twin_close` is the ordinary route -- the same one an operator\n"
         "  uses on a session found through `admin_sessions`.")
    for entry in dt.twin_list():
        print(f"  closing {entry['twin_id'][:8]}")
        dt.twin_close(entry["twin_id"])

    show("sessions", dt.admin_sessions())

    step("11.  ... and the session itself",
         "  Sessions are persistent by design -- twins gone is not session\n"
         "  gone.  `unregister_session` releases it: its engines shut down\n"
         "  and their `rhapsody.<session>.<role>` participants leave the\n"
         "  topology.  Watch them disappear from the Explorer.")
    sid = dt.sid
    dt.unregister_session()
    print(f"  session {sid} unregistered -- the service holds nothing of ours")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attach", metavar="SID", default=None,
                        help="reattach to an existing session")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    runtime = EndpointRuntime()
    runtime.start(wait=True)

    try:
        kwargs = {"sid": args.attach} if args.attach else {"config": ENGINES}
        dt = runtime.get_plugin(DT_HOST, "dt", **kwargs)

        if args.attach:
            attach(dt)
        else:
            build(dt)

    finally:
        runtime.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
