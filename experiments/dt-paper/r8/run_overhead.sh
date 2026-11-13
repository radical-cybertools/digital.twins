#!/bin/bash
# Round 8, R8-1: E1 in-situ overhead on Dragon.
#SBATCH -J r8-1
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:50:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-1-%j.out
#   sbatch -A m5290 -q regular r8/run_overhead.sh
# e1-overhead/bench_dt_insitu.py, rows bare / investigator / agent, at task
# costs --work-ms 0.58 (E1's), 20 (PINN) and 120 (FNO, CPU-bound), REPEATS
# repeats, each cell its own process:
#   local-dragon   the harness under `dragon -s` on node 0, local
#                  dragon_native pool (one worker per physical core)
#   orbit-dragon   tasks on a Dragon endpoint on node 1 through the broker on
#                  node 0, --backends dragon_native
#   local-conc / orbit-conc   the concurrent rows at 0.58 ms only (E1
#                  continuity): local process pool, and the endpoint's
#                  concurrent backend
# Knobs: REPEATS (5), WORKS ("0.58 20 120"), TASKS (200), CONC (50), PORT (8211).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8/env-r8.sh}
R=$X/results/${RES:-r8/r8-1}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8211}
URL=https://$IP0:$PORT
H=$X/e1-overhead/bench_dt_insitu.py
echo "node0 $N0 ($IP0) endpoint $N1  broker $URL  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8-1-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r8-1-$J; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r8-1-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$J.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; exit 3; }
export RADICAL_ORBIT_LOG_FILE=$L/client-r8-1-$J.log
EPN=r8_1_ep
srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w $N1 --export=ALL \
  env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8-1-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
      RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
      DT_TEST_ENDPOINT_TAG=$EPN \
  bash -c "ulimit -Sn \$(ulimit -Hn); exec dragon -s $(command -v radical-orbit-endpoint.py) -n $EPN -u $URL -p default --tunnel none" \
  > $R/endpoint.console-$J.log 2>&1 &
EP=$!
echo "endpoint up after $(timeout 330 python $X/r8/wait_endpoint.py $URL $EPN 300) s"
cell() {  # label work_ms args...
  local lab=$1 wk=$2; shift 2
  local f=$R/insitu-$lab-w$wk-r$r-$J-$D
  timeout ${CELL_TIMEOUT:-600} "$@" --work-ms $wk --tasks ${TASKS:-200} --concurrent ${CONC:-50} \
    --out $f.json > $f.log 2>&1
  echo "[$(date -u +%T)] $lab w=$wk r$r rc=$? $(grep -E 'p50=|req/s' $f.log | sed 's/  */ /g' | cut -c1-90 | tr '\n' '|')"
  if [ $lab = local-dragon ]; then  # only the local Dragon runtime left anything on node 0
    dragon-cleanup > /dev/null 2>&1 || true
    kill -0 $BP 2>/dev/null || { echo "broker died after dragon-cleanup"; exit 4; }
  fi
}
for r in $(seq 1 ${REPEATS:-5}); do
  for wk in ${WORKS:-0.58 20 120}; do
    R8_BACKEND=dragon_native cell local-dragon $wk dragon -s $H --local-backend dragon_native
    R8_BACKEND=dragon_native cell orbit-dragon $wk python $H --broker $URL --endpoint $EPN --backends dragon_native
  done
  R8_BACKEND=concurrent R8_WORKERS_PER_NODE=cpu-count cell local-conc 0.58 python $H
  R8_BACKEND=concurrent R8_WORKERS_PER_NODE=32-threads cell orbit-conc 0.58 python $H --broker $URL --endpoint $EPN --backends concurrent
done
srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
sleep 10; kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
srun --overlap -N1 -n1 -w $N1 dragon-cleanup > /dev/null 2>&1
kill -TERM $BP; wait $BP 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
