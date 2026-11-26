import asyncio

from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend
from concurrent.futures import ProcessPoolExecutor

from radical.doppelganger.components import *
from radical.doppelganger.runtime import DTRuntime
from radical.doppelganger.streaming import connect_stream_client

from radical.asyncflow.logging import init_default_logger

import logging

logger = logging.getLogger(__name__)


# Simply start and then stop the runtime.


# Globals:


if __name__ == "__main__":

    async def main():
        init_default_logger(logging.INFO)
        logging.getLogger("radical.asyncflow").setLevel(logging.WARNING)
        logging.getLogger("rhapsody").setLevel(logging.WARNING)

        exe = await ConcurrentExecutionBackend(ProcessPoolExecutor())
        flow = await WorkflowEngine.create(backend=exe)

        # create the twin's namespaced stream client
        pubsub_client = await connect_stream_client("00-start-stop")

        runtime = DTRuntime(flow, pubsub_client)

        runtime.print_graph()
        runtime.start()

        # let it run....
        print("Sleeping...")
        await asyncio.sleep(10)
        await runtime.stop()
        await flow.shutdown()

    asyncio.run(main())
