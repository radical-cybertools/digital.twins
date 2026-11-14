#!/usr/bin/env python3
"""Round 8, R8-B: can one training burst reach a site?

One twin in the broker's `dt` service, one investigator (`r8_components`)
that submits a burst of K function tasks at once (one gather) when asked.
`--layout one`: every task on the first endpoint; `--layout spread`: one
named engine per endpoint, task i on site i % n.  Task body: pure Python
holding the CPU (and its process's GIL) for --ms-list ms each.  Per
(ms, K, repeat), from the client:

  - wall time of the request, and at the service: time to the first task
    start, the spread of task starts, the makespan (service-side) against
    the ideal ceil(K / workers) x duration;
  - failed tasks with their error text;
  - probes every 0.5 s while the burst runs: `twin_list()` (the broker's dt
    service) and an executable task (on the endpoint, outside any pool);
    the break criterion (p99 > 1 s, any failure, a timeout) is applied to
    the probes and the burst.

A sweep over K runs one step past its first break, then stops.  With
--empty-k, one extra burst of that many empty tasks per repeat (tasks/s).

    python r8/bench_fanout.py --broker URL --endpoints ep0,ep1,ep2,ep3 \\
        --layout spread --backend dragon_native --workers 64 --out f.json
"""

import argparse
import json
import math
import statistics
import sys
import threading
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


def layout(eps, mode, backend):
    if mode == "spread":
        names = ["inference"] + [f"site_{k}" for k in range(1, len(eps))]
        engines = {n: {"endpoint_name": eps[k], "backends": [backend]} for k, n in enumerate(names)}
        sites = [None] + names[1:]
    else:
        engines = {"inference": {"endpoint_name": eps[0], "backends": [backend]}}
        sites = [None]
    return {"engines": engines}, sites


