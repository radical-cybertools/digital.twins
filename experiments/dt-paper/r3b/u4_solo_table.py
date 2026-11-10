#!/usr/bin/env python3
"""Round 3b U4: solo rows at pools 1, 8, 64, c=500 (5 repeats, 5 bursts).

Per pool x row: median over the repeats of the first burst and of the
median of bursts 2-5 (req/s), seq p50 (ms), x bare per pool.

    python experiments/dt-paper/r3b/u4_solo_table.py results/r3b/u4 [TAG]
"""

import json
import re
import statistics
import sys

from pathlib import Path

ROWS = ("bare", "investigator", "agent")
NAME = re.compile(r"insitu-pm-pool(\d+)-c(\d+)-solo-(\w+)-r\d+-")


def main() -> int:
    d = Path(sys.argv[1])
    tag = sys.argv[2] if len(sys.argv) > 2 else "stack-r3b-20261110"
    data = {}
    for f in sorted(d.glob(f"insitu-pm-pool*-solo-*-{tag}.json")):
        m = NAME.match(f.name)
        pool, c, row = int(m[1]), int(m[2]), m[3]
        r = json.loads(f.read_text())["rows"][row]
        rate = [r["concurrent"] / x for x in r["bursts_s"]]
        data.setdefault((pool, c, row), []).append(
            (rate[0], statistics.median(rate[1:]), r["p50_ms"]))
    print("| pool | c | row | first burst | x bare | bursts 2-5 | x bare | seq p50 ms |")
    print("|---|---|---|---|---|---|---|---|")
    for pool, c in sorted({k[:2] for k in data}):
        base = data[(pool, c, "bare")]
        b1 = statistics.median(x[0] for x in base)
        b2 = statistics.median(x[1] for x in base)
        for row in ROWS:
            v = data.get((pool, c, row))
            if not v:
                continue
            m1 = statistics.median(x[0] for x in v)
            m2 = statistics.median(x[1] for x in v)
            p50 = statistics.median(x[2] for x in v)
            print(f"| {pool} | {c} | {row} | {m1:.0f} | {m1 / b1:.2f} | {m2:.0f} | "
                  f"{m2 / b2:.2f} | {p50:.2f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
