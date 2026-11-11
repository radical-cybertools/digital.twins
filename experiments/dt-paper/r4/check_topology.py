#!/usr/bin/env python3
"""Round 4 W3: is an endpoint in the broker's topology, with its rhapsody
plugin?  Read-only: a client runtime that lists the topology and stops.

    python r4/check_topology.py --broker URL --name r3_site [--wait 60]

Exit 0 if the endpoint is there with rhapsody, 1 if not.  Prints the
endpoint names it saw (never credentials).
"""

import argparse
import sys
import time

from radical.orbit import EndpointRuntime


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--broker", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--wait", type=float, default=0.0,
                   help="keep looking this long (s) before giving up")
    args = p.parse_args()
    rt = EndpointRuntime(broker_url=args.broker)
    rt.start(wait=True)
    try:
        deadline = time.time() + args.wait
        while True:
            topo = rt.topology()
            info = topo.get(args.name) or {}
            if "rhapsody" in (info.get("plugins") or {}):
                print(f"{args.name}: in the topology with rhapsody; "
                      f"endpoints seen: {sorted(topo)}")
                return 0
            if time.time() >= deadline:
                print(f"{args.name}: NOT in the topology with rhapsody; "
                      f"endpoints seen: {sorted(topo)}")
                return 1
            time.sleep(5)
    finally:
        rt.stop()


if __name__ == "__main__":
    sys.exit(main())
