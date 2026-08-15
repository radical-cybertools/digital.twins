"""Service demo: a twin that retrains ex-situ while it serves in-situ.

    sensor --> calibration learner --> data sink

One stream drives both halves.  Every reading feeds the ROSE streaming
learner, whose training / active-learning / criterion tasks run on the
`'exsitu'` engine; every reading is also served by the inference task,
which runs on the co-located `'task'` engine.  When a window's model
beats the criterion it is published, and the very next prediction uses
it -- which is what the before/after inference below shows.

See README.md for the services this needs.
"""

import json
import logging
import os
import time

from radical.orbit import EndpointRuntime

from digitaltwin.components import NULL_DTYPE, TRUTHY, TypedData
from digitaltwin.service import register_user_modules

from dtypes import PREDICTION_DTYPE, SENSOR_DTYPE
from model import CalibrationLearner
from sensor import MySensor
from data_sink import MySink

# the service has none of this code -- ship it by value
import data_sink
import dtypes
import model
import sensor

register_user_modules([dtypes, sensor, model, data_sink])

logger = logging.getLogger(__name__)

# where the `dt` plugin is hosted ('broker', or an endpoint name)
DT_HOST = os.environ.get("DT_SERVICE_HOST", "broker")

# the two endpoints.  Unset: ORBIT picks one advertising rhapsody -- and
# an unconfigured 'exsitu' engine simply aliases 'task', so this demo
# also runs against a single endpoint.
TASK_ENDPOINT = os.environ.get("DT_TASK_ENDPOINT") or None
EXSITU_ENDPOINT = os.environ.get("DT_EXSITU_ENDPOINT") or None

# Engine wiring, stated explicitly.  'task' runs the twin's components
# (co-located: it is in the per-reading critical path); 'exsitu' runs the
# learner's tasks (typically remote HPC hardware).  One engine of each
# per session, shared by every twin in it.
ENGINES = {
    "engines": {
        "task": {"endpoint_name": TASK_ENDPOINT, "backends": ["concurrent"]},
        "exsitu": {"endpoint_name": EXSITU_ENDPOINT, "backends": ["concurrent"]},
    }
}

RUN_TIME = 40.0
PROBE = 4.0


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("radical.orbit").setLevel(logging.WARNING)

    runtime = EndpointRuntime()
    runtime.start(wait=True)

    try:
        dt = runtime.get_plugin(DT_HOST, "dt", config=ENGINES)
        print(f"session: {dt.sid}  (reattach with this sid)")

        twin = dt.create_twin()
        print(f"twin: {twin}")

        dt.add_task(twin, dt.package(MySensor), TRUTHY, SENSOR_DTYPE,
                    is_persistent=True)
        dt.add_investigator(twin, dt.package(CalibrationLearner),
                            SENSOR_DTYPE, PREDICTION_DTYPE)
        dt.add_task(twin, dt.package(MySink), PREDICTION_DTYPE, NULL_DTYPE)

        print(json.dumps(dt.describe(twin), indent=2))

        dt.start(twin)

        # the same reading, over and over: the answer changes only
        # because the learner keeps publishing better calibrations
        probe = TypedData(SENSOR_DTYPE, 4.0)
        deadline = time.time() + RUN_TIME

        while time.time() < deadline:
            answer = dt.get_inference(twin, probe, PREDICTION_DTYPE)
            print(f"calibrated reading of 4.0: {answer.data:.3f}")
            time.sleep(PROBE)

        print(json.dumps(dt.twin(twin), indent=2))

        dt.twin_close(twin)

    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
