#!/usr/bin/env python3
"""Round 8b, B2: tables from r8b/bench_windfield_stream.py results.

Per N and repeat: the probe (1 Hz get_inference) and the stream path
(reading published -> the agent's answer at the Sink): p50 / p99 (linear
interpolation) / max and the worst twin's p99 (stream); streamed answers
against those expected; the investigators' burst period, makespan and the
update delay; broker and inference-endpoint CPU (% of one core) over the
load window from broker-proc-* / endpoint-proc-*.  Markdown.

    python r8b/b2_table.py results/r8b/b2
"""
import json
import re
import sys
from pathlib import Path

d = Path(sys.argv[1])
NAME = re.compile(r"windfield-(?P<row>[a-z0-9]+)-(?P<tag>r\d+-\d+)-(?P<stamp>.+)\.json")


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


def f0(v, n=0):
    return "–" if v is None else f"{v:,.{n}f}"


rows = []
for f in sorted(d.glob("windfield-*.json")):
    m = NAME.match(f.name)
    if not m:
        continue
    bs = samples(d / f"broker-proc-{m['tag']}-{m['stamp']}.txt")
    es = samples(d / f"endpoint-proc-{m['tag']}-{m['stamp']}.txt")
    for p in json.loads(f.read_text())["points"]:
        a, b = p.get("load_start_epoch"), p.get("load_end_epoch")
        pr = p.get("probe") or {}
        rows.append((p["twins"], m["tag"].split("-")[0], p, pr,
                     cpu(bs, a, b) if a else None, cpu(es, a, b) if a else None))
rows.sort(key=lambda r: (r[0], r[1]))
print("| twins | rep | probe p50 / p99 / max ms | stream p50 / p99 / max ms | worst twin p99 ms (stream) "
      "| stream answers | burst period s | burst makespan s | update delay p50 / max s | broker CPU % "
      "| endpoint CPU % | break |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for n, rep, p, pr, bc, ec in rows:
    print(f"| {n} | {rep} | {f0(pr.get('p50_ms'))} / {f0(pr.get('p99_ms'))} / {f0(pr.get('max_ms'))} "
          f"| {f0(p.get('p50_ms'))} / {f0(p.get('p99_ms'))} / {f0(p.get('max_ms'))} "
          f"| {f0(p.get('worst_twin_p99_ms'))} | {p.get('stream_answers')} of {f0(p.get('stream_expected'))} "
          f"| {f0(p.get('burst_period_s_p50'), 1)} | {f0(p.get('burst_makespan_s_p50'), 2)} "
          f"| {f0(p.get('update_delay_s_p50'), 2)} / {f0(p.get('update_delay_s_max'), 2)} "
          f"| {f0(bc)} | {f0(ec)} | {p.get('break') or '–'} |")
