#!/usr/bin/env python3
"""E3 baseline: the same N-site layout, wired by hand the xGFabric way.

No DT framework.  The structure follows the `xgf` row of
`e1-overhead/bench_dt_insitu.py` (pre-DT xGFabric, `devel`:
`service/src/xgfabric/service/service.py`, a ZMQ request/reply service, one
reading per request, one task per reading), extended to N sites the way a
hand-wired deployment would do it: one asyncflow engine with one ORBIT
backend per site endpoint, one task per site labelled with that backend, and
a hand-written dispatcher in the service that sends request i to site
i mod N.  The client sends requests over ZMQ DEALER -> ROUTER on loopback.

Same work per request as `bench_sites.py` (a GIL-holding busy loop of
`--work-ms` on the site), same metrics: sequential p50, `--bursts` bursts of
`--tasks` requests at `--concurrent` in flight, median of bursts 2-5, and
where every request ran.  `code_per_site` records what a user changes per
added site here: the `SITES` entry; `wiring_lines` the lines of wiring
code a user owns at all (the block between the WIRING markers below, which
the DT service provides).

    python xgf_sites.py --broker URL --endpoints ep0,ep1,ep2,ep3 \\
        --n 1,2,3,4 --layout spread --out xgf-spread.json
"""

import argparse
import asyncio
import itertools
import json
import statistics
import sys
import time

from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bench_sites import provenance  # noqa: E402  (same provenance block)


# ---- WIRING begin: what a hand-wired N-site deployment owns -------------
async def wire(broker, sites, work_ms, work_model="wall"):
    """Engine, one backend and one task per site, a ZMQ service with a
    round-robin dispatcher, and a client.  `sites`: endpoint per site."""

    import zmq
    import zmq.asyncio

    from radical.asyncflow import WorkflowEngine  # type: ignore
    from rhapsody.backends.execution.orbit import OrbitExecutionBackend  # type: ignore

    names = sorted(set(sites), key=sites.index)
    backends = [
        await OrbitExecutionBackend(broker_url=broker, endpoint_name=ep,
                                    backends=["concurrent"], batch_window=0,
                                    name=f"site_{k}")
        for k, ep in enumerate(names)
    ]
    flow = await WorkflowEngine.create(backend=backends)
    tasks = []
    for k, ep in enumerate(sites):
        label = f"site_{names.index(ep)}"

        @flow.function_task(backend=label)
        async def work(value, inv=k, work_ms=work_ms, model=work_model):
            import os
            import socket
            import time

            # wall / cpu as in e3_components.SiteInvestigator (round 5); one
            # line, so wiring_lines stays as in round 4.  Not `work=`: in this
            # loop `work` names the previous site's task from k=1 on
            end = (clock := time.thread_time if model == "cpu" else time.perf_counter)() + work_ms / 1000.0
            while clock() < end:
                pass
            return {"site": os.environ.get("DT_TEST_ENDPOINT_TAG")
                    or socket.gethostname(), "inv": inv, "v": value}

        tasks.append(work)

    ctx = zmq.asyncio.Context()
    srv = ctx.socket(zmq.ROUTER)
    port = srv.bind_to_random_port("tcp://127.0.0.1")
    cli = ctx.socket(zmq.DEALER)
    cli.connect(f"tcp://127.0.0.1:{port}")
    turn = itertools.count()
    handlers, waiting, rids = set(), {}, itertools.count()

    async def handle(ident, rid, body):
        task = tasks[next(turn) % len(tasks)]  # the dispatcher
        answer = await task(json.loads(body))
        await srv.send_multipart([ident, rid, json.dumps(answer).encode()])

    async def serve():
        while True:
            ident, rid, body = await srv.recv_multipart()
            h = asyncio.create_task(handle(ident, rid, body))
            handlers.add(h)
            h.add_done_callback(handlers.discard)

    async def receive():
        while True:
            rid, body = await cli.recv_multipart()
            waiting.pop(rid).set_result(json.loads(body))

    async def call(i):
        rid = str(next(rids)).encode()
        fut = waiting[rid] = asyncio.get_running_loop().create_future()
        await cli.send_multipart([rid, json.dumps(i).encode()])
        return await fut

    loops = [asyncio.create_task(serve()), asyncio.create_task(receive())]

    async def close():
        for t in loops + list(handlers):
            t.cancel()
        await asyncio.gather(*loops, *handlers, return_exceptions=True)
        cli.close(0)
        srv.close(0)
        ctx.term()
        await flow.shutdown()

    return call, close
