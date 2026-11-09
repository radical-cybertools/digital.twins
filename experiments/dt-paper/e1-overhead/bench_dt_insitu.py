"""E1 in-situ overhead: the same no-op prediction, hand-wired vs through DT.

Three rows on the same execution backend, so the difference between them
is the DT layer and nothing else:

  bare        the hand-wired baseline: the prediction is one asyncflow
              function task, called directly (xGFabric-style: one call
              per reading, no framework)
  investigator  `DTRuntime.get_inference` into one `ModelInvestigator`
              whose inference task awaits that same function task
  agent       the xGFabric twin shape: a `SciAgent` with a model
              selector in front of the investigator
  xgf         (round 3) the workflow as xGFabric wired it before the DT
              framework: a ZMQ request/reply service, one reading per
              request, one asyncflow task per reading, the answer as the
              reply (see `xgf_row`)

Each row: N sequential requests (latency percentiles), then C requests
gathered at once (throughput).  Results go to stdout and, with --out, to
a JSON file that records host, python and the digital_twins commit.

    # local process pool (any host, incl. a Perlmutter compute node)
    python experiments/dt-paper/e1-overhead/bench_dt_insitu.py

    # tasks on an ORBIT endpoint (start it with
    # RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0, see README.md)
    python experiments/dt-paper/e1-overhead/bench_dt_insitu.py \\
        --broker https://127.0.0.1:8031 --endpoint dt_test_task_ep

The twin's stream client needs a broker even though get_inference
bypasses the queues; the harness starts an embedded ZMQ broker.
"""

import argparse
import asyncio
import itertools
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import time

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_insitu import report  # noqa: E402

from radical.asyncflow import WorkflowEngine  # type: ignore  # noqa: E402

from digitaltwin import (  # noqa: E402
    DataType,
    DTRuntime,
    ModelInvestigator,
    SciAgent,
    TypedData,
    ZMQ_BrokerProcess,
    connect_stream_client,
)
from digitaltwin.components import NULL_DTYPE  # noqa: E402

X = DataType("e1-in")
Y = DataType("e1-out")

N_WARM = 20
N_MEAS = 200
N_CONCURRENT = 50
READY_TIMEOUT = 30.0
N_BURSTS = 1          # --bursts: back-to-back bursts per row (round 3)
ON_BURST = None       # diagnostics: called (label, k, elapsed or None) around each burst


class Inv(ModelInvestigator):
    """One model: in-situ inference only, the prediction is `predict`."""

    def __init__(self, flow, predict):
        super().__init__(flow)
        self.predict = predict

    async def main_loop(self, runtime):
        predict = self.predict

        async def infer(in_data):
            return TypedData(Y, await predict(in_data.data))

        runtime.set_inference_task(infer)
        runtime.publish_new_model()


class Agent(SciAgent):
    """The xGFabric shape: a selector in front of the investigator."""

    def __init__(self, flow, predict):
        super().__init__(flow)
        self.inv = Inv(flow, predict)

    async def main_loop(self, runtime):
        runtime.start_investigator(self.inv)

        async def select(in_data, i_id=0):
            return i_id, {}

        runtime.set_model_selection_task(select)
        runtime.update_model_selector(i_id=self.inv.get_id())


async def run_row(label, call, n_meas, n_conc) -> dict:
    for i in range(N_WARM):
        await call(i)

    latencies = []
    for i in range(n_meas):
        start = time.perf_counter()
        answer = await call(i)
        latencies.append(time.perf_counter() - start)
        assert answer == i, (label, i, answer)

    report(label, latencies)

    bursts = []
    for k in range(N_BURSTS):
        if ON_BURST:
            ON_BURST(label, k, None)
        start = time.perf_counter()
        answers = await asyncio.gather(*[call(i) for i in range(n_conc)])
        elapsed = time.perf_counter() - start
        assert answers == list(range(n_conc)), label
        bursts.append(elapsed)
        if ON_BURST:
            ON_BURST(label, k, elapsed)

        print(f"{label:28s} {n_conc} concurrent requests in {elapsed * 1000:.1f}ms "
              f"({n_conc / elapsed:.0f} req/s)")

    row = {"latencies_s": latencies,
           "concurrent": n_conc,
           "concurrent_s": bursts[0]}
    if N_BURSTS > 1:
        row["bursts_s"] = bursts
    return row


async def wait_ready(runtime):
    """Until the investigator has published its model."""

    deadline = time.monotonic() + READY_TIMEOUT
    while True:
        answer = await runtime.get_inference(TypedData(X, 0), Y)
        if answer.dtype != NULL_DTYPE:
            return
        if time.monotonic() > deadline:
            raise RuntimeError(f"twin not ready: {runtime.state} "
                               f"{runtime.last_error}")
        await asyncio.sleep(0.1)


async def twin_row(label, stream, flow, add, args) -> dict:
    runtime = DTRuntime(flow, stream)
    add(runtime)
    runtime.start()
    try:
        await wait_ready(runtime)

        async def call(i):
            return (await runtime.get_inference(TypedData(X, i), Y)).data

        return await run_row(label, call, args.tasks, args.concurrent)
    finally:
        await runtime.stop()


