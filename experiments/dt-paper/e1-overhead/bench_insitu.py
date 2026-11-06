"""In-situ latency benchmark: local process pool vs ORBIT endpoint.

Models the DT in-situ inference path -- one prediction per call, awaited
sequentially -- plus a concurrency probe.  This is the harness behind
the compute-placement decision in the DTaaS plan (section 6): routing
all user compute through the Rhapsody abstraction costs single-digit
milliseconds per sequential prediction and wins under concurrency.

Run it against the integration stack (see `test/integration/conftest.py`
for how that stack is started, or start one by hand)::

    python experiments/dt-paper/e1-overhead/bench_insitu.py both \\
        --broker https://127.0.0.1:8031 --endpoint dt_test_task_ep

The server-side notification window is an *endpoint* setting and is the
dominating term when it is not zero -- start the endpoint with
`RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0` for the fast row, and leave it
at its 0.25 s default to reproduce the slow one.
"""

import argparse
import asyncio
import os
import statistics
import time

from concurrent.futures import ProcessPoolExecutor

from radical.asyncflow import WorkflowEngine  # type: ignore

N_WARM = 20
N_MEAS = 200
N_CONCURRENT = 50


def report(name: str, latencies: list) -> None:
    values = sorted(x * 1000 for x in latencies)
    n = len(values)

    def pct(q):
        return values[min(n - 1, int(q * n))]

    print(
        f"{name:28s} n={n}  mean={statistics.mean(values):7.2f}ms  "
        f"p50={pct(0.50):7.2f}  p90={pct(0.90):7.2f}  p99={pct(0.99):7.2f}  "
        f"max={values[-1]:7.2f}"
    )


async def measure(engine, label: str, n_meas: int, n_conc: int) -> None:
    @engine.function_task
    async def nop():
        return 42

    for _ in range(N_WARM):
        await nop()

    latencies = []
    for _ in range(n_meas):
        start = time.perf_counter()
        answer = await nop()
        latencies.append(time.perf_counter() - start)
        assert answer == 42, answer

    report(label, latencies)

    start = time.perf_counter()
    await asyncio.gather(*[nop() for _ in range(n_conc)])
    elapsed = time.perf_counter() - start

    print(f"{label:28s} {n_conc} concurrent tasks in {elapsed * 1000:.1f}ms "
          f"({n_conc / elapsed:.0f} tasks/s)")


async def bench_local(args) -> None:
    from rhapsody.backends.execution.concurrent import (  # type: ignore
        ConcurrentExecutionBackend,
    )

    backend = await ConcurrentExecutionBackend(ProcessPoolExecutor())
    engine = await WorkflowEngine.create(backend=backend)
    try:
        await measure(engine, "local concurrent pool", args.tasks,
                      args.concurrent)
    finally:
        await engine.shutdown()


async def bench_orbit(args) -> None:
    from rhapsody.backends.execution.orbit import (  # type: ignore
        OrbitExecutionBackend,
    )

    backend = await OrbitExecutionBackend(
        broker_url=args.broker,
        endpoint_name=args.endpoint,
        backends=args.backends,
        batch_window=0,  # no client-side batching: per-call latency
    )
    engine = await WorkflowEngine.create(backend=backend)
    try:
        await measure(engine, f"orbit {args.endpoint or '<auto>'}",
                      args.tasks, args.concurrent)
    finally:
        await engine.shutdown()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("which", nargs="?", default="both",
                        choices=["local", "orbit", "both"])
    parser.add_argument("--broker", default=os.environ.get(
        "RADICAL_ORBIT_BROKER_URL"),
        help="ORBIT broker URL (default: ORBIT's own resolution)")
    parser.add_argument("--endpoint", default=os.environ.get(
        "DT_TASK_ENDPOINT"),
        help="endpoint to run the tasks on (default: auto-select)")
    parser.add_argument("--backends", default="concurrent",
                        help="comma-separated remote backends")
    parser.add_argument("--tasks", type=int, default=N_MEAS)
    parser.add_argument("--concurrent", type=int, default=N_CONCURRENT)

    args = parser.parse_args()
    args.backends = [b for b in args.backends.split(",") if b]

    if args.which in ("local", "both"):
        await bench_local(args)

    if args.which in ("orbit", "both"):
        await bench_orbit(args)


if __name__ == "__main__":
    asyncio.run(main())
