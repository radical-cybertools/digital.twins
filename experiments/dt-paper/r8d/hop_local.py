"""Where one local no-op task spends its time: dragon_native vs concurrent pools."""
import asyncio, os, statistics, sys, time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from rhapsody.api import Session, ComputeTask

def stamp():
    import time
    return time.time()

def med(xs): return statistics.median(xs) * 1e3

async def run(backend, n=400):
    async with Session(backends=[backend]) as s:
        rows = []
        for i in range(n + 50):
            t = ComputeTask(function=stamp)
            t0 = time.time()
            await s.submit_tasks([t])
            await t
            t1 = time.time()
            if i >= 50:
                rows.append((t0, t.get("return_value"), t1))
        return rows

async def main(which):
    if which == "dragon":
        from rhapsody.backends import DragonNativeExecutionBackend
        b = await DragonNativeExecutionBackend(workers_per_node=int(os.environ.get("W", "4")))
    else:
        from rhapsody.backends import ConcurrentExecutionBackend
        ex = ProcessPoolExecutor(4) if which == "procpool" else ThreadPoolExecutor(4)
        b = await ConcurrentExecutionBackend(ex)
    rows = await run(b)
    tot = [c - a for a, b_, c in rows]; to = [b_ - a for a, b_, c in rows]; back = [c - b_ for a, b_, c in rows]
    print(f"{which:9s} total p50 {med(tot):6.3f} ms | submit->task {med(to):6.3f} | task->awaited {med(back):6.3f}", flush=True)

asyncio.run(main(sys.argv[1]))
