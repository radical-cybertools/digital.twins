#!/usr/bin/env python3
"""Round 4: E3 tables from bench_sites.py (dt) and xgf_sites.py (xgf) runs.

Per harness, layout, client concurrency and N: the median (min-max) over
the repeats of the bursts 2-5 throughput, the median sequential p50,
placement_ok in how many repeats, errors, and what a site costs in code
(dt: `code_per_site`; xgf: `wiring_lines`).  Markdown to stdout.

    python experiments/dt-paper/r4/e3_table.py results/r4/local [TAG [ROUND]]
"""

import json
import re
import statistics
import sys

from pathlib import Path

NAME = re.compile(r"^(sites|xgf)-(spread|one)(?:-c(\d+))?(?:-n[\d_]+)?-r(\d+)-")


def main() -> int:
    d = Path(sys.argv[1])
    tag = sys.argv[2] if len(sys.argv) > 2 else "stack-r4-20261111"
    rnd = sys.argv[3] if len(sys.argv) > 3 else "r4"  # round tag in the names
    cells, code, wiring = {}, {}, {}
    for f in sorted(d.glob(f"*-{rnd}-{tag}.json")):
        m = NAME.match(f.name)
        if not m:
            continue
        harness = "dt" if m[1] == "sites" else "xgf"
        conc = int(m[3]) if m[3] else json.loads(f.read_text())["provenance"]["args"].get("concurrent")
        data = json.loads(f.read_text())
        if "wiring_lines" in data:
            wiring[harness] = data["wiring_lines"]
        for p in data["points"]:
            key = (harness, m[2], conc, p["n"])
            cells.setdefault(key, []).append(p)
            if p.get("code_per_site") is not None:
                code.setdefault(key, p["code_per_site"])
    print("| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | "
          "placement ok | errors |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for key in sorted(cells, key=lambda k: (k[0], k[1] != "spread", k[2] or 0, k[3])):
        v = cells[key]
        rate = [p["req_per_s_bursts_2_5"] for p in v]
        base = cells.get(key[:3] + (1,))
        b = statistics.median(p["req_per_s_bursts_2_5"] for p in base) if base else float("nan")
        p50 = statistics.median(p["seq_p50_ms"] for p in v)
        ok = sum(bool(p["placement_ok"]) for p in v)
        err = sum(p.get("n_errors", 0) or 0 for p in v)
        print(f"| {key[0]} | {key[1]} | {key[2]} | {key[3]} | {len(v)} | "
              f"{statistics.median(rate):.1f} ({min(rate):.1f}-{max(rate):.1f}) | "
              f"{statistics.median(rate) / b:.2f} | {p50:.1f} | {ok}/{len(v)} | {err} |")
    if code or wiring:
        print("\nCode per site:\n")
        for key in sorted(code):
            print(f"- {key[0]} {key[1]} N={key[3]}: `{json.dumps(code[key])}`")
        for h, lines in sorted(wiring.items()):
            print(f"- {h}: wiring_lines {lines}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
