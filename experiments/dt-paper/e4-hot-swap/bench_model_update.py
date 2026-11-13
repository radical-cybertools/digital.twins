"""E4 (partial): model-update propagation, publish to first inference that uses it.

One twin, one `ModelInvestigator`.  Its main loop publishes model versions
v = 1..N every `--interval` seconds (`publish_new_model({"v": v})`) and
records the publish time.  The inference is an asyncflow function task
that returns the version it was called with, so the answer says which
model served it.  A client calls `get_inference` back to back.

Per version v:
  answered   first answer carrying v (or newer) minus publish time of v:
             what a consumer of the twin observes
  issued     issue time of that request minus publish time of v (negative
             when the request was issued before the publish and still got
             the new model); `answered - issued` is one inference
  skipped    versions never seen because the next one replaced them first

Backends as in `e1-overhead/bench_dt_insitu.py`: a local process pool, or
an ORBIT endpoint (`--broker`, `--endpoint`).

Round 8 (R8-A): `--payload-mb S` publishes every version by value with an
S MB blob in the model (the model args travel with every inference task);
`--path-mb S --path-dir DIR` writes one S MB file there and publishes its
path, and the task reads the file once per worker process and path (a
model loaded from the endpoint's file system).  The answers also give the
inference rate over the run (`rate_windows`: requests per 1 s window), so
the dip around a publish shows.

    python experiments/dt-paper/e4-hot-swap/bench_model_update.py \\
        --intervals 1,0.1,0.01 --out results/update.json
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


class Versioned(ModelInvestigator):
    def __init__(self, flow, predict, interval, n, extra=None):
        super().__init__(flow)
        self.extra = extra or {}
        self.predict = predict
        self.interval = interval
        self.n = n
        self.published: dict[int, float] = {}
        self.done = asyncio.Event()
        self.go = asyncio.Event()

    async def main_loop(self, runtime):
        predict = self.predict

        async def infer(in_data, v=0, **model):
            return TypedData(Y, await predict(v, **model))

        runtime.set_inference_task(infer)
        runtime.publish_new_model({"v": 0, **self.extra})
        await self.go.wait()
        t0 = time.perf_counter()
        for v in range(1, self.n + 1):
            delay = t0 + v * self.interval - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            self.published[v] = time.perf_counter()
            runtime.publish_new_model({"v": v, **self.extra})
        await asyncio.sleep(max(0.5, 3 * self.interval))
        self.done.set()


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def summarize(xs):
    if not xs:
        return None
    return {"n": len(xs), "p50_ms": statistics.median(xs) * 1e3,
            "p90_ms": pct(xs, 0.9) * 1e3, "min_ms": min(xs) * 1e3,
            "max_ms": max(xs) * 1e3}


async def one_interval(flow, broker, predict, interval, n, extra=None):
    stream = await connect_stream_client("e4-update", *broker.get_connection_str())
    rt = DTRuntime(flow, stream)
    inv = Versioned(flow, predict, interval, n, extra)
    rt.add_investigator(inv, X, Y)
    rt.start()
    answers = []           # (issued, answered, version)
    try:
        deadline = time.monotonic() + 30
        while True:
            a = await rt.get_inference(TypedData(X, 0), Y)
            if a.dtype != NULL_DTYPE:
                break
            if time.monotonic() > deadline:
                raise RuntimeError(f"twin not ready: {rt.state} {rt.last_error}")
            await asyncio.sleep(0.05)
        for _ in range(20):                       # warm-up
            await rt.get_inference(TypedData(X, 0), Y)
        inv.go.set()
        while not inv.done.is_set():
            t_issue = time.perf_counter()
            a = await rt.get_inference(TypedData(X, 0), Y)
            answers.append((t_issue, time.perf_counter(), a.data))
    finally:
        await rt.stop()

    answered, issued, seen = [], [], 0
    for v, t_pub in inv.published.items():
        first = next(((ti, ta) for ti, ta, av in answers
                      if av is not None and av >= v and ta >= t_pub), None)
        if first is None:
            continue
        exact = any(av == v for _, _, av in answers)
        seen += exact
        answered.append(first[1] - t_pub)
        issued.append(first[0] - t_pub)
    inference = [ta - ti for ti, ta, _ in answers]
    windows = {}
    if answers:
        a0 = answers[0][0]
        for _, ta, _ in answers:
            windows[int(ta - a0)] = windows.get(int(ta - a0), 0) + 1
    return {
        "rate_windows": [windows.get(i, 0) for i in range(max(windows, default=-1) + 1)],
        "interval_s": interval,
        "versions": n,
        "versions_seen": seen,
        "requests": len(answers),
        "inference": summarize(inference),
        "answered": summarize(answered),
        "issued": summarize(issued),
        "answered_raw_s": answered,
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
        "experiment": "E4 model-update propagation",
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
    p.add_argument("--broker", default=None, help="ORBIT broker URL")
    p.add_argument("--endpoint", default=None)
    p.add_argument("--backends", default="concurrent")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--intervals", default="1,0.1,0.01")
    p.add_argument("--seconds", type=float, default=20.0,
                   help="publishing time per interval (N = seconds / interval, "
                        "at most --max-versions)")
    p.add_argument("--max-versions", type=int, default=500)
    p.add_argument("--payload-mb", type=float, default=0.0,
                   help="round 8: model published by value with this many MB")
    p.add_argument("--path-mb", type=float, default=0.0,
                   help="round 8: model published by path, a file of this many MB")
    p.add_argument("--path-dir", default="/tmp")
    p.add_argument("--out")
    args = p.parse_args()
    args.backends = [b for b in args.backends.split(",") if b]
    intervals = [float(i) for i in args.intervals.split(",") if i]

    label, backend = await make_backend(args)
    flow = await WorkflowEngine.create(backend=backend)

    @flow.function_task
    async def predict(v, blob=None, path=None):
        if path is not None:  # a model on the endpoint's file system, read once per worker
            import builtins
            cache = builtins.__dict__.setdefault("_r8_model_cache", {})
            if path not in cache:
                with open(path, "rb") as f:
                    cache[path] = len(f.read())
        return v

    extra = {}
    if args.payload_mb:
        extra["blob"] = os.urandom(int(args.payload_mb * 2**20))
    elif args.path_mb:
        mp = Path(args.path_dir) / f"r8-model-{args.path_mb:g}MB.bin"
        if not mp.exists() or mp.stat().st_size != int(args.path_mb * 2**20):
            with open(mp, "wb") as f:
                left = int(args.path_mb * 2**20)
                while left:
                    n_ = min(left, 64 * 2**20)
                    f.write(os.urandom(n_))
                    left -= n_
        extra["path"] = str(mp)

    broker = ZMQ_BrokerProcess()
    await broker.start()
    results = {"provenance": provenance(args, label), "points": []}
    try:  # round 8: all five packages, backend, telemetry, file system
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "r8"))
        from prov import provenance as _r8prov
        results["provenance"]["r8"] = _r8prov("R8-A model publish", Path(__file__).name)
    except Exception as exc:
        results["provenance"]["r8"] = f"unavailable: {exc}"
    try:
        for interval in intervals:
            n = min(args.max_versions, max(5, int(args.seconds / interval)))
            r = await one_interval(flow, broker, predict, interval, n, extra)
            r["payload_mb"], r["path_mb"] = args.payload_mb, args.path_mb
            results["points"].append(r)
            a = r["answered"] or {}
            print(f"interval {interval*1e3:7.1f} ms: {r['versions_seen']}/{n} versions "
                  f"seen, answered p50 {a.get('p50_ms', float('nan')):.2f} ms "
                  f"p90 {a.get('p90_ms', float('nan')):.2f} ms, inference p50 "
                  f"{r['inference']['p50_ms']:.2f} ms", flush=True)
    finally:
        await broker.stop()
        await flow.shutdown()

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"results: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
