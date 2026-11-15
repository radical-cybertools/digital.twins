#!/usr/bin/env python3
"""Round 8c, C6: what a twin build costs, step by step.

One DT session (one experiment), N WindField-like twins of round 8b's B2
graph (r8b/r8b_components.py: WindAgent with three surrogate
investigators, TrendLearner, Sink), built one after another, not in
parallel.  Per twin, the wall time of each client call:

  register      create_twin(wait=False): the twin is registered (initializing)
  init          wait_ready: the twin's background initialization in the
                broker's dt service (stream participant, engines), until it
                leaves `initializing`
  add_input, add_agent, add_investigator (trend), add_investigator (sink),
  start
  first_answer  the first get_inference, split around the worker-side task
                time it returns (`t_task`): to_task = submit and run on the
                endpoint, from_task = the return path

Medians per step over the twins; every per-twin record in the JSON.

    python r8c/bench_build_steps.py --broker URL --inference EP --learning L0 \\
        --twins 16 --out f.json
"""

import argparse
import datetime
import json
import random
import statistics
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "r8b"))
sys.path.insert(0, str(HERE.parent / "r8"))

import r8b_components as rc  # noqa: E402
from prov import provenance  # noqa: E402

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import TypedData  # noqa: E402
from digitaltwin.service import register_user_modules  # noqa: E402

register_user_modules([rc])


def reading():
    r = random.random()
    return {"dt": datetime.datetime.now().isoformat(), "wind_speed": round(r * 20, 1),
            "wind_avg": round(r * 15, 1), "wind_dir": round(r * 360), "t_pub": time.time(),
            "probe": True}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--inference", required=True)
    p.add_argument("--learning", required=True)
    p.add_argument("--backend", default="dragon_native")
    p.add_argument("--twins", type=int, default=16)
    p.add_argument("--shared-stream", choices=["on", "off"], default=None)
    p.add_argument("--model-path", default="/pscratch/sd/m/merzky/dt-pm8/models/r8-model-10MB.bin")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    res = {"provenance": provenance("R8c-C6 twin build steps", Path(__file__).name, args,
                                    shared_stream=args.shared_stream or "default (on)"),
           "twins": []}
    rt = EndpointRuntime(broker_url=args.broker)
    rt.start(wait=True)
    dt = None
    try:
        cfg = {"engines": {"inference": {"endpoint_name": args.inference, "backends": [args.backend]},
                           "learning_0": {"endpoint_name": args.learning, "backends": [args.backend]}}}
        if args.shared_stream is not None:
            cfg["shared_stream"] = args.shared_stream == "on"
        t0 = time.time()
        dt = rt.get_plugin("broker", "dt", config=cfg)
        res["session_s"] = time.time() - t0
        run = uuid.uuid4().hex[:6]
        for k in range(args.twins):
            rec, tw = {"k": k}, None
            try:
                def step(name, fn, *a, **kw):
                    t = time.perf_counter()
                    out = fn(*a, **kw)
                    rec[name] = time.perf_counter() - t
                    return out
                tw = step("register", dt.create_twin, f"r8c6-{uuid.uuid4().hex[:12]}", wait=False)
                step("init", dt.wait_ready, tw, args.timeout)
                step("add_input", dt.add_input, tw, rc.DAVIS, f"r8c6/{run}/t{k}")
                step("add_agent", dt.add_agent, tw,
                     dt.package(rc.WindAgent, learn="learning_0", model_path=args.model_path),
                     rc.DAVIS, rc.FIELD)
                step("add_trend", dt.add_investigator, tw,
                     dt.package(rc.TrendLearner, learn="learning_0"), rc.DAVIS, rc.TREND)
                step("add_sink", dt.add_investigator, tw, dt.package(rc.Sink), rc.FIELD, rc.STATS)
                step("start", dt.start, tw)
                t1 = time.time()
                a = dt.get_inference(tw, TypedData(rc.DAVIS, reading()), rc.FIELD,
                                     timeout=args.timeout).data
                t2 = time.time()
                rec["first_answer"] = t2 - t1
                if isinstance(a, dict) and a.get("t_task"):
                    rec["to_task"] = a["t_task"] - t1
                    rec["from_task"] = t2 - a["t_task"]
                    rec["arch"] = a.get("arch")
                rec["total"] = sum(v for n, v in rec.items()
                                   if n in ("register", "init", "add_input", "add_agent",
                                            "add_trend", "add_sink", "start", "first_answer"))
            except Exception as exc:
                rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
            res["twins"].append(rec)
            Path(args.out).write_text(json.dumps(res, indent=1, default=str))
            print(f"twin {k}: " + " ".join(f"{n}={v * 1e3:.1f}ms" for n, v in rec.items()
                                            if isinstance(v, float)) + (f" error={rec['error']}" if
                                                                         rec.get("error") else ""),
                  flush=True)
        steps = ["register", "init", "add_input", "add_agent", "add_trend", "add_sink", "start",
                 "first_answer", "to_task", "from_task", "total"]
        res["median_ms"] = {s: statistics.median(r[s] for r in res["twins"] if s in r) * 1e3
                            for s in steps if any(s in r for r in res["twins"])}
        res["median_ms_after_first"] = {
            s: statistics.median(r[s] for r in res["twins"][1:] if s in r) * 1e3
            for s in steps if any(s in r for r in res["twins"][1:])}
        print("median ms:", json.dumps({k: round(v, 1) for k, v in res["median_ms"].items()}), flush=True)
        print("median ms (twins 2..N):",
              json.dumps({k: round(v, 1) for k, v in res["median_ms_after_first"].items()}), flush=True)
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
