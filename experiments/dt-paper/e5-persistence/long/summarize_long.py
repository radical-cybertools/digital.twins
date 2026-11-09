#!/usr/bin/env python3
"""Condense the E5 long run's event files into one summary per UTC day.

    python summarize_long.py --events ~/dt-long/events --out results/e5-long
    python summarize_long.py --events ... --out ... --day 20261110

Without `--day`, every day that has an event file is summarized, plus
`summary-all.json` over the whole run.  A probe gap longer than
`--gap` x the probe period counts as an outage (driver or host down).
"""

import argparse
import json
import statistics

from pathlib import Path


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def dist(xs):
    if not xs:
        return None
    return {"n": len(xs), "p50": statistics.median(xs), "p90": pct(xs, 0.9),
            "p99": pct(xs, 0.99), "max": max(xs)}


def summarize(recs, probe_period, gap):
    by = {}
    for r in recs:
        by.setdefault(r["kind"], []).append(r)
    out = {"from_utc": recs[0]["utc"], "to_utc": recs[-1]["utc"],
           "events": {k: len(v) for k, v in sorted(by.items())}}

    probes = by.get("probe", [])
    out["probes"] = {}
    for twin in ("inf", "lrn"):
        ps = [p for p in probes if p["twin"] == twin]
        ok = [p for p in ps if p["ok"]]
        out["probes"][twin] = {
            "n": len(ps), "ok": len(ok),
            "availability": len(ok) / len(ps) if ps else None,
            "rtt_ms": dist([p["rtt"] * 1e3 for p in ok]),
            "errors": sorted({p["error"] for p in ps if p["error"]})[:10],
        }
    ts = sorted(p["t"] for p in probes if p["twin"] == "inf")
    gaps = [(b - a, a) for a, b in zip(ts, ts[1:]) if b - a > gap * probe_period]
    out["outages"] = [{"start_t": a, "seconds": g} for g, a in gaps]
    out["epochs"] = sorted({p["epoch"] for p in probes if p.get("epoch") is not None})

    ra = by.get("reattach", [])
    out["reattach"] = {"n": len(ra), "ok": sum(r["ok"] for r in ra),
                       "attach_s": dist([r["attach_s"] for r in ra if r.get("attach_s")])}

    out["loss"] = {
        "kills": len(by.get("endpoint_killed", [])),
        "detected": len(by.get("loss_detected", [])),
        "not_detected": len(by.get("loss_not_detected", [])),
        "detect_s": dist([r["detect_s"] for r in by.get("loss_detected", [])]),
        "resume_s": dist([r["resume_s"] for r in by.get("learning_resumed", [])]),
        "cycle_failures": len(by.get("cycle_failed", [])),
    }

    stats = by.get("stats", [])
    out["resources"] = {}
    for proc in ("broker", "inference", "learning", "driver"):
        ss = [s[proc] for s in stats if s.get(proc) and "rss_kb" in s[proc]]
        if ss:
            out["resources"][proc] = {
                key: {"first": ss[0][key], "last": ss[-1][key],
                      "max": max(s[key] for s in ss)}
                for key in ("rss_kb", "threads", "fds")}
    for kind in ("driver_start", "session_a_created", "session_a_lost",
                 "client_rebuild", "client_rebuild_failed"):
        out.setdefault("notable", {})[kind] = [r["utc"] for r in by.get(kind, [])]
    return out


def load(files):
    recs = []
    for f in files:
        with open(f) as fh:
            recs.extend(json.loads(line) for line in fh if line.strip())
    return sorted(recs, key=lambda r: r["t"])


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--events", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--day", help="YYYYMMDD; default: every day plus the whole run")
    p.add_argument("--probe", type=float, default=10.0, help="probe period, s")
    p.add_argument("--gap", type=float, default=3.0)
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(args.events).glob("events-*.jsonl"))
    if args.day:
        files = [f for f in files if f.stem == f"events-{args.day}"]
    for f in files:
        day = f.stem.split("-", 1)[1]
        recs = load([f])
        if recs:
            path = out / f"summary-{day}.json"
            path.write_text(json.dumps(summarize(recs, args.probe, args.gap), indent=2) + "\n")
            print(path)
    if not args.day and files:
        path = out / "summary-all.json"
        path.write_text(json.dumps(summarize(load(files), args.probe, args.gap), indent=2) + "\n")
        print(path)


if __name__ == "__main__":
    main()
