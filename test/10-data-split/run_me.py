import asyncio
from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from digitaltwin.runtime import DTRuntime
from digitaltwin.streaming import PubSubClient, ZMQ_PS_Client, connect_stream_client
from digitaltwin.components import TRUTHY, NULL_DTYPE

from dtypes import *
from sensor import NumberSensor
from split import HighLow
from model import HighModel, LowModel
from data_sink import MySink

from radical.asyncflow.logging import init_default_logger
import logging

logger = logging.getLogger(__name__)

# put it all together
# sensor --> model --> data_sink


async def main():
    init_default_logger(logging.INFO)
    logging.getLogger("radical.asyncflow").setLevel(logging.WARNING)
    logging.getLogger("rhapsody").setLevel(logging.WARNING)

    # create engine
    exe = await ConcurrentExecutionBackend(ProcessPoolExecutor())
    flow = await WorkflowEngine.create(backend=exe)

    # create pubsub backend client
    pubsub_client = await connect_stream_client("10-data-split")

    runtime = DTRuntime(flow, pubsub_client)

    # create tasks and investigators
    numbers = NumberSensor(flow)
    split = HighLow(flow)  # asyncflow not required
    h_model = HighModel(flow)
    l_model = LowModel(flow)
    data_sink = MySink(flow)

    runtime.add_task(numbers, TRUTHY, NUMBER_SENSOR_DTYPE, is_persistent=True)

    runtime.add_data_split_task(
        split, NUMBER_SENSOR_DTYPE, [HIGH_NUMBER_DTYPE, LOW_NUMBER_DTYPE]
    )

    runtime.add_investigator(h_model, HIGH_NUMBER_DTYPE, INFERENCE_DTYPE)
    runtime.add_investigator(l_model, LOW_NUMBER_DTYPE, INFERENCE_DTYPE)

    # implicit JOIN (interleaving)
    runtime.add_task(data_sink, INFERENCE_DTYPE, NULL_DTYPE)

    runtime.print_graph()
    runtime.start()

    # let it run
    await asyncio.sleep(10)
    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
