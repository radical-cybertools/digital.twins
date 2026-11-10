#!/usr/bin/env python3
"""Round 3 T4 / T5: summary tables, medians over repeats (min-max).

    python experiments/dt-paper/r3/t45_tables.py results/r3 [TAG]
"""

import json
import statistics
import sys

from pathlib import Path


def load(d: Path, pattern: str):
    return [json.loads(f.read_text()) for f in sorted(d.glob(pattern))]


def mm(xs, fmt="{:.0f}"):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "-"
    return (fmt.format(statistics.median(xs)) + " (" + fmt.format(min(xs)) + "-"
            + fmt.format(max(xs)) + ")")


def main() -> int:
    d = Path(sys.argv[1])
    tag = sys.argv[2] if len(sys.argv) > 2 else "stack-r3-20261110"
    t4, t5 = d / "t4", d / "t5"

    runs = load(t4, f"twins-pm-pool64-r*-{tag}.json")
    if runs:
        print(f"## E2a twins, pool 64 ({len(runs)} repeats)\n")
        print("| twins | req/s | p50 ms (median twin) |\n|---|---|---|")
        for i, p in enumerate(runs[0]["points"]):
            print(f"| {p['twins']} | {mm([r['points'][i]['req_per_s'] for r in runs])} | "
                  f"{mm([r['points'][i]['p50_ms_median'] for r in runs], '{:.2f}')} |")

    runs = load(t4, f"join-pm-r*-{tag}.json")
    if runs:
        print(f"\n## E2b joined streams ({len(runs)} repeats)\n")
        print("| streams | max sustainable inputs/s | p50 ms there |\n|---|---|---|")
        for k in sorted(runs[0]["max_sustainable"], key=int):
            ms = [r["max_sustainable"][k] for r in runs]
            print(f"| {k} | {mm([m and m['inputs_per_s'] for m in ms])} | "
                  f"{mm([m and m['p50_ms'] for m in ms], '{:.2f}')} |")

    runs = load(t4, f"agents-pm-r*-{tag}.json")
    if runs:
        print(f"\n## E2 agents per twin ({len(runs)} repeats)\n")
        print("| mode | agents | max sustainable inputs/s | p50 ms there | base p50 ms (10/s) |\n"
              "|---|---|---|---|---|")
        for key in runs[0]["max_sustainable"]:
            ms = [r["max_sustainable"].get(key) for r in runs]
            mode, m = key.rsplit("-", 1)
            print(f"| {mode} | {m} | {mm([x and x['inputs_per_s'] for x in ms])} | "
                  f"{mm([x and x['p50_ms'] for x in ms], '{:.2f}')} | "
                  f"{mm([x and x['base_p50_ms'] for x in ms], '{:.2f}')} |")

    for title, sub, pat in (
            ("E2 publish, inference c=1, pool 8", t4, "publish-pm-pool8-c1-r*"),
            ("E4 dip, inference c=50, pool 8", t5, "dip-pm-pool8-c50-r*")):
        runs = load(sub, f"{pat}-{tag}.json")
        if not runs:
            continue
        print(f"\n## {title} ({len(runs)} repeats)\n")
        print("| publish rate | models published/s | models seen/s | req/s | x rate 0 | "
              "p50 ms | x rate 0 |\n|---|---|---|---|---|---|---|")
        for i, p in enumerate(runs[0]["points"]):
            col = lambda k: [r["points"][i][k] for r in runs]  # noqa: E731
            print(f"| {p['rate_target']} | {mm(col('models_published_per_s'))} | "
                  f"{mm(col('models_seen_per_s'))} | {mm(col('req_per_s'))} | "
                  f"{mm(col('req_per_s_x_rate0'), '{:.2f}')} | {mm(col('p50_ms'), '{:.2f}')} | "
                  f"{mm(col('p50_x_rate0'), '{:.2f}')} |")

    rows = []
    for lay in ("pool8", "orbit-cross"):
        for c in (1, 50):
            runs = load(t5, f"swap-pm-{lay}-c{c}-r*-{tag}.json")
            if runs:
                rows.append((lay, c, runs))
    if rows:
        print("\n## E4 hot-swap turnaround (20 swaps per run)\n")
        print("| layout | c | runs | swaps missed | turnaround p50 ms | p90 ms | max ms | "
              "stale answers |\n|---|---|---|---|---|---|---|---|")
        for lay, c, runs in rows:
            print(f"| {lay} | {c} | {len(runs)} | {sum(r['missed'] for r in runs)} | "
                  f"{mm([r['turnaround']['p50_ms'] for r in runs], '{:.2f}')} | "
                  f"{mm([r['turnaround']['p90_ms'] for r in runs], '{:.2f}')} | "
                  f"{mm([r['turnaround']['max_ms'] for r in runs], '{:.2f}')} | "
                  f"{sum(r['stale_after_first'] for r in runs)} |")

    for lay in ("local-pool8", "orbit-cross"):
        runs = load(t5, f"update-pm-{lay}-r*-{tag}.json")
        if not runs:
            continue
        print(f"\n## E4 model-update propagation, {lay} ({len(runs)} repeats)\n")
        print("| interval s | versions seen | answered p50 ms | inference p50 ms |\n"
              "|---|---|---|---|")
        for i, p in enumerate(runs[0]["points"]):
            pts = [r["points"][i] for r in runs]
            print(f"| {p['interval_s']} | {mm([x['versions_seen'] / x['versions'] * 100 for x in pts], '{:.0f}%')} | "
                  f"{mm([x['answered']['p50_ms'] for x in pts], '{:.2f}')} | "
                  f"{mm([x['inference']['p50_ms'] for x in pts], '{:.2f}')} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
