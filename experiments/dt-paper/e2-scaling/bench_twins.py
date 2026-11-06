"""E2a: N twins on one engine, closed-loop in-situ inference load.

N `DTRuntime`s, one `ModelInvestigator` each (the no-op prediction of
`e1-overhead/bench_dt_insitu.py`), sharing one embedded ZMQ broker and
one asyncflow engine on a local process pool.  Each twin gets one client
loop that issues `get_inference` back to back for `--seconds` after a
warm-up, so the offered concurrency equals N.

Per N: aggregate req/s over all twins, and p50 / p99 latency per twin
(the median over twins of each twin's own percentile, plus the worst
twin).

    python experiments/dt-paper/e2-scaling/bench_twins.py \\
        --twins 1,2,4,8,16,32,64 --workers 64 --out results/twins.json
"""

import argparse
import asyncio
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import time

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e1-overhead"))

from bench_dt_insitu import Inv, X, Y, wait_ready  # noqa: E402

from radical.asyncflow import WorkflowEngine  # type: ignore  # noqa: E402

from digitaltwin import (  # noqa: E402
    DTRuntime,
    TypedData,
    ZMQ_BrokerProcess,
    connect_stream_client,
)

N_WARM = 20


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def provenance(args) -> dict:
    root = Path(__file__).resolve().parents[3]

    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(root), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E2a twins scaling",
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


async def one_n(flow, broker, predict, n, seconds):
    runtimes = []
    for i in range(n):
        stream = await connect_stream_client(f"e2a-{n}-{i}",
                                             *broker.get_connection_str())
        rt = DTRuntime(flow, stream)
        rt.add_investigator(Inv(flow, predict), X, Y)
        rt.start()
        runtimes.append(rt)
    try:
        await asyncio.gather(*[wait_ready(rt) for rt in runtimes])

        async def client(rt):
            for i in range(N_WARM):
                await rt.get_inference(TypedData(X, i), Y)
            await start.wait()
            lat = []
            i = 0
            while time.perf_counter() < stop_at:
                t0 = time.perf_counter()
                answer = await rt.get_inference(TypedData(X, i), Y)
                lat.append(time.perf_counter() - t0)
                assert answer.data == i, (i, answer)
                i += 1
            return lat

        start = asyncio.Event()
        tasks = [asyncio.ensure_future(client(rt)) for rt in runtimes]
        await asyncio.sleep(0.5)          # warm-ups done well before this
        t0 = time.perf_counter()
        stop_at = t0 + seconds
        start.set()
        lats = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - t0
    finally:
        await asyncio.gather(*[rt.stop() for rt in runtimes])

    total = sum(len(lat) for lat in lats)
    p50s = [statistics.median(lat) * 1e3 for lat in lats]
    p99s = [pct(lat, 0.99) * 1e3 for lat in lats]
    return {
        "twins": n,
        "requests": total,
        "elapsed_s": elapsed,
        "req_per_s": total / elapsed,
        "per_twin_req_per_s": [len(lat) / elapsed for lat in lats],
        "p50_ms_median": statistics.median(p50s),
        "p50_ms_max": max(p50s),
        "p99_ms_median": statistics.median(p99s),
        "p99_ms_max": max(p99s),
    }


async def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--twins", default="1,2,4,8,16,32,64")
    p.add_argument("--workers", type=int, default=64)
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--out")
    args = p.parse_args()
    ns = [int(n) for n in args.twins.split(",") if n]

    from rhapsody.backends.execution.concurrent import (  # type: ignore
        ConcurrentExecutionBackend,
    )
    backend = await ConcurrentExecutionBackend(ProcessPoolExecutor(args.workers))
    flow = await WorkflowEngine.create(backend=backend)

    @flow.function_task
    async def predict(x):
        return x

    broker = ZMQ_BrokerProcess()
    await broker.start()
    results = {"provenance": provenance(args), "points": []}
    try:
        await one_n(flow, broker, predict, 2, 2.0)      # warm-up, not recorded
        for n in ns:
            r = await one_n(flow, broker, predict, n, args.seconds)
            results["points"].append(r)
            print(f"twins={n:3d} {r['req_per_s']:8.0f} req/s  "
                  f"p50 {r['p50_ms_median']:6.2f} (max {r['p50_ms_max']:6.2f}) ms  "
                  f"p99 {r['p99_ms_median']:6.2f} (max {r['p99_ms_max']:6.2f}) ms",
                  flush=True)
    finally:
        await broker.stop()
        await flow.shutdown()

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"results: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
