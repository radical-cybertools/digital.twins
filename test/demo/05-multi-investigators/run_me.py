import asyncio
from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from radical.doppelganger.runtime import DTRuntime
from radical.doppelganger.streaming import connect_stream_client
from radical.doppelganger.components import TRUTHY, NULL_DTYPE

from dtypes import *
from in_timer import Timer
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

    # create the twin's namespaced stream client
    pubsub_client = await connect_stream_client("05-multi-investigators")

    runtime = DTRuntime(flow, pubsub_client)

    # create tasks and investigators
    timer = Timer(flow)
    agent = MyAgent(flow)
    data_sink = MySink(flow)

    runtime.add_task(timer, TRUTHY, TIMER_TRIGGER_DTYPE, is_persistent=True)
    runtime.add_agent(agent, TIMER_TRIGGER_DTYPE, PI_DTYPE)
    runtime.add_task(data_sink, PI_DTYPE, NULL_DTYPE)

    runtime.print_graph()
    runtime.start()

    # let it run
    await asyncio.sleep(30)
    print("DONE======================")
    await runtime.stop()
    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
