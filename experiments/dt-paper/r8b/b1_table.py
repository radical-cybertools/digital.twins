#!/usr/bin/env python3
"""Round 8b, B1: per cell (venv x compression x twins), each repeat's
aggregate req/s, per-twin p50 / p99 (median over twins), the worst twin's
p99, and the broker's and endpoint's CPU (% of one core) over the load
window, from r8b/run_b1.sh results.  Markdown.

    python r8b/b1_table.py results/r8b/b1
"""
import json
import re
import sys
from pathlib import Path

d = Path(sys.argv[1])
NAME = re.compile(r"engine-noop-one-r(?P<cell>[a-z]+)(?P<rep>\d)-(?P<job>\d+)-")
CELLS = {"logon": "round 8 (ve8), compression on", "logfix": "log fix (ve8b), compression on",
         "compoff": "round 8 (ve8), compression off", "both": "both (ve8b, off)",
         "bothk": "both (ve8b, off)"}


def cpu(f, t0, t1):
    s = []
    if f.exists():
        for line in f.read_text().splitlines():
            x = line.split()
            if len(x) == 5 and not line.startswith("#"):
                s.append((float(x[0]), int(x[2])))
    w = [p for p in s if t0 <= p[0] <= t1]
    if len(w) < 2:
        return None
    return 100 * (w[-1][1] - w[0][1]) / 100 / (w[-1][0] - w[0][0])


rows = []
for f in sorted(d.glob("engine-noop-one-*.json")):
    m = NAME.search(f.name)
    if not m:
        continue
    r = json.loads(f.read_text())
    pv = r["provenance"]
    for p in r["points"]:
        tag = f"r{m['cell']}{m['rep']}-{m['job']}"
        stamp = f.name.split(f"{tag}-")[1].removesuffix(".json")
        b = cpu(d / f"broker-proc-{tag}-{stamp}.txt", p["load_start_epoch"], p["load_end_epoch"])
        e = cpu(d / f"endpoint-proc-{tag}-{stamp}.txt", p["load_start_epoch"], p["load_end_epoch"])
        rows.append((m["cell"], int(m["rep"]), p["twins"], p["req_per_s"], p["p50_ms_median"],
                     p["p99_ms_median"], p["p99_ms_max"], b, e, pv.get("ws_compression"),
                     pv.get("online_run_log_level")))
order = list(CELLS)
rows.sort(key=lambda x: (order.index(x[0]) if x[0] in order else 99, x[1]))
print("| cell | twins | rep | req/s | p50 ms | p99 ms | worst twin p99 ms | broker CPU % | endpoint CPU % | provenance |")
print("|---|---|---|---|---|---|---|---|---|---|")
f1 = lambda v, n=0: "–" if v is None else f"{v:,.{n}f}"
for c, rep, n, rps, p50, p99, w, b, e, comp, lvl in rows:
    print(f"| {CELLS.get(c, c)} | {n} | {rep} | {f1(rps, 1)} | {f1(p50)} | {f1(p99)} | {f1(w)} | {f1(b)} | {f1(e)} | "
          f"compression {comp}, Online run at {lvl} |")
