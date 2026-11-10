"""E2 (round 3): one twin with M agents, side by side or chained.

One twin, M agents of the xGFabric shape (a `SciAgent` with a model
selector in front of one `ModelInvestigator`); every inference is a plain
pass-through coroutine, so no task runs and the cost measured is the DT's
routing.  Embedded ZMQ broker, external `ChannelPublisher`s as producers,
as in `bench_streams_join.py`.

  side    agent i serves in_i -> out_i, each in_i bound to its own channel;
          a sink per out_i.  One message per channel per round:
          inputs/s = M x rounds/s, across all agents.
  chain   agent k serves x_k -> x_{k+1}; x_0 is bound to one channel, a
          sink on x_M.  One message per round: inputs/s at the end of the
          chain = rounds/s.

End-to-end latency is from the publish to the sink seeing the output.  Per
M: a base point at a low rate, then rising rates until p50 is at least
double the base point's, an output is lost, or the producer cannot keep
the rate; the highest rate below that is the max sustainable one.

    python experiments/dt-paper/e2-scaling/bench_agents.py \\
        --agents 1,2,4,8,16 --modes side,chain --out results/agents.json
"""

import argparse
import asyncio
import json
import os
import platform
import socket
import statistics
import subprocess
import time

from pathlib import Path

from digitaltwin import (
    CODEC_JSON,
    NULL_DTYPE,
    ChannelPublisher,
    DataType,
    DTRuntime,
    ModelInvestigator,
    PubSubConfig,
    SciAgent,
    TypedData,
    UtilityTask,
    ZMQ_BrokerProcess,
    connect_stream_client,
)

BASE_RATE = 10.0
RATES = [10, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
SETTLE = 3.0
READY_TIMEOUT = 30.0


class Inv(ModelInvestigator):
    def __init__(self, out_dtype):
        super().__init__(None)
        self.out_dtype = out_dtype

    async def main_loop(self, runtime):
        out = self.out_dtype

        async def infer(in_data):
            return TypedData(out, in_data.data)

        runtime.set_inference_task(infer)
        runtime.publish_new_model()


class Agent(SciAgent):
    def __init__(self, out_dtype):
        super().__init__(None)
        self.inv = Inv(out_dtype)

    async def main_loop(self, runtime):
        runtime.start_investigator(self.inv)

        async def select(in_data, i_id=0):
            return i_id, {}

        runtime.set_model_selection_task(select)
        runtime.update_model_selector(i_id=self.inv.get_id())


class Sink(UtilityTask):
    def __init__(self, seen):
        super().__init__(None)
        self.seen = seen

    async def main_loop(self, runtime, in_data):
        self.seen.append(time.perf_counter() - in_data.data["t"])


async def wait_ready(runtime, links):
    """Until every agent answers (its selector and model are published)."""
    deadline = time.monotonic() + READY_TIMEOUT
    for x, y in links:
        while (await runtime.get_inference(TypedData(x, {"t": 0}), y)).dtype == NULL_DTYPE:
            if time.monotonic() > deadline:
                raise RuntimeError(f"agent {x} -> {y} not ready: {runtime.state} "
                                   f"{runtime.last_error}")
            await asyncio.sleep(0.05)


async def one_point(broker, mode, m, rate, seconds, tag):
    seen: list = []
    stream = await connect_stream_client(f"e2a-{tag}", *broker.get_connection_str())
    runtime = DTRuntime(None, stream)
    if mode == "side":
        ins = [DataType(f"e2ag-in{i}") for i in range(m)]
        outs = [DataType(f"e2ag-out{i}") for i in range(m)]
        links = list(zip(ins, outs))
        channels = [f"e2ag/{tag}/s{i}" for i in range(m)]
        bound = [runtime.add_input(d, c, CODEC_JSON) for d, c in zip(ins, channels)]
        for x, y in links:
            runtime.add_agent(Agent(y), x, y)
            runtime.add_task(Sink(seen), y, NULL_DTYPE)
        per_round = m
    else:
        xs = [DataType(f"e2ag-x{k}") for k in range(m + 1)]
        links = list(zip(xs[:-1], xs[1:]))
        channels = [f"e2ag/{tag}/x0"]
        bound = [runtime.add_input(xs[0], channels[0], CODEC_JSON)]
        for x, y in links:
            runtime.add_agent(Agent(y), x, y)
        runtime.add_task(Sink(seen), xs[-1], NULL_DTYPE)
        per_round = 1
    runtime.start()
    config = PubSubConfig(None, *broker.get_connection_str())
    pubs = [await ChannelPublisher.open(c, CODEC_JSON, config=config, timeout=10.0)
            for c in channels]
    try:
        await asyncio.gather(*[b for b in bound if b is not None])
        await wait_ready(runtime, links)
        await asyncio.sleep(0.5)

        n_rounds = max(1, int(rate * seconds))
        period = 1.0 / rate
        t0 = time.perf_counter()
        for r in range(n_rounds):
            delay = t0 + r * period - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            for p in pubs:
                await p.publish({"t": time.perf_counter(), "r": r})
        pub_elapsed = time.perf_counter() - t0

        expected = n_rounds * per_round
        deadline = time.perf_counter() + SETTLE + seconds
        while len(seen) < expected and time.perf_counter() < deadline:
            await asyncio.sleep(0.05)
    finally:
        for p in pubs:
            await p.close()
        await runtime.stop()

    return {
        "mode": mode,
        "agents": m,
        "rate_target": rate,
        "rounds": n_rounds,
        "expected": expected,
        "rate_achieved": n_rounds / pub_elapsed,
        "outputs": len(seen),
        "p50_ms": statistics.median(seen) * 1e3 if seen else None,
        "p90_ms": sorted(seen)[int(0.9 * len(seen))] * 1e3 if seen else None,
        "inputs_per_s": per_round * n_rounds / pub_elapsed,
    }


def provenance(args) -> dict:
    root = Path(__file__).resolve().parents[3]

    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(root), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E2 agents per twin",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git("rev-parse", "HEAD"),
        "digital_twins_dirty": bool(git("status", "--porcelain", "--", "src")),
        "backend": "embedded ZMQ broker, no execution backend",
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args),
    }


