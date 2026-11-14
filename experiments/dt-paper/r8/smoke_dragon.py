#!/usr/bin/env python3
"""Round 8, R8-0: Dragon smoke through ORBIT and the DT service.

One twin in the broker's `dt` service, one investigator (`r8_components`)
whose inference runs what the request asks for, engine
`{"endpoint_name": EP, "backends": [BACKEND]}` (dragon_native by default:
the DT service names its backend, so the endpoint's
RADICAL_ORBIT_RHAPSODY_BACKEND alone does not select it).  Steps:

  basic     session + twin; function task, executable task, 1,000 empty
            function tasks in one burst (tasks/s); writes --state
  gil       a burst of --workers function tasks of 10 s CPU each, while
            probes every 0.5 s time twin_list() and an executable task (a
            native Process, so it needs no pool worker); all must answer
            within 1 s
  reattach  a fresh client handle on --state's session after the endpoint
            runtime was killed and restarted: time to the first good answer
  remote    session + twin on a remote broker (--broker), 10 function tasks
            (round trip), one executable task, 64 x 100 ms CPU
  sessions  S = --sessions-list DT sessions on one endpoint, each with a
            twin (each session builds its own backend, so its own pool):
            start time per session, node probe (worker processes, memory),
            then 64 x 100 ms CPU per session, all sessions at once (makespan)
  pool      one session, node probe, 256 x 50 ms CPU: distinct worker pids
            (does the pool follow a CPU restriction on the launch?)

    python r8/smoke_dragon.py --broker URL --endpoint EP --step basic --out f.json
"""

import argparse
import json
import statistics
import subprocess
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


def engines(args):
    return {"engines": {"inference": {"endpoint_name": args.endpoint,
                                      "backends": [args.backend]}}}


def open_twin(runtime, args):
    t0 = time.time()
    dt = runtime.get_plugin("broker", "dt", config=engines(args))
    t1 = time.time()
    twin = dt.create_twin(f"r8-{uuid.uuid4().hex[:12]}")  # unique across threads
    dt.add_investigator(twin, dt.package(r8_components.R8Investigator),
                        r8_components.IN, r8_components.OUT)
    dt.start(twin)
    first = ask(dt, twin, {"op": "fn"}, args.timeout)
    return dt, twin, {"session_s": t1 - t0, "ready_s": time.time() - t0, "first": first}


def ask(dt, twin, req, timeout):
    return dt.get_inference(twin, TypedData(r8_components.IN, req),
                            r8_components.OUT, timeout=timeout).data


def timed(dt, twin, req, timeout):
    t0 = time.perf_counter()
    try:
        a = ask(dt, twin, req, timeout)
        return time.perf_counter() - t0, a, None
    except Exception as exc:
        return time.perf_counter() - t0, None, f"{type(exc).__name__}: {exc}"[:300]


def node_probe(args):
    if not args.ep_node:
        return None
    cmd = ["srun", "--overlap", "-N1", "-n1", "-w", args.ep_node, str(HERE / "node_probe.sh")]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
        return json.loads(out.strip().splitlines()[-1])
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}


def burst_rec(ans, wall, k, ms):
    rec = {"k": k, "ms": ms, "wall_s": wall}
    if ans:
        rec.update({"svc_s": ans["svc_t1"] - ans["svc_t0"], "pids": ans["pids"],
                    "hosts": ans["hosts"],
                    "first_start_s": ans["first_start"] - ans["svc_t0"],
                    "start_spread_s": ans["last_start"] - ans["first_start"]})
        rec["tasks_per_s"] = k / rec["svc_s"] if rec["svc_s"] else None
    return rec


