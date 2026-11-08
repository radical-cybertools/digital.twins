#!/usr/bin/env python3
"""Round 2c: compare E1 in-situ results of two rounds, per layout, c and row.

For each `insitu-pm-<layout>-c<C>-r<K>-<D>.json` in two result directories:
the median (min-max over repeats) of the sequential p50 and of the burst
req/s, round A vs round B, and the change of the medians.

    python experiments/dt-paper/s1/compare_insitu.py \\
        results/s1/p4 stack-20261107 results/c3/p4 stack2c-20261108
"""

import json
import re
import statistics
import sys

from collections import defaultdict
from pathlib import Path

ROWS = ("bare", "investigator", "agent")
PAT = re.compile(r"insitu-pm-(?P<layout>.+)-c(?P<c>\d+)-r(?P<k>\d+)-(?P<d>.+)\.json$")


def load(directory, tag):
    out = defaultdict(list)  # (layout, c, row) -> [(p50, req/s)]
    for f in sorted(Path(directory).glob(f"insitu-pm-*-{tag}.json")):
        m = PAT.match(f.name)
        if not m or m["d"] != tag:
            continue
        rows = json.loads(f.read_text())["rows"]
        for row in ROWS:
            if row in rows:
                r = rows[row]
                out[(m["layout"], int(m["c"]), row)].append(
                    (r["p50_ms"], r["concurrent_req_per_s"]))
    return out


def fmt(xs, digits):
    return (f"{statistics.median(xs):.{digits}f} ({min(xs):.{digits}f}-{max(xs):.{digits}f})"
            if xs else "-")


def main() -> int:
    da, ta, db, tb = sys.argv[1:5]
    a, b = load(da, ta), load(db, tb)
    print("| layout | c | row | p50 ms A | p50 ms B | change | req/s A | req/s B | change |")
    print("|---|---|---|---|---|---|---|---|---|")
    for key in sorted(set(a) | set(b)):
        pa, ra = [x[0] for x in a.get(key, [])], [x[1] for x in a.get(key, [])]
        pb, rb = [x[0] for x in b.get(key, [])], [x[1] for x in b.get(key, [])]
        dp = (f"{statistics.median(pb) - statistics.median(pa):+.2f}" if pa and pb else "-")
        dr = (f"{(statistics.median(rb) / statistics.median(ra) - 1) * 100:+.0f}%"
              if ra and rb else "-")
        print(f"| {key[0]} | {key[1]} | {key[2]} | {fmt(pa, 2)} | {fmt(pb, 2)} | {dp} | "
              f"{fmt(ra, 0)} | {fmt(rb, 0)} | {dr} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
