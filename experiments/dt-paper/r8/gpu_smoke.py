#!/usr/bin/env python3
"""Round 8, R8-0 GPU check: TensorFlow inside a dragon_native pool worker.

Run under a single-node Dragon runtime on a GPU node (`dragon -s`): builds
rhapsody's DragonNativeExecutionBackend (2 workers: this check needs one),
an asyncflow engine on it, and runs one function task in a pool worker that
lists TensorFlow's GPUs and evaluates one PINN field from the September
archive with xGFabric's own `tk_pinn_eval` (as e6-use-cases/p8b_check_eval.py),
twice (cold, warm).  JSON on stdout; exit 0 if TF saw a GPU and the field is
38 x 85.

    dragon -s r8/gpu_smoke.py --xgf $XGF_DIR --out gpu.json
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prov import provenance  # noqa: E402


async def pinn_task(xgf, models, playground):
    import os
    import sys
    import time

    t0 = time.perf_counter()
    import tensorflow as tf

    gpus = [d.name for d in tf.config.list_physical_devices("GPU")]
    t_import = time.perf_counter() - t0
    sys.path.insert(0, xgf)
    os.chdir(xgf)
    import dotenv
    import numpy as np

    dotenv.load_dotenv("tasks/common/config.sh")
    cfg = dict(os.environ, AGENT_NAME="WindField", TASK_COUNTER=0,
               INVESTIGATOR_NAME="pinn", PLAYGROUND_DIR=playground)
    from tasks.do_pinn.main import tk_pinn_eval

    runs = []
    for _ in range(2):
        t1 = time.perf_counter()
        out = tk_pinn_eval(cfg, os.path.join(models, "pinn/0/results/pinn.tar.gz"), 0.5)
        runs.append({"s": time.perf_counter() - t1,
                     "shapes": [list(np.shape(o)) for o in out]})
    return {"pid": os.getpid(), "gpus": gpus, "tf": tf.__version__,
            "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "tf_import_s": t_import, "runs": runs}


async def main(args):
    from radical.asyncflow import WorkflowEngine
    from rhapsody.backends.execution.dragon_native import DragonNativeExecutionBackend

    t0 = time.time()
    be = DragonNativeExecutionBackend(workers_per_node=2)
    if hasattr(be, "__await__"):
        be = await be
    t_be = time.time() - t0
    flow = await WorkflowEngine.create(backend=be)
    task = flow.function_task(pinn_task)
    res = {"backend_start_s": t_be}
    try:
        res["task"] = await asyncio.wait_for(
            task(args.xgf, args.models, args.playground), timeout=900)
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"[:500]
    await flow.shutdown()
    return res


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--xgf", default=os.environ.get("XGF_DIR"))
    p.add_argument("--models", default="/pscratch/sd/m/merzky/xgf_playground/WindField")
    p.add_argument("--playground", default=os.environ.get("PLAYGROUND_DIR", "/tmp/xgf-pg"))
    p.add_argument("--out", required=True)
    args = p.parse_args()
    os.environ.setdefault("R8_WORKERS_PER_NODE", "2 (gpu check)")
    res = {"provenance": provenance("R8-0 GPU check", Path(__file__).name, args)}
    res.update(asyncio.run(main(args)))
    t = res.get("task") or {}
    res["ok"] = bool(t.get("gpus")) and all(r["shapes"] == [[38, 85]] * 3 for r in t.get("runs", []))
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "provenance"}, default=str))
    sys.exit(0 if res["ok"] else 1)
