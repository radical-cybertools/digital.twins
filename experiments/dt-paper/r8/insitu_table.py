#!/usr/bin/env python3
"""Round 8, R8-1: tables from r8/run_overhead.sh results.

Per (setup, task cost) and row (bare, investigator, agent): median over the
repeats of p50 latency (ms) and burst throughput (req/s), with min-max;
the DT's cost per request = row p50 - bare p50 (ms) and its ratio.  Markdown.

    python r8/insitu_table.py results/r8/r8-1
"""
import json
import re
import statistics
import sys
from pathlib import Path

NAME = re.compile(r"insitu-(?P<lab>[a-z-]+)-w(?P<w>[0-9.]+)-r(?P<r>\d+)-")
cells = {}
for f in sorted(Path(sys.argv[1]).glob("insitu-*.json")):
    m = NAME.match(f.name)
    if not m:
        continue
    d = json.loads(f.read_text())
    for row, v in d.get("rows", {}).items():
        cells.setdefault((m["lab"], float(m["w"])), {}).setdefault(row, []).append(
            (v["p50_ms"], v["concurrent_req_per_s"]))

print("| setup | task ms | row | repeats | p50 ms (min-max) | DT cost ms | vs bare | req/s, 50 at once (min-max) |")
print("|---|---|---|---|---|---|---|---|")
for (lab, w), rows in sorted(cells.items()):
    bare = statistics.median(x[0] for x in rows.get("bare", [(float("nan"), 0)]))
    for row in ("bare", "investigator", "agent"):
        xs = rows.get(row)
        if not xs:
            continue
        p = [x[0] for x in xs]
        q = [x[1] for x in xs]
        mp = statistics.median(p)
        cost = "–" if row == "bare" else f"{mp - bare:+.2f}"
        rel = "–" if row == "bare" else f"{mp / bare:.3f}x"
        print(f"| {lab} | {w:g} | {row} | {len(xs)} | {mp:.2f} ({min(p):.2f}-{max(p):.2f}) | {cost} | {rel} | "
              f"{statistics.median(q):.0f} ({min(q):.0f}-{max(q):.0f}) |")
