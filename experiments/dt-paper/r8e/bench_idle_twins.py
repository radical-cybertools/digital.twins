#!/usr/bin/env python3
"""Idle twins: what N built-and-started WindField twins cost one broker when
nothing flows (side track, 2026-11-16).

One DT session (one experiment) grows to each N in turn: twins are built
16 at a time with round 8c's WindField graph (an input channel, the agent
with its three surrogate investigators, the trend learner) and started, but
no reading is published and no probe runs between the measurements.  At
each N, after a settle period: CPU, RSS, threads and fds of the broker and
endpoint processes over a sampling window, then 50 sequential
get_inference calls on random twins (the cost an idle population puts on a
live request) and one twin_list (its time and size).

    python r8e/bench_idle_twins.py --broker URL --inference EP --learning EP \
        --broker-pid PID --endpoint-pid PID --twins 1000,2000,4000,8000,16000 --out F
"""

import argparse
import json
import random
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "r8"))

import r8c_components as rc  # noqa: E402
from prov import provenance  # noqa: E402

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import TypedData  # noqa: E402
from digitaltwin.service import register_user_modules  # noqa: E402

register_user_modules([rc])


def sample(pids, seconds):
    """CPU % of one core, RSS MB, threads, fds per process over `seconds`."""
    procs = {k: psutil.Process(p) for k, p in pids.items() if p}
    for p in procs.values():
        p.cpu_percent(None)
    time.sleep(seconds)
    out = {}
    for k, p in procs.items():
        with p.oneshot():
            out[k] = {"cpu_pct": p.cpu_percent(None),
                      "rss_mb": p.memory_info().rss / 2**20,
                      "threads": p.num_threads(), "fds": p.num_fds()}
    return out


def reading():
    return {"wind_speed": 5.0, "wind_avg": 4.0, "wind_dir": 180}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--broker", required=True)
    p.add_argument("--inference", required=True)
    p.add_argument("--learning", required=True)
    p.add_argument("--broker-pid", type=int, required=True)
    p.add_argument("--endpoint-pid", type=int, default=0)
    p.add_argument("--backend", default="concurrent")
    p.add_argument("--twins", default="1000,2000,4000,8000,16000")
    p.add_argument("--build-threads", type=int, default=16)
    p.add_argument("--settle", type=float, default=20.0)
    p.add_argument("--window", type=float, default=20.0)
    p.add_argument("--probes", type=int, default=50)
    p.add_argument("--model-path", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    res = {"provenance": provenance("r8e idle twins", vars(args)), "points": []}
    pids = {"broker": args.broker_pid, "endpoint": args.endpoint_pid}

    def save():
        Path(args.out).write_text(json.dumps(res, indent=1))

    rt = EndpointRuntime(broker_url=args.broker, name=f"r8e-client-{uuid.uuid4().hex[:6]}")
    rt.start(wait=True, timeout=60)
    engines = {"inference": {"endpoint_name": args.inference, "backends": [args.backend]},
               "learning_0": {"endpoint_name": args.learning, "backends": [args.backend]}}
    dt = rt.get_plugin("broker", "dt", config={"engines": engines})
    res["baseline"] = sample(pids, args.window)
    print(f"baseline {res['baseline']}", flush=True)

    twins = []

    def build(k):
        twin = dt.create_twin(f"r8e-{k:05d}-{uuid.uuid4().hex[:6]}")
        dt.add_input(twin, rc.DAVIS, f"r8e/idle/t{k}")
        dt.add_agent(twin, dt.package(rc.WindAgent, learn="learning_0",
                                      model_path=args.model_path, every=16),
                     rc.DAVIS, rc.FIELD)
        dt.add_investigator(twin, dt.package(rc.TrendLearner, learn="learning_0"),
                            rc.DAVIS, rc.TREND)
        dt.start(twin)
        return twin

    try:
        for n in [int(x) for x in args.twins.split(",")]:
            t0 = time.time()
            before = len(twins)
            errors = []
            with ThreadPoolExecutor(args.build_threads) as pool:
                for f in [pool.submit(build, k) for k in range(len(twins), n)]:
                    try:
                        twins.append(f.result())
                    except Exception as exc:
                        errors.append(f"{type(exc).__name__}: {exc}"[:200])
            build_s = time.time() - t0
            # wait until every twin left 'initializing'
            t1 = time.time()
            while True:
                states = {}
                lst = dt.twin_list()
                for t in lst:
                    states[t.get("state")] = states.get(t.get("state"), 0) + 1
                if states.get("initializing", 0) == 0 or time.time() - t1 > 600:
                    break
                time.sleep(2)
            ready_s = time.time() - t1
            time.sleep(args.settle)
            proc = sample(pids, args.window)

            lat, errs = [], 0
            for _ in range(args.probes):
                tw = random.choice(twins)
                a = time.time()
                try:
                    dt.get_inference(tw, TypedData(rc.DAVIS, reading()), rc.FIELD, timeout=60)
                except Exception:
                    errs += 1
                lat.append(time.time() - a)
            a = time.time()
            lst = dt.twin_list()
            tl_s = time.time() - a
            tl_bytes = len(json.dumps(lst))
            lat.sort()
            pt = {"twins": n, "created": len(twins), "build_errors": errors[:3],
                  "n_build_errors": len(errors), "build_s": build_s,
                  "build_ms_per_twin": 1e3 * build_s / max(1, len(twins) - before),
                  "ready_wait_s": ready_s, "states": states, "proc": proc,
                  "probe_p50_ms": 1e3 * statistics.median(lat),
                  "probe_p99_ms": 1e3 * lat[int(0.99 * (len(lat) - 1))],
                  "probe_errors": errs, "twin_list_s": tl_s, "twin_list_bytes": tl_bytes}
            res["points"].append(pt)
            save()
            print(f"N={n:6d} built {len(twins)} (+{len(errors)} err) in {build_s:6.1f} s, ready +{ready_s:5.1f} s, "
                  f"states {states} | broker {proc.get('broker')} | endpoint {proc.get('endpoint')} | "
                  f"probe p50 {pt['probe_p50_ms']:.1f} p99 {pt['probe_p99_ms']:.1f} ms err {errs} | "
                  f"twin_list {tl_s:.2f} s {tl_bytes/1e6:.1f} MB", flush=True)
            if errors and len(errors) > n // 10:
                res["stopped"] = f"too many build errors at {n}: {errors[0]}"
                break
    finally:
        save()
        try:
            dt.unregister_session()
        except Exception as exc:
            print(f"teardown: {exc}", flush=True)
        rt.stop()


if __name__ == "__main__":
    main()