def ask(dt, twin, req, timeout):
    return dt.get_inference(twin, TypedData(r8_components.IN, req),
                            r8_components.OUT, timeout=timeout).data


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def one_burst(dt, probe, twin, k, ms, args):
    out = {}

    def run():
        t0 = time.perf_counter()
        try:
            out["ans"] = ask(dt, twin, {"op": "burst", "k": k, "ms": ms}, args.burst_timeout)
        except Exception as exc:
            out["err"] = f"{type(exc).__name__}: {exc}"[:400]
        out["wall"] = time.perf_counter() - t0

    th = threading.Thread(target=run, daemon=True)
    th.start()
    probes = []
    time.sleep(0.2)
    while th.is_alive():
        a = time.perf_counter()
        perr = []
        try:
            probe.twin_list()
        except Exception as exc:
            perr.append(f"twin_list {type(exc).__name__}: {exc}"[:200])
        tl = time.perf_counter() - a
        b = time.perf_counter()
        try:
            ask(probe, twin, {"op": "exe"}, 60)
        except Exception as exc:
            perr.append(f"exe {type(exc).__name__}: {exc}"[:200])
        ex = time.perf_counter() - b
        probes.append({"twin_list_s": tl, "exe_s": ex, "errors": perr})
        th.join(timeout=args.probe_interval)
    th.join()
    workers = args.workers * (len(args.endpoints) if args.layout == "spread" else 1)
    ideal = math.ceil(k / workers) * ms / 1000.0
    rec = {"k": k, "ms": ms, "wall_s": out.get("wall"), "error": out.get("err"),
           "ideal_s": ideal, "workers": workers}
    a = out.get("ans")
    if a:
        rec.update({"ok_tasks": a["k"], "failed": a.get("failed", 0),
                    "task_errors": a.get("errors"), "pids": a["pids"],
                    "per_host": a.get("per_host"),
                    "makespan_s": a["last_end"] - a["svc_t0"],
                    "svc_s": a["svc_t1"] - a["svc_t0"],
                    "first_start_s": a["first_start"] - a["svc_t0"],
                    "last_start_s": a["last_start"] - a["svc_t0"]})
        rec["vs_ideal"] = rec["makespan_s"] / ideal if ideal else None
        rec["tasks_per_s"] = a["k"] / rec["svc_s"] if rec["svc_s"] else None
    lat = [max(p["twin_list_s"], p["exe_s"]) for p in probes]
    rec.update({"probes": len(probes), "probe_p50_s": pct(lat, 0.5), "probe_p99_s": pct(lat, 0.99),
                "probe_max_twin_list_s": max((p["twin_list_s"] for p in probes), default=None),
                "probe_max_exe_s": max((p["exe_s"] for p in probes), default=None),
                "probe_errors": [e for p in probes for e in p["errors"]][:5]})
    reasons = []
    if rec["error"]:
        reasons.append(f"burst: {rec['error'][:200]}")
    if rec.get("failed"):
        reasons.append(f"{rec['failed']} tasks failed: {(rec.get('task_errors') or [''])[0][:150]}")
    if rec["probe_p99_s"] is not None and rec["probe_p99_s"] > 1.0:
        reasons.append(f"probe p99 {rec['probe_p99_s']:.2f} s")
    if rec["probe_errors"]:
        reasons.append(f"probe error: {rec['probe_errors'][0][:150]}")
    rec["break"] = "; ".join(reasons) or None
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoints", required=True, type=lambda s: s.split(","))
    p.add_argument("--layout", choices=["one", "spread"], default="one")
    p.add_argument("--backend", default="dragon_native")
    p.add_argument("--workers", type=int, required=True, help="pool workers per site")
    p.add_argument("--ks", default="16,64,256,1024")
    p.add_argument("--ms-list", default="100,10000")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--empty-k", type=int, default=0)
    p.add_argument("--burst-timeout", type=float, default=400)
    p.add_argument("--probe-interval", type=float, default=0.5)
    p.add_argument("--row", default="", help="label for the result (e.g. dragon_native)")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    if args.layout == "one":
        args.endpoints = args.endpoints[:1]

    res = {"provenance": provenance("R8-B fan-out", Path(__file__).name, args),
           "row": args.row, "points": [], "breaks": {}}

    def save():
        Path(args.out).write_text(json.dumps(res, indent=1, default=str))

    runtime = EndpointRuntime(broker_url=args.broker)
    runtime.start(wait=True)
    dt = None
    try:
        cfg, sites = layout(args.endpoints, args.layout, args.backend)
        t0 = time.time()
        dt = runtime.get_plugin("broker", "dt", config=cfg)
        twin = dt.create_twin(f"r8b-{uuid.uuid4().hex[:12]}")
        dt.add_investigator(twin, dt.package(r8_components.R8Investigator, sites=sites),
                            r8_components.IN, r8_components.OUT)
        dt.start(twin)
        ask(dt, twin, {"op": "burst", "k": 4 * len(sites), "ms": 0}, 300)  # every site once
        res["ready_s"] = time.time() - t0
        probe = runtime.get_plugin("broker", "dt", sid=dt.sid)
        for ms in [float(x) for x in args.ms_list.split(",")]:
            broke_at = None
            for k in [int(x) for x in args.ks.split(",")]:
                recs = []
                for r in range(args.repeats):
                    rec = one_burst(dt, probe, twin, k, ms, args)
                    rec["repeat"] = r + 1
                    recs.append(rec)
                    res["points"].append(rec)
                    save()
                    mk = rec.get("makespan_s")
                    print(f"[{args.row} {args.layout}] ms={ms:.0f} K={k} r{r + 1}: "
                          f"makespan {mk if mk is None else round(mk, 2)} s (ideal {rec['ideal_s']:.2f}), "
                          f"first start {rec.get('first_start_s')}, probe p99 {rec['probe_p99_s']}, "
                          f"failed {rec.get('failed')}, break {rec['break']}", flush=True)
                    if rec["break"]:
                        break  # a broken point is not repeated (budget; the page wants the break point)
                if any(x["break"] for x in recs) and broke_at is None:
                    broke_at = k
                    res["breaks"][str(ms)] = {"k": k, "why": next(x["break"] for x in recs if x["break"])}
                elif broke_at is not None:
                    break  # one step past the first break
            if args.empty_k and ms == float(args.ms_list.split(",")[0]):
                for r in range(args.repeats):
                    rec = one_burst(dt, probe, twin, args.empty_k, 0.0, args)
                    rec["repeat"] = r + 1
                    rec["empty"] = True
                    res["points"].append(rec)
                    save()
                    print(f"[{args.row} {args.layout}] empty K={args.empty_k} r{r + 1}: "
                          f"{rec.get('tasks_per_s')} tasks/s", flush=True)
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"[:500]
        print(res["error"], flush=True)
    finally:
        save()
        if dt is not None:
            try:
                for t in dt.twin_list():
                    dt.twin_close(t["twin_id"])
                dt.unregister_session()
            except Exception as exc:
                print(f"teardown: {exc}", flush=True)
        runtime.stop()
    return 0 if "error" not in res else 1


if __name__ == "__main__":
    sys.exit(main())
