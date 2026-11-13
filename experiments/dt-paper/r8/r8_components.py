"""Round 8 twin components: one investigator whose inference runs what the
request asks for, so one twin drives every R8-0 check.

Shipped by value (`register_user_modules`).  A request is a dict:

  {"op": "fn"}                       one function task (pid, host, times)
  {"op": "fn", "ms": M}              one function task holding its process's
                                     CPU (and GIL) for M ms (thread_time)
  {"op": "exe"}                      one executable task (/bin/hostname)
  {"op": "burst", "k": K, "ms": M}   K function tasks of M ms CPU at once
                                     (one gather); returns the count, the
                                     distinct worker pids, and each task's
                                     start / end epoch (summarized)

Every return value is JSON-safe: the ORBIT rhapsody plugin carries only
JSON (or bytes) back (test/integration/twin_components.py).
"""

import asyncio

from digitaltwin.components import DataType, ModelInvestigator, TypedData

IN = DataType("r8_request")
OUT = DataType("r8_answer")


class R8Investigator(ModelInvestigator):

    def __init__(self, flow):
        super().__init__(flow)

        @flow.function_task
        async def fn(ms: float = 0.0):
            import os
            import socket
            import time

            t0 = time.time()
            if ms:
                end = time.thread_time() + ms / 1000.0
                while time.thread_time() < end:
                    pass
            return {"pid": os.getpid(), "host": socket.gethostname(),
                    "t0": t0, "t1": time.time()}

        @flow.executable_task
        async def exe():
            return "/bin/hostname"

        self.fn = fn
        self.exe = exe

    async def main_loop(self, runtime):
        import time

        async def infer(in_data: TypedData, **kwargs):
            req = in_data.data
            op = req.get("op", "fn")
            t0 = time.time()
            if op == "fn":
                out = await self.fn(req.get("ms", 0.0))
            elif op == "exe":
                out = {"stdout": str(await self.exe())[:200]}
            elif op == "burst":
                rs = await asyncio.gather(*[self.fn(req.get("ms", 0.0))
                                            for _ in range(int(req["k"]))])
                starts = sorted(r["t0"] for r in rs)
                out = {"k": len(rs), "pids": len({r["pid"] for r in rs}),
                       "hosts": sorted({r["host"] for r in rs}),
                       "first_start": starts[0], "last_start": starts[-1],
                       "last_end": max(r["t1"] for r in rs)}
            else:
                raise ValueError(f"unknown op {op!r}")
            out["svc_t0"] = t0
            out["svc_t1"] = time.time()
            return TypedData(OUT, out)

        runtime.set_inference_task(infer)
        runtime.publish_new_model({})
