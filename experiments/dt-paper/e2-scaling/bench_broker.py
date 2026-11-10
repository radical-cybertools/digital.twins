"""E2-C (round 3): broker capacity -- N service sessions, one twin each.

One client process opens N sessions on the broker's `dt` plugin
(`get_plugin("broker", "dt", ...)`), each with one twin: the integration
tests' `OffsetModel`, whose inference is one function task on the
`--inference` endpoint (as `s3/s3_service.py`).  Then N threads call
`get_inference` back to back, one per twin (c=1 per twin), for
`--seconds`.  Per N: session + twin creation time, aggregate req/s, p50
and p99 of the per-call latency, and the epoch times of the load phase so
a broker-side sampler (the job script's) can be joined on them.

N rises through `--sessions` until p50 is at least double N=1's (that point
is kept), or sessions fail to create (stop there and say why).  With
`--keep-going` it does not stop at the doubled p50 (how many sessions the
broker holds, past its throughput limit).

Client scaling (round 3, T4-C2): several of these processes share one load
window with `--start-at EPOCH` (each creates its sessions, then waits for
EPOCH before the load phase); `--dump-lat` keeps every latency in the
JSON so `r3/t4c_merge.py` can pool them across processes.

    python bench_broker.py --broker URL --inference EP \\
        --sessions 1,4,16,64,256 --out broker.json
"""

import argparse
import json
import os
import platform
import socket
import statistics
import sys
import threading
import time
import uuid

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e5-persistence"))

import bench_endpoint_loss as bel  # noqa: E402  (registers the user modules)

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def open_twin(runtime, inference, offset):
    dt = runtime.get_plugin("broker", "dt", config=bel.engines(inference=inference))
    twin = str(uuid.uuid4())
    bel.build_sibling(dt, twin, offset=offset)
    for _ in range(3):                                         # warm-up
        bel.infer(dt, twin)
    return dt, twin


def one_n(runtime, args, n):
    t0 = time.time()
    sessions, errors = [], []
    with ThreadPoolExecutor(min(n, args.create_threads)) as pool:
        futs = [pool.submit(open_twin, runtime, args.inference, i) for i in range(n)]
        for f in futs:
            try:
                sessions.append(f.result())
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}"[:300])
    t_create = time.time() - t0
    rec = {"sessions": n, "created": len(sessions), "create_s": t_create,
           "create_errors": errors[:5], "n_create_errors": len(errors)}
    if errors:
        for dt, _ in sessions:
            bel.drop(dt)
        return rec

    lat, fails = [], []
    lock = threading.Lock()
    stop = time.time() + args.seconds

    def loop(dt, twin, offset):
        mine, bad = [], 0
        i = 0
        while time.time() < stop:
            t = time.time()
            try:
                answer = bel.infer(dt, twin, value=float(i))
                if answer != i + offset:
                    bad += 1
            except Exception:
                bad += 1
            mine.append(time.time() - t)
            i += 1
        with lock:
            lat.extend(mine)
            fails.append(bad)

    if args.start_at:
        wait = args.start_at - time.time()
        if wait < 0:
            rec["late_s"] = -wait
        else:
            time.sleep(wait)
        stop = time.time() + args.seconds
    t_load = time.time()
    threads = [threading.Thread(target=loop, args=(dt, twin, k))
               for k, (dt, twin) in enumerate(sessions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    t_end = time.time()
    for dt, _ in sessions:
        bel.drop(dt)
    rec.update({
        "load_start_epoch": t_load, "load_end_epoch": t_end,
        "requests": len(lat), "failed": sum(fails),
        "req_per_s": len(lat) / (t_end - t_load),
        "p50_ms": statistics.median(lat) * 1e3 if lat else None,
        "p99_ms": pct(lat, 0.99) * 1e3 if lat else None,
    })
    if args.dump_lat:
        rec["latencies_ms"] = [round(x * 1e3, 3) for x in lat]
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--inference", required=True)
    p.add_argument("--sessions", default="1,4,16,64,256")
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--create-threads", type=int, default=16)
    p.add_argument("--keep-going", action="store_true",
                   help="do not stop when p50 doubles")
    p.add_argument("--start-at", type=float, default=None,
                   help="epoch at which the load phase starts (one N only)")
    p.add_argument("--dump-lat", action="store_true",
                   help="keep every latency in the JSON")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    ns = [int(n) for n in args.sessions.split(",") if n]

    res = {"provenance": {
        "experiment": "E2-C broker capacity (dt service sessions)",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args)}, "points": []}

    runtime = EndpointRuntime(broker_url=args.broker)
    runtime.start(wait=True)
    base = None
    try:
        for n in ns:
            rec = one_n(runtime, args, n)
            res["points"].append(rec)
            Path(args.out).write_text(json.dumps(res, indent=2))
            if rec["n_create_errors"]:
                print(f"N={n}: {rec['n_create_errors']} sessions failed to create "
                      f"after {rec['create_s']:.1f}s: {rec['create_errors'][:2]}", flush=True)
                res["stopped"] = f"session creation failed at N={n}"
                break
            if base is None:
                base = rec["p50_ms"]
            print(f"N={n:4d} create {rec['create_s']:6.1f}s  {rec['req_per_s']:7.1f} req/s  "
                  f"p50 {rec['p50_ms']:.1f} ms  p99 {rec['p99_ms']:.1f} ms  "
                  f"failed {rec['failed']}  load {rec['load_start_epoch']:.1f}-"
                  f"{rec['load_end_epoch']:.1f}", flush=True)
            if rec["p50_ms"] >= 2 * base and not args.keep_going:
                res["stopped"] = f"p50 doubled at N={n}"
                break
    finally:
        runtime.stop()
    Path(args.out).write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
