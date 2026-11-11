#!/usr/bin/env python3
"""Run a harness (or any Python script) with Python's cyclic garbage
collector changed.  Round 3b U4c: are the periodic slow bursts of U4b
collector pauses?  Round 3c: raised thresholds (V2) and the endpoint (V3).

    python r3b/nogc.py [--freeze | --gc-threshold G0[,G1[,G2]]] SCRIPT.py [args ...]

Default: gc.disable().  --freeze: gc.freeze() before the script runs.
--gc-threshold: gc.set_threshold() with the given values.
"""

import gc
import runpy
import sys

if sys.argv[1] == "--freeze":
    sys.argv.pop(1)
    gc.freeze()  # round 3b's version only printed "freeze" (never used)
    mode = "freeze"
elif sys.argv[1] == "--gc-threshold":
    sys.argv.pop(1)
    gc.set_threshold(*(int(x) for x in sys.argv.pop(1).split(",")))
    mode = f"threshold {gc.get_threshold()}"
else:
    gc.disable()
    mode = "disabled"
path = sys.argv[1]
sys.argv = sys.argv[1:]
print(f"nogc: gc {mode}", flush=True)
runpy.run_path(path, run_name="__main__")