def step_basic(runtime, args, res):
    dt, twin, rec = open_twin(runtime, args)
    res["twin"] = rec
    fns = [timed(dt, twin, {"op": "fn"}, args.timeout) for _ in range(10)]
    res["fn_s"] = [x[0] for x in fns]
    res["fn_errors"] = [x[2] for x in fns if x[2]]
    res["fn_pids"] = sorted({x[1]["pid"] for x in fns if x[1]})
    exes = [timed(dt, twin, {"op": "exe"}, args.timeout) for _ in range(3)]
    res["exe_s"] = [x[0] for x in exes]
    res["exe_answer"] = exes[0][1]
    res["exe_errors"] = [x[2] for x in exes if x[2]]
    w, a, e = timed(dt, twin, {"op": "burst", "k": 1000, "ms": 0}, 600)
    res["burst_1000_empty"] = burst_rec(a, w, 1000, 0)
    res["burst_1000_empty"]["error"] = e
    Path(args.state).write_text(json.dumps({"sid": dt.sid, "twin": twin}))
    return dt


def step_gil(runtime, args, res):
    st = json.loads(Path(args.state).read_text())
    dt = runtime.get_plugin("broker", "dt", sid=st["sid"])
    probe = runtime.get_plugin("broker", "dt", sid=st["sid"])
    twin = st["twin"]
    out = {}

    def run_burst():
        out["burst"] = timed(dt, twin, {"op": "burst", "k": args.workers, "ms": 10000}, 600)

    th = threading.Thread(target=run_burst)
    t0 = time.time()
    th.start()
    probes = []
    time.sleep(1.0)
    while th.is_alive() and time.time() - t0 < 300:
        a = time.perf_counter()
        try:
            probe.twin_list()
            tl, terr = time.perf_counter() - a, None
        except Exception as exc:
            tl, terr = time.perf_counter() - a, f"{type(exc).__name__}: {exc}"[:200]
        ex, _, eerr = timed(probe, twin, {"op": "exe"}, 30)
        probes.append({"t": time.time() - t0, "twin_list_s": tl, "exe_s": ex,
                       "errors": [e for e in (terr, eerr) if e]})
        time.sleep(0.5)
    th.join()
    w, a, e = out["burst"]
    res["burst"] = burst_rec(a, w, args.workers, 10000)
    res["burst"]["error"] = e
    res["probes"] = probes
    res["probe_max_twin_list_s"] = max((p["twin_list_s"] for p in probes), default=None)
    res["probe_max_exe_s"] = max((p["exe_s"] for p in probes), default=None)
    res["probe_ok"] = bool(probes) and all(p["twin_list_s"] < 1 and p["exe_s"] < 1
                                           and not p["errors"] for p in probes)


def step_reattach(runtime, args, res):
    st = json.loads(Path(args.state).read_text())
    t0 = time.time()
    tries, last = 0, None
    while time.time() - t0 < args.reattach_wait:
        tries += 1
        try:
            dt = runtime.get_plugin("broker", "dt", sid=st["sid"])
            twins = [t["twin_id"] for t in dt.twin_list()]
            a = ask(dt, st["twin"], {"op": "fn"}, 30)
            res.update({"reattach_s": time.time() - t0, "tries": tries,
                        "twins": twins, "answer": a})
            return
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"[:300]
            time.sleep(2)
    res.update({"reattach_s": None, "tries": tries, "last_error": last})


def step_remote(runtime, args, res):
    dt, twin, rec = open_twin(runtime, args)
    res["twin"] = rec
    fns = [timed(dt, twin, {"op": "fn"}, args.timeout) for _ in range(10)]
    res["fn_s"] = [x[0] for x in fns]
    res["fn_p50_s"] = statistics.median(res["fn_s"])
    res["fn_errors"] = [x[2] for x in fns if x[2]]
    w, a, e = timed(dt, twin, {"op": "exe"}, args.timeout)
    res["exe"] = {"s": w, "answer": a, "error": e}
    w, a, e = timed(dt, twin, {"op": "burst", "k": 64, "ms": 100}, 600)
    res["burst_64x100ms"] = burst_rec(a, w, 64, 100)
    res["burst_64x100ms"]["error"] = e
    drop(dt)


def drop(dt):
    try:
        for t in dt.twin_list():
            dt.twin_close(t["twin_id"])
        dt.unregister_session()
    except Exception as exc:
        print(f"session teardown: {exc}", flush=True)


