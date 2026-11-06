"""E1 ex-situ overhead: ROSE's streaming learner, hand-wired vs through DT.

Two rows on the same local process pool and the same no-op tasks (a
training, an active-learning and an always-met criterion task per window,
all `as_executable=False` function tasks):

  bare   ROSE's `SequentialActiveLearner` on a `rose.Stream` fed in-process
         (`attach_source`, `skip_simulation_step=True`), as in
         `streaming_learner_perf.py` engine mode
  dt     a `StreamingLearnerInvestigator` subclass in a `DTRuntime`, fed
         through the twin's input edge: an external `ChannelPublisher`
         (as a sensor script opens one) publishes every sample on a
         channel that `add_input` binds to the input dtype (embedded ZMQ
         broker); it reaches the learner via `ON_INPUT`.  The twin also
         runs its (no-op, local) inference task per sample, as the real
         shape does

Per row and batch size, two runs:

  throughput  all samples offered at once; msg/s = samples / time from the
              first sample to the last window
  latency     paced: one window's worth of samples, then wait for that
              window's published model, `--windows` times; per window the
              time from its last sample to its published model (bare:
              `on_model_ready`; dt: `published_model`, the call
              `publish_new_model` makes).  Paced so that no queueing is
              included -- under the saturating feed of the throughput run
              this time is mostly the backlog ahead of the window.

The criterion is met on every window, so every window publishes.  Both
rows must process the same number of samples; the harness asserts it.

Both rows use `conflate=False` and `max_wait=None`: no dropped samples,
windows only by size, so window k is samples [k*b, (k+1)*b).

    python experiments/dt-paper/e1-overhead/bench_dt_exsitu.py \\
        --workers 8 --out results/exsitu.json
"""

import argparse
import asyncio
import json
import os
import platform
import socket
import statistics
import subprocess
import time

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from radical.asyncflow import WorkflowEngine  # type: ignore
from rose import Stream  # type: ignore
from rose.al.active_learner import SequentialActiveLearner  # type: ignore

from digitaltwin import (
    CODEC_JSON,
    ChannelPublisher,
    DataType,
    DTRuntime,
    PubSubConfig,
    TypedData,
    ZMQ_BrokerProcess,
    connect_stream_client,
)
from digitaltwin.learn import StreamingLearnerInvestigator

X = DataType("e1x-in")
CHANNEL = "e1x/samples"
Y = DataType("e1x-out")

BATCH_SIZES = [1, 2, 5, 10, 20, 50, 100]
N_SAMPLES = 400
DRAIN_TIMEOUT = 120.0


# module-level so they pickle into the process pool
async def training(*args):
    return {"w": 1.0}


async def active_learn(*args):
    return None


async def criterion(*args):
    return 0.0


def register(learner):
    learner.training_task(as_executable=False)(training)
    learner.active_learn_task(as_executable=False)(active_learn)
    learner.as_stop_criterion(metric_name="noop", threshold=1.0, operator="<",
                              as_executable=False)(criterion)


def window_latencies(feed_t, pub_t, bs):
    """Last sample of window k -> its published model, in seconds."""
    out = []
    for k, tp in enumerate(pub_t):
        last = (k + 1) * bs - 1
        if last < len(feed_t):
            out.append(tp - feed_t[last])
    return out


def bare_learner(flow, bs):
    learner = SequentialActiveLearner(flow)
    register(learner)
    return learner, Stream(batch_size=bs, max_wait=None, conflate=False)


async def run_bare(flow, bs, n):
    learner, stream = bare_learner(flow, bs)
    feed_t, pub_t = [], []
    learner.on_model_ready(lambda state: pub_t.append(time.perf_counter()))

    async def source():
        for i in range(n):
            feed_t.append(time.perf_counter())
            yield i

    stream.attach_source(source())
    count = 0
    t_last = None
    async for state in learner.start(stream=stream, skip_simulation_step=True):
        count += state.window_size
        t_last = time.perf_counter()
    return count, t_last - feed_t[0], window_latencies(feed_t, pub_t, bs)


async def run_bare_paced(flow, bs, windows):
    learner, stream = bare_learner(flow, bs)
    published = asyncio.Event()
    pub_t = []

    def ready(state):
        pub_t.append(time.perf_counter())
        published.set()

    learner.on_model_ready(ready)
    count = 0

    async def consume():
        nonlocal count
        async for state in learner.start(stream=stream,
                                         skip_simulation_step=True):
            count += state.window_size

    consumer = asyncio.ensure_future(consume())
    lat = []
    try:
        for w in range(windows):
            published.clear()
            for i in range(bs):
                t_feed = time.perf_counter()
                await stream.feed(w * bs + i)
            await asyncio.wait_for(published.wait(), DRAIN_TIMEOUT)
            lat.append(pub_t[-1] - t_feed)
    finally:
        learner.stop()
        await asyncio.wait_for(consumer, DRAIN_TIMEOUT)
    return count, lat


class Learner(StreamingLearnerInvestigator):
    """The DT row: same tasks, timestamps on feed, window and publish."""

    def __init__(self, flow, bs):
        super().__init__(flow, None, batch_size=bs, max_wait=None,
                         conflate=False)
        register(self.learner)
        self.feed_t, self.pub_t = [], []
        self.count = 0
        self.t_last = None
        self.done = asyncio.Event()
        self.published = asyncio.Event()
        self.expected = None

        async def infer(in_data, **kwargs):
            return TypedData(Y, in_data.data)

        self.inference_task = infer

    async def _feed(self, in_data):
        self.feed_t.append(time.perf_counter())
        await super()._feed(in_data)

    def published_model(self, state):
        self.pub_t.append(time.perf_counter())
        self.published.set()
        return super().published_model(state)

    def on_window(self, state):
        self.count += state.window_size
        self.t_last = time.perf_counter()
        if self.expected is not None and self.count >= self.expected:
            self.done.set()


