"""Run the surrogate twin on this machine: no service, no HPC.

    python run_local.py [--timeout SECONDS]

The graph:

    sensor --READING--> surrogate --PREDICTION--> sink

Every few seconds the script asks the twin for predictions on a grid of
points and prints their error against the simulation.  It exits 0 once
the served surrogate is accurate, 1 if that does not happen in time.
"""

import argparse
import asyncio
import logging
import math
import sys
from concurrent.futures import ThreadPoolExecutor

from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from radical.doppelganger import (NULL_DTYPE, TRUTHY, DTRuntime, TypedData,
                                  ZMQ_BrokerProcess, connect_stream_client)

from dtypes import PREDICTION, READING
from physics import simulate
from sensor import Sensor
from sink import Sink
from surrogate import PUBLISH_RMSE, Surrogate

PROBES = [0.5 + i for i in range(6)]


async def served_rmse(runtime) -> float:
    """Error of what the twin serves right now, on `PROBES`."""

    errors = []
    for x in PROBES:
        answer = await runtime.get_inference(TypedData(READING, x), PREDICTION)
        if answer.data is None:             # a failed twin answers nothing
            return math.inf
        errors.append((answer.data - simulate(x, noise=0.0)) ** 2)

    return math.sqrt(sum(errors) / len(errors))


# --8<-- [start:main]
async def main(timeout: float) -> int:
    logging.basicConfig(level=logging.WARNING)

    # 1. the stream broker that carries the twin's data, on a random
    #    loopback port.  The service runs its own; locally we start one.
    broker = ZMQ_BrokerProcess()
    await broker.start()

    # 2. the execution engine: where tasks run.  Threads here; on the
    #    service, a rhapsody endpoint on a laptop or an HPC machine.
    backend = await ConcurrentExecutionBackend(ThreadPoolExecutor())
    flow = await WorkflowEngine.create(backend=backend)

    # 3. the twin: a runtime with its own stream namespace
    stream = await connect_stream_client("surrogate", *broker.get_connection_str())
    runtime = DTRuntime(flow, stream)

    try:
        # 4. the graph: components are connected by the dtypes they
        #    consume and produce
        runtime.add_task(Sensor(flow), TRUTHY, READING, is_persistent=True)
        runtime.add_investigator(Surrogate(flow), READING, PREDICTION)
        runtime.add_task(Sink(flow), PREDICTION, NULL_DTYPE)
        runtime.start()

        # 5. watch the served surrogate improve
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while loop.time() < deadline:
            await asyncio.sleep(2.0)
            error = await served_rmse(runtime)
            print(f"served surrogate rmse: {error:.4f}")

            if error < 2 * PUBLISH_RMSE:
                print("surrogate is accurate: done")
                return 0
            if runtime.last_error:
                break

        print(f"no accurate surrogate (state {runtime.state},"
              f" error {runtime.last_error})")
        return 1

    finally:
        await runtime.stop()
        await flow.shutdown()
        await broker.stop()
# --8<-- [end:main]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=120.0)
    sys.exit(asyncio.run(main(parser.parse_args().timeout)))
