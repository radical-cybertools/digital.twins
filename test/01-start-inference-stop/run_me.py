import asyncio
from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from radical.doppelganger.runtime import DTRuntime
from radical.doppelganger.streaming import connect_stream_client
from radical.doppelganger.components import NULL_DTYPE

from dtypes import *
from model import MyModel
from data_sink import MySink

from radical.asyncflow.logging import init_default_logger
import logging

logger = logging.getLogger(__name__)

# put it all together
# sensor channel --> model --> data_sink
#
# The sensor is external: run sensor.py in its own terminal.


async def main():
    init_default_logger(logging.INFO)
    logging.getLogger("radical.asyncflow").setLevel(logging.WARNING)
    logging.getLogger("rhapsody").setLevel(logging.WARNING)

    # create engine
    exe = await ConcurrentExecutionBackend(ProcessPoolExecutor())
    flow = await WorkflowEngine.create(backend=exe)

    # create the twin's namespaced stream client
    pubsub_client = await connect_stream_client("01-start-inference-stop")

    runtime = DTRuntime(flow, pubsub_client)

    # create tasks and investigators
    model = MyModel(flow)
    data_sink = MySink(flow)

    # the graph opens at its input edge: bind the sensor's shared channel
    runtime.add_input(SENSOR_DTYPE, SENSOR_CHANNEL)
    runtime.add_investigator(model, SENSOR_DTYPE, INFERENCE_DTYPE)
    runtime.add_task(data_sink, INFERENCE_DTYPE, NULL_DTYPE)

    runtime.print_graph()
    runtime.start()

    # let it run
    await asyncio.sleep(30)
    await runtime.stop()
    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
