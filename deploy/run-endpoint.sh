#!/usr/bin/env bash
#
# A rhapsody endpoint: this is where a twin's compute actually runs.
# The demo wants two, so the dashboard's `inference` and `learning` lanes are
# distinct hardware rather than one endpoint aliased twice.
#
#   ./run-endpoint.sh <name> <broker-host> [venv-dir]
#
#   ./run-endpoint.sh dt_inference_ep radical.3
#   ./run-endpoint.sh dt_learning_ep  radical.3
#
set -euo pipefail
NAME="${1:?usage: $0 <name> <broker-host> [venv-dir]}"
BROKER="${2:?usage: $0 <name> <broker-host> [venv-dir]}"
VENV="${3:-$PWD/ve.demo}"

export RADICAL_ORBIT_BROKER_URL="wss://$BROKER:8000"

# Batching a notification window in front of a demo only adds latency
# nobody can see the reason for: 0.25s per round trip was the whole of an
# earlier benchmark surprise.
export RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW="${RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW:-0}"
export RADICAL_ORBIT_RHAPSODY_BACKEND="${RADICAL_ORBIT_RHAPSODY_BACKEND:-concurrent}"

# A cloudpickled task body has no other way to find out where it ran, and
# the demo shows in-situ and ex-situ landing on different hardware.
export DT_ENDPOINT_TAG="$NAME"

echo "endpoint: $NAME -> $RADICAL_ORBIT_BROKER_URL"
echo

exec "$VENV/bin/radical-orbit-endpoint.py" -n "$NAME"
