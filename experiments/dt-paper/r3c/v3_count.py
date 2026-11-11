#!/usr/bin/env python3
"""Round 3c V3: per setting (client GC / endpoint GC), the first bursts
below 600 req/s, all bursts below 600, and the median of bursts 2-5, per
row and in total.  Markdown.

    python experiments/dt-paper/r3c/v3_count.py results/r3c/v3 [TAG]
"""

import json
import re
import statistics
import sys

from pathlib import Path

NAME = re.compile(r"-solo-(\w+)-cgc(on|off)-egc(on|off)-r(\d+)-")
SLOW = 600


def main() -> int:
    d = Path(sys.argv[1])
    tag = sys.argv[2] if len(sys.argv) > 2 else "stack-r3c-20261111"
    data = {}  # (cgc, egc) -> row -> [rates per run]
    for f in sorted(d.glob(f"insitu-pm-orbit-cross-c50-solo-*-{tag}.json")):
        m = NAME.search(f.name)
        r = json.loads(f.read_text())["rows"][m[1]]
        rates = [r["concurrent"] / x for x in r["bursts_s"]]
        data.setdefault((m[2], m[3]), {}).setdefault(m[1], []).append((int(m[4]), rates))
    print(f"| client GC | endpoint GC | first bursts < {SLOW} | which (row r#: req/s) | "
          f"all bursts < {SLOW} | bursts 2-5 median req/s |")
    print("|---|---|---|---|---|---|")
    for key in (("on", "on"), ("off", "on"), ("on", "off"), ("off", "off")):
        rows = data.get(key, {})
        runs = [(row, k, rates) for row, v in rows.items() for k, rates in v]
        slow_first = [(row, k, rates[0]) for row, k, rates in runs if rates[0] < SLOW]
        slow_all = sum(x < SLOW for _, _, rates in runs for x in rates)
        n_all = sum(len(rates) for _, _, rates in runs)
        rest = statistics.median(x for _, _, rates in runs for x in rates[1:])
        which = ", ".join(f"{row} r{k}: {v:.0f}" for row, k, v in sorted(slow_first)) or "-"
        print(f"| {key[0]} | {key[1]} | {len(slow_first)} of {len(runs)} | {which} | "
              f"{slow_all} of {n_all} | {rest:.0f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
