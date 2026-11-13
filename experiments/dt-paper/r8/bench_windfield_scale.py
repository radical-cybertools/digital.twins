#!/usr/bin/env python3
"""Round 8, R8-C: how many WindField-like twins fit on one broker?

N twins of `r8c_components` (the WindField graph with synthetic tasks at
measured costs) in the broker's `dt` service, T twins per DT service
session (`--per-session`, 0 = all in one).  Engines: `inference` on one
Dragon endpoint, `learning_0..3` on four (twin k trains on learning_{k%4}).
Per twin: one Davis-like stream at --rate Hz (90 B JSON records, published
from this process with `ChannelPublisher`), and a probe that asks the
agent for an inference once a second.  After --warmup s, --seconds of
measurement:

  answer time    p50 / p99 over all probes, the worst twin's p99
  failures       probe errors, twins not running
  burst makespan the simulation bursts' makespan and the trainings' time,
                 as the answers report them (model kwargs)
  update delay   per (twin, model, version): first probe answer carrying
                 the version minus its publish time

N rises through --twins until the break (p99 > 1 s, any failure), one step
past it, then stops.

    python r8/bench_windfield_scale.py --broker URL --inference EP \\
        --learning L0,L1,L2,L3 --twins 1,4,16 --per-session 16 --out f.json
"""

import argparse
import asyncio
import datetime
import json
import random
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import r8c_components as rc  # noqa: E402
from prov import provenance  # noqa: E402

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import DataType, TypedData  # noqa: E402
from digitaltwin.service import register_user_modules  # noqa: E402
from digitaltwin.streaming import ChannelPublisher  # noqa: E402

register_user_modules([rc])
TREND = DataType("r8c_trend")


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def reading():
    r = random.random()
    return {"dt": datetime.datetime.now().isoformat(), "wind_speed": round(r * 20, 1),
            "wind_avg": round(r * 15, 1), "wind_dir": round(r * 360)}


def drop(dt):
    try:
        for t in dt.twin_list():
            dt.twin_close(t["twin_id"])
        dt.unregister_session()
    except Exception as exc:
        print(f"session teardown: {exc}", flush=True)


def publishers(channels, rate, stop_evt, stats):
    async def one(ch, delay):
        pub = await ChannelPublisher.open(ch, ready_timeout=0)
        try:
            await asyncio.sleep(delay)
            while not stop_evt.is_set():
                await pub.publish(reading())
                stats["published"] += 1
                await asyncio.sleep(1.0 / rate)
        finally:
            await pub.close()

    async def main():
        await asyncio.gather(*[one(ch, k / max(1, len(channels))) for k, ch in enumerate(channels)],
                             return_exceptions=True)

    asyncio.run(main())


