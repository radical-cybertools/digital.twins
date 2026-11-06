"""P2 diagnosis: is asyncflow's 10 ms run-loop sleep the per-task floor?

radical.asyncflow 0.5.1, `WorkflowEngine` run loop
(`workflow_manager.py`, the `else: await asyncio.sleep(0.01)` branch):
after every iteration that submitted or completed something, the loop
sleeps 10 ms before it looks at the ready queue again.  A task that
becomes ready meanwhile waits for it.

This wrapper changes nothing installed.  It replaces the `asyncio` name
inside `radical.asyncflow.workflow_manager` with a proxy whose `sleep`
maps 0.01 to `--poll` seconds (every other attribute is the real asyncio),
then runs a harness unchanged:

    python diag_asyncflow_poll.py --poll 0.001 -- \\
        streaming_learner_perf.py --modes engine --out x.json
"""

import argparse
import asyncio
import runpy
import sys
import types

from pathlib import Path

import radical.asyncflow.workflow_manager as wm  # type: ignore


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--poll", type=float, required=True,
                   help="replacement for the run loop's 0.01 s sleep")
    p.add_argument("harness")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    args = p.parse_args()

    real_sleep = asyncio.sleep
    calls = {"patched": 0}

    async def sleep(delay, *a, **kw):
        if delay == 0.01:
            calls["patched"] += 1
            delay = args.poll
        return await real_sleep(delay, *a, **kw)

    proxy = types.ModuleType("asyncio_poll_proxy")
    proxy.__dict__.update(asyncio.__dict__)
    proxy.sleep = sleep
    wm.asyncio = proxy

    harness = Path(args.harness)
    if not harness.is_absolute():
        harness = Path(__file__).with_name(args.harness)
    rest = [a for a in args.rest if a != "--"]
    sys.argv = [str(harness), *rest]
    try:
        runpy.run_path(str(harness), run_name="__main__")
    finally:
        print(f"DIAG poll={args.poll} patched_sleeps={calls['patched']}", flush=True)


if __name__ == "__main__":
    main()