async def run_dt(flow, broker, bs, n, paced_windows=None):
    stream = await connect_stream_client("e1-exsitu", *broker.get_connection_str())
    runtime = DTRuntime(flow, stream)
    learner = Learner(flow, bs)
    learner.expected = n if n is not None else bs * paced_windows
    bound = runtime.add_input(X, CHANNEL, CODEC_JSON)
    runtime.add_investigator(learner, X, Y)
    runtime.start()
    publisher = await ChannelPublisher.open(
        CHANNEL, CODEC_JSON, config=PubSubConfig(None, *broker.get_connection_str()),
        timeout=10.0)
    try:
        if bound is not None:
            await bound
        # bootstrap model published: the twin answers
        deadline = time.monotonic() + 30
        while not learner._started:
            if time.monotonic() > deadline:
                raise RuntimeError(f"twin not ready: {runtime.state} "
                                   f"{runtime.last_error}")
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.3)  # let the subscription reach the broker
        lat = []
        if paced_windows:
            for w in range(paced_windows):
                learner.published.clear()
                for i in range(bs):
                    t_pub = time.perf_counter()
                    await publisher.publish(w * bs + i)
                await asyncio.wait_for(learner.published.wait(), DRAIN_TIMEOUT)
                # from the last sample's publish on the channel: includes
                # the hop through the broker into the twin
                lat.append(learner.pub_t[-1] - t_pub)
        else:
            for i in range(n):
                await publisher.publish(i)
        try:
            await asyncio.wait_for(learner.done.wait(), DRAIN_TIMEOUT)
        except TimeoutError:
            raise RuntimeError(f"dt row stalled: {len(learner.feed_t)} fed, "
                               f"{learner.count} in windows of {n}; "
                               f"{runtime.state} {runtime.last_error}")
    finally:
        await publisher.close()
        await runtime.stop()
    if paced_windows:
        return learner.count, lat
    return (learner.count, learner.t_last - learner.feed_t[0],
            window_latencies(learner.feed_t, learner.pub_t, bs))


def provenance(args) -> dict:
    root = Path(__file__).resolve().parents[3]

    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(root), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E1 ex-situ overhead",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git("rev-parse", "HEAD"),
        "digital_twins_dirty": bool(git("status", "--porcelain", "--", "src")),
        "backend": f"local concurrent pool ({args.workers} workers)",
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args),
    }


def summary(lat):
    if not lat:
        return {"n": 0}
    return {"n": len(lat), "p50_ms": statistics.median(lat) * 1e3,
            "mean_ms": statistics.fmean(lat) * 1e3,
            "max_ms": max(lat) * 1e3}


async def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--samples", type=int, default=N_SAMPLES)
    p.add_argument("--batch-sizes", default=",".join(map(str, BATCH_SIZES)))
    p.add_argument("--windows", type=int, default=20,
                   help="windows per paced latency run")
    p.add_argument("--rows", default="bare,dt")
    p.add_argument("--out")
    args = p.parse_args()
    sizes = [int(b) for b in args.batch_sizes.split(",") if b]
    rows = [r for r in args.rows.split(",") if r]

    from rhapsody.backends import ConcurrentExecutionBackend  # type: ignore

    exe = await ConcurrentExecutionBackend(ProcessPoolExecutor(args.workers))
    flow = await WorkflowEngine.create(backend=exe)
    broker = ZMQ_BrokerProcess()
    await broker.start()

    results = {"provenance": provenance(args), "batch_sizes": sizes, "rows": {}}
    try:
        # warm-up: one small run per row, not recorded
        if "bare" in rows:
            await run_bare(flow, 5, 50)
        if "dt" in rows:
            await run_dt(flow, broker, 5, 50)

        for row in rows:
            out = results["rows"][row] = {"msg_per_s": [], "samples": [],
                                          "publish_latency_saturated": [],
                                          "publish_latency": []}
            for bs in sizes:
                if row == "bare":
                    count, elapsed, lat = await run_bare(flow, bs, args.samples)
                else:
                    count, elapsed, lat = await run_dt(flow, broker, bs,
                                                       args.samples)
                assert count == args.samples, (row, bs, count, args.samples)
                rate = count / elapsed
                out["msg_per_s"].append(rate)
                out["samples"].append(count)
                out["publish_latency_saturated"].append(summary(lat))

                if row == "bare":
                    pcount, plat = await run_bare_paced(flow, bs, args.windows)
                else:
                    pcount, plat = await run_dt(flow, broker, bs, None,
                                                paced_windows=args.windows)
                assert pcount == bs * args.windows, (row, bs, pcount)
                out["publish_latency"].append(summary(plat))
                print(f"{row:5s} batch={bs:4d} {rate:9.0f} msg/s  "
                      f"paced publish p50 {summary(plat).get('p50_ms', float('nan')):7.2f} ms "
                      f"({count} + {pcount} samples)", flush=True)
    finally:
        await broker.stop()
        await flow.shutdown()

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"results: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
