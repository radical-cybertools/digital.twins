#!/usr/bin/env python3
"""Round 6 Y1b: pool the client-scaling runs (N sessions over P processes).

As r3/t4c_merge.py, for round 6's five-column /proc samples (epoch, RSS kB,
CPU ticks, threads, fds): per (N, P), aggregate req/s over the shared load
window, pooled p50 / p99, failures, late starts, the clients' CPU (sum and
maximum of each process's client_cpu_pct) and the broker's CPU, RSS,
threads and fds in that window.  Markdown to stdout.

    python experiments/dt-paper/r6/clients_table.py results/r6/clients PROCFILE
"""

import json
import re
import statistics
import sys

from pathlib import Path

NAME = re.compile(r"clients-n(\d+)-p(\d+)-k(\d+)-")


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def main() -> int:
    d = Path(sys.argv[1])
    proc = [tuple(map(float, l.split())) for l in open(sys.argv[2]) if len(l.split()) == 5]
    runs: dict = {}
    for f in sorted(d.glob("clients-n*-p*-k*-*.json")):
        n, p, k = map(int, NAME.match(f.name).groups())
        pts = json.loads(f.read_text())["points"]
        runs.setdefault((n, p), []).append(pts[0] if pts else {"n_create_errors": -1})
    print("| N | P | processes ok | req/s | p50 ms | p99 ms | failed | late | "
          "client CPU sum / max % | broker CPU % | RSS MB | threads | fds |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for (n, p), recs in sorted(runs.items()):
        ok = [r for r in recs if not r.get("n_create_errors") and "requests" in r]
        if not ok:
            print(f"| {n} | {p} | 0/{len(recs)} | " + " | ".join(["–"] * 10) + " |")
            continue
        lat = [x for r in ok for x in r["latencies_ms"]]
        t0 = min(r["load_start_epoch"] for r in ok)
        t1 = max(r["load_end_epoch"] for r in ok)
        rate = sum(r["requests"] for r in ok) / (t1 - t0)
        late = sum(1 for r in ok if r.get("late_s"))
        ccpu = [r["client_cpu_pct"] for r in ok if "client_cpu_pct" in r]
        win = [s for s in proc if t0 <= s[0] <= t1]
        cpu = ((win[-1][2] - win[0][2]) / 100 / (win[-1][0] - win[0][0]) * 100
               if len(win) > 1 else float("nan"))
        rss = max(s[1] for s in win) / 1024 if win else float("nan")
        thr = max(s[3] for s in win) if win else float("nan")
        fds = max(s[4] for s in win) if win else float("nan")
        cc = f"{sum(ccpu):.0f} / {max(ccpu):.0f}" if ccpu else "–"
        print(f"| {n} | {p} | {len(ok)}/{len(recs)} | {rate:.1f} | {statistics.median(lat):.1f} | "
              f"{pct(lat, 0.99):.1f} | {sum(r['failed'] for r in ok)} | {late} | {cc} | "
              f"{cpu:.0f} | {rss:.0f} | {thr:.0f} | {fds:.0f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
