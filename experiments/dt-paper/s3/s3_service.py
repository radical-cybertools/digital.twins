#!/usr/bin/env python3
"""Round 2 S3: in-situ inference through the broker's dt service (preliminary).

The twin lives in the broker's `dt` plugin (here: radical.3); its engine is
a rhapsody endpoint on Perlmutter (`--inference`).  The twin is the
integration tests' `OffsetModel` (inference = one function task on the
engine).  Per repeat: a fresh session and twin, 10 warm-up and `--n`
sequential `get_inference` calls (client latency, i.e. client -> broker ->
endpoint -> broker -> client), then the session is closed.  Then
`--reattaches` client-loss cycles, as in `bench_endpoint_loss.py`.

    python s3_service.py --broker https://95.217.193.116:8010 \\
        --inference pm_s3_ep_<job> --out s3.json
"""

import argparse
import json
import os
import socket
import statistics
import sys
import time
import uuid

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e5-persistence"))

import bench_endpoint_loss as bel  # noqa: E402  (registers the user modules)

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--inference", required=True)
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--reattaches", type=int, default=10)
    p.add_argument("--gap", type=float, default=2.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    res = {"provenance": {
        "experiment": "S3 service-path in-situ inference",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args)}, "repeats": [], "reattaches": []}

    runtime = EndpointRuntime(broker_url=args.broker)
    runtime.start(wait=True)
    try:
        for r in range(args.repeats):
            t0 = time.time()
            dt = runtime.get_plugin("broker", "dt",
                                    config=bel.engines(inference=args.inference))
            twin = str(uuid.uuid4())
            bel.build_sibling(dt, twin, offset=r)
            t_ready = time.time() - t0
            lat = []
            try:
                for _ in range(10):
                    bel.infer(dt, twin)
                for i in range(args.n):
                    t1 = time.time()
                    answer = bel.infer(dt, twin, value=float(i))
                    lat.append(time.time() - t1)
                    assert answer == i + r, (i, r, answer)
            finally:
                bel.drop(dt)
            rec = {"repeat": r, "session_and_twin_s": t_ready, "n": len(lat),
                   "p50_ms": statistics.median(lat) * 1e3,
                   "p90_ms": pct(lat, 0.9) * 1e3, "p99_ms": pct(lat, 0.99) * 1e3,
                   "min_ms": min(lat) * 1e3, "max_ms": max(lat) * 1e3}
            res["repeats"].append(rec)
            print(f"repeat {r}: session+twin {t_ready:.2f}s, p50 {rec['p50_ms']:.1f} ms "
                  f"p90 {rec['p90_ms']:.1f} p99 {rec['p99_ms']:.1f}", flush=True)
            Path(args.out).write_text(json.dumps(res, indent=2))
    finally:
        runtime.stop()

    for k in range(args.reattaches):
        try:
            res["reattaches"].append(bel.reattach_cycle(args, k))
        except Exception as exc:
            print(f"reattach {k} FAILED: {exc}", flush=True)
            res["reattaches"].append({"reattach": k, "error": str(exc)[:300]})
        Path(args.out).write_text(json.dumps(res, indent=2))

    ok = [x for x in res["reattaches"] if x.get("ok")]
    res["summary"] = {
        "p50_ms": statistics.median(x["p50_ms"] for x in res["repeats"]),
        "session_and_twin_s": statistics.median(x["session_and_twin_s"] for x in res["repeats"]),
        "reattaches_ok": len(ok), "reattaches": args.reattaches,
        "attach_s": statistics.median(x["attach_s"] for x in ok) if ok else None,
        "first_answer_s": statistics.median(x["first_answer_s"] for x in ok) if ok else None,
    }
    Path(args.out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res["summary"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
