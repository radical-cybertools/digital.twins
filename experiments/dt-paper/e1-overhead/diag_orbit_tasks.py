"""Count the ORBIT tasks behind each `bench_dt_insitu.py` row (P4 diagnosis).

Runs `bench_dt_insitu.py` unchanged in this process, with the rhapsody
ORBIT backend's `submit_tasks` and `_send_batch` wrapped to count what
crosses to the endpoint.  Arguments are passed through:

    python diag_orbit_tasks.py --broker https://<addr>:<port> \\
        --endpoint <name> --rows agent --tasks 200 --concurrent 50

Requests issued by the harness per row: 20 warm-up + --tasks sequential +
--concurrent in the burst, plus the readiness polls of the twin rows
(answered locally while no model is published).  The JSON line at the end
has the totals; tasks per request is total tasks / (20 + tasks + concurrent).
"""

import collections
import json
import runpy
import sys

from pathlib import Path

from rhapsody.backends.execution.orbit import OrbitExecutionBackend  # type: ignore

counts = collections.Counter()
names = collections.Counter()

_submit = OrbitExecutionBackend.submit_tasks
_send = OrbitExecutionBackend._send_batch


async def submit_tasks(self, tasks):
    counts["submit_calls"] += 1
    counts["tasks"] += len(tasks)
    for t in tasks:
        fn = t.get("function")
        names[getattr(fn, "__name__", None) or t.get("name") or "?"] += 1
    return await _submit(self, tasks)


async def _send_batch(self, batch):
    counts["send_batches"] += 1
    counts["sent_tasks"] += len(batch)
    return await _send(self, batch)


OrbitExecutionBackend.submit_tasks = submit_tasks
OrbitExecutionBackend._send_batch = _send_batch

if __name__ == "__main__":
    harness = Path(__file__).with_name("bench_dt_insitu.py")
    sys.argv = [str(harness), *sys.argv[1:]]
    try:
        runpy.run_path(str(harness), run_name="__main__")
    finally:
        print("DIAG " + json.dumps({"counts": dict(counts),
                                    "task_names": dict(names),
                                    "argv": sys.argv[1:]}), flush=True)
