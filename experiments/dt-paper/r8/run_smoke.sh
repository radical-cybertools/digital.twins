#!/bin/bash
# Round 8, R8-0: Dragon smoke through ORBIT (the gate).
#SBATCH -J r8-smoke
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-smoke-%j.out
#   sbatch -A m5290 -q debug r8/run_smoke.sh
# Node 0: broker (--plugins dt, throwaway TLS) and the client
# (r8/smoke_dragon.py); node 1: one ORBIT endpoint inside a single-node
# Dragon runtime (`dragon -s radical-orbit-endpoint.py ...`), launched with
# `srun -c 256 --cpu-bind=none` so the runtime sees the whole node.  The
# client names `dragon_native` in its engine config (the DT service always
# names a backend; the endpoint's RADICAL_ORBIT_RHAPSODY_BACKEND is set too).
# Steps, each under a timeout: basic, gil, kill + cleanup + restart +
# reattach, remote (radical.3:8010 -> r3_site, if reachable), pool (endpoint
# restarted under `taskset -c 0-15`), sessions (S = SESSIONS_LIST).
# Knobs: STEPS ("basic gil kill remote pool sessions"), SESSIONS_LIST
# (1,4,16,64), PORT (8181), KILL_WAIT (1: restart after the broker detects
# the loss), POOL_CPUS (taskset list for the pool step, 0-15).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8/env-r8.sh}
R=$X/results/${RES:-r8/r8-0}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8181}
URL=https://$IP0:$PORT
S=$X/r8/smoke_dragon.py
echo "node0 $N0 ($IP0) endpoint node $N1  broker $URL  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)

T=$W/tls/r8-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r8-0-$J; touch $STAMP

RADICAL_ORBIT_LOG_FILE=$L/broker-r8-0-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$J.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; tail -20 $R/broker.console-$J.log; exit 3; }
export RADICAL_ORBIT_LOG_FILE=$L/client-r8-0-$J.log

EPN=r8_ep
EP=
start_ep() {  # tag [prefix...]: endpoint inside a single-node Dragon runtime on node 1
  local tag=$1; shift
  srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8-0-$tag-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
        RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
        DT_TEST_ENDPOINT_TAG=$EPN \
    bash -c "ulimit -Sn \$(ulimit -Hn); exec $* dragon -s $(command -v radical-orbit-endpoint.py) -n $EPN -u $URL -p default --tunnel none" \
    > $R/endpoint.console-$tag-$J.log 2>&1 &
  EP=$!
  local w; w=$(timeout 330 python $X/r8/wait_endpoint.py $URL $EPN 300)
  echo "[$(date -u +%T)] endpoint $tag up after ${w} s"
}
stop_ep() {  # SIGTERM the runtime, then dragon-cleanup on node 1
  srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
  sleep 10
  kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
  srun --overlap -N1 -n1 -w $N1 dragon-cleanup > /dev/null 2>&1
  srun --overlap -N1 -n1 -w $N1 $X/r8/node_probe.sh
}
step() {  # name timeout args...
  local name=$1 tmo=$2; shift 2
  timeout $tmo python $S --broker $URL --endpoint $EPN --ep-node $N1 --state $R/state-$J.json \
    --out $R/smoke-$name-$J-$D.json "$@" > $R/smoke-$name-$J-$D.log 2>&1
  echo "[$(date -u +%T)] $name rc=$? $(tail -1 $R/smoke-$name-$J-$D.log | cut -c1-600)"
}

start_ep main
STEPS=${STEPS:-basic gil kill remote pool sessions}
for s in $STEPS; do
  case $s in
    basic) step basic 400 --step basic ;;
    gil)
      WK=$(python -c "import json;print(json.load(open('$R/smoke-basic-$J-$D.json'))['burst_1000_empty'].get('pids') or 128)" 2>/dev/null || echo 128)
      echo "gil: $WK tasks of 10 s"
      step gil 300 --step gil --workers $WK ;;
    kill)
      srun --overlap -N1 -n1 -w $N1 $X/r8/node_probe.sh
      t0=$(date +%s.%N)
      srun --overlap -N1 -n1 -w $N1 pkill -KILL -u $USER -f dragon 2>/dev/null
      kill -KILL $EP 2>/dev/null; wait $EP 2>/dev/null
      srun --overlap -N1 -n1 -w $N1 dragon-cleanup > $R/dragon-cleanup-kill-$J.log 2>&1
      echo "[$(date -u +%T)] killed and cleaned up in $(echo "$(date +%s.%N) - $t0" | bc) s; node: $(srun --overlap -N1 -n1 -w $N1 $X/r8/node_probe.sh)"
      # KILL_WAIT=1 (rerun): restart only once the broker no longer holds the
      # endpoint as present (run 1 restarted within ~3 s, before detection)
      [ "${KILL_WAIT:-0}" = 1 ] && echo "[$(date -u +%T)] broker lost the endpoint after $(timeout 150 python $X/r8/wait_lost.py $URL $EPN 120) s (from cleanup)"
      start_ep restart
      step reattach 300 --step reattach ;;
    remote)
      code=$(curl -sk -o /dev/null -m 10 -w '%{http_code}' https://95.217.193.116:8010/)
      echo "radical.3:8010 from $N0: http $code"
      if [ "$code" = 200 ]; then
        ( unset RADICAL_ORBIT_BROKER_CERT RADICAL_ORBIT_BROKER_KEY RADICAL_ORBIT_BROKER_TOKEN
          export RADICAL_ORBIT_LOG_FILE=$L/client-r8-0-remote-$J.log
          timeout 300 python $S --broker https://95.217.193.116:8010 --endpoint r3_site \
            --step remote --out $R/smoke-remote-$J-$D.json > $R/smoke-remote-$J-$D.log 2>&1
          echo "[$(date -u +%T)] remote rc=$? $(tail -1 $R/smoke-remote-$J-$D.log | cut -c1-600)" )
      fi ;;
    pool)
      stop_ep
      start_ep taskset taskset -c ${POOL_CPUS:-0-15}
      step pool 400 --step pool
      stop_ep
      start_ep main2 ;;
    sessions) step sessions 900 --step sessions --sessions-list ${SESSIONS_LIST:-1,4,16,64} ;;
  esac
done

stop_ep
kill -TERM $BP; wait $BP 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
