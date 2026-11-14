#!/usr/bin/env python3
"""P8b: the xGFabric WindField twin with real surrogates, measured.

Imports xGFabric's `twin_service_real.py` unchanged (its module setup:
config.sh via dotenv, `register_user_modules` over `tasks.*`, the ENGINES
from the DT_* env knobs) and builds the same graph as its `main()`.  On top,
it probes the running twin: every `--probe` seconds one `get_inference` on
the agent with a fake Davis reading, recording the latency and the `arch`
of the answer (`na` until a model is published, then `fno` / `pinn` /
`pcr`): which model the selector picked, and what that inference cost.
Every 10 s it records the twin's `twin_list` entry.

    python p8b_client.py --xgf $XGF_DIR --runtime 1200 --out p8b.json
"""

import argparse
import json
import os
import platform
import random
import socket
import statistics
import subprocess
import sys
import time
import datetime

from pathlib import Path


def git(path, *cmd):
    try:
        return subprocess.check_output(["git", "-C", str(path), *cmd], text=True).strip()
    except Exception:
        return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--xgf", default=os.environ.get("XGF_DIR"))
    p.add_argument("--runtime", type=float, default=1200)
    p.add_argument("--probe", type=float, default=3.0)
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    sys.path.insert(0, args.xgf)
    os.chdir(args.xgf)
    import twin_service_real as tsr  # noqa: E402  (module setup runs here)

    from digitaltwin.components import NULL_DTYPE, TypedData

    config = dict(os.environ)
    playground = config["PLAYGROUND_DIR"]
    root = Path(__file__).resolve().parents[3]
    res = {
        "provenance": {
            "experiment": "E6 P8b WindField twin, real surrogates",
            "harness": Path(__file__).name,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "host": socket.gethostname(),
            "python": platform.python_version(),
            "digital_twins_commit": git(root, "rev-parse", "HEAD"),
            "xgfabric_commit": git(args.xgf, "rev-parse", "HEAD"),
            "xgfabric_dirty": bool(git(args.xgf, "status", "--porcelain", "--", "tasks")),
            "slurm_job": os.environ.get("SLURM_JOB_ID"),
            "engines": tsr.ENGINES,
            "args": vars(args),
        },
        "probes": [], "states": [],
    }

    try:  # round 8: commits of all five repos, backend, telemetry, file system
        sys.path.insert(0, str(root / "experiments" / "dt-paper" / "r8"))
        from prov import provenance as _r8prov
        res["provenance"]["r8"] = _r8prov("R8-E WindField decomposed", Path(__file__).name)
    except Exception as exc:
        res["provenance"]["r8"] = f"unavailable: {exc}"

    def save():
        Path(args.out).write_text(json.dumps(res, indent=1))

    runtime = tsr.EndpointRuntime()
    runtime.start(wait=True)
    dt = None
    try:
        dt = runtime.get_plugin(tsr.DT_HOST, "dt", config=tsr.ENGINES)
        twin = dt.create_twin()
        print(f"[p8b] twin {twin}", flush=True)

        field = dt.package(tsr.WindFieldAgent, config)
        sink = dt.package(tsr.CUPS_Sink, config)
        learner = dt.package(tsr.WindTrendLearner, learn_backend="learning")
        base_profiler = dt.package(tsr.ProfilerInvestigator,
                                   playground + "/profiler/nersc_profiler")
        pi_profiler = dt.package(tsr.EndpointInvestigator, "pi",
                                 playground + "/profiler/pi_profiler")
        dt.add_input(twin, tsr.DAVIS_WIND_SENSOR, tsr.DAVIS_CHANNEL)
        dt.add_agent(twin, field, tsr.DAVIS_WIND_SENSOR, tsr.WIND_FIELD)
        dt.add_task(twin, sink, tsr.WIND_FIELD, NULL_DTYPE)
        dt.add_investigator(twin, base_profiler, tsr.TASK_DESCRIPTION_DTYPE,
                            tsr.PROFILE_RESULTS)
        dt.add_investigator(twin, pi_profiler, tsr.PROFILE_RESULTS,
                            tsr.PI_PREDICT_RUNTIME)
        dt.add_investigator(twin, learner, tsr.DAVIS_WIND_SENSOR, tsr.WIND_TREND)
        dt.start(twin)
        t_start = time.time()

        next_state = 0.0
        while time.time() - t_start < args.runtime:
            now = time.time() - t_start
            if now >= next_state:
                info = dt.twin(twin)
                res["states"].append({"t": now, "state": info.get("state"),
                                      "calls": info.get("calls"),
                                      "last_error": info.get("last_error")})
                print(f"[p8b] t={now:6.0f}s state={info.get('state')} "
                      f"calls={info.get('calls')}", flush=True)
                if info.get("state") == "failed":
                    print(f"[p8b] twin failed: {info.get('last_error')}", flush=True)
                    break
                next_state = now + 10
                save()
            r = random.random()
            reading = {"dt": datetime.datetime.now().isoformat(),
                       "wind_speed": round(r * 20, 1), "wind_avg": round(r * 15, 1),
                       "wind_dir": round(r * 360)}
            t0 = time.time()
            data = {}
            try:
                a = dt.get_inference(twin, TypedData(tsr.DAVIS_WIND_SENSOR, reading),
                                     tsr.WIND_FIELD, timeout=args.timeout)
                data = a.data if isinstance(a.data, dict) else {}
                arch, err = data.get("arch", "?"), None
            except Exception as exc:
                arch, err = "error", f"{type(exc).__name__}: {exc}"[:300]
            t1 = time.time()
            lat = t1 - t0
            # round 8 (R8-E): send / receive epochs and, with the r8/timings
            # xGFabric patch, the inference task's own times ("t")
            res["probes"].append({"t": t0 - t_start, "latency_s": lat, "arch": arch,
                                  "error": err, "t_send": t0, "t_recv": t1,
                                  "task": data.get("t")})
            if arch not in ("na",) or err:
                print(f"[p8b] t={t0 - t_start:6.0f}s arch={arch} {lat * 1e3:8.1f} ms"
                      + (f" {err}" if err else ""), flush=True)
            time.sleep(max(0.0, args.probe - lat))
    finally:
        by = {}
        for pr in res["probes"]:
            if not pr["error"]:
                by.setdefault(pr["arch"], []).append(pr["latency_s"])
        res["summary"] = {a: {"n": len(v), "p50_ms": statistics.median(v) * 1e3,
                              "min_ms": min(v) * 1e3, "max_ms": max(v) * 1e3}
                          for a, v in by.items()}
        first = {}
        for pr in res["probes"]:
            first.setdefault(pr["arch"], pr["t"])
        res["first_seen_s"] = first
        save()
        print("[p8b] summary " + json.dumps(res["summary"]), flush=True)
        print("[p8b] first seen " + json.dumps(first), flush=True)
        if dt is not None:
            try:
                for t in dt.twin_list():
                    dt.twin_close(t["twin_id"])
                dt.unregister_session()
            except Exception as exc:
                print(f"[p8b] teardown: {exc}", flush=True)
        runtime.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
