#!/usr/bin/env python3
"""Round 3c V1 / V2: per pool, c and row, the median over the repeats of
the first burst and of the median of bursts 2-5 (req/s), x bare, and the
seq p50 (ms); with V2, V1 and V2 side by side at V2's pools.  Markdown.

    python experiments/dt-paper/r3c/v12_table.py results/r3c [TAG]
"""

import json
import re
import statistics
import sys

from pathlib import Path

ROWS = ("bare", "investigator", "agent")
NAME = re.compile(r"insitu-pm-pool(\d+)-c(\d+)-r\d+-")


def load(d: Path, tag: str):
    out = {}  # (pool, c, row) -> [(first, rest, p50)]
    for f in sorted(d.glob(f"insitu-pm-pool*-{tag}.json")):
        m = NAME.match(f.name)
        rows = json.loads(f.read_text())["rows"]
        for row, r in rows.items():
            rate = [r["concurrent"] / x for x in r["bursts_s"]]
            out.setdefault((int(m[1]), int(m[2]), row), []).append(
                (rate[0], statistics.median(rate[1:]), r["p50_ms"]))
    return out


def med(v, i):
    return statistics.median(x[i] for x in v)


def main() -> int:
    d = Path(sys.argv[1])
    tag = sys.argv[2] if len(sys.argv) > 2 else "stack-r3c-20261111"
    v1, v2 = load(d / "v1", tag), load(d / "v2", tag)
    print("V1: all rows in one process, 5 bursts per row, GC as it comes.\n")
    print("| pool | c | row | first burst | x bare | bursts 2-5 | x bare | seq p50 ms |")
    print("|---|---|---|---|---|---|---|---|")
    for pool, c in sorted({k[:2] for k in v1}):
        base = v1[(pool, c, "bare")]
        for row in ROWS:
            v = v1[(pool, c, row)]
            print(f"| {pool} | {c} | {row} | {med(v, 0):.0f} | {med(v, 0) / med(base, 0):.2f} | "
                  f"{med(v, 1):.0f} | {med(v, 1) / med(base, 1):.2f} | {med(v, 2):.2f} |")
    if v2:
        print("\nV1 vs V2 (client GC threshold raised), c=500.\n")
        print("| pool | row | V1 first | V2 first | V1 bursts 2-5 | V2 bursts 2-5 | "
              "V2 first x bare | V2 bursts 2-5 x bare |")
        print("|---|---|---|---|---|---|---|---|")
        for pool, c in sorted({k[:2] for k in v2}):
            base = v2[(pool, c, "bare")]
            for row in ROWS:
                a, b = v1[(pool, c, row)], v2[(pool, c, row)]
                print(f"| {pool} | {row} | {med(a, 0):.0f} | {med(b, 0):.0f} | {med(a, 1):.0f} | "
                      f"{med(b, 1):.0f} | {med(b, 0) / med(base, 0):.2f} | "
                      f"{med(b, 1) / med(base, 1):.2f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
