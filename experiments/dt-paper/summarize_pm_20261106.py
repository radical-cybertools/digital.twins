"""Tables for the 2026-11-06 Perlmutter batch (journal JOURNAL-pm-20261106.md).

Reads `results/p<N>/*.json` and prints markdown tables (median and min-max
over repeats) per phase; `--json` also writes `results/summary-pm-20261106.json`
for the plots on the handover page.

    python experiments/dt-paper/summarize_pm_20261106.py [p1 p2 ...] [--json]
"""

import glob
import json
import re
import statistics
import sys

from pathlib import Path

R = Path(__file__).resolve().parent / "results"
D = "20261106"
SUMMARY = {}


def load(pattern):
    out = []
    for f in sorted(glob.glob(str(R / pattern))):
        try:
            out.append((f, json.loads(Path(f).read_text())))
        except Exception as exc:
            print(f"skip {f}: {exc}", file=sys.stderr)
    return out


def mmm(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {"median": statistics.median(xs), "min": min(xs), "max": max(xs), "n": len(xs)}


def fmt(m, digits=0, scale=1.0):
    if not m:
        return "–"
    f = f"{{:,.{digits}f}}"
    return (f"{f.format(m['median'] * scale)} "
            f"({f.format(m['min'] * scale)}–{f.format(m['max'] * scale)})")


def p1():
    cells = {}
    for f, d in load(f"p1/insitu-pm-pool*-c*-r*-{D}.json"):
        m = re.search(r"pool(\d+)-c(\d+)-r(\d+)", f)
        w, c = int(m.group(1)), int(m.group(2))
        for row, v in d["rows"].items():
            cells.setdefault((w, c, row), []).append(v)
    rows = ["bare", "investigator", "agent"]
    out = {}
    for c in sorted({k[1] for k in cells}):
        print(f"\n### P1, c={c}: p50 ms and req/s, median (min–max) of repeats\n")
        print("| pool | " + " | ".join(f"{r} p50" for r in rows) + " | "
              + " | ".join(f"{r} req/s" for r in rows) + " |")
        print("|---" * (1 + 2 * len(rows)) + "|")
        for w in sorted({k[0] for k in cells if k[1] == c}):
            p50 = [mmm([v["p50_ms"] for v in cells.get((w, c, r), [])]) for r in rows]
            rps = [mmm([v["concurrent_req_per_s"] for v in cells.get((w, c, r), [])])
                   for r in rows]
            out[f"pool{w}-c{c}"] = {r: {"p50_ms": a, "req_per_s": b}
                                    for r, a, b in zip(rows, p50, rps)}
            print(f"| {w} | " + " | ".join(fmt(x, 2) for x in p50) + " | "
                  + " | ".join(fmt(x) for x in rps) + " |")
    SUMMARY["p1"] = out


def p2():
    cells = {}
    bs = None
    for f, d in load(f"p2/learner-engine-pool*-r*-{D}.json"):
        pool = re.search(r"pool(\w+?)-r", f).group(1)
        bs = d["batch_sizes"]
        for key in ("engine/inproc", "engine/zmq"):
            for b, rate in zip(bs, d[key]):
                cells.setdefault((pool, key, b), []).append(rate)
    out = {}
    pools = sorted({k[0] for k in cells}, key=lambda p: (p == "default", int(p) if p.isdigit() else 0))
    for key in ("engine/inproc", "engine/zmq"):
        print(f"\n### P2, {key}: msg/s, median (min–max) of 3 repeats\n")
        print("| pool | " + " | ".join(f"b={b}" for b in bs) + " |")
        print("|---" * (1 + len(bs)) + "|")
        for pool in pools:
            ms = [mmm(cells.get((pool, key, b), [])) for b in bs]
            out[f"{key}/pool{pool}"] = dict(zip(map(str, bs), ms))
            print(f"| {pool} | " + " | ".join(fmt(m) for m in ms) + " |")
    diag = {}
    for f, d in load(f"p2/diag-poll*-{D}.json"):
        m = re.search(r"diag-poll([\d.]+)-(learner|insitu)", f)
        poll, kind = m.group(1), m.group(2)
        if kind == "learner":
            diag.setdefault((poll, "learner"), []).append(d["engine/inproc"][-1])
            diag.setdefault((poll, "learner-zmq"), []).append(d["engine/zmq"][-1])
        else:
            for row, v in d["rows"].items():
                diag.setdefault((poll, row), []).append(v["p50_ms"])
                diag.setdefault((poll, row + "-rps"), []).append(v["concurrent_req_per_s"])
    if diag:
        print("\n### P2 diagnosis: asyncflow run-loop sleep patched at run time (2 repeats)\n")
        print("| sleep | learner engine/inproc b=100 msg/s | engine/zmq b=100 | "
              "bare p50 ms | investigator p50 | agent p50 | bare req/s c=50 | agent req/s |")
        print("|---|---|---|---|---|---|---|---|")
        for poll in ("0.01", "0.001", "0"):
            g = lambda k: mmm(diag.get((poll, k), []))  # noqa: E731
            print(f"| {poll} | {fmt(g('learner'))} | {fmt(g('learner-zmq'))} | "
                  f"{fmt(g('bare'), 2)} | {fmt(g('investigator'), 2)} | {fmt(g('agent'), 2)} | "
                  f"{fmt(g('bare-rps'))} | {fmt(g('agent-rps'))} |")
            out[f"diag-poll{poll}"] = {k: g(k) for k in ("learner", "learner-zmq", "bare",
                                                         "investigator", "agent",
                                                         "bare-rps", "agent-rps")}
    SUMMARY["p2"] = out


def p3():
    cells = {}
    bs = None
    for f, d in load(f"p3/exsitu-pm-pool8-r*-{D}.json"):
        bs = d["batch_sizes"]
        for row, v in d["rows"].items():
            for i, b in enumerate(bs):
                cells.setdefault((row, b, "rate"), []).append(v["msg_per_s"][i])
                cells.setdefault((row, b, "pub"), []).append(v["publish_latency"][i].get("p50_ms"))
    out = {}
    print("\n### P3: msg/s and paced publish latency p50 (ms), median (min–max) of 5 repeats\n")
    print("| batch | bare msg/s | dt msg/s | dt/bare | bare publish ms | dt publish ms |")
    print("|---|---|---|---|---|---|")
    for b in bs or []:
        br, dr = mmm(cells[("bare", b, "rate")]), mmm(cells[("dt", b, "rate")])
        bp, dp = mmm(cells[("bare", b, "pub")]), mmm(cells[("dt", b, "pub")])
        out[str(b)] = {"bare_rate": br, "dt_rate": dr, "bare_pub_ms": bp, "dt_pub_ms": dp}
        print(f"| {b} | {fmt(br)} | {fmt(dr)} | {dr['median'] / br['median']:.3f} | "
              f"{fmt(bp, 2)} | {fmt(dp, 2)} |")
    SUMMARY["p3"] = out


def p5():
    tw = {}
    for f, d in load(f"p5/twins-pm-pool64-r*-{D}.json"):
        for pt in d["points"]:
            tw.setdefault(pt["twins"], []).append(pt)
    out = {"twins": {}, "join": {}}
    print("\n### P5 E2a: N twins, pool 64, closed loop, median (min–max) of 3 repeats\n")
    print("| twins | aggregate req/s | per-twin p50 ms (median twin) | worst twin p50 | p99 (median twin) | worst twin p99 |")
    print("|---|---|---|---|---|---|")
    for n in sorted(tw):
        g = lambda k: mmm([pt[k] for pt in tw[n]])  # noqa: E731
        out["twins"][str(n)] = {k: g(k) for k in ("req_per_s", "p50_ms_median",
                                                  "p50_ms_max", "p99_ms_median", "p99_ms_max")}
        print(f"| {n} | {fmt(g('req_per_s'))} | {fmt(g('p50_ms_median'), 2)} | "
              f"{fmt(g('p50_ms_max'), 2)} | {fmt(g('p99_ms_median'), 2)} | {fmt(g('p99_ms_max'), 2)} |")
    js = {}
    pts = {}
    for f, d in load(f"p5/join-pm-r*-{D}.json"):
        for k, best in d["max_sustainable"].items():
            js.setdefault(int(k), []).append(best)
        for pt in d["points"]:
            pts.setdefault((pt["streams"], pt["rate_target"]), []).append(pt)
    print("\n### P5 E2b: K joined streams, max sustainable rate (p50 below 2x the 10/s base), 3 repeats\n")
    print("| K | rounds/s (per stream) | inputs/s | p50 ms at that rate | base p50 ms (10/s) |")
    print("|---|---|---|---|---|")
    for k in sorted(js):
        b = [x for x in js[k] if x]
        g = lambda key: mmm([x[key] for x in b])  # noqa: E731
        out["join"][str(k)] = {key: g(key) for key in ("rounds_per_s", "inputs_per_s",
                                                       "p50_ms", "base_p50_ms")}
        print(f"| {k} | {fmt(g('rounds_per_s'))} | {fmt(g('inputs_per_s'))} | "
              f"{fmt(g('p50_ms'), 2)} | {fmt(g('base_p50_ms'), 2)} |")
    print("\n### P5 E2b: p50 latency (ms) per K and rate, median of repeats\n")
    rates = sorted({r for _, r in pts})
    print("| K | " + " | ".join(f"{r:g}/s" for r in rates) + " |")
    print("|---" * (1 + len(rates)) + "|")
    out["join_grid"] = {}
    for k in sorted({k for k, _ in pts}):
        cells = []
        for r in rates:
            m = mmm([pt["p50_ms"] for pt in pts.get((k, r), [])])
            out["join_grid"][f"{k}@{r:g}"] = m
            cells.append(f"{m['median']:.2f}" if m else "–")
        print(f"| {k} | " + " | ".join(cells) + " |")
    SUMMARY["p5"] = out


if __name__ == "__main__":
    phases = [a for a in sys.argv[1:] if not a.startswith("--")] or ["p1", "p2", "p3"]
    for ph in phases:
        globals()[ph]()
    if "--json" in sys.argv:
        out = R / f"summary-pm-{D}.json"
        old = json.loads(out.read_text()) if out.exists() else {}
        old.update(SUMMARY)
        out.write_text(json.dumps(old, indent=2))
        print(f"\nwrote {out}")
