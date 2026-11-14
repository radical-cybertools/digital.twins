#!/usr/bin/env python3
"""Round 8, R8-2: table from r8/run_engine.sh results.

Per row (noop-one, w20-one, noop-persession) and N: medians over the
repeats of aggregate req/s, per-twin p50 / p99 (median over twins), the
worst twin's p99 (max over repeats), and the CPU (% of one core) of the
broker and the endpoint over each load window (joined from
broker-proc-* / endpoint-proc-*), plus the client's own CPU.  Markdown.

    python r8/engine_table.py results/r8/r8-2
"""
import json
import re
import statistics
import sys
from pathlib import Path

d = Path(sys.argv[1])
NAME = re.compile(r"engine-(?P<row>[a-z0-9-]+)-(?P<tag>r\d+-\d+)-")


def samples(f):
    out = []
    if f.exists():
        for line in f.read_text().splitlines():
            x = line.split()
            if len(x) == 5 and not line.startswith("#"):
                out.append((float(x[0]), int(x[2])))
    return out


def cpu(s, a, b):
    w = [x for x in s if a <= x[0] <= b]
    if len(w) < 2:
        return None
    return (w[-1][1] - w[0][1]) / 100 / (w[-1][0] - w[0][0]) * 100


rows = {}
for f in sorted(d.glob("engine-*.json")):
    m = NAME.match(f.name)
    if not m:
        continue
    tag = m["tag"]
    stack = f.name.split(tag + "-")[1].rsplit(".json", 1)[0]
    bs = samples(d / f"broker-proc-{tag}-{stack}.txt")
    es = samples(d / f"endpoint-proc-{tag}-{stack}.txt")
    for p in json.loads(f.read_text())["points"]:
        a, b = p.get("load_start_epoch"), p.get("load_end_epoch")
        p["broker_cpu"] = cpu(bs, a, b) if a else None
        p["endpoint_cpu"] = cpu(es, a, b) if a else None
        rows.setdefault((m["row"], p["twins"]), []).append(p)


def med(xs, fmt):
    xs = [x for x in xs if x is not None]
    return format(statistics.median(xs), fmt) if xs else "–"


print("| row | twins | repeats ok | req/s (min-max) | p50 ms | p99 ms | worst twin p99 ms | broker CPU % | endpoint CPU % | client CPU % | breaks |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for (row, n), ps in sorted(rows.items(), key=lambda k: (k[0][0], k[0][1])):
    ok = [p for p in ps if p.get("req_per_s")]
    q = [p["req_per_s"] for p in ok]
    rng = f" ({min(q):.0f}-{max(q):.0f})" if q else ""
    worst = max((p.get("p99_ms_max") or 0 for p in ok), default=None)
    br = "; ".join(sorted({p["break"][:60] for p in ps if p.get("break")}))
    print(f"| {row} | {n} | {len(ok)}/{len(ps)} | {med(q, '.0f')}{rng} | {med([p.get('p50_ms_median') for p in ok], '.1f')} | "
          f"{med([p.get('p99_ms_median') for p in ok], '.1f')} | {worst:.0f} | {med([p['broker_cpu'] for p in ok], '.0f')} | "
          f"{med([p['endpoint_cpu'] for p in ok], '.0f')} | {med([p.get('client_cpu_pct') for p in ok], '.0f')} | {br or '–'} |")
