"""Round 8d, D3b: does the per-task cost grow with the pool because tasks
rotate through every idle worker?

rhapsody's DragonNativeExecutionBackend keeps idle workers per host in a
deque: a finished worker is appended at the right (`_feed`), a new task takes
the leftmost (`_idle_pop`, popleft). So sequential tasks rotate through all
W workers: each lands on the worker that has been idle longest (about
W x one task's time). ORDER=lifo monkeypatches `_idle_pop` to take the
rightmost (the most recently finished, still warm) worker instead; this is
a harness-side patch, rhapsody's code is not changed. ORDER=fifo (default)
is the stock behaviour, as r8d/hop_local.py. The rest is hop_local.py: 400
sequential no-op tasks after 50 warm-up, total p50 and the split at the
worker. Also prints how many distinct workers ran the measured tasks.

    W=128 ORDER=lifo dragon -s r8d/hop_local_order.py
"""
import asyncio
import os
import statistics
import time

from rhapsody.api import ComputeTask, Session


def stamp():
    import os
    import time
    return [time.time(), os.getpid()]


def med(xs):
    return statistics.median(xs) * 1e3


def patch_lifo():
    from rhapsody.backends.execution import dragon_native as dn

    def _idle_pop(self, key, avoid=None):
        host, gpus = key
        if gpus or host is not None:
            idle = self._idle.get(key)
            return idle.pop() if idle else None
        hosts = self._host_order
        if avoid is not None:
            hosts = [h for h in hosts if h != avoid] + [avoid]
        for h in hosts:
            idle = self._idle.get((h, ()))
            if idle:
                return idle.pop()
        return None

    dn.DragonNativeExecutionBackend._idle_pop = _idle_pop


async def main():
    order = os.environ.get("ORDER", "fifo")
    if order == "lifo":
        patch_lifo()
    from rhapsody.backends import DragonNativeExecutionBackend
    w = int(os.environ.get("W", "4"))
    b = await DragonNativeExecutionBackend(workers_per_node=w)
    async with Session(backends=[b]) as s:
        rows = []
        for i in range(450):
            t = ComputeTask(function=stamp)
            t0 = time.time()
            await s.submit_tasks([t])
            await t
            t1 = time.time()
            if i >= 50:
                ts, pid = t.get("return_value")
                rows.append((t0, ts, t1, pid))
    tot = [c - a for a, b_, c, _ in rows]
    to = [b_ - a for a, b_, c, _ in rows]
    back = [c - b_ for a, b_, c, _ in rows]
    print(f"W={w:3d} {order:4s} total p50 {med(tot):6.3f} ms | submit->task {med(to):6.3f} | "
          f"task->awaited {med(back):6.3f} | workers used {len({r[3] for r in rows})}", flush=True)


asyncio.run(main())
