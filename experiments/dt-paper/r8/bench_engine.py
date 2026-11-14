#!/usr/bin/env python3
"""Round 8, R8-2: N twins on one dragon_native engine, through the DT service.

As round 6's e2-scaling/bench_broker.py, with round 8's investigator
(`r8_components`, one function task of --work-ms CPU per request) on a
`dragon_native` engine: N twins, T per DT service session (`--per-session
T`, 0 = all N in one session, one pool), one closed-loop client thread per
twin for --seconds.  Per N: aggregate req/s, per-twin p50 / p99 (median
over twins and the worst twin), failures, creation time, and the load
window's epochs (the job's /proc samplers join on them).  N rises through
--twins until the break (p99 > 1 s, a failure, a timeout), one step past
it, then stops.

    python r8/bench_engine.py --broker URL --endpoint EP --twins 1,4,16 --out f.json
"""

import argparse
import json
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import r8_components  # noqa: E402
from prov import provenance  # noqa: E402

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import TypedData  # noqa: E402
from digitaltwin.service import register_user_modules  # noqa: E402

register_user_modules([r8_components])


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def ask(dt, twin, req, timeout):
    return dt.get_inference(twin, TypedData(r8_components.IN, req),
                            r8_components.OUT, timeout=timeout).data


def drop(dt):
    try:
        for t in dt.twin_list():
            dt.twin_close(t["twin_id"])
        dt.unregister_session()
    except Exception as exc:
        print(f"session teardown: {exc}", flush=True)


def one_n(runtime, args, n):
    per = args.per_session or n
    s = -(-n // per)
    cfg = {"engines": {"inference": {"endpoint_name": args.endpoint, "backends": [args.backend]}}}
    t0 = time.time()
    errors = []
    with ThreadPoolExecutor(min(s, 16)) as pool:
        dts = list(pool.map(lambda _: runtime.get_plugin("broker", "dt", config=cfg), range(s)))

    def build(i):
        dt = dts[i // per]
        twin = dt.create_twin(f"r8e2-{uuid.uuid4().hex[:12]}")
        dt.add_investigator(twin, dt.package(r8_components.R8Investigator),
                            r8_components.IN, r8_components.OUT)
        dt.start(twin)
        for _ in range(3):
            ask(dt, twin, {"op": "fn", "ms": args.work_ms}, args.timeout)
        return dt, twin

    twins = []
    with ThreadPoolExecutor(min(n, 16)) as pool:
        for f in [pool.submit(build, i) for i in range(n)]:
            try:
                twins.append(f.result())
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}"[:300])
    rec = {"twins": n, "per_session": per, "sessions": s, "created": len(twins),
           "create_s": time.time() - t0, "create_errors": errors[:3], "n_create_errors": len(errors)}
    if errors:
        for dt in dts:
            drop(dt)
        rec["break"] = f"creation: {errors[0][:200]}"
        return rec

    lats, fails, errs = [], [0] * n, []
    lock = threading.Lock()
    stop = time.time() + args.seconds

    def loop(k, dt, twin):
        mine = []
        while time.time() < stop:
            t = time.perf_counter()
            try:
                ask(dt, twin, {"op": "fn", "ms": args.work_ms}, args.timeout)
            except Exception as exc:
                fails[k] += 1
                with lock:
                    if len(errs) < 3:
                        errs.append(f"{type(exc).__name__}: {exc}"[:200])
            mine.append(time.perf_counter() - t)
        with lock:
            lats.append(mine)

    c0 = time.process_time()
    t_load = time.time()
    if args.load_marker:  # the broker profile starts on this (round 8, broker profile)
        Path(f"{args.load_marker}.n{n}").write_text(f"{t_load}\n")
    ths = [threading.Thread(target=loop, args=(k, dt, twin)) for k, (dt, twin) in enumerate(twins)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    t_end = time.time()
    total = sum(len(x) for x in lats)
    p50s = [statistics.median(x) * 1e3 for x in lats if x]
    p99s = [pct(x, 0.99) * 1e3 for x in lats if x]
    rec.update({
        "load_start_epoch": t_load, "load_end_epoch": t_end,
        "requests": total, "req_per_s": total / (t_end - t_load),
        "failed": sum(fails), "errors": errs,
        "p50_ms_median": statistics.median(p50s) if p50s else None,
        "p50_ms_max": max(p50s, default=None),
        "p99_ms_median": statistics.median(p99s) if p99s else None,
        "p99_ms_max": max(p99s, default=None),
        "worst_twin_req_per_s": min((len(x) for x in lats), default=0) / (t_end - t_load),
        "client_cpu_pct": 100 * (time.process_time() - c0) / (t_end - t_load),
    })
    reasons = []
    if rec["failed"]:
        reasons.append(f"{rec['failed']} failed: {errs[0] if errs else ''}")
    if rec["p99_ms_max"] and rec["p99_ms_max"] > 1000:
        reasons.append(f"worst twin p99 {rec['p99_ms_max']:.0f} ms")
    rec["break"] = "; ".join(reasons) or None
    for dt in dts:
        drop(dt)
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--backend", default="dragon_native")
    p.add_argument("--twins", default="1,4,16,64,256,1024")
    p.add_argument("--per-session", type=int, default=0, help="twins per session (0: all in one)")
    p.add_argument("--work-ms", type=float, default=0.0)
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--load-marker", default=None, help="write the load start epoch to <path>.n<N>")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    res = {"provenance": provenance("R8-2 one engine", Path(__file__).name, args), "points": []}
    rt = EndpointRuntime(broker_url=args.broker)
    rt.start(wait=True)
    broke = None
    try:
        for n in [int(x) for x in args.twins.split(",") if x]:
            rec = one_n(rt, args, n)
            res["points"].append(rec)
            Path(args.out).write_text(json.dumps(res, indent=1, default=str))
            print(f"N={n:5d} per-session={rec['per_session']}: {rec.get('req_per_s', 0):8.1f} req/s "
                  f"p50 {rec.get('p50_ms_median')} p99 {rec.get('p99_ms_median')} (worst {rec.get('p99_ms_max')}) "
                  f"failed {rec.get('failed')} create {rec['create_s']:.1f}s break {rec.get('break')}", flush=True)
            time.sleep(5)
            if broke is not None:
                break
            if rec.get("break"):
                broke = n
                res["break"] = {"twins": n, "why": rec["break"]}
    finally:
        Path(args.out).write_text(json.dumps(res, indent=1, default=str))
        rt.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
