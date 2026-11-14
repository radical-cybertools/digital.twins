#!/bin/bash
# Round 8, R8-B: fan-out, one twin, bursts of K function tasks.
#SBATCH -J r8-b
#SBATCH -C cpu
#SBATCH -N 5
#SBATCH -t 01:10:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-b-%j.out
#   sbatch -A m5290 -q regular r8/run_fanout.sh
# Node 0: broker (--plugins dt, throwaway TLS) and the client
# (r8/bench_fanout.py); nodes 1-4: one site endpoint each.  Rows:
#  dragon_native  endpoints in single-node Dragon runtimes held to 64
#                 physical cores (taskset -c 0-63,128-191: R8-0 showed the
#                 pool follows the launch's CPUs, in physical cores) ->
#                 64 workers per site; layouts one and spread
#  concurrent     the same endpoints, backend concurrent (rhapsody's thread
#                 pool, min(32, cpus + 4) = 32 threads); one and spread
#  process        endpoints restarted under e6-use-cases/p8b_endpoint.py
#                 (concurrent backend with a spawn ProcessPoolExecutor,
#                 P8B_WORKERS=64), not under Dragon; layout one
# Knobs: ROWS ("dragon_native concurrent process"), KS, MS_LIST, REPEATS,
#   CONC_LAYOUTS ("one spread"; the rerun of 61247211's spread row: "spread").
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8/env-r8.sh}
R=$X/results/${RES:-r8/r8-b}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
SN=($(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -4))
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8191}
URL=https://$IP0:$PORT
echo "node0 $N0 ($IP0) sites ${SN[*]}  broker $URL  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8b-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r8b-$J; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r8b-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$J.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; exit 3; }
export RADICAL_ORBIT_LOG_FILE=$L/client-r8b-$J.log
EPS=(); EPIDS=()
start_eps() {  # mode: dragon | process
  EPS=(); EPIDS=()
  for k in 0 1 2 3; do
    name=r8b_s$k
    if [ $1 = dragon ]; then
      cmd="taskset -c 0-63,128-191 dragon -s $(command -v radical-orbit-endpoint.py)"
    else
      cmd="python $PWD/$X/e6-use-cases/p8b_endpoint.py"
    fi
    srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w ${SN[$k]} --export=ALL \
      env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8b-$1-$name-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
          RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
          DT_TEST_ENDPOINT_TAG=$name P8B_WORKERS=64 \
      bash -c "ulimit -Sn \$(ulimit -Hn); exec $cmd -n $name -u $URL -p default --tunnel none" \
      > $R/endpoint.console-$1-$name-$J.log 2>&1 &
    EPIDS+=($!); EPS+=($name)
  done
  for n in ${EPS[@]}; do echo "  $n up after $(timeout 330 python $X/r8/wait_endpoint.py $URL $n 300) s"; done
}
stop_eps() {  # wait only on these steps: a bare `wait` would wait for the broker too
  local ps=()
  for k in 0 1 2 3; do
    srun --overlap -N1 -n1 -w ${SN[$k]} pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n r8b_s$k|p8b_endpoint.py -n r8b_s$k" 2>/dev/null &
    ps+=($!)
  done; wait ${ps[@]}
  sleep 10; kill -TERM ${EPIDS[@]} 2>/dev/null; wait ${EPIDS[@]} 2>/dev/null
  ps=()
  for k in 0 1 2 3; do srun --overlap -N1 -n1 -w ${SN[$k]} dragon-cleanup > /dev/null 2>&1 & ps+=($!); done; wait ${ps[@]}
  EPIDS=(); EPS=()
  sleep 5
}
run() {  # row backend workers layout
  local f=$R/fanout-$1-$4-$J-$D
  R8_BACKEND=$2 R8_WORKERS_PER_NODE=$3 timeout ${RUN_TIMEOUT:-2400} python $X/r8/bench_fanout.py --broker $URL \
    --endpoints $(IFS=,; echo "${EPS[*]}") --layout $4 --backend $2 --workers $3 --row $1 \
    --ks ${KS:-16,64,256,1024} --ms-list ${MS_LIST:-100,10000} --repeats ${REPEATS:-3} \
    $([ $2 = dragon_native ] && echo --empty-k 1024) --out $f.json > $f.log 2>&1
  echo "[$(date -u +%T)] $1 $4 rc=$? breaks: $(python -c "import json;print(json.load(open('$f.json')).get('breaks'))" 2>/dev/null)"
}
for row in ${ROWS:-dragon_native concurrent process}; do
  case $row in
    dragon_native) start_eps dragon; run dragon_native dragon_native 64 one; run dragon_native dragon_native 64 spread ;;
    concurrent) [ ${#EPS[@]} = 4 ] || start_eps dragon
                for lay in ${CONC_LAYOUTS:-one spread}; do run concurrent concurrent 32 $lay; done; stop_eps ;;
    process) start_eps process; run process concurrent 64 one; stop_eps ;;
  esac
done
[ ${#EPIDS[@]} -gt 0 ] && stop_eps
kill -TERM $BP; wait $BP 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
