"""Analyze path-2 (broadcast model update) runs: driver.json, pub.csv, stats-*.csv -> summary.json per run dir."""
import glob, json, os, statistics, sys

def q(xs, f):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(f * len(xs)))]

def one(out, skip=2.0):
    d = json.load(open(os.path.join(out, "driver.json")))
    lo, hi = d["base"] + int(skip * 1e9), d["t_end"] - int(0.5e9)
    pub = {}
    if os.path.exists(os.path.join(out, "pub.csv")):
        for l in open(os.path.join(out, "pub.csv")):
            _, v, tp, tr = l.strip().split(","); pub[int(v)] = (int(tp), int(tr))
    first, buckets, lat = {}, {}, []
    for f in glob.glob(os.path.join(out, "stats-*.csv")):
        for l in open(f):
            r = l.strip().split(",")
            if r[0] == "V":
                v, t = int(r[1]), int(r[2]); first[v] = min(first.get(v, t), t)
            elif r[0] == "B":
                b = int(r[1]); buckets[b] = buckets.get(b, 0) + int(r[2])
            elif r[0] == "L":
                ts, ta = int(r[3]), int(r[4])
                if lo <= ta < hi: lat.append((ta - ts) / 1e6)
    win = [buckets.get(b, 0) for b in range(lo // 100_000_000, hi // 100_000_000)]
    a = d["args"]
    # publish -> first answer carrying v (or newer: a version that is overtaken before any request sees it counts as unseen)
    p2a, r2a, seen = [], [], 0
    vs = sorted(v for v, (tp, _) in pub.items() if lo <= tp < hi) if a["upd"] > 0 else []
    for v in vs:
        tp, tr = pub[v]
        t = min((first[w] for w in first if w >= v), default=None)
        if v in first: seen += 1
        if t is not None:
            p2a.append((t - tp) / 1e6); r2a.append((t - tr) / 1e6)
    res = dict(upd=a["upd"], rate=a["rate"], p=a["p"], work_us=a["work_us"], seconds=len(win) / 10,
               req_per_s=sum(win) / (len(win) / 10), bucket_req_per_s_min=min(win) * 10, bucket_req_per_s_p50=statistics.median(win) * 10,
               lat_p50_ms=statistics.median(lat), lat_p90_ms=q(lat, .9), lat_p99_ms=q(lat, .99), lat_samples=len(lat),
               versions_published=len(vs), versions_seen_frac=(seen / len(vs)) if vs else None,
               pub_to_first_answer_p50_ms=statistics.median(p2a) if p2a else None,
               pub_to_first_answer_p90_ms=q(p2a, .9) if p2a else None,
               pub_to_first_answer_max_ms=max(p2a) if p2a else None,
               pub_to_operator_p50_ms=statistics.median([(tr - tp) / 1e6 for v, (tp, tr) in pub.items() if v in vs]) if vs else None,
               operator_to_first_answer_p50_ms=statistics.median(r2a) if r2a else None)
    json.dump(dict(provenance=dict(experiment="E4 Flink baseline path 2 (broadcast model update)", args=a), point=res),
              open(os.path.join(out, "summary.json"), "w"), indent=1)
    return res

if __name__ == "__main__":
    for o in sys.argv[1:]:
        r = one(o); print(os.path.basename(o), json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}))
