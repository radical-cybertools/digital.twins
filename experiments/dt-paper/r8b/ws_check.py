#!/usr/bin/env python3
"""Round 8b: which WebSocket extensions a runtime negotiates with a broker
(permessage-deflate or none), under the current $RADICAL_ORBIT_WS_COMPRESSION.

    python r8b/ws_check.py URL
"""
import os
import sys
import time

from radical.orbit import EndpointRuntime  # type: ignore

rt = EndpointRuntime(broker_url=sys.argv[1])
rt.start(wait=True)
try:
    ws = None
    for _ in range(50):
        ws = getattr(rt, "_ws", None)
        if ws is not None:
            break
        time.sleep(0.1)
    ext = [type(e).__name__ for e in getattr(getattr(ws, "protocol", None), "extensions", []) or []]
    print(f"WS_COMPRESSION={os.environ.get('RADICAL_ORBIT_WS_COMPRESSION', 'unset')} "
          f"extensions={ext or 'none'}")
finally:
    rt.stop()