async def xgf_row(label, predict, args) -> dict:
    """The pre-DT xGFabric wiring, structure copied, not code.

    xGFabric `devel`: `service/src/xgfabric/service/service.py` is a
    `radical.utils` ZMQ server whose `register_fname` request carries one
    sensor reading, runs the workload for it and returns the result as the
    reply; `service/bin/xgfabric-client.py` is the client that sends it.
    (The readings reach it over CSPOT/WOOF, `demo1/ucsb/rpi-5G-scripts/
    cups-relay.sh`, or a polled input directory -- not reproducible here.)
    Here: ROUTER service <- DEALER client on loopback, JSON bodies, and an
    asyncio loop that submits one asyncflow task per request instead of the
    service's blocking `run_workload`.
    """

    import zmq
    import zmq.asyncio

    ctx = zmq.asyncio.Context()
    srv = ctx.socket(zmq.ROUTER)
    port = srv.bind_to_random_port("tcp://127.0.0.1")
    cli = ctx.socket(zmq.DEALER)
    cli.connect(f"tcp://127.0.0.1:{port}")
    handlers: set = set()
    waiting: dict = {}
    rids = itertools.count()

    async def handle(ident, rid, body):
        answer = await predict(json.loads(body))
        await srv.send_multipart([ident, rid, json.dumps(answer).encode()])

    async def serve():
        while True:
            ident, rid, body = await srv.recv_multipart()
            task = asyncio.create_task(handle(ident, rid, body))
            handlers.add(task)
            task.add_done_callback(handlers.discard)

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
    try:
        return await run_row(label, call, args.tasks, args.concurrent)
    finally:
        for task in loops + list(handlers):
            task.cancel()
        await asyncio.gather(*loops, *handlers, return_exceptions=True)
        cli.close(0)
        srv.close(0)
        ctx.term()


async def make_backend(args):
    if args.broker or args.endpoint:
        from rhapsody.backends.execution.orbit import (  # type: ignore
            OrbitExecutionBackend,
        )
        return f"orbit {args.endpoint or '<auto>'}", await OrbitExecutionBackend(
            broker_url=args.broker,
            endpoint_name=args.endpoint,
            backends=args.backends,
            batch_window=0,  # no client-side batching: per-call latency
        )

    from rhapsody.backends.execution.concurrent import (  # type: ignore
        ConcurrentExecutionBackend,
    )
    return "local concurrent pool", await ConcurrentExecutionBackend(
        ProcessPoolExecutor(args.workers))


def provenance(args, backend_label) -> dict:
    root = Path(__file__).resolve().parents[3]

    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(root), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E1 in-situ overhead",
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


async def main() -> None:
    global N_BURSTS
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--broker", default=os.environ.get("RADICAL_ORBIT_BROKER_URL"),
                        help="ORBIT broker URL; with it (or --endpoint) the "
                             "tasks run on an ORBIT endpoint")
    parser.add_argument("--endpoint", default=os.environ.get("DT_TASK_ENDPOINT"),
                        help="endpoint to run the tasks on")
    parser.add_argument("--backends", default="concurrent",
                        help="comma-separated remote backends")
    parser.add_argument("--workers", type=int, default=None,
                        help="local process pool size (default: cpu count)")
    parser.add_argument("--tasks", type=int, default=N_MEAS)
    parser.add_argument("--concurrent", type=int, default=N_CONCURRENT)
    parser.add_argument("--rows", default="bare,investigator,agent")
    parser.add_argument("--bursts", type=int, default=N_BURSTS,
                        help="back-to-back bursts per row; the first is "
                             "concurrent_s, all are in bursts_s")
    parser.add_argument("--out", help="write results as JSON here")

    args = parser.parse_args()
    args.backends = [b for b in args.backends.split(",") if b]
    rows = [r for r in args.rows.split(",") if r]
    N_BURSTS = args.bursts

    backend_label, backend = await make_backend(args)
    flow = await WorkflowEngine.create(backend=backend)

    @flow.function_task
    async def predict(x):
        return x

    broker = ZMQ_BrokerProcess()
    await broker.start()
    stream = await connect_stream_client("e1-insitu", *broker.get_connection_str())

    results = {"provenance": provenance(args, backend_label), "rows": {}}
    print(f"backend: {backend_label}")

    try:
        if "bare" in rows:
            results["rows"]["bare"] = await run_row(
                "bare asyncflow task", predict, args.tasks, args.concurrent)

        if "investigator" in rows:
            results["rows"]["investigator"] = await twin_row(
                "DT investigator", stream, flow,
                lambda rt: rt.add_investigator(Inv(flow, predict), X, Y), args)

        if "agent" in rows:
            results["rows"]["agent"] = await twin_row(
                "DT agent + selector", stream, flow,
                lambda rt: rt.add_agent(Agent(flow, predict), X, Y), args)

        if "xgf" in rows:
            results["rows"]["xgf"] = await xgf_row(
                "xgf zmq request/reply", predict, args)
    finally:
        await stream.close()
        await broker.stop()
        await flow.shutdown()

    for row in results["rows"].values():
        lat = row["latencies_s"]
        row["p50_ms"] = statistics.median(lat) * 1000
        row["mean_ms"] = statistics.mean(lat) * 1000
        row["concurrent_req_per_s"] = row["concurrent"] / row["concurrent_s"]

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"results: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
