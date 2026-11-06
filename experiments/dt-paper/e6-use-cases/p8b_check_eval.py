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
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
