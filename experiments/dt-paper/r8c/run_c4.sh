#!/bin/bash
# Round 8c, C4: the E4 figure (round 3 T4/T5, round 2 S2 P7-remote) on dragon_native.
#SBATCH -J r8c-c4
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:45:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8c-c4-%j.out
#   sbatch -A m5290 -q regular r8c/run_c4.sh
# (a) e4-hot-swap/bench_swap.py: swap a running investigator, time to the
#     first answer from the new one, c = 1 and 50, 20 swaps 0.5 s apart,
#     5 repeats; local (harness under dragon -s, local dragon_native pool,
#     the twin's stream through this job's broker) and through ORBIT to a
#     Dragon endpoint on node 1 (--backends dragon_native).
# (b) e4-hot-swap/bench_model_update.py: publish to first use, intervals
#     1 / 0.1 / 0.01 s, --seconds per interval; local and ORBIT 5 repeats,
#     through radical.3:8010 3 repeats (round 2 S2 had 3), with a Dragon
#     endpoint on node 1 registered there.
# (c) e2-scaling/bench_publish.py: inference throughput while models are
#     published at 0 / 1 / 10 / 100 per second, c = 1 and c = 50 (the dip),
#     10 s per rate, 5 repeats, local dragon_native.
# Local dragon_native runs use the backend default pool (one worker per physical
# core, --workers 0), as R8-1 and the endpoints, not the original pool of 8.
# Knobs: REPEATS (5), R3_REPEATS (3), UPD_SECONDS (10), PARTS ("A B C"), PORT (8851).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8c/env-r8c.sh}
R=$X/results/${RES:-r8c/c4}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8851}
URL=https://$IP0:$PORT
R3=https://95.217.193.116:8010
SW=$X/e4-hot-swap/bench_swap.py
UP=$X/e4-hot-swap/bench_model_update.py
PB=$X/e2-scaling/bench_publish.py
export R8_BACKEND=dragon_native
echo "node0 $N0 ($IP0) endpoint $N1  broker $URL  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8c-c4-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r8c-c4-$J; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r8c-c4-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$J.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; exit 3; }
export RADICAL_ORBIT_LOG_FILE=$L/client-r8c-c4-$J.log
start_ep() {  # name url
  local n=$1 u=$2
  srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8c-c4-$n-$J.log RADICAL_ORBIT_BROKER_URL=$u \
        RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
        DT_TEST_ENDPOINT_TAG=$n \
    bash -c "ulimit -Sn \$(ulimit -Hn); exec dragon -s $(command -v radical-orbit-endpoint.py) -n $n -u $u -p default --tunnel none" \
    > $R/endpoint.console-$n-$J.log 2>&1 &
  EP=$!
  echo "endpoint $n up after $(timeout 330 python $X/r8/wait_endpoint.py $u $n 300) s"
}
stop_ep() {  # name
  srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $1" 2>/dev/null
  sleep 10; kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
  srun --overlap -N1 -n1 -w $N1 dragon-cleanup > /dev/null 2>&1
}
r3() {  # radical.3 with its default credentials (read only)
  ( unset RADICAL_ORBIT_BROKER_CERT RADICAL_ORBIT_BROKER_KEY RADICAL_ORBIT_BROKER_TOKEN
    export RADICAL_ORBIT_LOG_FILE=$L/client-r8c-c4-r3-$J.log
    "$@" )
}
local_run() {  # out-prefix harness args...   (under dragon -s, local dragon_native)
  local f=$1; shift
  timeout ${CELL_TIMEOUT:-600} dragon -s "$@" --workers 0 --local-backend dragon_native --stream-broker $URL \
    --out $f.json > $f.log 2>&1
  local rc=$?
  dragon-cleanup > /dev/null 2>&1 || true
  kill -0 $BP 2>/dev/null || { echo "broker died after dragon-cleanup"; exit 4; }
  return $rc
}
on() { [[ " ${PARTS:-A B C} " == *" $1 "* ]]; }
NR=${REPEATS:-5}
US=${UPD_SECONDS:-10}
# --- local parts first (no endpoint needed)
if on A; then for k in $(seq 1 $NR); do for c in 1 50; do
  f=$R/swap-local-dragon-c$c-r$k-$J-$D
  local_run $f $SW --concurrency $c --swaps 20 --interval 0.5
  echo "[$(date -u +%T)] A local c$c r$k rc=$? $(grep -h swaps= $f.log | cut -c1-160)"
