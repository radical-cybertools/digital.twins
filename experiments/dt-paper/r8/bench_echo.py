#!/usr/bin/env python3
"""Round 8, R8-A: task argument and return size through the DT service.

One twin, one investigator (`r8_components`, op "echo"): the investigator
(in the broker's dt service) makes S random bytes, submits a function task
with them as its argument, and the task returns S bytes.  Per size, --calls
calls from the client: latency, and exactly what came back (bytes and
their length, another type, or the error text).  ORBIT's return limit is 2
MiB; the sizes straddle it.

    python r8/bench_echo.py --broker URL --endpoint EP --out f.json
"""

import argparse
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import r8_components  # noqa: E402
from prov import provenance  # noqa: E402

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import TypedData  # noqa: E402
from digitaltwin.service import register_user_modules  # noqa: E402

register_user_modules([r8_components])

SIZES = [1000, 100_000, 1_000_000, 2 * 2**20 - 1024, 2 * 2**20 + 1024, 16_000_000]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--backend", default="dragon_native")
    p.add_argument("--sizes", default=",".join(map(str, SIZES)))
    p.add_argument("--calls", type=int, default=5)
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    res = {"provenance": provenance("R8-A task argument / return size", Path(__file__).name, args),
           "points": []}
    rt = EndpointRuntime(broker_url=args.broker)
    rt.start(wait=True)
    dt = None
    try:
        dt = rt.get_plugin("broker", "dt", config={"engines": {"inference": {
            "endpoint_name": args.endpoint, "backends": [args.backend]}}})
        twin = dt.create_twin(f"r8a-{uuid.uuid4().hex[:12]}")
        dt.add_investigator(twin, dt.package(r8_components.R8Investigator),
                            r8_components.IN, r8_components.OUT)
        dt.start(twin)
        dt.get_inference(twin, TypedData(r8_components.IN, {"op": "fn"}),
                         r8_components.OUT, timeout=args.timeout)
        for size in [int(x) for x in args.sizes.split(",")]:
            calls = []
            for _ in range(args.calls):
                t0 = time.perf_counter()
                try:
                    a = dt.get_inference(twin, TypedData(r8_components.IN, {"op": "echo", "size": size}),
                                         r8_components.OUT, timeout=args.timeout).data
                    calls.append({"s": time.perf_counter() - t0, "answer": a, "error": None})
                except Exception as exc:
                    calls.append({"s": time.perf_counter() - t0, "answer": None,
                                  "error": f"{type(exc).__name__}: {exc}"[:400]})
            ok = [c for c in calls if not c["error"] and c["answer"].get("returned") == size]
            rec = {"size": size, "calls": calls, "ok": len(ok),
                   "p50_s": statistics.median(c["s"] for c in ok) if ok else None,
                   "outcome": (f"{len(ok)}/{len(calls)} returned {size} bytes" if len(ok) == len(calls) else
                               "; ".join(sorted({c["error"] or
                                                 f"returned {c['answer'].get('returned')} "
                                                 f"{c['answer'].get('returned_type')} {c['answer'].get('returned_head') or ''}"
                                                 for c in calls if c not in ok}))[:600])}
            res["points"].append(rec)
            Path(args.out).write_text(json.dumps(res, indent=1, default=str))
            print(f"size {size}: {rec['outcome']}  p50 {rec['p50_s']}", flush=True)
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"[:500]
        print(res["error"], flush=True)
    finally:
        Path(args.out).write_text(json.dumps(res, indent=1, default=str))
        if dt is not None:
            try:
                for t in dt.twin_list():
                    dt.twin_close(t["twin_id"])
                dt.unregister_session()
            except Exception as exc:
                print(f"teardown: {exc}", flush=True)
        rt.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
