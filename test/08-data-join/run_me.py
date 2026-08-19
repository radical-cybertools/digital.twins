import asyncio
from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from digitaltwin.runtime import DTRuntime
from digitaltwin.streaming import PubSubClient, ZMQ_PS_Client, connect_stream_client
from digitaltwin.components import TRUTHY, NULL_DTYPE

from dtypes import *
from sensor import NumberSensor, LetterSensor
from model import MyModel
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
    pubsub_client = await connect_stream_client("08-data-join")

    runtime = DTRuntime(flow, pubsub_client)

    # create tasks and investigators
    numbers = NumberSensor(flow)
    letters = LetterSensor(flow)
    model = MyModel(flow)
    data_sink = MySink(flow)

    runtime.add_task(numbers, TRUTHY, NUMBER_SENSOR_DTYPE, is_persistent=True)
    runtime.add_task(letters, TRUTHY, LETTER_SENSOR_DTYPE, is_persistent=True)

    JOIN_NUM_LETTER_DTYPE = JoinDataType([NUMBER_SENSOR_DTYPE, LETTER_SENSOR_DTYPE])

    runtime.add_data_join(JOIN_NUM_LETTER_DTYPE)
    runtime.add_investigator(model, JOIN_NUM_LETTER_DTYPE, INFERENCE_DTYPE)
    runtime.add_task(data_sink, INFERENCE_DTYPE, NULL_DTYPE)

    runtime.print_graph()
    runtime.start()

    # let it run
    await asyncio.sleep(30)
    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
