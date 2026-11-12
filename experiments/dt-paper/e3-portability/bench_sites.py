#!/usr/bin/env python3
"""E3: the same twin on 1 to N sites, run as a service.

One twin in the broker's `dt` service: a `SiteAgent` (`e3_components.py`)
with N investigators.  With `--layout spread` investigator k runs on site
k: the session configures one engine per site (`inference` on the first,
`site_1` ... on the others, named engines #62) and the agent's package gets
the site names, which its investigators put on their inference tasks as
`backend=` labels.  With `--layout one` every investigator runs on the
first site.  The agent round-robins requests over the investigators; each
request is one task holding a site's GIL for `--work-ms`, so a site serves
about `1000 / work_ms` requests per second.

Per N (`--n`, e.g. 1,2,3,4): sequential p50 (`--seq` requests), then
`--bursts` bursts of `--tasks` requests from `--concurrent` client threads;
throughput is the median of bursts 2-5 (the first warms up).  Every answer
names the endpoint its task ran on, so the JSON records per investigator
where it ran, and `placement_ok` says whether that is where it was placed.
`code_per_site` records what a user adds per site: one engine config entry
and one entry in the agent's `sites` list.

    python bench_sites.py --broker URL --endpoints ep0,ep1,ep2,ep3 \\
        --n 1,2,3,4 --layout spread --out sites-spread.json

Endpoints must tag their tasks: start each with
`DT_TEST_ENDPOINT_TAG=<its name>` (the run scripts do).
"""

import argparse
import json
import os
import platform
import queue
import socket
import statistics
import subprocess
import sys
import threading
import time
import uuid

from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import e3_components  # noqa: E402

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import TypedData  # noqa: E402
from digitaltwin.service import register_user_modules  # noqa: E402

register_user_modules([e3_components])

BACKENDS = ["concurrent"]


def provenance(args) -> dict:
    root = HERE.parents[2]

    def git(*cmd):
        try:
            return subprocess.check_output(
                ["git", "-C", str(root), *cmd], text=True
            ).strip()
        except Exception:
            return None

    return {
        "experiment": "E3 portability: one twin on N sites",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git("rev-parse", "HEAD"),
        "digital_twins_dirty": bool(git("status", "--porcelain", "--", "src")),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args),
    }


def layout(endpoints, n, mode):
    """Engine config and the agent's `sites` list for N investigators."""

    if mode == "spread":
        names = ["inference"] + [f"site_{k}" for k in range(1, n)]
        engines = {
            name: {"endpoint_name": endpoints[k], "backends": BACKENDS}
            for k, name in enumerate(names)
        }
        sites = [None] + names[1:]  # None: the default engine (`inference`)
        expected = endpoints[:n]
    else:
        engines = {"inference": {"endpoint_name": endpoints[0], "backends": BACKENDS}}
        sites = [None] * n
        expected = [endpoints[0]] * n
    return engines, sites, expected


def code_per_site(engines, sites, n):
    """What a user adds to go from n-1 to n sites (spread layout)."""

    if n < 2:
        return None
    name = sites[n - 1]
    return {
        "engine_config_entry": {name: engines[name]},
        "agent_sites_entry": name,
        "lines": 2,  # one config entry, one list element; no other code
    }


def build_twin(dt, sites, work_ms, work="wall"):
    twin = str(uuid.uuid4())
    dt.create_twin(twin)
    dt.add_agent(
        twin,
        dt.package(e3_components.SiteAgent, sites=sites, work_ms=work_ms, work=work),
        e3_components.IN,
        e3_components.OUT,
    )
    dt.start(twin)
    return twin


def call(dt, twin, i, timeout):
    answer = dt.get_inference(
        twin, TypedData(e3_components.IN, i), e3_components.OUT, timeout=timeout
    )
    return answer.data


def burst(handles, twin, tasks, timeout, placed):
    """`tasks` requests from len(handles) threads, one client handle each."""

    todo = queue.Queue()
    for i in range(tasks):
        todo.put(i)
    errors = []

    def worker(dt):
        while True:
            try:
                i = todo.get_nowait()
            except queue.Empty:
                return
            try:
                a = call(dt, twin, i, timeout)
                placed.append((a["inv"], a["site"]))
            except Exception as exc:  # reported, not raised
                errors.append(f"{type(exc).__name__}: {exc}"[:200])

    threads = [threading.Thread(target=worker, args=(dt,)) for dt in handles]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return time.perf_counter() - t0, errors


