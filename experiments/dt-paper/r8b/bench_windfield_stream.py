#!/usr/bin/env python3
"""Round 8b, B2: WindField-like twins per experiment, measured on the
stream-driven path.

Round 8's R8-C setup (r8/bench_windfield_scale.py: N twins in the broker's
`dt` service, all in one DT session; inference on one Dragon endpoint,
learning on four; one 1 Hz Davis-like stream per twin) with the round 8b
corrections (r8b/r8b_components.py):

  answer time   reading published (`t_in`, stamped by the publisher on
                node 0) -> the agent's answer arriving at the twin's Sink
                (`t_arrive`, in the broker on node 0): the path the
                WindField field takes to its consumer.  p50, p99 (linear
                interpolation), max and the worst twin's p99 over every
                streamed answer that arrives in the measurement window.
  probe         a low-rate get_inference per twin (--probe-hz, 0.1) marked
                {"probe": True}, which the investigators ignore; its
                latency is reported separately.
  burst         each investigator's real burst period (successive `t_b0`
                of the models its answers carry), the burst makespan and
                the training time.
  update delay  per (twin, arch, version): first streamed answer carrying
                the version (its `t_arrive`) minus the model's publish time.

Every per-sample record (stream answers and probes) goes into the result
JSON.  N rises through --twins; one step past the break (p99 > 1 s, a
failure or a twin not running), then stops.

    python r8b/bench_windfield_stream.py --broker URL --inference EP \\
        --learning L0,L1,L2,L3 --twins 16,32,64 --seconds 120 --out f.json
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
sys.path.insert(0, str(HERE.parent / "r8"))

import r8b_components as rc  # noqa: E402
from prov import provenance  # noqa: E402

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import TypedData  # noqa: E402
from digitaltwin.service import register_user_modules  # noqa: E402
from digitaltwin.streaming import ChannelPublisher  # noqa: E402

register_user_modules([rc])


def pct(xs, q):
    """Percentile with linear interpolation between closest ranks."""
    xs = sorted(xs)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def reading(probe=False):
    r = random.random()
    d = {"dt": datetime.datetime.now().isoformat(), "wind_speed": round(r * 20, 1),
         "wind_avg": round(r * 15, 1), "wind_dir": round(r * 360), "t_pub": time.time()}
    if probe:
        d["probe"] = True
    return d


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


def summary(lat_s):
    if not lat_s:
        return {"n": 0}
    return {"n": len(lat_s), "p50_ms": statistics.median(lat_s) * 1e3,
            "p99_ms": pct(lat_s, 0.99) * 1e3, "max_ms": max(lat_s) * 1e3}


def stream_participants(runtime):
    """dt_stream.* participants in the broker's topology (round 8c, #66)."""
    try:
        names = [k for k in (runtime.topology() or {}) if str(k).startswith("dt_stream")]
        return {"count": len(names), "names": sorted(names)[:4]}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}


