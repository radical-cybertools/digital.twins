#!/usr/bin/env python3
"""Round 3 T2: ex-situ msg/s and paced publish p50 per row and window.

Medians over the repeats, min-max in brackets, x bare per window.

    python experiments/dt-paper/r3/t2_table.py results/r3/t2 [TAG]
"""

import json
import statistics
import sys

from pathlib import Path


def main() -> int:
    d = Path(sys.argv[1])
    tag = sys.argv[2] if len(sys.argv) > 2 else "stack-r3-20261110"
    runs = [json.loads(f.read_text())
            for f in sorted(d.glob(f"exsitu-pm-pool8-r*-{tag}.json"))]
    sizes = runs[0]["batch_sizes"]
    rows = list(runs[0]["rows"])
    rate = {r: [[run["rows"][r]["msg_per_s"][i] for run in runs]
                for i in range(len(sizes))] for r in rows}
    pub = {r: [[run["rows"][r]["publish_latency"][i]["p50_ms"] for run in runs]
               for i in range(len(sizes))] for r in rows}
    print(f"{len(runs)} repeats\n")
    print("| window | " + " | ".join(f"{r} msg/s" for r in rows) + " | " +
          " | ".join(f"{r} x bare" for r in rows if r != "bare") + " |")
    print("|---" * (2 * len(rows)) + "|")
    for i, bs in enumerate(sizes):
        med = {r: statistics.median(rate[r][i]) for r in rows}
        cells = [f"{med[r]:.0f} ({min(rate[r][i]):.0f}-{max(rate[r][i]):.0f})" for r in rows]
        ratios = [f"{med[r] / med['bare']:.2f}" for r in rows if r != "bare"]
        print(f"| {bs} | " + " | ".join(cells + ratios) + " |")
    print("\n| window | " + " | ".join(f"{r} paced p50 ms" for r in rows) + " |")
    print("|---" * (len(rows) + 1) + "|")
    for i, bs in enumerate(sizes):
        print(f"| {bs} | " + " | ".join(f"{statistics.median(pub[r][i]):.2f}" for r in rows) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
