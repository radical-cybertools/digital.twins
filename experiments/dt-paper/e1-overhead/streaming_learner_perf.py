"""Throughput benchmark for ROSE's stream-driven learner.

A `SequentialActiveLearner` started on a `rose.Stream` with
`skip_simulation_step=True` (window -> training -> active learning, the
shape of the former `StreamingActiveLearner`).

Measures raw msg/sec over batch size for two feed paths:
  - inproc:  items pushed straight into the stream (attach_source)
  - zmq:     items published through the DT ZMQ broker (XSUB/XPUB proxy)
             and forwarded to Stream.feed() by a PubSubClient subscriber

and two task payloads:
  - stub:    task submission replaced by an async no-op
             (pure streaming machinery: queue -> window -> iteration)
  - engine:  real no-op function tasks through asyncflow +
             ConcurrentExecutionBackend(ProcessPoolExecutor)

Writes results to streaming_perf.json, or to --out (plot with
plot_streaming_perf.py).  Self-contained: spawns its own broker process.

    # all cells, default pool (ProcessPoolExecutor() = os.cpu_count() workers)
    python streaming_learner_perf.py
    # engine rows only, 8 workers
    python streaming_learner_perf.py --modes engine --workers 8 --out p2.json
"""

import argparse
import asyncio
import json
import multiprocessing
import os
import platform
import socket
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

from radical.asyncflow import WorkflowEngine
from rose import Stream
from rose.al.active_learner import SequentialActiveLearner

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
    stream = Stream(batch_size=batch_size)
    if mode == "stub":
        learner = SequentialActiveLearner(MagicMock(spec=WorkflowEngine))
        learner.training_function = {"func": training}
        learner.active_learn_function = {"func": active_learn}
        learner._register_task = _stub_register
    else:
        learner = SequentialActiveLearner(flow)
        learner.training_task(as_executable=False)(training)
        learner.active_learn_task(as_executable=False)(active_learn)
    return learner, stream


async def consume(learner, stream):
    """Drain the learner; return (n_items, elapsed until last window)."""
    n = 0
    t0 = t_last = time.perf_counter()
    async for state in learner.start(stream=stream, skip_simulation_step=True):
        n += state.window_size
        t_last = time.perf_counter()
    return n, t_last - t0


async def run_inproc(batch_size, mode, flow):
    learner, stream = make_learner(batch_size, mode, flow)

    async def source():
        for i in range(N_MSGS[mode]):
            yield i

    stream.attach_source(source())
    n, elapsed = await consume(learner, stream)
    return n / elapsed


async def run_zmq(batch_size, mode, flow):
    learner, stream = make_learner(batch_size, mode, flow)

    pub = ZMQ_PS_Client(PUB_ADDR)
    await pub.connect()
    pub_client = PubSubClient(pub, "e1-perf")

    sub = ZMQ_PS_Client(sub_addr=SUB_ADDR)
    await sub.connect()
    queue: asyncio.Queue = asyncio.Queue()
    await PubSubClient(sub, "e1-perf").subscribe_to_dtype(PERF_DTYPE, queue)

    async def forward():
        # end of stream: idle timeout (PUB/SUB may drop under load)
        while True:
            try:
                td = await asyncio.wait_for(queue.get(), IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                learner.stop()
                return
            await stream.feed(td.data)

    async def publish():
        for i in range(N_MSGS[mode]):
            await pub_client.publish(PERF_DTYPE, i)

    fwd = asyncio.ensure_future(forward())
    pub_task = asyncio.ensure_future(publish())
    n, elapsed = await consume(learner, stream)
    await pub_task
    fwd.cancel()
    # learner.stop() fires after IDLE_TIMEOUT of silence; the last windows
    # processed before that are already timed, no idle time is included
    for client in (pub, sub):
        await client.close()
    return n / elapsed


def provenance(args) -> dict:
    root = Path(__file__).resolve().parents[3]

    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(root), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E1 ROSE streaming learner throughput",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git("rev-parse", "HEAD"),
        "digital_twins_dirty": bool(git("status", "--porcelain", "--", "src")),
        "backend": f"local concurrent pool ({args.workers or os.cpu_count()} workers)",
        "cpu_count": os.cpu_count(),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args),
    }


async def main(args):
    from concurrent.futures import ProcessPoolExecutor

    from rhapsody.backends import ConcurrentExecutionBackend

    exe = await ConcurrentExecutionBackend(ProcessPoolExecutor(args.workers))
    flow = await WorkflowEngine.create(backend=exe)

    results = {}
    for mode in args.modes:
        for feed in args.feeds:
            run = run_inproc if feed == "inproc" else run_zmq
            rates = []
            for bs in BATCH_SIZES:
                rate = await run(bs, mode, flow)
                rates.append(rate)
                print(f"{mode:7s} {feed:7s} batch={bs:4d}  {rate:10.0f} msg/s", flush=True)
            results[f"{mode}/{feed}"] = rates

    results["batch_sizes"] = BATCH_SIZES
    results["provenance"] = provenance(args)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"wrote {args.out}")

    await flow.shutdown()


def _run_broker():
    # broker (and its ZMQ context) must be created inside the child
    # process: ZMQ sockets are not fork-safe
    ZMQ_Broker(PUB_ADDR, SUB_ADDR).run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=None,
                        help="process pool size (default: ProcessPoolExecutor() "
                             "default, os.cpu_count())")
    parser.add_argument("--modes", default="stub,engine")
    parser.add_argument("--feeds", default="inproc,zmq")
    parser.add_argument("--out", default="streaming_perf.json")
    args = parser.parse_args()
    args.modes = [m for m in args.modes.split(",") if m]
    args.feeds = [f for f in args.feeds.split(",") if f]

    broker_proc = multiprocessing.Process(target=_run_broker, daemon=True)
    broker_proc.start()
    time.sleep(0.5)
    try:
        asyncio.run(main(args))
    finally:
        broker_proc.terminate()
