#!/usr/bin/env python3
"""Wait until the broker no longer holds an endpoint as present (gone from
the topology, or its liveness is not 'present').  Prints the seconds waited.

    python r8/wait_lost.py URL NAME [TIMEOUT]
"""
import sys
import time

from radical.orbit import EndpointRuntime  # type: ignore

url, name = sys.argv[1], sys.argv[2]
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 120
rt = EndpointRuntime(broker_url=url)
rt.start(wait=True)
t0 = time.time()
try:
    while time.time() - t0 < timeout:
        info = rt.topology().get(name)
        if not info or info.get("liveness", "present") != "present":
            print(f"{time.time() - t0:.1f} {info.get('liveness') if info else 'gone'}")
            sys.exit(0)
        time.sleep(0.25)
    print("timeout")
    sys.exit(1)
finally:
    rt.stop()
