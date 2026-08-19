import asyncio
from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from digitaltwin.runtime import DTRuntime
from digitaltwin.streaming import PubSubClient, ZMQ_PS_Client, connect_stream_client
from digitaltwin.components import TRUTHY, NULL_DTYPE

from dtypes import *
from sensor import MySensor
from agent import MyAgent
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
    pubsub_client = await connect_stream_client("11-shared-sim")

    runtime = DTRuntime(flow, pubsub_client)

    # create tasks and investigators
    sensor = MySensor(flow)
    agent = MyAgent(flow)
    data_sink = MySink(flow)

    runtime.add_task(sensor, TRUTHY, SENSOR_DTYPE, is_persistent=True)
    runtime.add_agent(agent, SENSOR_DTYPE, INFERENCE_DTYPE)
    runtime.add_task(data_sink, INFERENCE_DTYPE, NULL_DTYPE)

    runtime.print_graph()
    runtime.start()

    # let it run
    await asyncio.sleep(30)
    print("DONE======================")
    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
