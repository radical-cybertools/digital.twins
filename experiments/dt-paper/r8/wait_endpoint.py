#!/usr/bin/env python3
"""Wait until an endpoint advertises the rhapsody plugin in the broker's
topology (as bench_endpoint_loss.py does).  Prints the seconds waited.

    python r8/wait_endpoint.py URL NAME [TIMEOUT]
"""
import sys
import time

from radical.orbit import EndpointRuntime  # type: ignore

url, name = sys.argv[1], sys.argv[2]
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 300
rt = EndpointRuntime(broker_url=url)
rt.start(wait=True)
t0 = time.time()
try:
    while time.time() - t0 < timeout:
        info = rt.topology().get(name) or {}
        if "rhapsody" in (info.get("plugins") or {}):
            print(f"{time.time() - t0:.1f}")
            sys.exit(0)
        time.sleep(0.5)
    print("timeout")
    sys.exit(1)
finally:
    rt.stop()
