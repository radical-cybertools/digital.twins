#!/usr/bin/env python3
"""E6: per-surrogate inference cost of the xGFabric WindField surrogates.

One model per process, so the first call is a true cold start (TensorFlow
import, model build, weight load, graph trace).  Three numbers per run:

  cold    process start to the first full field (TF import + prepare + one
          field evaluation)
  reload  prepare + one field evaluation in a warm process: what the
          twin's tk_<model>_eval does on every call (it rebuilds the model
          from the weights each time)
  warm    one field evaluation with the model already loaded

A "field evaluation" is what tk_<model>_eval computes: the speed field on
the 85 x 38 PCR grid at z = 1, 3, 5 m for one wind speed.

The model code comes from an xGFabric checkout (``--xgf``, default
``$XGF_DIR``); the weights from a playground the September demo trained
(``--models``).  ``CUDA_VISIBLE_DEVICES=`` gives the CPU comparison.

Uses the models' own ``prepare`` / ``*_predict_field`` functions rather
than tk_<model>_eval, because tk_pinn_eval cannot run as is (it never
waits for its tar process, and it expects model.weights.h5 /
model_meta.json while the PINN archive holds pinn.weights.h5 /
pinn.model_meta.json with different meta keys).  The PINN meta keys are
mapped here; nothing else differs.
"""

import argparse
import json
import logging
import os
import platform
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

T_START = time.perf_counter()


def provenance(args) -> dict:
    root = Path(__file__).resolve().parents[3]

    def git(path, *cmd):
        try:
            return subprocess.check_output(["git", "-C", str(path), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E6 surrogate inference cost",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git(root, "rev-parse", "HEAD"),
        "xgfabric_commit": git(args.xgf, "rev-parse", "HEAD"),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "args": vars(args),
    }


def stats(xs):
    xs = sorted(xs)
    return {"n": len(xs), "median": statistics.median(xs), "min": xs[0],
            "max": xs[-1], "mean": statistics.fmean(xs),
            "p90": xs[min(len(xs) - 1, int(0.9 * len(xs)))]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=["fno", "pinn"], required=True)
    p.add_argument("--xgf", default=os.environ.get("XGF_DIR"))
    p.add_argument("--models", default="/pscratch/sd/m/merzky/xgf_playground/WindField")
    p.add_argument("--warm", type=int, default=50)
    p.add_argument("--reload", type=int, default=10)
    p.add_argument("--wind", type=float, default=0.5)
    p.add_argument("--budget", type=float, default=240.0,
                   help="seconds per warm / reload loop; a loop stops early "
                        "once it is spent (the count is recorded)")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    sys.path.insert(0, args.xgf)
    log = logging.getLogger("bench")
    logging.basicConfig(level=logging.WARNING)

    t0 = time.perf_counter()
    import numpy as np
    import tensorflow as tf
    t_import = time.perf_counter() - t0

    gpus = [d.name for d in tf.config.list_physical_devices("GPU")]
    print(f"[{args.model}] TF {tf.__version__}  GPUs: {gpus}", flush=True)

    x = np.linspace(8.3, 176.5, 85)
    y = np.linspace(8.1, 82.1, 38)
    pts = np.meshgrid(x, y)

    if args.model == "fno":
        from tasks.do_fno import inference as m
        d = Path(args.models) / "fno/0/results"
        weights, meta_file = d / "model.weights.h5", d / "model_meta.json"

        def prepare():
            model, meta = m.prepare(str(weights), str(meta_file), log)
            return model, meta, m.precompute_static(meta)

        def field(state):
            model, meta, (xg, yg, xl, yl) = state
            return [m.fno_predict_field(model, meta, xg, yg, xl, yl, pts,
                                        args.wind, z) for z in (1, 3, 5)]
    else:
        from tasks.do_pinn import inference as m
        d = Path(args.models) / "pinn/0/results"
        weights = d / "pinn.weights.h5"
        meta = json.loads((d / "pinn.model_meta.json").read_text())
        meta.setdefault("hidden", meta["hidden_dim"])
        meta.setdefault("n_layers", meta["n_hidden_layers"])
        meta.setdefault("best_val_mse", meta.get("best_val_loss", float("nan")))
        meta_file = Path(args.out).with_suffix(".pinn_meta.json")
        meta_file.write_text(json.dumps(meta))

        def prepare():
            model, meta_ = m.prepare(str(weights), str(meta_file), log)
            return model, meta_

        def field(state):
            model, meta_ = state
            return [m.pinn_predict_field(model, meta_, pts, args.wind, z)
                    for z in (1, 3, 5)]

    t0 = time.perf_counter()
    state = prepare()
    t_prepare = time.perf_counter() - t0
    t0 = time.perf_counter()
    out = field(state)
    t_first = time.perf_counter() - t0
    cold = time.perf_counter() - T_START
    shapes = [list(np.shape(o)) for o in out]

    warm = []
    t_loop = time.perf_counter()
    for _ in range(args.warm):
        t0 = time.perf_counter()
        field(state)
        warm.append(time.perf_counter() - t0)
        if time.perf_counter() - t_loop > args.budget:
            break

    reload = []
    t_loop = time.perf_counter()
    for _ in range(args.reload):
        t0 = time.perf_counter()
        s = prepare()
        field(s)
        reload.append(time.perf_counter() - t0)
        if time.perf_counter() - t_loop > args.budget:
            break

    res = {
        "provenance": provenance(args),
        "model": args.model,
        "tf_version": tf.__version__,
        "gpus": gpus,
        "field_shapes": shapes,
        "cold": {"total_s": cold, "tf_import_s": t_import,
                 "prepare_s": t_prepare, "first_field_s": t_first},
        "warm_field_s": stats(warm),
        "reload_field_s": stats(reload),
        "warm_raw_s": warm,
        "reload_raw_s": reload,
    }
    Path(args.out).write_text(json.dumps(res, indent=2))
    print(f"[{args.model}] gpus={len(gpus)} cold {cold:.2f}s  "
          f"reload p50 {res['reload_field_s']['median']*1e3:.1f} ms  "
          f"warm p50 {res['warm_field_s']['median']*1e3:.2f} ms", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