def one_n(runtime, args, n, run):
    per = args.per_session or n
    s = -(-n // per)
    engines = {"inference": {"endpoint_name": args.inference, "backends": [args.backend]}}
    for k, ep in enumerate(args.learning):
        engines[f"learning_{k}"] = {"endpoint_name": ep, "backends": [args.backend]}
    t0 = time.time()
    with ThreadPoolExecutor(min(s, 16)) as pool:
        dts = list(pool.map(lambda _: runtime.get_plugin("broker", "dt", config={"engines": engines}),
                            range(s)))
    channels = [f"r8c/{run}/n{n}/t{k}" for k in range(n)]
    errors = []

    def build(k):
        dt = dts[k // per]
        learn = f"learning_{k % len(args.learning)}" if args.learning else None
        twin = dt.create_twin(f"r8c-{uuid.uuid4().hex[:12]}")
        dt.add_input(twin, rc.DAVIS, channels[k])
        dt.add_agent(twin, dt.package(rc.WindAgent, learn=learn, model_path=args.model_path),
                     rc.DAVIS, rc.FIELD)
        dt.add_investigator(twin, dt.package(rc.TrendLearner, learn=learn), rc.DAVIS, TREND)
        dt.start(twin)
        dt.get_inference(twin, TypedData(rc.DAVIS, reading()), rc.FIELD, timeout=args.timeout)
        return dt, twin

    twins = []
    with ThreadPoolExecutor(min(n, 16)) as pool:
        for f in [pool.submit(build, k) for k in range(n)]:
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

    stop_evt = threading.Event()
    pstats = {"published": 0}
    pth = threading.Thread(target=publishers, args=(channels, args.rate, stop_evt, pstats), daemon=True)
    pth.start()
    t_meas = time.time() + args.warmup
    t_end = t_meas + args.seconds
    probes = [[] for _ in twins]

    def probe(k, dt, twin):
        while time.time() < t_end:
            t1 = time.time()
            try:
                a = dt.get_inference(twin, TypedData(rc.DAVIS, reading()), rc.FIELD,
                                     timeout=args.timeout).data
                err = None
            except Exception as exc:
                a, err = {}, f"{type(exc).__name__}: {exc}"[:200]
            t2 = time.time()
            if t1 >= t_meas:
                probes[k].append({"t": t1, "lat": t2 - t1, "err": err, **(a if isinstance(a, dict) else {})})
            time.sleep(max(0.0, 1.0 - (time.time() - t1)))

    ths = [threading.Thread(target=probe, args=(k, dt, tw)) for k, (dt, tw) in enumerate(twins)]
    c0 = time.process_time()
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    stop_evt.set()
    pth.join(timeout=30)
    states = {}
    for dt, tw in twins:
        try:
            st = dt.twin(tw).get("state")
        except Exception as exc:
            st = f"error {type(exc).__name__}"
        states[st] = states.get(st, 0) + 1
    allp = [p for ps in probes for p in ps]
    ok = [p for p in allp if not p["err"]]
    lat = [p["lat"] for p in ok]
    worst = max((pct([p["lat"] for p in ps if not p["err"]], 0.99) or 0 for ps in probes), default=None)
    first = {}
    for k, ps in enumerate(probes):
        for p in ps:
            if p.get("v") and p.get("t_pub"):
                first.setdefault((k, p.get("arch"), p["v"]), p["t"] + p["lat"] - p["t_pub"])
    bursts = [p["burst_s"] for p in ok if p.get("burst_s")]
    trains = [p["train_s"] for p in ok if p.get("train_s")]
    rec.update({
        "measure_s": args.seconds, "published": pstats["published"],
        "probes": len(allp), "failed": len(allp) - len(ok),
        "errors": sorted({p["err"] for p in allp if p["err"]})[:3],
        "p50_ms": statistics.median(lat) * 1e3 if lat else None,
        "p99_ms": pct(lat, 0.99) * 1e3 if lat else None,
        "worst_twin_p99_ms": worst * 1e3 if worst else None,
        "arch_share": {a: sum(1 for p in ok if p.get("arch") == a) / max(1, len(ok))
                       for a in ("pinn", "fno", "pcr")},
        "burst_makespan_s_p50": statistics.median(bursts) if bursts else None,
        "burst_makespan_s_max": max(bursts, default=None),
        "train_s_p50": statistics.median(trains) if trains else None,
        "update_delay_s_p50": statistics.median(first.values()) if first else None,
        "update_delay_s_max": max(first.values(), default=None),
        "updates_seen": len(first),
        "twin_states": states, "load_start_epoch": t_meas, "load_end_epoch": t_end,
        "client_cpu_pct": 100 * (time.process_time() - c0) / (time.time() - t_meas + args.warmup),
    })
    reasons = []
    if rec["failed"]:
        reasons.append(f"{rec['failed']} probes failed: {rec['errors'][0] if rec['errors'] else ''}")
    if rec["p99_ms"] and rec["p99_ms"] > 1000:
        reasons.append(f"p99 {rec['p99_ms']:.0f} ms")
    if set(states) - {"running"}:
        reasons.append(f"twin states {states}")
    rec["break"] = "; ".join(reasons) or None
    for dt in dts:
        drop(dt)
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--inference", required=True)
    p.add_argument("--learning", default="", type=lambda s: [x for x in s.split(",") if x])
    p.add_argument("--backend", default="dragon_native")
    p.add_argument("--twins", default="1,4,16,64,128,256")
    p.add_argument("--per-session", type=int, default=16)
    p.add_argument("--rate", type=float, default=1.0)
    p.add_argument("--warmup", type=float, default=25.0)
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--model-path", default="/pscratch/sd/m/merzky/dt-pm8/models/r8-model-10MB.bin")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    run = uuid.uuid4().hex[:6]
    res = {"provenance": provenance("R8-C WindField at scale", Path(__file__).name, args), "points": []}
    rt = EndpointRuntime(broker_url=args.broker)
    rt.start(wait=True)
    broke = None
    try:
        for n in [int(x) for x in args.twins.split(",") if x]:
            try:
                rec = one_n(rt, args, n, run)
            except Exception as exc:
                rec = {"twins": n, "error": f"{type(exc).__name__}: {exc}"[:400],
                       "break": f"harness error: {exc}"[:200]}
            res["points"].append(rec)
            Path(args.out).write_text(json.dumps(res, indent=1, default=str))
            print(f"N={n:4d} per-session={args.per_session}: p50 {rec.get('p50_ms')} p99 {rec.get('p99_ms')} "
                  f"worst {rec.get('worst_twin_p99_ms')} failed {rec.get('failed')} burst p50 "
                  f"{rec.get('burst_makespan_s_p50')} update p50 {rec.get('update_delay_s_p50')} "
                  f"create {rec.get('create_s')} break {rec.get('break')}", flush=True)
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
