"""Throughput benchmark for ROSE's StreamingActiveLearner.

Measures raw msg/sec over batch size for two feed paths:
  - inproc:  items pushed straight into the learner via feed()
  - zmq:     items published through the DT ZMQ broker (XSUB/XPUB proxy)
             and forwarded to feed() by a PubSubClient subscriber

and two task payloads:
  - stub:    task submission replaced by an async no-op
             (pure streaming machinery: queue -> window -> iteration)
  - engine:  real no-op function tasks through asyncflow +
             ConcurrentExecutionBackend(ProcessPoolExecutor)

Writes results to streaming_perf.json (plot with plot_streaming_perf.py).
Self-contained: spawns its own broker process.
"""

import asyncio
import json
import multiprocessing
import time
from unittest.mock import MagicMock

from radical.asyncflow import WorkflowEngine
from rose.al.streaming_learner import StreamingActiveLearner

from digitaltwin.components import DataType
from digitaltwin.streaming import PubSubClient, ZMQ_Broker, ZMQ_PS_Client

PUB_ADDR = "tcp://127.0.0.1:5100"
SUB_ADDR = "tcp://127.0.0.1:5101"
PERF_DTYPE = DataType(name="perf_data")

BATCH_SIZES = [1, 2, 5, 10, 20, 50, 100]
N_MSGS = {"stub": 5000, "engine": 400}
IDLE_TIMEOUT = 3.0  # zmq: end of stream = no message for this long


# module-level so they pickle into the process pool
async def training(*args):
    return None


async def active_learn(*args):
    return None


async def _stub_register(task_obj, deps=None):
    return None


def make_learner(batch_size, mode, flow):
    if mode == "stub":
        learner = StreamingActiveLearner(
            MagicMock(spec=WorkflowEngine), batch_size=batch_size
        )
        learner.training_function = {"func": training}
        learner.active_learn_function = {"func": active_learn}
        learner._register_task = _stub_register
    else:
        learner = StreamingActiveLearner(flow, batch_size=batch_size)
        learner.training_task(as_executable=False)(training)
        learner.active_learn_task(as_executable=False)(active_learn)
    return learner


async def consume(learner):
    """Drain the learner; return (n_items, elapsed until last window)."""
    n = 0
    t0 = t_last = time.perf_counter()
    async for state in learner.start():
        n += state.window_size
        t_last = time.perf_counter()
    return n, t_last - t0


async def run_inproc(batch_size, mode, flow):
    learner = make_learner(batch_size, mode, flow)

    async def source():
        for i in range(N_MSGS[mode]):
            yield i

    learner.attach_source(source())
    n, elapsed = await consume(learner)
    return n / elapsed


async def run_zmq(batch_size, mode, flow):
    learner = make_learner(batch_size, mode, flow)

    pub = ZMQ_PS_Client(PUB_ADDR)
    await pub.connect()
    pub_client = PubSubClient(pub)

    sub = ZMQ_PS_Client(sub_addr=SUB_ADDR)
    await sub.connect()
    queue: asyncio.Queue = asyncio.Queue()
    await PubSubClient(sub).subscribe_to_dtype(PERF_DTYPE, queue)

    async def forward():
        # end of stream: idle timeout (PUB/SUB may drop under load)
        while True:
            try:
                td = await asyncio.wait_for(queue.get(), IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                learner.stop()
                return
            await learner.feed(td.data)

    async def publish():
        for i in range(N_MSGS[mode]):
            await pub_client.publish(PERF_DTYPE, i)

    fwd = asyncio.ensure_future(forward())
    pub_task = asyncio.ensure_future(publish())
    n, elapsed = await consume(learner)
    await pub_task
    fwd.cancel()
    # learner.stop() fires after IDLE_TIMEOUT of silence; the last windows
    # processed before that are already timed, no idle time is included
    for client in (pub, sub):
        if client.task:
            client.task.cancel()
        for soc in (client.pub_soc, client.sub_soc):
            if soc is not None:
                soc.close()
    return n / elapsed


async def main():
    from concurrent.futures import ProcessPoolExecutor

    from rhapsody.backends import ConcurrentExecutionBackend

    exe = await ConcurrentExecutionBackend(ProcessPoolExecutor())
    flow = await WorkflowEngine.create(backend=exe)

    results = {}
    for mode in ("stub", "engine"):
        for feed in ("inproc", "zmq"):
            run = run_inproc if feed == "inproc" else run_zmq
            rates = []
            for bs in BATCH_SIZES:
                rate = await run(bs, mode, flow)
                rates.append(rate)
                print(f"{mode:7s} {feed:7s} batch={bs:4d}  {rate:10.0f} msg/s", flush=True)
            results[f"{mode}/{feed}"] = rates

    results["batch_sizes"] = BATCH_SIZES
    with open("streaming_perf.json", "w") as f:
        json.dump(results, f, indent=2)
    print("wrote streaming_perf.json")

    await flow.shutdown()


def _run_broker():
    # broker (and its ZMQ context) must be created inside the child
    # process: ZMQ sockets are not fork-safe
    ZMQ_Broker(PUB_ADDR, SUB_ADDR).run()


if __name__ == "__main__":
    broker_proc = multiprocessing.Process(target=_run_broker, daemon=True)
    broker_proc.start()
    time.sleep(0.5)
    try:
        asyncio.run(main())
    finally:
        broker_proc.terminate()
