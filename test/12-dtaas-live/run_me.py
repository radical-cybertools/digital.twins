#!/usr/bin/env python3
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
    DT_INFERENCE_ENDPOINT      endpoint serving inference
    DT_LEARNING_ENDPOINT       endpoint for the learner's training windows
"""

import argparse
import json
import logging
import os
import sys
import textwrap
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
INFERENCE_EP = os.environ.get("DT_INFERENCE_ENDPOINT") or None
LEARNING_EP = os.environ.get("DT_LEARNING_ENDPOINT") or INFERENCE_EP

# Two role backends, pinned to hardware.  'learning' is what
# makes the learner's training a separate lane in the dashboard rather
# than an alias of 'inference'.
ENGINES = {
    "engines": {
        "inference": {"endpoint_name": INFERENCE_EP, "backends": ["concurrent"]},
        "learning": {"endpoint_name": LEARNING_EP, "backends": ["concurrent"]},
    }
}

PACE = os.environ.get("DEMO_STEP", "manual")

# syntax highlighting is a soft dependency: without pygments (or with
# NO_COLOR set) the api snippets print plain
try:
    from pygments import highlight
    from pygments.formatters import Terminal256Formatter
    from pygments.lexers import PythonLexer
    _LEXER = PythonLexer()
    _FORMATTER = Terminal256Formatter(style="monokai")
except ImportError:
    _LEXER = None


def _render_code(code: str) -> None:
    """The step's API surface, as a block the audience can read."""

    text = textwrap.dedent(code).strip("\n")
    if _LEXER is not None and not os.environ.get("NO_COLOR"):
        text = highlight(text, _LEXER, _FORMATTER).rstrip("\n")

    print("  \033[2mapi:\033[0m")
    for line in text.splitlines():
        print(f"      {line}")
    print()


