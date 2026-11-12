"""Analyze a path-1 (code swap) run: driver.json + ans-g*-*.csv -> per-swap metrics and summary JSON."""
import glob, json, os, statistics, sys

def q(xs, f):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(f * len(xs)))]

def summ(xs):
    return None if not xs else {"n": len(xs), "p50_ms": statistics.median(xs), "p90_ms": q(xs, .9),
                                "min_ms": min(xs), "max_ms": max(xs)}

out = sys.argv[1]
drv = json.load(open(os.path.join(out, "driver.json")))
by_gen = {}
for f in glob.glob(os.path.join(out, "ans-g*-*.csv")):
    for line in open(f):
        _, seq, gen, ver, ts, ta = line.strip().split(",")
        by_gen.setdefault(int(gen), []).append((int(seq), int(ver), int(ts), int(ta)))
for g in by_gen.values():
    g.sort(key=lambda r: r[3])
allseq = sorted(s for g in by_gen.values() for s, *_ in g)
dups = sum(1 for a, b in zip(allseq, allseq[1:]) if a == b)
missing = (allseq[-1] - allseq[0] + 1) - len(set(allseq))
per = []
steady = []
for i, s in enumerate(drv["swaps"]):
    k = s["gen"]; old, new = by_gen[k - 1], by_gen[k]
    first_new = new[0][3]; last_old = old[-1][3]
    t_req = s["t_req"]
    # baseline latency of the old job in the second before the request
    base = [(ta - ts) / 1e6 for _, _, ts, ta in old if t_req - 1e9 <= ta < t_req]
    steady += base
    p99 = q(base, .99)
    delayed = [r for r in new if r[2] <= first_new]          # requests that arrived before v_k answered
    late = [(ta - ts) / 1e6 for _, _, ts, ta in new]
    rec_t = next(((ta - first_new) / 1e6 for _, _, ts, ta in new if ts > first_new and (ta - ts) / 1e6 <= max(2 * p99, 1.0)), None)
    per.append(dict(gen=k, ver=s["ver"],
                    turnaround_ms=(first_new - t_req) / 1e6,
                    savepoint_ms=(s["t_savepoint"] - t_req) / 1e6,
                    submit_call_ms=(s["t_submit_returned"] - s["t_submit"]) / 1e6,
                    running_seen_ms=(s["t_running"] - t_req) / 1e6,
                    gap_ms=(first_new - last_old) / 1e6,
                    last_old_after_req_ms=(last_old - t_req) / 1e6,
                    delayed_requests=len(delayed), max_latency_ms=max(late),
                    catchup_ms=rec_t,
                    stale_after_first=sum(1 for r in old if r[3] > first_new),
                    first_new_ver=new[0][1]))
res = {"provenance": {"experiment": "E4 hot-swap, Flink baseline path 1 (stop-with-savepoint + resubmit)",
                      "harness": "driver.py swap + analyze_swap.py", "args": drv["args"]},
       "swaps": len(per), "answers": len(allseq), "duplicates": dups, "missing": missing,
       "versions_ok": all(p["first_new_ver"] == p["ver"] for p in per),
       "stale_after_first": sum(p["stale_after_first"] for p in per)}
for key in ("turnaround_ms", "savepoint_ms", "submit_call_ms", "running_seen_ms", "gap_ms", "max_latency_ms", "catchup_ms", "delayed_requests"):
    res[key.replace("_ms", "")] = summ([p[key] for p in per if p[key] is not None])
res["steady_latency"] = {"p50_ms": statistics.median(steady), "p99_ms": q(steady, .99)}
res["per_swap"] = per
json.dump(res, open(os.path.join(out, "summary.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k not in ("per_swap", "provenance")}, indent=1))
