#!/usr/bin/env python3
"""P8b precheck: run xGFabric's own tk_fno_eval / tk_pinn_eval once each.

Uses the archives the September demo produced, a scratch playground and the
config the twin would use (`tasks/common/config.sh`, with PLAYGROUND_DIR from
the environment).  Exit 0 only if both return three 38 x 85 fields.

    PLAYGROUND_DIR=$W/xgf/check python p8b_check_eval.py --xgf $XGF_DIR
"""

import argparse
import json
import os
import sys
import time


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--xgf", default=os.environ.get("XGF_DIR"))
    p.add_argument("--models", default="/pscratch/sd/m/merzky/xgf_playground/WindField")
    p.add_argument("--concurrent", type=int, default=4,
                   help="then N overlapping evals per model in separate "
                        "processes (the twin's endpoint runs them so)")
    args = p.parse_args()

    sys.path.insert(0, args.xgf)
    os.chdir(args.xgf)

    import dotenv
    import numpy as np

    dotenv.load_dotenv("tasks/common/config.sh")
    config = dict(os.environ)
    config["AGENT_NAME"] = "WindField"
    config["TASK_COUNTER"] = 0

    from tasks.do_fno.main import tk_fno_eval
    from tasks.do_pinn.main import tk_pinn_eval

    ok = True
    for name, fn, tar in (("fno", tk_fno_eval, "fno/0/results/fno.tar.gz"),
                          ("pinn", tk_pinn_eval, "pinn/0/results/pinn.tar.gz")):
        cfg = dict(config, INVESTIGATOR_NAME=name)
        t0 = time.perf_counter()
        try:
            out = fn(cfg, os.path.join(args.models, tar), 0.5)
            shapes = [list(np.shape(o)) for o in out]
            good = len(out) == 3 and all(s == [38, 85] for s in shapes)
            print(json.dumps({"model": name, "ok": good, "shapes": shapes,
                              "seconds": time.perf_counter() - t0}), flush=True)
        except Exception as exc:
            good = False
            print(json.dumps({"model": name, "ok": False,
                              "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        ok = ok and good

    if args.concurrent > 1:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        ctx = multiprocessing.get_context("spawn")
        for name, tar in (("fno", "fno/0/results/fno.tar.gz"),
                          ("pinn", "pinn/0/results/pinn.tar.gz")):
            cfg = dict(config, INVESTIGATOR_NAME=name)
            path = os.path.join(args.models, tar)
            with ProcessPoolExecutor(args.concurrent, mp_context=ctx) as pool:
                futs = [pool.submit(_eval, args.xgf, name, cfg, path)
                        for _ in range(args.concurrent * 2)]
                res = []
                for f in futs:
                    try:
                        res.append(f.result())
                    except Exception as exc:
                        res.append(f"{type(exc).__name__}: {exc}")
            good = all(r == [[38, 85]] * 3 for r in res)
            print(json.dumps({"model": name, "concurrent": args.concurrent,
                              "calls": len(res), "ok": good,
                              "errors": [r for r in res if not isinstance(r, list)][:3]}),
                  flush=True)
            ok = ok and good
    return 0 if ok else 1


def _eval(xgf, name, cfg, path):
    sys.path.insert(0, xgf)
    os.chdir(xgf)
    import numpy as np

    if name == "fno":
        from tasks.do_fno.main import tk_fno_eval as fn
    else:
        from tasks.do_pinn.main import tk_pinn_eval as fn
    return [list(np.shape(o)) for o in fn(cfg, path, 0.5)]


if __name__ == "__main__":
    sys.exit(main())
