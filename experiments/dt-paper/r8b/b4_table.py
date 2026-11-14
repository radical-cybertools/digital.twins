#!/usr/bin/env python3
"""Round 8b, B4: the tail at one twin, from r8b/run_windfield_b.sh's B4
rows (round 8's harness with --records).

Per row (b4base, b4noburst, b4nostream): probes, p50 / p99 (linear
interpolation) / max per arch and overall; then the slowest probes with
their arch, the distance to the nearest burst start (from the `t_b0`
stamps the answers carry) and the split around the worker-side `t_task`
(t_task - t = submit, queueing and run on the endpoint; t + lat - t_task =
the return path).  `t_task` is the inference node's clock, `t` the
client's (node 0): the split carries their offset (NTP, typically well
under 1 ms on Perlmutter).  Markdown.

    python r8b/b4_table.py results/r8b/b4 [SLOWEST]
"""
import json
import statistics
import sys
from pathlib import Path


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    pos = q * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


d = Path(sys.argv[1])
top = int(sys.argv[2]) if len(sys.argv) > 2 else 8
for f in sorted(d.glob("windfield-b4*.json")):
    res = json.loads(f.read_text())
    for pt in res["points"]:
        rec = pt.get("records") or {}
        probes = [p for ps in rec.get("probes", []) for p in ps if not p.get("err")]
        bursts = sorted({b[3] for b in rec.get("bursts", []) if b[3]})
        burst_s = {b[3]: b[4] for b in rec.get("bursts", []) if b[3]}
        print(f"\n## {f.name.split('-r1-')[0].removeprefix('windfield-')} ({len(probes)} probes, "
              f"{len(bursts)} bursts seen, failed {pt.get('failed')})\n")
        print("| arch | probes | p50 ms | p99 ms | max ms |\n|---|---|---|---|---|")
        for arch in ("pinn", "fno", "pcr", None):
            xs = [p["lat"] * 1e3 for p in probes if arch is None or p.get("arch") == arch]
            if xs:
                print(f"| {arch or 'all'} | {len(xs)} | {statistics.median(xs):.1f} | {pct(xs, .99):.1f} | {max(xs):.1f} |")
        if len(bursts) > 1:
            gaps = [b - a for a, b in zip(bursts, bursts[1:])]
            print(f"\nburst starts: {len(bursts)}, period p50 {statistics.median(gaps):.1f} s "
                  f"(min {min(gaps):.1f}, max {max(gaps):.1f}); makespan p50 "
                  f"{statistics.median(burst_s.values()):.2f} s")
        print(f"\nslowest {top}:\n")
        print("| t (s into load) | arch | lat ms | to nearest burst start s | submit+run ms | return ms |\n|---|---|---|---|---|---|")
        t0 = pt.get("load_start_epoch") or (probes[0]["t"] if probes else 0)
        for p in sorted(probes, key=lambda p: -p["lat"])[:top]:
            near = min(bursts, key=lambda b: abs(p["t"] - b)) if bursts else None
            dist = f"{p['t'] - near:+.1f}" if near else "–"
            tt = p.get("t_task")
            split = (f"{(tt - p['t']) * 1e3:.0f} | {(p['t'] + p['lat'] - tt) * 1e3:.0f}"
                     if tt else "– | –")
            print(f"| {p['t'] - t0:.1f} | {p.get('arch')} | {p['lat'] * 1e3:.0f} | {dist} | {split} |")
        # typical split, by arch
        for arch in ("pinn", "fno"):
            xs = [p for p in probes if p.get("arch") == arch and p.get("t_task")]
            if xs:
                sub = statistics.median((p["t_task"] - p["t"]) * 1e3 for p in xs)
                ret = statistics.median((p["t"] + p["lat"] - p["t_task"]) * 1e3 for p in xs)
                print(f"\n{arch} median split: submit+run {sub:.1f} ms, return {ret:.1f} ms ({len(xs)} probes)")