done; done; fi
if on B; then for k in $(seq 1 $NR); do
  f=$R/update-local-dragon-r$k-$J-$D
  local_run $f $UP --intervals 1,0.1,0.01 --seconds $US
  echo "[$(date -u +%T)] B local r$k rc=$? $(grep -h interval $f.log | tr '\n' '|' | cut -c1-250)"
done; fi
if on C; then for k in $(seq 1 $NR); do
  f=$R/publish-local-dragon-c1-r$k-$J-$D
  local_run $f $PB --concurrency 1 --rates 0,1,10,100 --seconds 10
  echo "[$(date -u +%T)] C c1 r$k rc=$? $(grep -h rate= $f.log | tr '\n' '|' | cut -c1-250)"
  f=$R/dip-local-dragon-c50-r$k-$J-$D
  local_run $f $PB --concurrency 50 --rates 0,1,10,100 --seconds 10
  echo "[$(date -u +%T)] C c50 r$k rc=$? $(grep -h rate= $f.log | tr '\n' '|' | cut -c1-250)"
done; fi
# --- through ORBIT, cross-node
if on A || on B; then
  EPN=r8c_c4_ep; start_ep $EPN $URL
  if on A; then for k in $(seq 1 $NR); do for c in 1 50; do
    f=$R/swap-orbit-dragon-c$c-r$k-$J-$D
    timeout 600 python $SW --broker $URL --endpoint $EPN --backends dragon_native \
      --concurrency $c --swaps 20 --interval 0.5 --out $f.json > $f.log 2>&1
    echo "[$(date -u +%T)] A orbit c$c r$k rc=$? $(grep -h swaps= $f.log | cut -c1-160)"
  done; done; fi
  if on B; then for k in $(seq 1 $NR); do
    f=$R/update-orbit-dragon-r$k-$J-$D
    timeout 600 python $UP --broker $URL --endpoint $EPN --backends dragon_native \
      --intervals 1,0.1,0.01 --seconds $US --out $f.json > $f.log 2>&1
    echo "[$(date -u +%T)] B orbit r$k rc=$? $(grep -h interval $f.log | tr '\n' '|' | cut -c1-250)"
  done; fi
  stop_ep $EPN
fi
# --- through radical.3:8010
if on B; then
  R3OK=$(curl -sk -o /dev/null -m 10 -w '%{http_code}' $R3/)
  echo "radical.3:8010 http $R3OK; connect s (median of 20): $(for i in $(seq 20); do curl -sk -o /dev/null -m 10 -w '%{time_connect}\n' $R3/; done | sort -n | sed -n 10p)"
  if [ "$R3OK" = 200 ]; then
    EPR=pm_r8c_c4_$J
    r3 start_ep $EPR $R3
    for k in $(seq 1 ${R3_REPEATS:-3}); do
      f=$R/update-remote-dragon-r$k-$J-$D
      r3 timeout 900 python $UP --broker $R3 --endpoint $EPR --backends dragon_native \
        --intervals 1,0.1,0.01 --seconds $US --out $f.json > $f.log 2>&1
      echo "[$(date -u +%T)] B remote r$k rc=$? $(grep -h interval $f.log | tr '\n' '|' | cut -c1-250)"
    done
    r3 stop_ep $EPR
  fi
fi
kill -TERM $BP; wait $BP 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