# ---- WIRING end ----------------------------------------------------------


def wiring_lines():
    text = Path(__file__).read_text().splitlines()
    a = next(i for i, l in enumerate(text) if l.startswith("# ---- WIRING begin"))
    b = next(i for i, l in enumerate(text) if l.startswith("# ---- WIRING end"))
    return sum(1 for l in text[a + 1:b] if l.strip() and not l.strip().startswith("#"))


async def one_n(args, n):
    sites = args.endpoints[:n] if args.layout == "spread" else [args.endpoints[0]] * n
    t0 = time.time()
    call, close = await wire(args.broker, sites, args.work_ms, args.work)
    placed = []
    try:
        for i in range(3 * n):
            a = await call(i)
            placed.append((a["inv"], a["site"]))
        ready_s = time.time() - t0
        seq = []
        for i in range(args.seq):
            t1 = time.perf_counter()
            a = await call(i)
            seq.append(time.perf_counter() - t1)
            placed.append((a["inv"], a["site"]))
        bursts = []
        sem = asyncio.Semaphore(args.concurrent)

        async def one(i):
            async with sem:
                a = await call(i)
                placed.append((a["inv"], a["site"]))

        for _ in range(args.bursts):
            t1 = time.perf_counter()
            await asyncio.gather(*(one(i) for i in range(args.tasks)))
            bursts.append(time.perf_counter() - t1)
    finally:
        await close()

    ran = {}
    for inv, site in placed:
        ran.setdefault(str(inv), {}).setdefault(site, 0)
        ran[str(inv)][site] += 1
    rates = [args.tasks / b for b in bursts]
    return {
        "n": n,
        "layout": args.layout,
        "sites": sites,
        "ran_on": ran,
        "placement_ok": all(set(ran.get(str(k), {})) == {sites[k]} for k in range(n)),
        "ready_s": ready_s,
        "seq_p50_ms": statistics.median(seq) * 1e3 if seq else None,
        "bursts_s": bursts,
        "req_per_s_bursts_2_5": statistics.median(rates[1:]) if len(rates) > 1 else rates[0],
        "req_per_s_first": rates[0],
        "code_per_site": {"SITES_entry": sites[-1], "lines": 1}
        if args.layout == "spread" and n > 1 else None,
    }


async def amain(args, ns):
    res = {"provenance": provenance(args), "work_model": args.work,
           "wiring_lines": wiring_lines(), "points": []}
    res["provenance"]["experiment"] = "E3 portability: hand-wired N-site baseline"
    res["provenance"]["harness"] = Path(__file__).name
    for n in ns:
        try:
            rec = await one_n(args, n)
        except Exception as exc:
            rec = {"n": n, "layout": args.layout,
                   "error": f"{type(exc).__name__}: {exc}"[:500]}
        res["points"].append(rec)
        Path(args.out).write_text(json.dumps(res, indent=2))
        print(f"xgf {args.layout} n={n}: "
              + (rec["error"] if "error" in rec else
                 f"seq p50 {rec['seq_p50_ms']:.1f} ms, bursts 2-5 "
                 f"{rec['req_per_s_bursts_2_5']:.1f} req/s, placement "
                 f"{'ok' if rec['placement_ok'] else 'WRONG'} {rec['ran_on']}"),
              flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--endpoints", required=True)
    p.add_argument("--n", default="1,2,3,4")
    p.add_argument("--layout", choices=["spread", "one"], default="spread")
    p.add_argument("--work-ms", type=float, default=50.0)
    p.add_argument("--work", choices=["wall", "cpu"], default="wall")
    p.add_argument("--seq", type=int, default=20)
    p.add_argument("--tasks", type=int, default=200)
    p.add_argument("--concurrent", type=int, default=16)
    p.add_argument("--bursts", type=int, default=5)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    args.endpoints = [e for e in args.endpoints.split(",") if e]
    ns = [int(x) for x in args.n.split(",") if x]
    asyncio.run(amain(args, ns))
    return 0


if __name__ == "__main__":
    sys.exit(main())
