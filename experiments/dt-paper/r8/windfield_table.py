#!/usr/bin/env python3
"""Round 8, R8-C: table from r8/run_windfield.sh results (one experiment = one
DT session, N twins).

Per N: repeats, medians over the repeats of the probes' p50 / p99 answer
time, the worst twin's p99 (max), the simulation-burst makespan and the
model-update delay (p50 / max), probes and failures, twin states, and the
CPU (% of one core) of the broker and of the inference endpoint process
over each measurement window, from broker-proc-* / endpoint-proc-*.

    python r8/windfield_table.py results/r8/r8-c3
"""
import json
import re
import statistics
import sys
from pathlib import Path

d = Path(sys.argv[1])
NAME = re.compile(r"windfield-(?P<row>[a-z0-9]+)-(?P<tag>r\d+-\d+)-(?P<stack>.+)\.json$")


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
    return (w[-1][1] - w[0][1]) / 100 / (w[-1][0] - w[0][0]) * 100 if len(w) > 1 else None


rows = {}
for f in sorted(d.glob("windfield-*.json")):
    m = NAME.match(f.name)
    if not m:
        continue
    bs = samples(d / f"broker-proc-{m['tag']}-{m['stack']}.txt")
    es = samples(d / f"endpoint-proc-{m['tag']}-{m['stack']}.txt")
    for p in json.loads(f.read_text())["points"]:
        a, b = p.get("load_start_epoch"), p.get("load_end_epoch")
        p["broker_cpu"] = cpu(bs, a, b) if a else None
        p["endpoint_cpu"] = cpu(es, a, b) if a else None
        rows.setdefault((m["row"], p["twins"]), []).append(p)


def med(xs, fmt):
    xs = [x for x in xs if x is not None]
    return format(statistics.median(xs), fmt) if xs else "–"


def mx(xs, fmt):
    xs = [x for x in xs if x is not None]
    return format(max(xs), fmt) if xs else "–"


print("| row | twins | repeats | p50 ms | p99 ms | worst twin p99 ms | burst s p50 / max | update delay s p50 / max | probes / failed | broker CPU % | inference endpoint CPU % | break |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for (row, n), ps in sorted(rows.items()):
    br = "; ".join(sorted({p["break"][:70] for p in ps if p.get("break")})) or "–"
    print(f"| {row} | {n} | {len(ps)} | {med([p.get('p50_ms') for p in ps], '.1f')} | "
          f"{med([p.get('p99_ms') for p in ps], '.0f')} | {mx([p.get('worst_twin_p99_ms') for p in ps], '.0f')} | "
          f"{med([p.get('burst_makespan_s_p50') for p in ps], '.2f')} / {mx([p.get('burst_makespan_s_max') for p in ps], '.2f')} | "
          f"{med([p.get('update_delay_s_p50') for p in ps], '.2f')} / {mx([p.get('update_delay_s_max') for p in ps], '.2f')} | "
          f"{sum(p.get('probes') or 0 for p in ps)} / {sum(p.get('failed') or 0 for p in ps)} | "
          f"{med([p['broker_cpu'] for p in ps], '.0f')} | {med([p['endpoint_cpu'] for p in ps], '.0f')} | {br} |")
