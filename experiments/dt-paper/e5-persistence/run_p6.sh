#!/bin/bash
#SBATCH -J dt-p6
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm2/logs/p6-%j.out
# P6: E5 learning-endpoint loss (10 SIGKILLs) and client reattach (10x),
# loopback on one node.  Broker hosts dt only; the inference endpoint runs
# for the whole job, bench_endpoint_loss.py owns the learning endpoint.
#   sbatch -A m5290 -q regular run_p6.sh
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm2/env.sh
R=$X/results/p6; mkdir -p $R
L=$W/orbit-logs
PORT=8231
URL=https://127.0.0.1:$PORT

T=$W/tls/p6-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm2-p6" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

touch $W/orbit-stamp-p6
RADICAL_ORBIT_LOG_FILE=$L/broker-p6.log \
  radical-orbit-broker.py --host 127.0.0.1 --port $PORT --plugins dt \
  > $R/broker-p6.console.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP || { echo "broker died"; tail -20 $R/broker-p6.console.log; exit 3; }
export RADICAL_ORBIT_LOG_FILE=$L/client-p6.log

RADICAL_ORBIT_LOG_FILE=$L/endpoint-dt_p6_inference_ep.log \
RADICAL_ORBIT_BROKER_URL=$URL \
RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
DT_TEST_ENDPOINT_TAG=dt_p6_inference_ep \
  radical-orbit-endpoint.py -n dt_p6_inference_ep -u $URL -p default --tunnel none \
  > $R/endpoint-inference.console.log 2>&1 &
EP=$!
sleep 15

python $X/e5-persistence/bench_endpoint_loss.py --broker $URL \
    --inference dt_p6_inference_ep --kills ${KILLS:-10} --reattaches ${REATTACHES:-10} \
    --logs $L --out $R/endpoint-loss-pm${TAG:-}-$D.json > $R/endpoint-loss-pm${TAG:-}-$D.log 2>&1
echo "bench rc=$?"
grep -E "^kill|^reattach|FAILED" $R/endpoint-loss-pm${TAG:-}-$D.log

kill -TERM $EP; wait $EP
kill -TERM $BP; wait $BP
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $W/orbit-stamp-p6 | tee $R/orbit-isolation-check-$D.txt
echo "--- end"
