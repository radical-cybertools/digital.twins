"""Aggregate a results dir into markdown tables (medians, [min-max] over swaps / repeats)."""
import glob, json, os, re, statistics, sys

R = sys.argv[1]
med = statistics.median
def rng(xs, f="{:.0f}"):
    return f"{f.format(med(xs))} [{f.format(min(xs))}-{f.format(max(xs))}]"

print("## Path 1: code swap (stop-with-savepoint + resubmit), p=1, 1000 req/s open loop\n")
print("| variant | swaps | lost | dup | stale | turnaround ms | p90 | gap ms | savepoint ms | submit call ms | requests delayed | max latency ms | catch-up ms |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
groups = {}
for d in sorted(glob.glob(os.path.join(R, "swap-*"))):
    groups.setdefault(re.sub(r"-r\d+$", "", os.path.basename(d)), []).append(json.load(open(os.path.join(d, "summary.json"))))
for g, ss in groups.items():
    per = [p for s in ss for p in s["per_swap"]]
    col = lambda k: [p[k] for p in per if p[k] is not None]
    ta = sorted(col("turnaround_ms"))
    print(f"| {g} ({len(ss)} runs) | {len(per)} | {sum(s['missing'] for s in ss)} | {sum(s['duplicates'] for s in ss)} | "
          f"{sum(s['stale_after_first'] for s in ss)} | {rng(ta)} | {ta[int(.9*len(ta))]:.0f} | {rng(col('gap_ms'))} | "
          f"{rng(col('savepoint_ms'))} | {rng(col('submit_call_ms'))} | {rng(col('delayed_requests'))} | "
          f"{rng(col('max_latency_ms'))} | {rng(col('catchup_ms'), '{:.1f}')} |")
    print(f"<!-- {g}: steady latency p50 {med([s['steady_latency']['p50_ms'] for s in ss]):.3f} ms, p99 {med([s['steady_latency']['p99_ms'] for s in ss]):.3f} ms; answers {sum(s['answers'] for s in ss)} -->")

print("\n## Path 2: model update via broadcast state\n")
pts = {}
for d in sorted(glob.glob(os.path.join(R, "bc-*"))):
    p = json.load(open(os.path.join(d, "summary.json")))["point"]
    series = re.sub(r"-u[\d.]+-r\d+$", "", os.path.basename(d))
    pts.setdefault(series, {}).setdefault(p["upd"], []).append(p)
for series, by_u in pts.items():
    print(f"\n### {series}\n")
    print("| models/s | runs | req/s | x rate 0 | latency p50 ms | p99 ms | versions seen | publish -> first answer p50 ms | p90 | max | publish -> operator p50 ms |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    base = med([p["req_per_s"] for p in by_u.get(0.0, [])]) if 0.0 in by_u else None
    for u in sorted(by_u):
        ps = by_u[u]
        rq = [p["req_per_s"] for p in ps]
        g = lambda k: [p[k] for p in ps if p[k] is not None]
        x = f"{med(rq)/base:.3f} [{min(rq)/base:.3f}-{max(rq)/base:.3f}]" if base else "-"
        fmt = "{:.0f}" if med(rq) > 100 else "{:.1f}"
        pf = lambda k, f="{:.3f}": rng(g(k), f) if g(k) else "-"
        print(f"| {u:g} | {len(ps)} | {rng(rq, fmt)} | {x} | {pf('lat_p50_ms')} | {pf('lat_p99_ms', '{:.1f}')} | "
              f"{pf('versions_seen_frac', '{:.2f}')} | {pf('pub_to_first_answer_p50_ms')} | {pf('pub_to_first_answer_p90_ms')} | "
              f"{pf('pub_to_first_answer_max_ms', '{:.1f}')} | {pf('pub_to_operator_p50_ms')} |")
