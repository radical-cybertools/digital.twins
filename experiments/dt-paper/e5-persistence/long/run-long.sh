#!/usr/bin/env bash
# E5 long run on one host: broker + dt plugin, inference endpoint and the
# driver, each in a window of tmux session `dt-long`.  Idempotent: a window
# that is already running is left alone, so this also serves as the
# @reboot cron entry.  The broker and the inference endpoint are never
# restarted by anything (a restart ends session A's epoch); the driver is,
# in a loop, since it reattaches to session A by sid.
#
#   L=~/dt-long  (checkout in $L/digital.twins, venv in $L/ve)
#   DT_LONG_ARGS="--kill-every 3600" ./run-long.sh     # dry run settings
set -euo pipefail

L=${L:-$HOME/dt-long}
PORT=${DT_LONG_PORT:-8011}
X=$L/digital.twins/experiments/dt-paper/e5-persistence/long
mkdir -p "$L/logs" "$L/events"

common="source $L/ve/bin/activate && cd $L/digital.twins"
broker_env="RADICAL_ORBIT_LOG_FILE=$L/logs/broker.log RADICAL_ORBIT_BROKER_URL=wss://localhost:$PORT DT_STREAM_BACKEND=orbit"
ep_env="RADICAL_ORBIT_BROKER_URL=https://localhost:$PORT RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0"

tmux has-session -t dt-long 2>/dev/null || tmux new-session -d -s dt-long -n shell

window() {  # name command: start the window unless it exists
    tmux list-windows -t dt-long -F '#W' | grep -qx "$1" && return 0
    tmux new-window -d -t dt-long -n "$1" "bash -c '$2'"
}

window broker "$common && env $broker_env radical-orbit-broker.py --host 0.0.0.0 --port $PORT --plugins dt 2>&1 | tee -a $L/logs/broker.console.log"
sleep 5
window inf "$common && env $ep_env RADICAL_ORBIT_LOG_FILE=$L/logs/endpoint-dt_long_inf.log DT_TEST_ENDPOINT_TAG=dt_long_inf radical-orbit-endpoint.py -n dt_long_inf -u https://localhost:$PORT -p default --tunnel none 2>&1 | tee -a $L/logs/endpoint-dt_long_inf.console.log"
sleep 10
window driver "$common && while true; do env $ep_env python $X/dt_long.py --broker https://localhost:$PORT --state $L/state.json --events $L/events --logs $L/logs ${DT_LONG_ARGS:-} 2>&1 | tee -a $L/logs/driver.console.log; echo driver exited, restart in 30 s; sleep 30; done"
tmux list-windows -t dt-long -F '#W'
