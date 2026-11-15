#!/usr/bin/env python3
"""Round 8c, C4: the E4 figure's rows (round 3 T4/T5, round 2 S2) on
dragon_native, next to the originals.  Markdown.

(a) swap turnaround to the first answer, p50 ms (median of repeats, min-max)
(b) publish to first use with the new model, p50 ms (all intervals pooled,
    as plots/make_figures.py)
(c) inference throughput while models are published at 1 / 10 / 100 per s,
    as a ratio to no publishing (req_per_s_x_rate0)

    python r8c/c4_table.py results/r8c/c4 results
"""
import glob
import json
import statistics as st
import sys
from pathlib import Path

d = Path(sys.argv[1])
base = Path(sys.argv[2]) if len(sys.argv) > 2 else d.parents[1]


def load(pat):
    return [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(pat)))]


def cell(vals, n=2):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "–"
    return f"{st.median(vals):,.{n}f} ({min(vals):,.{n}f}-{max(vals):,.{n}f})"


print("## (a) swap a running investigator: to the first answer from the new one, p50 ms\n")
print("| config | dragon_native (r8c) | round 3 T5 |\n|---|---|---|")
for lab, new, old in (("local c=1", "swap-local-dragon-c1-r*.json", "r3/t5/swap-pm-pool8-c1-r*-stack-r3-*.json"),
                      ("local c=50", "swap-local-dragon-c50-r*.json", "r3/t5/swap-pm-pool8-c50-r*-stack-r3-*.json"),
                      ("ORBIT c=1", "swap-orbit-dragon-c1-r*.json", "r3/t5/swap-pm-orbit-cross-c1-r*-stack-r3-*.json"),
                      ("ORBIT c=50", "swap-orbit-dragon-c50-r*.json", "r3/t5/swap-pm-orbit-cross-c50-r*-stack-r3-*.json")):
    n = load(d / new)
    o = load(base / old)
    print(f"| {lab} | {cell([r['turnaround']['p50_ms'] for r in n if r.get('turnaround')])} "
          f"| {cell([r['turnaround']['p50_ms'] for r in o if r.get('turnaround')])} |")

print("\n## (b) a new model, publish to first answer that uses it, p50 ms (intervals pooled)\n")
print("| path | dragon_native (r8c) | original | versions seen (r8c) |\n|---|---|---|---|")
for lab, new, old in (("local", "update-local-dragon-r*.json", "r3/t5/update-pm-local-pool8-r*-stack-r3-*.json"),
                      ("ORBIT", "update-orbit-dragon-r*.json", "r3/t5/update-pm-orbit-cross-r*-stack-r3-*.json"),
                      ("radical.3 (WAN)", "update-remote-dragon-r*.json", "s2/update-pm-remote-r*-stack-*.json")):
    n = load(d / new)
    o = load(base / old)
    seen = [f"{p.get('interval_s', p.get('interval'))}s: {p.get('versions_seen')}/{p.get('versions')}"
            for p in n[0]["points"]] if n else []
    print(f"| {lab} | {cell([p['answered']['p50_ms'] for r in n for p in r['points'] if p.get('answered')])} "
          f"| {cell([p['answered']['p50_ms'] for r in o for p in r['points'] if p.get('answered')])} "
          f"| {'; '.join(seen)} |")

print("\n## (c) inference throughput while publishing models, ratio to none (median of repeats, min-max)\n")
print("| concurrency | rate /s | dragon_native (r8c) | round 3 (T4 c=1, T5 dip c=50) |\n|---|---|---|---|")
for lab, new, old in (("c=1", "publish-local-dragon-c1-r*.json", "r3/t4/publish-pm-pool8-c1-r*-stack-r3-*.json"),
                      ("c=50", "dip-local-dragon-c50-r*.json", "r3/t5/dip-pm-pool8-c50-r*-stack-r3-*.json")):
    n = load(d / new)
    o = load(base / old)
    for rate in (1.0, 10.0, 100.0):
        f = lambda runs: [p["req_per_s_x_rate0"] for r in runs for p in r["points"] if p.get("rate_target") == rate]
        print(f"| {lab} | {rate:g} | {cell(f(n))} | {cell(f(o))} |")
    r0 = [p.get("req_per_s") for r in n for p in r["points"] if p.get("rate_target") == 0.0]
    o0 = [p.get("req_per_s") for r in o for p in r["points"] if p.get("rate_target") == 0.0]
    print(f"| {lab} | 0 (req/s) | {cell(r0, 0)} | {cell(o0, 0)} |")
