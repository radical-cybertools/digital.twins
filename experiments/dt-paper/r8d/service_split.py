#!/usr/bin/env python3
"""Round 8d, D2: the service row, split at the worker.

A twin in the remote broker's DT plugin (radical.3:8010) with one
`r8_components.R8Investigator`, its engine on a Perlmutter endpoint
(`--endpoint`, `--backend`). Each request is `{"op": "fn"}`: one no-op
function task that returns its worker-side start and end (`t0`, `t1`,
epoch). The client (Perlmutter node 0) and the endpoint (node 1) share a
clock to well under a millisecond, so each request splits into

  to_task    client send -> the task starts on the worker
  task       t1 - t0 (the no-op itself)
  from_task  the task ends -> the answer is back at the client

10 warm-up requests, then --repeats x --n sequential requests.

    python r8d/service_split.py --broker https://95.217.193.116:8010 \\
        --endpoint EP --backend dragon_native --out f.json
"""

import argparse
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "r8"))

import r8_components  # noqa: E402
from prov import provenance  # noqa: E402

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import TypedData  # noqa: E402
from digitaltwin.service import register_user_modules  # noqa: E402

register_user_modules([r8_components])


def med(xs):
    return statistics.median(xs) * 1e3 if xs else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--backend", default="dragon_native")
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    res = {"provenance": provenance("R8d-D2 service row split", Path(__file__).name, args,
                                    backend_requested=args.backend), "repeats": []}
    rt = EndpointRuntime(broker_url=args.broker)
    rt.start(wait=True)
    try:
        for r in range(args.repeats):
            t0 = time.time()
            dt = rt.get_plugin("broker", "dt", config={"engines": {"inference": {
                "endpoint_name": args.endpoint, "backends": [args.backend]}}})
            twin = dt.create_twin(f"r8d-{uuid.uuid4().hex[:12]}")
            dt.add_investigator(twin, dt.package(r8_components.R8Investigator),
                                r8_components.IN, r8_components.OUT)
            dt.start(twin)
            ready = time.time() - t0
            req = TypedData(r8_components.IN, {"op": "fn"})
            try:
                for _ in range(10):
                    dt.get_inference(twin, req, r8_components.OUT, timeout=args.timeout)
                recs = []
                for _ in range(args.n):
                    t1 = time.time()
                    a = dt.get_inference(twin, req, r8_components.OUT, timeout=args.timeout).data
                    t2 = time.time()
                    w = a.get("task") or a  # R8Investigator answers carry the task's dict
                    recs.append({"t_send": t1, "t_recv": t2, "w0": w.get("t0"), "w1": w.get("t1"),
                                 "host": w.get("host")})
            finally:
                try:
                    for t in dt.twin_list():
                        dt.twin_close(t["twin_id"])
                    dt.unregister_session()
                except Exception as exc:
                    print(f"teardown: {exc}", flush=True)
            tot = [x["t_recv"] - x["t_send"] for x in recs]
            ok = [x for x in recs if x["w0"] and x["w1"]]
            rep = {"repeat": r, "session_and_twin_s": ready, "n": len(recs),
                   "p50_ms": med(tot), "min_ms": min(tot) * 1e3, "max_ms": max(tot) * 1e3,
                   "to_task_p50_ms": med([x["w0"] - x["t_send"] for x in ok]),
                   "task_p50_ms": med([x["w1"] - x["w0"] for x in ok]),
                   "from_task_p50_ms": med([x["t_recv"] - x["w1"] for x in ok]),
                   "split_n": len(ok), "records": recs}
            res["repeats"].append(rep)
            Path(args.out).write_text(json.dumps(res, indent=1))
            print(f"{args.backend} repeat {r}: ready {ready:.2f}s p50 {rep['p50_ms']:.1f} ms "
                  f"(to task {rep['to_task_p50_ms']}, task {rep['task_p50_ms']}, "
                  f"from task {rep['from_task_p50_ms']}) n={len(ok)}", flush=True)
    finally:
        rt.stop()
    reps = res["repeats"]
    res["summary"] = {k: statistics.median(x[k] for x in reps if x.get(k) is not None)
                      for k in ("p50_ms", "to_task_p50_ms", "task_p50_ms", "from_task_p50_ms",
                                "session_and_twin_s") if any(x.get(k) is not None for x in reps)}
    Path(args.out).write_text(json.dumps(res, indent=1))
    print(json.dumps(res["summary"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
