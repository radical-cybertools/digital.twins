#!/usr/bin/env python3
"""Round 7: E2 tables from r7/run_broker.sh results (round 6's r6/broker_table.py
plus the endpoint's /proc samples: CPU, RSS, threads; and S x T for Z3).

Per N: median over the repeats of sessions created, creation time (total
and per session), aggregate req/s, p50 and p99 (ms) and failed requests,
joined with the broker's /proc samples over each load window (CPU in % of
one core, RSS, threads, fds), plus keepalive ping timeouts per repeat.
Markdown to stdout.

    python experiments/dt-paper/r7/broker_table.py results/r7/notel [TAG]
"""

import glob
import json
import os
import re
import statistics
import sys

from pathlib import Path


def proc_samples(f):
    out = []
    for line in open(f):
        x = line.split()
        if len(x) == 5:
            out.append((float(x[0]), int(x[1]), int(x[2]), int(x[3]), int(x[4])))
    return out


def window(samples, a, b):
    w = [s for s in samples if a <= s[0] <= b]
    if len(w) < 2:
        return None
    cpu = (w[-1][2] - w[0][2]) / 100 / (w[-1][0] - w[0][0])    # ticks at 100 Hz
    return {"cpu": cpu * 100, "rss_mb": max(s[1] for s in w) / 1024,
            "threads": max(s[3] for s in w), "fds": max(s[4] for s in w)}


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def main() -> int:
    d = Path(sys.argv[1])
    tag = sys.argv[2] if len(sys.argv) > 2 else "stack-r7-20261113"
    rows, keep = {}, []
    for f in sorted(d.glob(f"broker-capacity-r*-{tag}.json")):
        rep = re.search(r"broker-capacity-(r\d+-\d+)-", f.name)[1]
        res = json.loads(f.read_text())
        pf = d / f"broker-proc-{rep}-{tag}.txt"
        samples = proc_samples(pf) if pf.exists() else []
        ef = d / f"endpoint-proc-{rep}-{tag}.txt"
        esamples = proc_samples(ef) if ef.exists() else []
        kf = d / f"keepalive-timeouts-{rep}.txt"
        keep.append((rep, kf.read_text().strip() if kf.exists() else "?",
                     res.get("stopped"), res["provenance"].get("ping_timeout")))
        for p in res["points"]:
            w = window(samples, p.get("load_start_epoch", 0), p.get("load_end_epoch", 0)) \
                if "load_start_epoch" in p else None
            e = window(esamples, p.get("load_start_epoch", 0), p.get("load_end_epoch", 0)) \
                if "load_start_epoch" in p else None
            key = (p["sessions"], p.get("twins_per_session", 1))
            rows.setdefault(key, []).append((p, w, e))
    print("| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | "
          "failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for key in sorted(rows):
        n, per = key
        ps = [p for p, _, _ in rows[key]]
        ws = [w for _, w, _ in rows[key] if w]
        es = [e for _, _, e in rows[key] if e]
        f = lambda v, fmt: "–" if v is None else format(v, fmt)
        nses = -(-n // per)
        print(f"| {n} | {per} | {nses} | {len(ps)} | {f(med([p['created'] for p in ps]), '.0f')} | "
              f"{f(med([p['create_s'] for p in ps]), '.1f')} | "
              f"{f(med([p['create_s'] / nses for p in ps]), '.3f')} | "
              f"{f(med([p.get('req_per_s') for p in ps]), '.1f')} | "
              f"{f(med([p.get('p50_ms') for p in ps]), '.1f')} | "
              f"{f(med([p.get('p99_ms') for p in ps]), '.1f')} | "
              f"{f(med([p.get('failed') for p in ps]), '.0f')} | "
              f"{f(med([w['cpu'] for w in ws]), '.0f')} | {f(med([w['rss_mb'] for w in ws]), '.0f')} | "
              f"{f(med([w['threads'] for w in ws]), '.0f')} | {f(med([w['fds'] for w in ws]), '.0f')} | "
              f"{f(med([e['cpu'] for e in es]), '.0f')} | {f(med([e['rss_mb'] for e in es]), '.0f')} | "
              f"{f(med([e['threads'] for e in es]), '.0f')} |")
    print("\nPer repeat: keepalive ping timeouts in the broker log, stop reason, "
          "RADICAL_ORBIT_PING_TIMEOUT\n")
    for rep, k, stopped, ping in keep:
        print(f"- {rep}: {k} timeouts, stopped: {stopped or 'no (all N ran)'}, "
              f"ping timeout {ping or 'default (3 s)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
