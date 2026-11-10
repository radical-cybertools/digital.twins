#!/usr/bin/env python3
"""Run a harness with Python's cyclic garbage collector disabled (or with
`--freeze`: gc.freeze() after imports).  Round 3b U4c: are the periodic slow
bursts of U4b collector pauses?

    python r3b/nogc.py [--freeze] HARNESS.py [harness args ...]
"""

import gc
import runpy
import sys

if sys.argv[1] == "--freeze":
    sys.argv.pop(1)
    mode = "freeze"
else:
    gc.disable()
    mode = "disabled"
path = sys.argv[1]
sys.argv = sys.argv[1:]
print(f"nogc: gc {mode}", flush=True)
runpy.run_path(path, run_name="__main__")