def step_sessions(runtime, args, res):
    res["points"] = []
    for s in [int(x) for x in args.sessions_list.split(",") if x]:
        rec = {"sessions": s, "probe_before": node_probe(args)}
        made, errs = [], []
        lock = threading.Lock()

        def one():
            try:
                dt, twin, r = open_twin(runtime, args)
                with lock:
                    made.append((dt, twin, r))
            except Exception as exc:
                with lock:
                    errs.append(f"{type(exc).__name__}: {exc}"[:300])

        t0 = time.time()
        ths = [threading.Thread(target=one) for _ in range(s)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        rec["create_wall_s"] = time.time() - t0
        rec["ready_s"] = sorted(r["ready_s"] for _, _, r in made)
        rec["created"] = len(made)
        rec["create_errors"] = errs[:5]
        rec["n_create_errors"] = len(errs)
        rec["probe_ready"] = node_probe(args)
        bursts = [None] * len(made)

        def burst(i, dt, twin):
            bursts[i] = timed(dt, twin, {"op": "burst", "k": 64, "ms": 100}, 600)

        t1 = time.time()
        ths = [threading.Thread(target=burst, args=(i, dt, twin))
               for i, (dt, twin, _) in enumerate(made)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        rec["burst_wall_s"] = time.time() - t1
        rec["bursts"] = [dict(burst_rec(b[1], b[0], 64, 100), error=b[2]) for b in bursts]
        rec["burst_errors"] = sum(1 for b in bursts if b[2])
        rec["makespan_max_s"] = max((b[0] for b in bursts), default=None)
        rec["probe_after"] = node_probe(args)
        for dt, _, _ in made:
            drop(dt)
        res["points"].append(rec)
        Path(args.out).write_text(json.dumps(res, indent=2))
        print(f"S={s}: created {len(made)}/{s} in {rec['create_wall_s']:.1f}s, "
              f"burst max {rec['makespan_max_s']}, errors {rec['burst_errors']}, "
              f"probe {rec['probe_ready']}", flush=True)
        time.sleep(10)
        if errs and s != max(int(x) for x in args.sessions_list.split(",")):
            res.setdefault("break", f"S={s}: {errs[0]}")


def step_pool(runtime, args, res):
    dt, twin, rec = open_twin(runtime, args)
    res["twin"] = rec
    res["probe"] = node_probe(args)
    w, a, e = timed(dt, twin, {"op": "burst", "k": 256, "ms": 50}, 600)
    res["burst_256x50ms"] = burst_rec(a, w, 256, 50)
    res["burst_256x50ms"]["error"] = e
    drop(dt)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--backend", default="dragon_native")
    p.add_argument("--step", required=True,
                   choices=["basic", "gil", "reattach", "remote", "sessions", "pool"])
    p.add_argument("--state", default="smoke-state.json")
    p.add_argument("--workers", type=int, default=128, help="gil: tasks in the 10 s burst")
    p.add_argument("--sessions-list", default="1,4,16,64")
    p.add_argument("--ep-node", default=None, help="endpoint node for node_probe.sh")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--reattach-wait", type=float, default=180.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    res = {"provenance": provenance("R8-0 Dragon smoke", Path(__file__).name, args),
           "step": args.step}
    runtime = EndpointRuntime(broker_url=args.broker)
    runtime.start(wait=True)
    try:
        {"basic": step_basic, "gil": step_gil, "reattach": step_reattach,
         "remote": step_remote, "sessions": step_sessions, "pool": step_pool}[args.step](
            runtime, args, res)
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"[:500]
        print(res["error"], flush=True)
    finally:
        Path(args.out).write_text(json.dumps(res, indent=2, default=str))
        runtime.stop()
    print(json.dumps({k: v for k, v in res.items() if k not in ("provenance", "probes", "points")},
                     default=str)[:1500], flush=True)
    return 0 if "error" not in res else 1


if __name__ == "__main__":
    sys.exit(main())