async def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agents", default="1,2,4,8,16")
    p.add_argument("--modes", default="side,chain")
    p.add_argument("--rates", default=",".join(map(str, RATES)))
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--out")
    args = p.parse_args()
    ms = [int(m) for m in args.agents.split(",") if m]
    modes = [m for m in args.modes.split(",") if m]
    rates = [float(r) for r in args.rates.split(",") if r]

    broker = ZMQ_BrokerProcess()
    await broker.start()
    results = {"provenance": provenance(args), "points": [], "max_sustainable": {}}
    try:
        await one_point(broker, "chain", 2, BASE_RATE, 1.0, "warm")
        for mode in modes:
            for m in ms:
                base = best = None
                for i, rate in enumerate(rates):
                    r = await one_point(broker, mode, m, rate, args.seconds,
                                        f"{mode}{m}r{i}")
                    results["points"].append(r)
                    ok = (r["outputs"] == r["expected"]
                          and r["rate_achieved"] >= 0.9 * rate)
                    if base is None:
                        base = r["p50_ms"]
                    doubled = r["p50_ms"] is None or r["p50_ms"] >= 2 * base
                    print(f"{mode:5s} M={m:3d} rate={rate:7.0f}/s "
                          f"achieved={r['rate_achieved']:8.0f} "
                          f"outputs={r['outputs']}/{r['expected']} "
                          f"p50={r['p50_ms']} ms  ok={ok} doubled={doubled}", flush=True)
                    if not ok or doubled:
                        break
                    best = r
                results["max_sustainable"][f"{mode}-{m}"] = best and {
                    "rounds_per_s": best["rate_target"],
                    "inputs_per_s": best["inputs_per_s"],
                    "p50_ms": best["p50_ms"],
                    "base_p50_ms": base,
                }
    finally:
        await broker.stop()

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"results: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