def one_n(runtime, args, n, run):
    engines = {"inference": {"endpoint_name": args.inference, "backends": [args.backend]}}
    for k, ep in enumerate(args.learning):
        engines[f"learning_{k}"] = {"endpoint_name": ep, "backends": [args.backend]}
    t0 = time.time()
    cfg = {"engines": engines}
    if args.shared_stream is not None:  # round 8c: #66, one stream participant per session
        cfg["shared_stream"] = args.shared_stream == "on"
    dt = runtime.get_plugin("broker", "dt", config=cfg)
    channels = [f"r8b/{run}/n{n}/t{k}" for k in range(n)]
    errors = []

    def build(k):
        learn = f"learning_{k % len(args.learning)}" if args.learning else None
        twin = dt.create_twin(f"r8b-{uuid.uuid4().hex[:12]}")
        dt.add_input(twin, rc.DAVIS, channels[k])
        dt.add_agent(twin, dt.package(rc.WindAgent, learn=learn, model_path=args.model_path),
                     rc.DAVIS, rc.FIELD)
        dt.add_investigator(twin, dt.package(rc.TrendLearner, learn=learn), rc.DAVIS, rc.TREND)
        dt.add_investigator(twin, dt.package(rc.Sink), rc.FIELD, rc.STATS)
        dt.start(twin)
        dt.get_inference(twin, TypedData(rc.DAVIS, reading(probe=True)), rc.FIELD, timeout=args.timeout)
        return twin

    twins = []
    with ThreadPoolExecutor(min(n, 16)) as pool:
        for f in [pool.submit(build, k) for k in range(n)]:
            try:
                twins.append(f.result())
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}"[:300])
    rec = {"twins": n, "sessions": 1, "created": len(twins), "create_s": time.time() - t0,
           "create_errors": errors[:3], "n_create_errors": len(errors),
           "shared_stream": args.shared_stream or "default (on)",
           "stream_participants": stream_participants(runtime)}
    if errors:
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
    period = 1.0 / args.probe_hz if args.probe_hz > 0 else None

    def probe(k, twin):
        time.sleep(random.random() * (period or 0))
        while period and time.time() < t_end:
            t1 = time.time()
            try:
                a = dt.get_inference(twin, TypedData(rc.DAVIS, reading(probe=True)), rc.FIELD,
                                     timeout=args.timeout).data
                err = None
            except Exception as exc:
                a, err = {}, f"{type(exc).__name__}: {exc}"[:200]
            t2 = time.time()
            if t1 >= t_meas:
                probes[k].append({"t": t1, "lat": t2 - t1, "err": err, **(a if isinstance(a, dict) else {})})
            time.sleep(max(0.0, period - (time.time() - t1)))

    ths = [threading.Thread(target=probe, args=(k, tw)) for k, tw in enumerate(twins)]
    for t in ths:
        t.start()
    while time.time() < t_end:
        time.sleep(1)
    for t in ths:
        t.join()
    stop_evt.set()
    pth.join(timeout=30)
    time.sleep(3)  # let the last answers reach the sinks

    states, last_errors = {}, set()
    sinks = []
    fetch_errors = []
    for tw in twins:
        try:
            info = dt.twin(tw)
            st = info.get("state")
            if info.get("last_error"):
                last_errors.add(str(info["last_error"])[:200])
        except Exception as exc:
            st = f"error {type(exc).__name__}"
        states[st] = states.get(st, 0) + 1
        try:
            s = dt.get_inference(tw, TypedData(rc.FIELD, {"query": True}), rc.STATS,
                                 timeout=args.timeout).data
            sinks.append(s.get("records", []))
        except Exception as exc:
            sinks.append([])
            fetch_errors.append(f"{type(exc).__name__}: {exc}"[:200])

    # stream-driven answers whose reading was published in the window
    win = [[r for r in rs if r.get("t_in") and t_meas <= r["t_in"] < t_end] for rs in sinks]
    lat = [r["t_arrive"] - r["t_in"] for rs in win for r in rs]
    worst = max((pct([r["t_arrive"] - r["t_in"] for r in rs], 0.99) or 0 for rs in win), default=None)
    expected = n * args.seconds * args.rate
    allp = [p for ps in probes for p in ps]
    okp = [p for p in allp if not p["err"]]

    # bursts: distinct (twin, arch, v) with their start, from every answer seen
    bursts = {}
    first = {}
    for k, rs in enumerate(sinks):
        for r in rs:
            if r.get("t_b0"):
                bursts[(k, r["arch"], r["v"])] = (r["t_b0"], r.get("burst_s"), r.get("train_s"))
            if r.get("v") and r.get("t_pub"):
                first.setdefault((k, r.get("arch"), r["v"]), r["t_arrive"] - r["t_pub"])
    periods = []
    for (k, arch) in {(k, a) for (k, a, _) in bursts}:
        b0 = sorted(v[0] for (kk, aa, _), v in bursts.items() if kk == k and aa == arch)
        periods += [b - a for a, b in zip(b0, b0[1:])]
    bmk = [v[1] for v in bursts.values() if v[1] is not None]
    trn = [v[2] for v in bursts.values() if v[2] is not None]
    s = summary(lat)
    rec.update({
        "measure_s": args.seconds, "warmup_s": args.warmup, "rate_hz": args.rate,
        "probe_hz": args.probe_hz, "published": pstats["published"],
        "stream_answers": s["n"], "stream_expected": expected,
        "stream_missing": max(0, int(expected - s["n"])),
        "p50_ms": s.get("p50_ms"), "p99_ms": s.get("p99_ms"), "max_ms": s.get("max_ms"),
        "worst_twin_p99_ms": worst * 1e3 if worst else None,
        "arch_share": {a: sum(1 for rs in win for r in rs if r.get("arch") == a) / max(1, s["n"])
                       for a in ("pinn", "fno", "pcr")},
        "probe": {**summary([p["lat"] for p in okp]), "count": len(allp), "failed": len(allp) - len(okp),
                  "errors": sorted({p["err"] for p in allp if p["err"]})[:3]},
        "burst_period_s_p50": statistics.median(periods) if periods else None,
        "burst_period_s_min": min(periods, default=None),
        "bursts_seen": len(bursts),
        "burst_makespan_s_p50": statistics.median(bmk) if bmk else None,
        "burst_makespan_s_max": max(bmk, default=None),
        "train_s_p50": statistics.median(trn) if trn else None,
        "update_delay_s_p50": statistics.median(first.values()) if first else None,
        "update_delay_s_max": max(first.values(), default=None),
        "updates_seen": len(first),
        "twin_states": states, "twin_last_errors": sorted(last_errors)[:3],
        "sink_fetch_errors": fetch_errors[:3], "n_sink_fetch_errors": len(fetch_errors),
        "load_start_epoch": t_meas, "load_end_epoch": t_end,
        "records": {"stream": sinks, "probes": probes},
    })
    reasons = []
    if okp != allp:
        reasons.append(f"{len(allp) - len(okp)} probes failed: {rec['probe']['errors'][:1]}")
    if fetch_errors:
        reasons.append(f"{len(fetch_errors)} sink fetches failed: {fetch_errors[0]}")
    if rec["p99_ms"] and rec["p99_ms"] > 1000:
        reasons.append(f"p99 {rec['p99_ms']:.0f} ms")
    if expected and s["n"] < 0.95 * expected:
        reasons.append(f"{s['n']} of {expected:.0f} streamed answers arrived")
    if set(states) - {"running"}:
        reasons.append(f"twin states {states}: {sorted(last_errors)[:1]}")
    rec["break"] = "; ".join(reasons) or None
    drop(dt)
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--inference", required=True)
    p.add_argument("--learning", default="", type=lambda s: [x for x in s.split(",") if x])
    p.add_argument("--backend", default="dragon_native")
    p.add_argument("--twins", default="16,32,64,96,128")
    p.add_argument("--rate", type=float, default=1.0)
    p.add_argument("--probe-hz", type=float, default=0.1)
    p.add_argument("--warmup", type=float, default=25.0)
    p.add_argument("--seconds", type=float, default=120.0)
    p.add_argument("--model-path", default="/pscratch/sd/m/merzky/dt-pm8/models/r8-model-10MB.bin")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--run-all-to", type=int, default=0,
                   help="round 8c: run every N up to this; larger N only if nothing broke yet "
                        "(default 0: round 8b's rule, one step past the break)")
    p.add_argument("--shared-stream", choices=["on", "off"], default=None,
                   help="round 8c: set the session's shared_stream (#66); unset = stack default (on)")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    run = uuid.uuid4().hex[:6]
    res = {"provenance": provenance("R8b-B2 / R8c-C1 WindField per experiment, stream path",
                                    Path(__file__).name, args,
                                    shared_stream=args.shared_stream or "default (on)"), "points": []}
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
            Path(args.out).write_text(json.dumps(res, default=str))
            print(f"N={n:4d}: stream p50 {rec.get('p50_ms')} p99 {rec.get('p99_ms')} max {rec.get('max_ms')} "
                  f"worst {rec.get('worst_twin_p99_ms')} answers {rec.get('stream_answers')}/"
                  f"{rec.get('stream_expected')} probe {(rec.get('probe') or {}).get('p50_ms')} "
                  f"burst period {rec.get('burst_period_s_p50')} burst {rec.get('burst_makespan_s_p50')} "
                  f"update {rec.get('update_delay_s_p50')} create {rec.get('create_s')} "
                  f"stream participants {(rec.get('stream_participants') or {}).get('count')} "
                  f"break {rec.get('break')}", flush=True)
            time.sleep(5)
            if rec.get("break") and broke is None:
                broke = n
                res["break"] = {"twins": n, "why": rec["break"]}
            if args.run_all_to:   # round 8c: every N <= run_all_to; beyond only before a break
                nxt = [int(x) for x in args.twins.split(",") if x and int(x) > n]
                if broke is not None and nxt and nxt[0] > args.run_all_to:
                    break
                continue
            if broke is not None and broke != n:
                break
    finally:
        Path(args.out).write_text(json.dumps(res, default=str))
        rt.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
