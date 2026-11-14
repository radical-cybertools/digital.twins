#!/bin/bash
# Round 8, R8-5 (stretch): E5 endpoint loss on Dragon.
#SBATCH -J r8-5
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:45:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-5-%j.out
#   sbatch -A m5290 -q regular r8/run_persistence.sh
# As round 2's s1/run_s1_p6.sh, with both endpoints on dragon_native: node 0
# runs the broker (--plugins dt, throwaway TLS) and the inference endpoint in
# its own single-node Dragon runtime; node 1 runs
# e5-persistence/bench_endpoint_loss.py, which owns the learning endpoint:
# it starts it under `dragon -s` in its own session (E5_LAUNCH), kills the
# whole runtime (SIGKILL to the process group), runs dragon-cleanup on node
# 1 (E5_CLEANUP; the inference runtime on node 0 is untouched) and restarts
# it, 10 times; then 10 client reattaches.  E5_BACKEND=dragon_native.
# Knobs: KILLS (10), REATTACHES (10), PORT (8251).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8/env-r8.sh}
R=$X/results/${RES:-r8/r8-5}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8251}
URL=https://$IP0:$PORT
export E5_BACKEND=dragon_native R8_BACKEND=dragon_native
echo "node0 $N0 ($IP0, broker + inference endpoint) node1 $N1 (harness + learning endpoint)  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8-5-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token) RADICAL_ORBIT_BROKER_URL=$URL
STAMP=$W/orbit-stamp-r8-5-$J; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r8-5-$J.log \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$J.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; exit 3; }
INF=r8_5_inference_ep
RADICAL_ORBIT_LOG_FILE=$L/endpoint-$INF-$J.log RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native \
RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 DT_TEST_ENDPOINT_TAG=$INF \
  dragon -s $(command -v radical-orbit-endpoint.py) -n $INF -u $URL -p default --tunnel none \
  > $R/endpoint-inference.console-$J.log 2>&1 &
EP=$!
echo "inference endpoint up after $(timeout 330 python $X/r8/wait_endpoint.py $URL $INF 300) s"
export RADICAL_ORBIT_LOG_FILE=$L/client-r8-5-$J.log
timeout ${RUN_TIMEOUT:-2400} srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w $N1 --export=ALL \
  env E5_LAUNCH="dragon -s" E5_CLEANUP=dragon-cleanup RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
  bash -c "ulimit -Sn \$(ulimit -Hn); exec python $X/e5-persistence/bench_endpoint_loss.py --broker $URL \
    --inference $INF --learning r8_5_learning_ep --kills ${KILLS:-10} --reattaches ${REATTACHES:-10} \
    --logs $L --out $R/endpoint-loss-$J-$D.json" > $R/endpoint-loss-$J-$D.log 2>&1
echo "bench rc=$?"
grep -E "^kill|^reattach|FAILED|Error" $R/endpoint-loss-$J-$D.log | cut -c1-300
srun --overlap -N1 -n1 -w $N1 dragon-cleanup > /dev/null 2>&1
kill -TERM $EP 2>/dev/null; sleep 10; kill -KILL $EP 2>/dev/null; wait $EP 2>/dev/null
kill -TERM $BP; wait $BP 2>/dev/null
dragon-cleanup > /dev/null 2>&1   # after the broker: node 0's Dragon runtime only
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
