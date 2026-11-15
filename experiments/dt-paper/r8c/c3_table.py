#!/usr/bin/env python3
"""Round 8c, C3: the E1 paths table (round 3b U2/U3, round 2 S3) on
dragon_native, next to the original's values.

Per path (local, ORBIT cross-node, radical.3 client) and row (bare,
investigator, agent, xgf): p50 per sequential request (median over the
repeats, with min-max) and throughput under bursts of 500 (per run the
median of bursts 2-5, as plots/make_figures.py's later_bursts; median over
the repeats); the service row's p50 per repeat.  Markdown.

    python r8c/c3_table.py results/r8c/c3 results
"""
import glob
import json
import statistics as st
import sys
from pathlib import Path

d = Path(sys.argv[1])
base = Path(sys.argv[2]) if len(sys.argv) > 2 else d.parents[1]
ROWS = ["bare", "investigator", "agent", "xgf"]


def load(pat):
    return [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(pat)))]


def later(run, row):
    r = run["rows"][row]
    return st.median(r["concurrent"] / b for b in r["bursts_s"][1:]) if len(r.get("bursts_s", [])) > 1 else None


def cell(vals, n=2):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "–"
    return f"{st.median(vals):,.{n}f} ({min(vals):,.{n}f}-{max(vals):,.{n}f})"


new = {
    "local": {r: load(d / f"insitu-local-dragon-c500-solo-{r}-r*.json") for r in ROWS},
    "ORBIT cross-node": {r: load(d / f"insitu-orbit-dragon-c500-solo-{r}-r*.json") for r in ROWS},
}
remote = load(d / "insitu-remote-dragon-c1-r*.json")
old = {
    "local": {r: load(base / f"r3b/u2/insitu-pm-pool8-c50-solo-{r}-r*-stack-r3b-*.json") for r in ROWS},
    "ORBIT cross-node": {r: load(base / f"r3b/u2/insitu-pm-orbit-cross-c1-solo-{r}-r*-stack-r3b-*.json") for r in ROWS},
}
old_burst = {
    "local": {r: load(base / f"r3b/u2/insitu-pm-pool8-c500-solo-{r}-r*-stack-r3b-*.json") for r in ROWS},
    "ORBIT cross-node": {r: load(base / f"r3b/u2/insitu-pm-orbit-cross-c500-solo-{r}-r*-stack-r3b-*.json") for r in ROWS},
}
old_remote = load(base / "r3b/u3/insitu-pm-remote-c1-r*-stack-r3b-*.json")

print("## p50 per request, ms (median of repeats, min-max)\n")
print("| path | row | dragon_native (r8c) | round 3b (concurrent pool / endpoint) |")
print("|---|---|---|---|")
for path in new:
    for r in ROWS:
        print(f"| {path} | {r} | {cell([x['rows'][r]['p50_ms'] for x in new[path][r]])} "
              f"| {cell([x['rows'][r]['p50_ms'] for x in old[path][r]])} |")
for r in ROWS[:3]:
    print(f"| radical.3 client | {r} | {cell([x['rows'][r]['p50_ms'] for x in remote if r in x['rows']])} "
          f"| {cell([x['rows'][r]['p50_ms'] for x in old_remote if r in x['rows']])} |")
svc = load(d / "service-remote-dragon-*.json")
svc_old = load(base / "s3/service-remote-stack-*.json")
if svc:
    print(f"| radical.3 service | bare (twin in the broker's dt plugin) "
          f"| {cell([rep['p50_ms'] for rep in svc[0]['repeats']])} "
          f"| {cell([rep['p50_ms'] for rep in svc_old[0]['repeats']]) if svc_old else '–'} |")

print("\n## throughput under bursts of 500, req/s (per run median of bursts 2-5; median of repeats, min-max)\n")
print("| path | row | dragon_native (r8c) | round 3b |")
print("|---|---|---|---|")
for path in new:
    for r in ROWS:
        print(f"| {path} | {r} | {cell([later(x, r) for x in new[path][r]], 0)} "
              f"| {cell([later(x, r) for x in old_burst[path][r]], 0)} |")
if svc:
    s, o = svc[0]["summary"], (svc_old[0]["summary"] if svc_old else {})
    print(f"\nService: session + twin {s.get('session_and_twin_s', 0):.2f} s (S3 {o.get('session_and_twin_s', 0):.2f}), "
          f"reattach {s.get('reattaches_ok')}/{s.get('reattaches')} in {s.get('attach_s', 0):.2f} s "
          f"(S3 {o.get('reattaches_ok')}/{o.get('reattaches')} in {o.get('attach_s', 0):.2f} s), "
          f"first answer after reattach {s.get('first_answer_s', 0):.2f} s (S3 {o.get('first_answer_s', 0):.2f}).")
