#!/usr/bin/env bash
#
# The DTaaS host: ORBIT broker + the `dt` plugin.  Run this on radical.3.
#
#   ./run-broker.sh [venv-dir]
#
set -euo pipefail
VENV="${1:-$PWD/ve-dtaas}"

# The broker needs its *own* URL in the environment, not just on the CLI:
# the `dt` plugin builds a rhapsody client from it when a twin is created,
# and without it twin creation fails with a misleading
# "twin ... failed to initialize: Broker URL required".  Pointing it at
# localhost is right -- the plugin is talking to the broker it lives in.
export RADICAL_ORBIT_BROKER_URL="${RADICAL_ORBIT_BROKER_URL:-wss://localhost:8000}"

# The twins' data plane.  `orbit` puts stream traffic inside the
# token-authenticated ORBIT channel instead of the plugin's embedded ZMQ
# broker -- which is both the better story and the only way the dashboard
# can see the traffic at all, since the pulses are drawn from the
# gateway's event tap.  With `zmq` the stream never touches ORBIT and the
# sensors lane stays quiet.
export DT_STREAM_BACKEND="${DT_STREAM_BACKEND:-orbit}"

echo "broker  : 0.0.0.0:8000"
echo "self-url: $RADICAL_ORBIT_BROKER_URL"
echo "dataplane: $DT_STREAM_BACKEND"
echo

exec "$VENV/bin/radical-orbit-broker.py" --plugins default,dt "${@:2}"
