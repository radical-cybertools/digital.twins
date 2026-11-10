"""E2 / E4 (round 3): model publishing under closed-loop inference.

One twin, one `ModelInvestigator`.  Its main loop publishes model versions
(`publish_new_model({"v": v})`) at a target rate; `max` publishes as fast
as it can, yielding to the event loop once per model (no criterion, no
window: the minimal learner).  Meanwhile C clients call `get_inference`
back to back; the inference is an asyncflow function task that returns the
version it was called with, so every answer says which model served it.

Per publish rate, for `--seconds`:
  models_published_per_s   versions published / time
  models_seen_per_s        distinct versions that served an answer / time
  req_per_s, p50_ms        the inference side, and both relative to rate 0

E2-B (publish as fast as possible, inference at c=1):
    python bench_publish.py --concurrency 1 --rates 0,1,10,100,1000,max
E4-B (the dip, c=50):
    python bench_publish.py --concurrency 50 --rates 0,1,10,100

Backends as in `e1-overhead/bench_dt_insitu.py`: a local process pool, or
an ORBIT endpoint (`--broker`, `--endpoint`).
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

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e1-overhead"))

from bench_dt_insitu import X, Y, make_backend  # noqa: E402

from radical.asyncflow import WorkflowEngine  # type: ignore  # noqa: E402

from digitaltwin import (  # noqa: E402
    DTRuntime,
    ModelInvestigator,
    TypedData,
    ZMQ_BrokerProcess,
    connect_stream_client,
)
from digitaltwin.components import NULL_DTYPE  # noqa: E402


class Publisher(ModelInvestigator):
    def __init__(self, flow, predict, rate):
        super().__init__(flow)
        self.predict = predict
        self.rate = rate          # models/s; None = as fast as possible; 0 = none
        self.published = 0
        self.go = asyncio.Event()
        self.stop = asyncio.Event()

    async def main_loop(self, runtime):
        predict = self.predict

        async def infer(in_data, v=0):
            return TypedData(Y, await predict(v))

        runtime.set_inference_task(infer)
        runtime.publish_new_model({"v": 0})
        await self.go.wait()
        if self.rate == 0:
            return
        t0 = time.perf_counter()
        v = 0
        while not self.stop.is_set():
            v += 1
            if self.rate is not None:
                delay = t0 + v / self.rate - time.perf_counter()
                if delay > 0:
                    await asyncio.sleep(delay)
            else:
                await asyncio.sleep(0)
            if self.stop.is_set():
                break
            runtime.publish_new_model({"v": v})
            self.published = v


async def one_rate(flow, broker, predict, rate, conc, seconds):
    stream = await connect_stream_client("e2-publish", *broker.get_connection_str())
    rt = DTRuntime(flow, stream)
    pub = Publisher(flow, predict, rate)
    rt.add_investigator(pub, X, Y)
    rt.start()
    lat, seen = [], set()
    try:
        deadline = time.monotonic() + 30
        while (await rt.get_inference(TypedData(X, 0), Y)).dtype == NULL_DTYPE:
            if time.monotonic() > deadline:
                raise RuntimeError(f"twin not ready: {rt.state} {rt.last_error}")
            await asyncio.sleep(0.05)
        for _ in range(20):                                    # warm-up
            await rt.get_inference(TypedData(X, 0), Y)

        t_end = None

        async def client():
            while time.perf_counter() < t_end:
                t = time.perf_counter()
                a = await rt.get_inference(TypedData(X, 0), Y)
                lat.append(time.perf_counter() - t)
                seen.add(a.data)

        pub.go.set()
        t0 = time.perf_counter()
        t_end = t0 + seconds
        await asyncio.gather(*[client() for _ in range(conc)])
        elapsed = time.perf_counter() - t0
        pub.stop.set()
    finally:
        await rt.stop()
    return {
        "rate_target": "max" if rate is None else rate,
        "concurrency": conc,
        "seconds": elapsed,
        "models_published_per_s": pub.published / elapsed,
        "models_seen_per_s": len(seen - {0}) / elapsed,
        "requests": len(lat),
        "req_per_s": len(lat) / elapsed,
        "p50_ms": statistics.median(lat) * 1e3,
        "p90_ms": sorted(lat)[int(0.9 * len(lat))] * 1e3,
    }


def provenance(args, backend_label) -> dict:
    root = Path(__file__).resolve().parents[3]

    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(root), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E2/E4 model publishing under inference",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git("rev-parse", "HEAD"),
        "digital_twins_dirty": bool(git("status", "--porcelain", "--", "src")),
        "backend": backend_label,
        "notify_window": os.environ.get("RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW"),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args),
    }


async def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", default=os.environ.get("RADICAL_ORBIT_BROKER_URL"))
    p.add_argument("--endpoint", default=os.environ.get("DT_TASK_ENDPOINT"))
    p.add_argument("--backends", default="concurrent")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--rates", default="0,1,10,100,1000,max")
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--out")
    args = p.parse_args()
    args.backends = [b for b in args.backends.split(",") if b]
    rates = [None if r == "max" else float(r) for r in args.rates.split(",") if r]

    backend_label, backend = await make_backend(args)
    flow = await WorkflowEngine.create(backend=backend)

    @flow.function_task
    async def predict(v):
        return v

    broker = ZMQ_BrokerProcess()
    await broker.start()
    results = {"provenance": provenance(args, backend_label), "points": []}
    try:
        for rate in rates:
            r = await one_rate(flow, broker, predict, rate, args.concurrency,
                               args.seconds)
            base = results["points"][0] if results["points"] else r
            r["req_per_s_x_rate0"] = r["req_per_s"] / base["req_per_s"]
            r["p50_x_rate0"] = r["p50_ms"] / base["p50_ms"]
            results["points"].append(r)
            print(f"rate={r['rate_target']!s:>5} c={args.concurrency} "
                  f"published={r['models_published_per_s']:9.1f}/s "
                  f"seen={r['models_seen_per_s']:8.1f}/s "
                  f"req/s={r['req_per_s']:7.0f} ({r['req_per_s_x_rate0']:.2f}x) "
                  f"p50={r['p50_ms']:.2f} ms ({r['p50_x_rate0']:.2f}x)", flush=True)
    finally:
        await broker.stop()
        await flow.shutdown()

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"results: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
