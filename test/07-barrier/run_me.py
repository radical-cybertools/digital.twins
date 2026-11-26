import asyncio
from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from radical.doppelganger.runtime import DTRuntime
from radical.doppelganger.streaming import connect_stream_client
from radical.doppelganger.components import TRUTHY, NULL_DTYPE, Barrier, DataType

from sensor import MySensor
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

    # create the twin's namespaced stream client
    pubsub_client = await connect_stream_client("07-barrier")

    runtime = DTRuntime(flow, pubsub_client)

    a = DataType("A")
    b = DataType("B")
    c = DataType("C")
    fast = DataType("FAST")
    slow = DataType("SLOW")

    # create tasks and investigators
    sensorA = MySensor(flow, 1, a)
    sensorB = MySensor(flow, 2, b)
    sensorC = MySensor(flow, 5, c)
    fast_sensor = MySensor(flow, 0.5, fast)
    slow_sensor = MySensor(flow, 10, slow)

    model = MyModel(flow)
    window_model = MyModel(flow, is_window=True)

    data_sink = MySink(flow)

    # Add a barrier
    # barrier = Barrier(name="Barrier")
    # barrier.add_dtype(a)
    # barrier.add_dtype(b)
    # runtime.add_barrier(barrier)

    # # tiered barriers
    # barrier2 = Barrier(name="Barrier2")
    # barrier2.add_dtype(b)
    # barrier2.add_dtype(c)
    # runtime.add_barrier(barrier2)

    # Add a soft barrier
    sb = Barrier(name="SoftBarrier")
    a_w = sb.add_dtype(a, False)
    b_w = sb.add_dtype(b, False)
    c_w = sb.add_dtype(c, False)
    sb.add_dtype(fast, hard=True)
    runtime.add_barrier(sb)

    runtime.add_task(sensorA, TRUTHY, a, is_persistent=True)
    runtime.add_task(sensorB, TRUTHY, b, is_persistent=True)
    runtime.add_task(sensorC, TRUTHY, c, is_persistent=True)
    runtime.add_task(fast_sensor, TRUTHY, fast, is_persistent=True)

    runtime.add_investigator(window_model, a_w, DataType("INF-A"))
    runtime.add_investigator(window_model, b_w, DataType("INF-B"))
    runtime.add_investigator(window_model, c_w, DataType("INF-C"))
    runtime.add_investigator(model, fast, DataType("INF-FAST"))

    runtime.add_task(data_sink, DataType("INF-A"), NULL_DTYPE)
    runtime.add_task(data_sink, DataType("INF-B"), NULL_DTYPE)
    runtime.add_task(data_sink, DataType("INF-C"), NULL_DTYPE)
    runtime.add_task(data_sink, DataType("INF-FAST"), NULL_DTYPE)

    runtime.print_graph()
    runtime.start()

    # let it run
    await asyncio.sleep(30)
    await runtime.stop()
    await flow.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
