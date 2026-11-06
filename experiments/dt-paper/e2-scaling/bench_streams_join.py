"""E2b: K input streams joined into one consumer, at rising input rates.

One twin.  K external producers (`ChannelPublisher`, as a sensor script
opens one) publish on K channels; `add_input` binds each to its own input
dtype, `add_data_join(JoinDataType([...]))` joins them, and a `UtilityTask`
consumes the join output and records end-to-end latency: from the latest
of the K publishes that make up a joined tuple to the consumer seeing the
tuple.  Embedded ZMQ broker; no execution backend involved (no task runs).

The join is lockstep: depth-1 queues per input, one tuple per complete set
(`runtime._JoinComponent`).  Producers therefore publish in rounds -- one
message on every channel per round, at `rate` rounds per second -- which
is what keeps a lockstep join well-defined.

Per K: first a base point at a low rate, then rising rates until the p50
latency is at least double the base point's, the join drops tuples, or the
producers cannot keep the rate.  The highest rate below that is the max
sustainable input rate; inputs/s = K x rounds/s.

    python experiments/dt-paper/e2-scaling/bench_streams_join.py \\
        --streams 1,2,4,8,16,32 --out results/join.json
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

from pathlib import Path

from digitaltwin import (
    CODEC_JSON,
    NULL_DTYPE,
    ChannelPublisher,
    DataType,
    DTRuntime,
    PubSubConfig,
    UtilityTask,
    ZMQ_BrokerProcess,
    connect_stream_client,
)
from digitaltwin.components import JoinDataType

BASE_RATE = 10.0
RATES = [10, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
SETTLE = 3.0


class Sink(UtilityTask):
    def __init__(self, seen):
        super().__init__(None)
        self.seen = seen

    async def main_loop(self, runtime, in_data):
        now = time.perf_counter()
        ts = [td.data["t"] for td in in_data.data]
        rounds = {td.data["r"] for td in in_data.data}
        self.seen.append((now - max(ts), len(rounds) == 1))


def provenance(args) -> dict:
    root = Path(__file__).resolve().parents[3]

    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(root), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E2b streams join scaling",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git("rev-parse", "HEAD"),
        "digital_twins_dirty": bool(git("status", "--porcelain", "--", "src")),
        "backend": "embedded ZMQ broker, no execution backend",
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args),
    }


async def one_point(broker, k, rate, seconds, tag):
    dtypes = [DataType(f"e2b-in{i}") for i in range(k)]
    channels = [f"e2b/{tag}/s{i}" for i in range(k)]
    seen: list = []

    stream = await connect_stream_client(f"e2b-{tag}", *broker.get_connection_str())
    runtime = DTRuntime(None, stream)
    bound = [runtime.add_input(d, c, CODEC_JSON) for d, c in zip(dtypes, channels)]
    join = JoinDataType(dtypes)
    runtime.add_data_join(join)
    runtime.add_task(Sink(seen), join, NULL_DTYPE)
    runtime.start()
    config = PubSubConfig(None, *broker.get_connection_str())
    pubs = [await ChannelPublisher.open(c, CODEC_JSON, config=config, timeout=10.0)
            for c in channels]
    try:
        await asyncio.gather(*[b for b in bound if b is not None])
        await asyncio.sleep(0.5)

        n_rounds = max(1, int(rate * seconds))
        period = 1.0 / rate
        t0 = time.perf_counter()
        for r in range(n_rounds):
            target = t0 + r * period
            delay = target - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            for p in pubs:
                await p.publish({"t": time.perf_counter(), "r": r})
        pub_elapsed = time.perf_counter() - t0

        deadline = time.perf_counter() + SETTLE + seconds
        while len(seen) < n_rounds and time.perf_counter() < deadline:
            await asyncio.sleep(0.05)
    finally:
        for p in pubs:
            await p.close()
        await runtime.stop()

    lat = [x for x, _ in seen]
    return {
        "streams": k,
        "rate_target": rate,
        "rounds": n_rounds,
        "rate_achieved": n_rounds / pub_elapsed,
        "joined": len(seen),
        "aligned": sum(1 for _, ok in seen if ok),
        "p50_ms": statistics.median(lat) * 1e3 if lat else None,
        "p90_ms": sorted(lat)[int(0.9 * len(lat))] * 1e3 if lat else None,
        "inputs_per_s": k * n_rounds / pub_elapsed,
    }


async def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--streams", default="1,2,4,8,16,32")
    p.add_argument("--rates", default=",".join(map(str, RATES)))
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--out")
    args = p.parse_args()
    ks = [int(k) for k in args.streams.split(",") if k]
    rates = [float(r) for r in args.rates.split(",") if r]

    broker = ZMQ_BrokerProcess()
    await broker.start()
    results = {"provenance": provenance(args), "points": [], "max_sustainable": {}}
    try:
        await one_point(broker, 2, BASE_RATE, 1.0, "warm")
        for k in ks:
            base = None
            best = None
            for i, rate in enumerate(rates):
                r = await one_point(broker, k, rate, args.seconds, f"k{k}r{i}")
                results["points"].append(r)
                ok = (r["joined"] == r["rounds"] and r["aligned"] == r["joined"]
                      and r["rate_achieved"] >= 0.9 * rate)
                if base is None:
                    base = r["p50_ms"]
                doubled = r["p50_ms"] is None or r["p50_ms"] >= 2 * base
                print(f"K={k:3d} rate={rate:7.0f}/s achieved={r['rate_achieved']:8.0f} "
                      f"joined={r['joined']}/{r['rounds']} aligned={r['aligned']} "
                      f"p50={r['p50_ms']} ms  ok={ok} doubled={doubled}", flush=True)
                if not ok or doubled:
                    break
                best = r
            results["max_sustainable"][k] = best and {
                "rounds_per_s": best["rate_target"],
                "inputs_per_s": best["inputs_per_s"],
                "p50_ms": best["p50_ms"],
                "base_p50_ms": base,
            }
    finally:
        await broker.stop()

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"results: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