def step(title: str, note: str = "", code: str = "") -> None:
    """Announce the next beat and hold until the narrator is ready."""

    print(f"\n\033[1m{'=' * 70}\n{title}\033[0m")
    if note:
        print(f"{note}\n")
    if code:
        _render_code(code)

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

    step("1.  Session",
         f"  - sid: {dt.sid}\n"
         "  - the sid is a bearer capability: it is the only client state\n"
         "  - twins belong to the session, not to this process",
         code="""
             ENGINES = {'engines': {'inference': {'endpoint_name': 'dt_inference_ep'},
                                    'learning':  {'endpoint_name': 'dt_learning_ep'}}}

             runtime = EndpointRuntime()        # the ORBIT client runtime
             dt      = runtime.get_plugin('broker', 'dt', config=ENGINES)
         """)

    # -- twin A: plain in-situ inference -----------------------------------

    step("2.  Create a twin",
         "  - create_twin returns on registration; the helper polls to ready\n"
         "  - dashboard: card in the broker lane, initializing -> ready",
         code="""
             twin = dt.create_twin()
         """)
    twin_a = dt.create_twin()
    print(f"  twin A: {twin_a}")

    step("3.  Ship the graph",
         "  - the service has none of this code\n"
         "  - component classes go over the wire (cloudpickle, by value)\n"
         "  - the service instantiates them, injecting the session engine\n"
         "  - graph: sensor -> model -> sink",
         code="""
             dt.add_task        (twin, dt.package(PacedSensor),
                                 TRUTHY,          SENSOR_DTYPE, is_persistent=True)
             dt.add_investigator(twin, dt.package(RampModel),
                                 SENSOR_DTYPE,    INFERENCE_DTYPE)
             dt.add_task        (twin, dt.package(EchoSink),
                                 INFERENCE_DTYPE, NULL_DTYPE)
             dt.describe(twin)
         """)
    dt.add_task(twin_a, dt.package(PacedSensor), TRUTHY, SENSOR_DTYPE,
                is_persistent=True)
    dt.add_investigator(twin_a, dt.package(RampModel), SENSOR_DTYPE,
                        INFERENCE_DTYPE)
    dt.add_task(twin_a, dt.package(EchoSink), INFERENCE_DTYPE, NULL_DTYPE)
    show("graph", dt.describe(twin_a))

    step("4.  Start",
         "  - sensor publishes a reading every 2.5s\n"
         "  - inference runs on the rhapsody endpoint, not in the broker\n"
         "  - dashboard: sensor tile, client -> broker arcs, task tiles on\n"
         "    the HPC lane",
         code="""
             dt.start(twin)
         """)
    dt.start(twin_a)

    # -- twin B: the dual-engine learner -----------------------------------

    step("5.  Second twin: ex-situ learning",
         "  - same session, same stream shape\n"
         "  - retrains on input windows, on a second engine / endpoint\n"
         "  - inference serves from the task endpoint while training runs\n"
         "  - dashboard: convergence bar = ROSE stop criterion (fit_error\n"
         "    vs threshold, updated per window)",
         code="""
             dt.add_investigator(twin_b, dt.package(DriftingLearner),
                                 SENSOR_DTYPE, INFERENCE_DTYPE)

             # inside DriftingLearner (ROSE):
             @learner.training_task
             async def training(window): ...

             @learner.as_stop_criterion(metric_name='fit_error',
                                        threshold=1e-6, operator='<')
             async def criterion(): ...
         """)
    twin_b = dt.create_twin()
    dt.add_task(twin_b, dt.package(PacedSensor), TRUTHY, SENSOR_DTYPE,
                is_persistent=True)
    dt.add_investigator(twin_b, dt.package(DriftingLearner), SENSOR_DTYPE,
                        INFERENCE_DTYPE)
    dt.add_task(twin_b, dt.package(EchoSink), INFERENCE_DTYPE, NULL_DTYPE)
    dt.start(twin_b)
    print(f"  twin B: {twin_b}")

    # -- the client asks directly ------------------------------------------

    step("6.  Query twin A",
         "  - get_inference is the one call that answers the caller\n"
         "  - all other results flow component to component in the twin\n"
         "  - 10 calls, 2s apart; dashboard: one arc per call\n"
         "  - meanwhile twin B trains: learning-lane tiles, convergence bar\n"
         "    per window (~15s)",
         code="""
             for value in range(10):
                 answer = dt.get_inference(twin, TypedData(SENSOR_DTYPE, value),
                                           INFERENCE_DTYPE)
         """)
    for value in range(10):
        answer = dt.get_inference(twin_a, TypedData(SENSOR_DTYPE, value),
                                  INFERENCE_DTYPE)
        print(f"  {value} -> {answer.data}", flush=True)
        time.sleep(2)



    step("7.  Operator view",
         "  - admin_sessions: owner, age, twins, states, last errors\n"
         "  - names the endpoint behind each engine role\n"
         "  - this is how orphaned sessions are found",
         code="""
             dt.admin_sessions()
         """)
    show("sessions", dt.admin_sessions())

    step("8.  Client exits",
         "  - this process ends; the twins do not\n"
         "  - no timeout: twins run for days, clients come and go\n"
         "  - the dashboard keeps updating",
         code="""
             # no teardown call
             sys.exit(0)
         """)

    print("\n  reattach with:\n")
    print(f"      python run_me.py --attach {dt.sid}\n")

    return dt.sid


def attach(dt):
    """Phase two: the client is a different process now."""

    step("9.  Reattach",
         "  - a new process; its only input is the sid",
         code="""
             dt = runtime.get_plugin('broker', 'dt', sid=sid)
             dt.twin_list()
         """)
    for entry in dt.twin_list():
        print(f"  {entry['twin_id'][:8]}  {entry['state']:<10}"
              f"  metrics={list((entry.get('metrics') or {}).keys())}")

    step("10.  Close the twins",
         "  - twin_close, per twin; same route an operator uses",
         code="""
             for twin in dt.twin_list():
                 dt.twin_close(twin['twin_id'])
         """)
    for entry in dt.twin_list():
        print(f"  closing {entry['twin_id'][:8]}")
        dt.twin_close(entry["twin_id"])

    show("sessions", dt.admin_sessions())

    step("11.  Close the session",
         "  - sessions are persistent: twins gone != session gone\n"
         "  - unregister_session shuts the engines down\n"
         "  - explorer: the rhapsody.<session>.<role> participants leave",
         code="""
             dt.unregister_session()
         """)
    sid = dt.sid
    dt.unregister_session()
    print(f"  session {sid} unregistered; the service holds no state of ours")


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
