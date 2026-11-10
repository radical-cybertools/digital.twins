"""E4 (round 3): hot-swap turnaround with the existing API.

A running twin with one `SciAgent` (model selector) and its investigator
v0.  Under closed-loop inference (C clients calling `get_inference` back
to back), swap k = 1..N: the agent starts investigator v_k
(`RuntimeAPI.start_investigator`, whose main loop starts at once) and
switches its selector to it (`update_model_selector`).  The inference of
v_k is an asyncflow function task returning k, so every answer names the
investigator that produced it.

The page asked for the twin-level `DTRuntime.add_investigator`; an agent's
selector only picks among the agent's own investigators, so the swap uses
the agent-side `start_investigator` -- the same immediate start.

Per swap:
  turnaround   from the `start_investigator` call to the first answer
               carrying k
  stale        answers still from an older investigator after the switch
  gap          the longest time without any answer around the swap

Backends as in `e1-overhead/bench_dt_insitu.py`: a local process pool, or
an ORBIT endpoint (`--broker`, `--endpoint`).

    python experiments/dt-paper/e4-hot-swap/bench_swap.py --swaps 20 \\
        --concurrency 1 --out results/swap.json
"""

import argparse
import asyncio
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import time

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e1-overhead"))

from bench_dt_insitu import X, Y, make_backend  # noqa: E402

from radical.asyncflow import WorkflowEngine  # type: ignore  # noqa: E402

from digitaltwin import (  # noqa: E402
    DTRuntime,
    ModelInvestigator,
    SciAgent,
    TypedData,
    ZMQ_BrokerProcess,
    connect_stream_client,
)
from digitaltwin.components import NULL_DTYPE  # noqa: E402


class Inv(ModelInvestigator):
    """Investigator v_k: its answers carry k."""

    def __init__(self, flow, predict, k):
        super().__init__(flow)
        self.predict = predict
        self.k = k

    async def main_loop(self, runtime):
        predict, k = self.predict, self.k

        async def infer(in_data):
            return TypedData(Y, await predict(k))

        runtime.set_inference_task(infer)
        runtime.publish_new_model()


class Agent(SciAgent):
    def __init__(self, flow, predict):
        super().__init__(flow)
        self.flow, self.predict = flow, predict
        self.rt = None
        self.ready = asyncio.Event()

    async def main_loop(self, runtime):
        self.rt = runtime
        v0 = Inv(self.flow, self.predict, 0)
        runtime.start_investigator(v0)

        async def select(in_data, i_id=0):
            return i_id, {}

        runtime.set_model_selection_task(select)
        runtime.update_model_selector(i_id=v0.get_id())
        self.ready.set()

    def swap(self, k):
        inv = Inv(self.flow, self.predict, k)
        self.rt.start_investigator(inv)
        self.rt.update_model_selector(i_id=inv.get_id())


def summarize(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return {"n": len(xs), "p50_ms": statistics.median(xs) * 1e3,
            "p90_ms": xs[min(len(xs) - 1, int(0.9 * len(xs)))] * 1e3,
            "min_ms": xs[0] * 1e3, "max_ms": xs[-1] * 1e3}


async def run(flow, broker, predict, args):
    stream = await connect_stream_client("e4-swap", *broker.get_connection_str())
    rt = DTRuntime(flow, stream)
    agent = Agent(flow, predict)
    rt.add_agent(agent, X, Y)
    rt.start()
    answers = []                                 # (answered at, k)
    swaps = []                                   # (called at, k)
    stop = asyncio.Event()
    try:
        await agent.ready.wait()
        deadline = time.monotonic() + 30
        while (await rt.get_inference(TypedData(X, 0), Y)).dtype == NULL_DTYPE:
            if time.monotonic() > deadline:
                raise RuntimeError(f"twin not ready: {rt.state} {rt.last_error}")
            await asyncio.sleep(0.05)

        async def client():
            while not stop.is_set():
                a = await rt.get_inference(TypedData(X, 0), Y)
                answers.append((time.perf_counter(), a.data))

        clients = [asyncio.create_task(client()) for _ in range(args.concurrency)]
        await asyncio.sleep(args.interval)
        for k in range(1, args.swaps + 1):
            swaps.append((time.perf_counter(), k))
            agent.swap(k)
            await asyncio.sleep(args.interval)
        stop.set()
        await asyncio.gather(*clients)
    finally:
        await rt.stop()

    turnaround, stale, gaps, missed = [], [], [], 0
    for i, (t_call, k) in enumerate(swaps):
        t_next = swaps[i + 1][0] if i + 1 < len(swaps) else float("inf")
        window = [(t, v) for t, v in answers if t_call <= t < t_next]
        first = next((t for t, v in window if v == k), None)
        if first is None:
            missed += 1
            continue
        turnaround.append(first - t_call)
        stale.append(sum(1 for t, v in window if t > first and v != k))
        around = [t for t, _ in answers if t_call - args.interval / 2 <= t <= first]
        ts = [t_call] + around + [first]
        gaps.append(max(b - a for a, b in zip(ts, ts[1:])))
    return {
        "swaps": len(swaps), "missed": missed,
        "answers": len(answers),
        "turnaround": summarize(turnaround),
        "turnaround_s": turnaround,
        "stale_after_first": sum(stale),
        "gap": summarize(gaps),
    }


def provenance(args, backend_label) -> dict:
    root = Path(__file__).resolve().parents[3]

    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(root), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E4 hot-swap turnaround",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git("rev-parse", "HEAD"),
        "digital_twins_dirty": bool(git("status", "--porcelain", "--", "src")),
        "backend": backend_label,
        "notify_window": os.environ.get("RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW"),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args),
    }


async def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", default=os.environ.get("RADICAL_ORBIT_BROKER_URL"))
    p.add_argument("--endpoint", default=os.environ.get("DT_TASK_ENDPOINT"))
    p.add_argument("--backends", default="concurrent")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--swaps", type=int, default=20)
    p.add_argument("--interval", type=float, default=0.5,
                   help="seconds between swaps")
    p.add_argument("--out")
    args = p.parse_args()
    args.backends = [b for b in args.backends.split(",") if b]

    backend_label, backend = await make_backend(args)
    flow = await WorkflowEngine.create(backend=backend)

    @flow.function_task
    async def predict(k):
        return k

    broker = ZMQ_BrokerProcess()
    await broker.start()
    try:
        r = await run(flow, broker, predict, args)
    finally:
        await broker.stop()
        await flow.shutdown()
    t = r["turnaround"] or {}
    print(f"swaps={r['swaps']} missed={r['missed']} c={args.concurrency} "
          f"turnaround p50={t.get('p50_ms', float('nan')):.2f} ms "
          f"p90={t.get('p90_ms', float('nan')):.2f} max={t.get('max_ms', float('nan')):.2f} "
          f"stale={r['stale_after_first']} gap p50={(r['gap'] or {}).get('p50_ms', float('nan')):.2f} ms",
          flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps({"provenance": provenance(args, backend_label),
                                              **r}, indent=2))
        print(f"results: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
