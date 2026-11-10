"""Round 3 T1c: run radical-orbit-endpoint.py with finished tasks pruned.

Harness-side check of the T1 diagnosis (see diag_thread_decay.py), not a
rhapsody change: `ConcurrentExecutionBackend._handle_task` is wrapped so a
finished task leaves `self.tasks` and its `"future"` key, the asyncio Task
that would otherwise stay referenced (and in asyncio's task set) for the
whole session.  Arguments are passed to the endpoint script unchanged.

    python endpoint_prune.py -n NAME -u URL -p default --tunnel none
"""

import runpy
import shutil
import sys

from rhapsody.backends.execution.concurrent import (  # type: ignore
    ConcurrentExecutionBackend,
)

_handle = ConcurrentExecutionBackend._handle_task


async def _pruned(self, task):
    try:
        await _handle(self, task)
    finally:
        self.tasks.pop(task["uid"], None)
        task.pop("future", None)


ConcurrentExecutionBackend._handle_task = _pruned

if __name__ == "__main__":
    script = shutil.which("radical-orbit-endpoint.py")
    sys.argv = [script, *sys.argv[1:]]
    runpy.run_path(script, run_name="__main__")
