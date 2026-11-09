#!/usr/bin/env python3
"""Round 3 T1: tabulate the solo / in-process E1 runs through ORBIT.

Per row x c x mode: every repeat's first burst (the number rounds 2-2c
report), the median of bursts 2-5, and the sequential p50.  Ratios are
against the bare row of the same mode and c.  Markdown to stdout.

    python experiments/dt-paper/r3/t1_table.py results/r3/t1 [TAG]
"""

import json
import statistics
import sys

from pathlib import Path

ROWS = ("bare", "investigator", "agent")


def load(d: Path, tag: str):
    out = {}  # (mode, c, row) -> list of (first, rest-median, p50)
    for f in sorted(d.glob(f"insitu-pm-orbit-cross-c*-{tag}.json")):
        parts = f.name.split("-")
        c = int(parts[4][1:])
        mode = parts[5]
        rows = json.loads(f.read_text())["rows"]
        for row, r in rows.items():
            b = r.get("bursts_s", [r["concurrent_s"]])
            rate = [r["concurrent"] / x for x in b]
            rest = statistics.median(rate[1:]) if len(rate) > 1 else float("nan")
            out.setdefault((mode, c, row), []).append((rate[0], rest, r["p50_ms"]))
    return out


def main() -> int:
    d = Path(sys.argv[1])
    tag = sys.argv[2] if len(sys.argv) > 2 else "stack-r3-20261110"
    data = load(d, tag)
    print("| mode | c | row | first burst per repeat (req/s) | median first | x bare | "
          "median bursts 2-5 | x bare | seq p50 ms |")
    print("|---|---|---|---|---|---|---|---|---|")
    for mode in ("solo", "inproc"):
        for c in (50, 500):
            base = data.get((mode, c, "bare"))
            if not base:
                continue
            b1 = statistics.median(x[0] for x in base)
            b2 = statistics.median(x[1] for x in base)
            for row in ROWS:
                v = data.get((mode, c, row))
                if not v:
                    continue
                m1 = statistics.median(x[0] for x in v)
                m2 = statistics.median(x[1] for x in v)
                p50 = statistics.median(x[2] for x in v)
                firsts = " ".join(f"{x[0]:.0f}" for x in v)
                print(f"| {mode} | {c} | {row} | {firsts} | {m1:.0f} | {m1 / b1:.2f} | "
                      f"{m2:.0f} | {m2 / b2:.2f} | {p50:.2f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
