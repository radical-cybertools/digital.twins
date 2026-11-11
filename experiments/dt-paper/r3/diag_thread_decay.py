"""Round 3 T1: the per-session burst decay, without ORBIT.

The endpoint runs tasks on rhapsody's `ConcurrentExecutionBackend` with a
thread pool.  There every async function task is `asyncio.run()` in a
worker thread, and `asyncio.run()` ends with `_cancel_all_tasks`, which
copies and filters `asyncio.tasks._scheduled_tasks` -- the process-wide
WeakSet of every Task still referenced anywhere.  `submit_tasks` keeps each
task's asyncio Task in `self.tasks` and never drops it, so that set grows
by one per task for the backend's lifetime and every later task pays for
all earlier ones.

This drives the same backend in-process, bursts of C no-op tasks through
asyncflow, and prints the burst rate and the size of `_scheduled_tasks`.
The Task is also stored in the task dict itself (`task["future"]`), and
that dict lives on in asyncflow's component registry here and in the ORBIT
rhapsody plugin's session `_tasks` on an endpoint.  `--prune` drops a
finished task from `self.tasks` and its `"future"` key (harness-side
patch, not a rhapsody change) to show the decay goes with them.

    python diag_thread_decay.py --bursts 20 --concurrent 500 [--prune]
"""

import argparse
import asyncio
import json
import os
import platform
import socket
import subprocess
import time

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from radical.asyncflow import WorkflowEngine  # type: ignore
from rhapsody.backends.execution.concurrent import (  # type: ignore
    ConcurrentExecutionBackend,
)


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=32)
    p.add_argument("--concurrent", type=int, default=500)
    p.add_argument("--bursts", type=int, default=20)
    p.add_argument("--prune", action="store_true")
    p.add_argument("--out")
    args = p.parse_args()

    backend = await ConcurrentExecutionBackend(ThreadPoolExecutor(args.workers))
    if args.prune:
        handle = backend._handle_task

        async def pruned(task):
            try:
                await handle(task)
            finally:
                backend.tasks.pop(task["uid"], None)
                # the asyncio Task also sits in the task dict itself, which
                # asyncflow (here) and the ORBIT rhapsody plugin's session
                # `_tasks` (on an endpoint) keep for the session's lifetime
                task.pop("future", None)

        backend._handle_task = pruned
    flow = await WorkflowEngine.create(backend=backend)

    @flow.function_task
    async def predict(x):
        return x

    rows = []
    try:
        for k in range(args.bursts):
            start = time.perf_counter()
            out = await asyncio.gather(*[predict(i) for i in range(args.concurrent)])
            elapsed = time.perf_counter() - start
            assert out == list(range(args.concurrent))
            live = len(asyncio.tasks._scheduled_tasks)
            rows.append({"burst": k, "req_per_s": args.concurrent / elapsed,
                         "scheduled_tasks": live,
                         "backend_tasks": len(backend.tasks)})
            print(f"burst {k:2d} {args.concurrent / elapsed:7.0f} req/s  "
                  f"_scheduled_tasks {live:6d}  backend.tasks {len(backend.tasks):6d}",
                  flush=True)
    finally:
        await flow.shutdown()
    if args.out:
        Path(args.out).write_text(json.dumps({"provenance": provenance(args),
                                              "args": vars(args), "bursts": rows},
                                             indent=2))


def provenance(args) -> dict:
    """As `e1-overhead/bench_dt_insitu.py`'s (round 3b)."""
    root = Path(__file__).resolve().parents[3]

    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(root), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E1 thread-pool decay repro",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git("rev-parse", "HEAD"),
        "backend": f"concurrent (ThreadPoolExecutor({args.workers}))",
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args),
    }


if __name__ == "__main__":
    asyncio.run(main())
