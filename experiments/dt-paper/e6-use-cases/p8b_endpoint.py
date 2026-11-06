#!/usr/bin/env python3
"""P8b: run the ORBIT endpoint with process-isolated rhapsody tasks.

The endpoint's rhapsody plugin builds `ConcurrentExecutionBackend()` with
no executor, which falls back to a `ThreadPoolExecutor`: every task of a
session (inference, simulations, FNO / PINN / PCR training) then runs as a
thread of one process, and two Keras trainings in parallel threads crash
(P8b run 1, job 60902704: "Input to reshape is a tensor with 1 values, but
the requested shape has 20736").  The September demo ran on dragon, one
process per task.  Dragon is out of scope here, so this wrapper changes
nothing installed and only gives the backend a spawn-based
`ProcessPoolExecutor` (`P8B_WORKERS`, default 8) when none is passed, then
runs `radical-orbit-endpoint.py` unchanged with the same arguments.

    python p8b_endpoint.py -n <name> -u <url> -p default --tunnel none
"""

import multiprocessing
import os
import runpy
import shutil
import sys

from concurrent.futures import ProcessPoolExecutor


def patch():
    import rhapsody.backends.execution.concurrent as conc  # type: ignore

    init = conc.ConcurrentExecutionBackend.__init__

    def process_init(self, executor=None, *args, **kwargs):
        if executor is None:
            executor = ProcessPoolExecutor(
                max_workers=int(os.environ.get("P8B_WORKERS", "8")),
                mp_context=multiprocessing.get_context("spawn"))
        init(self, executor, *args, **kwargs)

    conc.ConcurrentExecutionBackend.__init__ = process_init


if __name__ == "__main__":
    patch()
    script = shutil.which("radical-orbit-endpoint.py")
    sys.argv = [script, *sys.argv[1:]]
    runpy.run_path(script, run_name="__main__")
