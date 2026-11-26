import asyncio
from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from radical.doppelganger.runtime import DTRuntime
from radical.doppelganger.streaming import connect_stream_client
from radical.doppelganger.components import TRUTHY, NULL_DTYPE

from dtypes import *
from sensor import NumberCamera
from sensor import FashionCamera

from investigators import HandwritingInvestigator, FashionInvestigator
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
    pubsub_client = await connect_stream_client("03-mnst-active-learn-multi-stream")

    runtime = DTRuntime(flow, pubsub_client)

    # create tasks and investigators
    sensor = NumberCamera(flow)
    fcam = FashionCamera(flow)
    investigator = HandwritingInvestigator(flow)
    fashion = FashionInvestigator(flow)
    data_sink = MySink(flow, "number-sink.out")
    f_sink = MySink(flow, "f-sink.out")

    runtime.add_task(sensor, TRUTHY, NUMBER_CAMERA_DTYPE, is_persistent=True)
    runtime.add_task(fcam, TRUTHY, FASHION_CAMERA_DTYPE, is_persistent=True)
    runtime.add_investigator(investigator, NUMBER_CAMERA_DTYPE, DIGIT_DTYPE)
    runtime.add_investigator(fashion, FASHION_CAMERA_DTYPE, FASHION_DTYPE)
    runtime.add_task(data_sink, DIGIT_DTYPE, NULL_DTYPE)
    runtime.add_task(f_sink, FASHION_DTYPE, NULL_DTYPE)

    runtime.print_graph()
    runtime.start()

    # let it run
    await asyncio.sleep(70)
    await runtime.stop()
    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
