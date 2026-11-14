#!/usr/bin/env python3
"""Round 8, R8-E: latency breakdown per answer, PINN / FNO / PCR, cold vs warm model.

Reads results/r8/r8-e/warm<0|1>/twin-*.json (p8b_client probes with send /
receive epochs and the task's own times, "task") and timing-*/ (one jsonl
per process: select, simulate, train).  Client, broker and endpoint run on
one node, so the epochs share a clock.  Per variant and model, medians over
the probes of all repeats (ms):

  to task start   t_send -> task_start: client -> service, selector task,
                  inference dispatch (submit -> start)
  setup / extract / reload / field / cleanup   inside tk_*_eval
  in task         task_start -> task_end
  return          task_end -> t_recv
  total           t_recv - t_send

plus the selector task's own duration, training wall time per model, and
the selector's choices over time (share per arch in 4 time quarters).

    python r8/r8e_table.py results/r8/r8-e
"""
import glob
import json
import statistics
import sys
from pathlib import Path

base = Path(sys.argv[1])


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) * 1e3 if xs else None


def f(v):
    return "–" if v is None else f"{v:.1f}"


for var in ("warm0", "warm1"):
    d = base / var
    probes, runs = [], 0
    for j in sorted(d.glob("twin-*.json")):
        runs += 1
        probes += [p for p in json.loads(j.read_text())["probes"] if not p.get("error")]
    print(f"\n### {var} ({'warm model per worker' if var == 'warm1' else 'reload per call, as xGFabric'}): "
          f"{runs} runs, {len(probes)} answers\n")
    print("| model | n | total | to task start | in task | setup | extract | reload | field | cleanup | return | cached share |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arch in ("pinn", "fno", "pcr", "na"):
        ps = [p for p in probes if p.get("arch") == arch and p.get("task")]
        if not ps:
            continue
        t = [p["task"] for p in ps]
        row = [len(ps), med([p["t_recv"] - p["t_send"] for p in ps]),
               med([x["task_start"] - p["t_send"] for p, x in zip(ps, t)]),
               med([x["task_end"] - x["task_start"] for x in t])]
        for k in ("setup_s", "extract_s", "reload_s", "field_s", "cleanup_s"):
            row.append(med([x.get(k) for x in t]))
        row.append(med([p["t_recv"] - x["task_end"] for p, x in zip(ps, t)]))
        cached = [x.get("cached") for x in t if "cached" in x]
        share = f"{sum(1 for c in cached if c) / len(cached):.2f}" if cached else "–"
        print(f"| {arch} | {row[0]} | " + " | ".join(f(v) for v in row[1:]) + f" | {share} |")
    sel = []
    trains = {}
    for tdir in sorted(d.glob("timing-*")):
        for fn in tdir.glob("select-*.jsonl"):
            sel += [json.loads(l) for l in fn.read_text().splitlines() if l.strip()]
        for fn in tdir.glob("train-*.jsonl"):
            for l in fn.read_text().splitlines():
                if l.strip():
                    r = json.loads(l)
                    key = r.get("model") + (f":{r['step']}" if r.get("step") else "")
                    trains.setdefault(key, []).append(r["t1"] - r["t0"])
    if sel:
        print(f"\nselector task: n={len(sel)}, p50 {med([s['t1'] - s['t0'] for s in sel]):.2f} ms")
    for k, v in sorted(trains.items()):
        print(f"training {k}: n={len(v)}, p50 {statistics.median(v):.1f} s (min {min(v):.1f}, max {max(v):.1f})")
    arch_t = sorted((p["t"], p.get("arch")) for p in probes)
    if arch_t:
        end = arch_t[-1][0]
        qs = []
        for q in range(4):
            sub = [a for t, a in arch_t if q * end / 4 <= t < (q + 1) * end / 4 + (q == 3)]
            qs.append(", ".join(f"{a} {sub.count(a) / len(sub):.2f}" for a in ("na", "pinn", "fno", "pcr")
                                if sub and sub.count(a)))
        print("choices by time quarter: " + " | ".join(qs))
