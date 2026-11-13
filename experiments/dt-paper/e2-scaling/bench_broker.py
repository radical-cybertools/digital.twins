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


def git_head():
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parents[3]), "rev-parse", "HEAD"],
            text=True).strip()
    except Exception:
        return None


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


def open_session_twins(runtime, args, n, errors, per=None):
    """N twins on N / per sessions, per twins each (round 7, Z3, --twins-per-session).

    --one-session (round 6, Y1c) is per = N.  Sessions are opened first, then
    the twins are built over all sessions on --create-threads threads.
    """
    per = per or n
    s = -(-n // per)
    with ThreadPoolExecutor(min(s, args.create_threads)) as pool:
        dts = list(pool.map(lambda _: runtime.get_plugin(
            "broker", "dt", config=bel.engines(inference=args.inference)), range(s)))

    def one(i):
        dt = dts[i // per]
        twin = str(uuid.uuid4())
        bel.build_sibling(dt, twin, offset=i)
        for _ in range(3):                                     # warm-up
            bel.infer(dt, twin)
        return dt, twin

    out = []
    with ThreadPoolExecutor(min(n, args.create_threads)) as pool:
        for f in [pool.submit(one, i) for i in range(n)]:
            try:
                out.append(f.result())
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}"[:300])
    return out


def one_n(runtime, args, n):
    t0 = time.time()
    sessions, errors = [], []
    if args.one_session:
        sessions = open_session_twins(runtime, args, n, errors)
    elif args.twins_per_session:
        sessions = open_session_twins(runtime, args, n, errors, args.twins_per_session)
    else:
        with ThreadPoolExecutor(min(n, args.create_threads)) as pool:
            futs = [pool.submit(open_twin, runtime, args.inference, i) for i in range(n)]
            for f in futs:
                try:
                    sessions.append(f.result())
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}"[:300])
    t_create = time.time() - t0
    per = n if args.one_session else (args.twins_per_session or 1)
    rec = {"sessions": n, "twins_per_session": per, "service_sessions": -(-n // per),
           "created": len(sessions), "create_s": t_create,
           "create_errors": errors[:5], "n_create_errors": len(errors)}
    if errors:
        for dt in {id(dt): dt for dt, _ in sessions}.values():
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
    if args.load_marker:                # round 7, Z2: the profiler starts on this
        Path(f"{args.load_marker}.n{n}").write_text(f"{t_load}\n")
    c0 = os.times()                     # round 6: this client's CPU in the load phase
    threads = [threading.Thread(target=loop, args=(dt, twin, k))
               for k, (dt, twin) in enumerate(sessions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    t_end = time.time()
    c1 = os.times()
    cpu_s = (c1.user + c1.system) - (c0.user + c0.system)
    for dt in {id(dt): dt for dt, _ in sessions}.values():   # once per session
        bel.drop(dt)
    rec.update({
        "load_start_epoch": t_load, "load_end_epoch": t_end,
        "requests": len(lat), "failed": sum(fails),
        "req_per_s": len(lat) / (t_end - t_load),
        "client_cpu_s": cpu_s, "client_cpu_pct": 100 * cpu_s / (t_end - t_load),
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
    p.add_argument("--one-session", action="store_true",
                   help="all N twins in one DT service session (round 6, Y1c)")
    p.add_argument("--twins-per-session", type=int, default=None,
                   help="T twins per DT service session, N / T sessions (round 7, Z3)")
    p.add_argument("--load-marker", default=None,
                   help="write the load start epoch to <path>.n<N> (round 7, Z2)")
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
        "digital_twins_commit": git_head(),          # round 6
        "ping_timeout": os.environ.get("RADICAL_ORBIT_PING_TIMEOUT"),
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
