"""Integration demo: a digital twin hosted by the `dt` ORBIT plugin.

    sensor --> agent (one investigator) --> data sink

Everything below the client is remote: the twin's runtime, its stream
client and the components all live in the plugin host; the components'
compute runs on a rhapsody endpoint.  See README.md for the two services
this needs.
"""

import json
import logging
import os
import time

from radical.orbit import EndpointRuntime

from digitaltwin.components import NULL_DTYPE, TRUTHY
from digitaltwin.service import register_user_modules

from dtypes import INFERENCE_DTYPE, SENSOR_DTYPE
from sensor import MySensor
from agent import MyAgent
from data_sink import MySink

# the service has none of this code -- ship it by value
import agent
import data_sink
import dtypes
import model
import sensor

register_user_modules([dtypes, sensor, agent, model, data_sink])

logger = logging.getLogger(__name__)

# where the `dt` plugin is hosted ('broker', or an endpoint name), and
# which endpoint runs the twin's tasks (unset: let ORBIT pick one)
DT_HOST = os.environ.get("DT_SERVICE_HOST", "broker")
TASK_ENDPOINT = os.environ.get("DT_INFERENCE_ENDPOINT") or None

# engine wiring, stated explicitly: one 'inference' backend per session, on a
# co-located endpoint, with the concurrent backend
# ENGINES = {
#     "engines": {
#         "inference": {"endpoint_name": TASK_ENDPOINT, "backends": ["concurrent"]}
#     }
# }

# "pools": [{"name": "exsitu", "endpoint_name": "hpc"},
#           {"name": "insitu", "endpoint_name": "pi"}],

ENGINES = {
        "engines": {
            "inference" : {"endpoint_name": "pi", "backends": ["concurrent"]},
            "learning" : {"endpoint_name": "hpc", "backends": ["dragon"]},
        }
}


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("radical.orbit").setLevel(logging.WARNING)

    runtime = EndpointRuntime()
    runtime.start(wait=True)

    try:
        dt = runtime.get_plugin(DT_HOST, "dt", config=ENGINES)
        print(f"session: {dt.sid}  (reattach with this sid)")

        # one asynchronous verb: returns as soon as the twin is
        # registered, the helper polls twin_list until it is ready
        twin = dt.create_twin()
        print(f"twin: {twin}")

        dt.add_task(twin, dt.package(MySensor), TRUTHY, SENSOR_DTYPE,
                    is_persistent=True)
        dt.add_agent(twin, dt.package(MyAgent), SENSOR_DTYPE, INFERENCE_DTYPE)
        dt.add_task(twin, dt.package(MySink), INFERENCE_DTYPE, NULL_DTYPE)

        print(json.dumps(dt.describe(twin), indent=2))

        dt.start(twin)
        time.sleep(15)

        print(json.dumps(dt.twin(twin), indent=2))

        dt.twin_close(twin)

    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
