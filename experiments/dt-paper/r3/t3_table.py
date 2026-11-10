#!/usr/bin/env python3
"""Round 3 T3: E1 rows incl. xgf, local pool 8 and ORBIT cross-node, solo.

Per layout x c x row: median over the repeats of the first burst, of the
median of bursts 2-5, and of the sequential p50; x bare per layout and c.

    python experiments/dt-paper/r3/t3_table.py results/r3/t3 [TAG]
"""

import json
import re
import statistics
import sys

from pathlib import Path

ROWS = ("bare", "investigator", "agent", "xgf")
NAME = re.compile(r"insitu-pm-(pool8|orbit-cross)-c(\d+)-solo-(\w+)-r\d+-")


def main() -> int:
    d = Path(sys.argv[1])
    tag = sys.argv[2] if len(sys.argv) > 2 else "stack-r3-20261110"
    data: dict = {}
    for f in sorted(d.glob(f"insitu-pm-*-{tag}.json")):
        m = NAME.match(f.name)
        if not m:
            continue
        lay, c, row = m.group(1), int(m.group(2)), m.group(3)
        r = json.loads(f.read_text())["rows"][row]
        rate = [r["concurrent"] / x for x in r.get("bursts_s", [r["concurrent_s"]])]
        data.setdefault((lay, c, row), []).append(
            (rate[0], statistics.median(rate[1:]) if len(rate) > 1 else rate[0],
             r["p50_ms"]))
    print("| layout | c | row | n | first burst req/s | x bare | bursts 2-5 req/s | x bare | seq p50 ms | x bare |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for lay in ("pool8", "orbit-cross"):
        for c in (1, 50, 500):
            base = data.get((lay, c, "bare"))
            if not base:
                continue
            med = lambda v, i: statistics.median(x[i] for x in v)  # noqa: E731
            for row in ROWS:
                v = data.get((lay, c, row))
                if not v:
                    continue
                print(f"| {lay} | {c} | {row} | {len(v)} | {med(v, 0):.0f} | {med(v, 0) / med(base, 0):.2f} | "
                      f"{med(v, 1):.0f} | {med(v, 1) / med(base, 1):.2f} | {med(v, 2):.2f} | "
                      f"{med(v, 2) / med(base, 2):.2f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