def one_n(runtime, args, n):
    engines, sites, expected = layout(args.endpoints, n, args.layout)
    cfg = {"engines": engines}
    t0 = time.time()
    dt = runtime.get_plugin("broker", "dt", config=cfg)
    twin = build_twin(dt, sites, args.work_ms, args.work)
    placed = []
    for i in range(3 * n):  # warm-up: every investigator a few times
        a = call(dt, twin, i, args.timeout)
        placed.append((a["inv"], a["site"]))
    ready_s = time.time() - t0

    seq = []
    for i in range(args.seq):
        t1 = time.perf_counter()
        a = call(dt, twin, i, args.timeout)
        seq.append(time.perf_counter() - t1)
        placed.append((a["inv"], a["site"]))

    handles = [dt] + [
        runtime.get_plugin("broker", "dt", sid=dt.sid)
        for _ in range(args.concurrent - 1)
    ]
    bursts, errors = [], []
    for _ in range(args.bursts):
        dur, errs = burst(handles, twin, args.tasks, args.timeout, placed)
        bursts.append(dur)
        errors.extend(errs)

    ran = {}
    for inv, site in placed:
        ran.setdefault(str(inv), {}).setdefault(site, 0)
        ran[str(inv)][site] += 1
    placement_ok = all(
        set(ran.get(str(k), {})) == {expected[k]} for k in range(n)
    )
    rates = [args.tasks / b for b in bursts]
    rec = {
        "n": n,
        "layout": args.layout,
        "engines": engines,
        "sites": sites,
        "expected_endpoint": expected,
        "ran_on": ran,
        "placement_ok": placement_ok,
        "ready_s": ready_s,
        "seq_p50_ms": statistics.median(seq) * 1e3 if seq else None,
        "bursts_s": bursts,
        "req_per_s_bursts_2_5": statistics.median(rates[1:]) if len(rates) > 1 else rates[0],
        "req_per_s_first": rates[0],
        "errors": errors[:20],
        "n_errors": len(errors),
        "code_per_site": code_per_site(engines, sites, n)
        if args.layout == "spread" else None,
    }
    try:
        dt.twin_close(twin)
        dt.unregister_session()
    except Exception as exc:
        rec["teardown"] = str(exc)[:200]
    return rec


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoints", required=True,
                   help="comma-separated endpoint names, site 0 first")
    p.add_argument("--n", default="1,2,3,4", help="investigator / site counts")
    p.add_argument("--layout", choices=["spread", "one"], default="spread")
    p.add_argument("--work-ms", type=float, default=50.0)
    p.add_argument("--work", choices=["wall", "cpu"], default="wall",
                   help="wall: wall-clock busy loop; cpu: thread CPU time (round 5)")
    p.add_argument("--seq", type=int, default=20)
    p.add_argument("--tasks", type=int, default=200, help="requests per burst")
    p.add_argument("--concurrent", type=int, default=16, help="client threads")
    p.add_argument("--bursts", type=int, default=5)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    args.endpoints = [e for e in args.endpoints.split(",") if e]
    ns = [int(x) for x in args.n.split(",") if x]
    if args.layout == "spread" and max(ns) > len(args.endpoints):
        p.error(f"spread needs {max(ns)} endpoints, got {len(args.endpoints)}")

    res = {"provenance": provenance(args), "work_model": args.work, "points": []}
    runtime = EndpointRuntime(broker_url=args.broker)
    runtime.start(wait=True)
    try:
        for n in ns:
            try:
                rec = one_n(runtime, args, n)
            except Exception as exc:
                rec = {"n": n, "layout": args.layout,
                       "error": f"{type(exc).__name__}: {exc}"[:500]}
            res["points"].append(rec)
            Path(args.out).write_text(json.dumps(res, indent=2))
            print(
                f"{args.layout} n={n}: "
                + (rec["error"] if "error" in rec else
                   f"seq p50 {rec['seq_p50_ms']:.1f} ms, "
                   f"bursts 2-5 {rec['req_per_s_bursts_2_5']:.1f} req/s, "
                   f"placement {'ok' if rec['placement_ok'] else 'WRONG'} "
                   f"{rec['ran_on']}, errors {rec['n_errors']}"),
                flush=True,
            )
    finally:
        runtime.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
