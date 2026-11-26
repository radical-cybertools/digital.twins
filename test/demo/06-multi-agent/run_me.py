import asyncio
from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from radical.doppelganger.runtime import DTRuntime
from radical.doppelganger.streaming import connect_stream_client
from radical.doppelganger.components import TRUTHY, NULL_DTYPE

from dtypes import *
from sensor import Camera
from hand_agent import HandAgent
from translate_agent import TranslateAgent

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

    # create the twin's namespaced stream client
    pubsub_client = await connect_stream_client("06-multi-agent")

    runtime = DTRuntime(flow, pubsub_client)

    # create tasks and investigators
    sensor = Camera(flow)
    digits = HandAgent(flow)
    english = TranslateAgent(flow)
    data_sink = MySink(flow)

    #   sensor ---> digit ---> english ---> sink

    runtime.add_task(sensor, TRUTHY, CAMERA_DTYPE, is_persistent=True)
    runtime.add_agent(digits, CAMERA_DTYPE, DIGIT_DTYPE)
    runtime.add_agent(english, DIGIT_DTYPE, ENGLISH_DTYPE)
    runtime.add_task(data_sink, ENGLISH_DTYPE, NULL_DTYPE)

    runtime.print_graph()
    runtime.start()

    # let it run
    await asyncio.sleep(85)
    await runtime.stop()
    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
