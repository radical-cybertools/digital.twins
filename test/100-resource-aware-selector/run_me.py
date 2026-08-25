import asyncio
from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from digitaltwin.runtime import DTRuntime
from digitaltwin.streaming import connect_stream_client
from digitaltwin.components import TRUTHY, NULL_DTYPE

from dtypes import *
from sensor import MySensor
from agent import MyAgent
from profiler.components import (
    ProfilerInvestigator,
    EndpointInvestigator,
    TASK_DESCRIPTION_DTYPE,
    PROFILE_RESULTS,
)
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
    pubsub_client = await connect_stream_client("05-agent-w-multi-investigators")

    runtime = DTRuntime(flow, pubsub_client)

    # create tasks and investigators
    sensor = MySensor(flow)
    agent = MyAgent(flow)
    data_sink = MySink(flow)

    # Add profiling agents
    base_profiler = ProfilerInvestigator(flow, "./profile/nersc_profiler")
    pi_profiler = EndpointInvestigator(flow, "pi", "./profiler/pi_profiler")

    # add profiling tasks
    runtime.add_investigator(base_profiler, TASK_DESCRIPTION_DTYPE, PROFILE_RESULTS)
    runtime.add_investigator(
        pi_profiler, PROFILE_RESULTS, DataType("pi_PREDICT_RUNTIME")
    )

    # add main tasks
    runtime.add_task(sensor, TRUTHY, SENSOR_DTYPE, is_persistent=True)
    runtime.add_agent(agent, SENSOR_DTYPE, INFERENCE_DTYPE)
    runtime.add_task(data_sink, INFERENCE_DTYPE, NULL_DTYPE)

    runtime.print_graph()
    runtime.start()

    # let it run
    await asyncio.sleep(30)
    print("DONE======================")
    await runtime.stop()
    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
