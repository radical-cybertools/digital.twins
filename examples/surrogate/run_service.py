"""Run the same surrogate twin on a DTaaS service.

    python run_service.py [--timeout SECONDS]

The components are the ones `run_local.py` uses, unchanged.  The service
does not have this code, so the client ships the classes; the twin runs
on the service and its tasks run on the endpoints the session names.

Needs a broker hosting the `dt` plugin and at least one rhapsody
endpoint, plus the broker's certificate and token in ~/.radical/orbit/
(see "Run the twin on the service" in the docs).

    DT_SERVICE_HOST        participant hosting `dt`    (default: broker)
    DT_INFERENCE_ENDPOINT  endpoint for the inference  (default: any rhapsody endpoint)
    DT_LEARNING_ENDPOINT   endpoint for the learner    (default: same as inference)
"""

import argparse
import math
import os
import sys
import time

from radical.orbit import EndpointRuntime

from radical.doppelganger import NULL_DTYPE, TRUTHY, TypedData
from radical.doppelganger.service import register_user_modules

import dtypes
import physics
import sensor
import sink
import surrogate

from dtypes import PREDICTION, READING

# the service has none of this code: ship these modules by value
register_user_modules([dtypes, physics, sensor, sink, surrogate])

PROBES = [0.5 + i for i in range(6)]


# --8<-- [start:config]
def session_config() -> dict:
    """The engines this session uses: where the twin's tasks run."""

    inference = os.environ.get("DT_INFERENCE_ENDPOINT") or None
    learning = os.environ.get("DT_LEARNING_ENDPOINT")

    engines = {"inference": {"endpoint_name": inference,
                             "backends": ["concurrent"]}}

    # without a learning endpoint the learner shares the inference engine
    if learning:
        engines["learning"] = {"endpoint_name": learning,
                               "backends": ["concurrent"]}

    return {"engines": engines}
# --8<-- [end:config]


def served_rmse(dt, twin) -> float:
    errors = []
    for x in PROBES:
        answer = dt.get_inference(twin, TypedData(READING, x), PREDICTION)
        if answer.data is None:             # no component serves the pair
            return math.inf
        errors.append((answer.data - physics.simulate(x, noise=0.0)) ** 2)

    return math.sqrt(sum(errors) / len(errors))


# --8<-- [start:main]
def main(timeout: float) -> int:
    runtime = EndpointRuntime()
    runtime.start(wait=True)
    dt = None

    try:
        dt = runtime.get_plugin(os.environ.get("DT_SERVICE_HOST", "broker"),
                                "dt", config=session_config())
        print(f"session {dt.sid}")

        twin = dt.create_twin()           # returns once the twin is ready

        dt.add_task(twin, dt.package(sensor.Sensor), TRUTHY, READING,
                    is_persistent=True)
        dt.add_investigator(twin, dt.package(surrogate.Surrogate),
                            READING, PREDICTION)
        dt.add_task(twin, dt.package(sink.Sink), PREDICTION, NULL_DTYPE)
        dt.start(twin)

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2.0)
            error = served_rmse(dt, twin)
            print(f"served surrogate rmse: {error:.4f}")

            if error < 2 * surrogate.PUBLISH_RMSE:
                print("surrogate is accurate: done")
                return 0

            # a failed twin keeps answering with its last model: ask it
            if dt.twin(twin)["state"] == "failed":
                break

        print(f"no accurate surrogate: {dt.twin(twin)}")
        return 1

    finally:
        # sessions outlive their client; end this one explicitly
        if dt is not None:
            dt.unregister_session()
        runtime.stop()
# --8<-- [end:main]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=180.0)
    sys.exit(main(parser.parse_args().timeout))
