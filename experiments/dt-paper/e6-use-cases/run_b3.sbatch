#!/bin/bash
#SBATCH -J b3-p8b
#SBATCH -C gpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/b3-p8b-%j.out
# P8b: the xGFabric WindField twin end to end with real surrogates, on one
# A100 node over loopback.
#   sbatch -A m5290_g -q debug run_b3.sbatch     (RUNTIME=1080 by default)
# Round 2b B3: round 1 P8b (dt-pm2 run_p8b.sbatch, run 6) on the 72e4f7c stack:
# venv ve2b-xgf = round 1 TF conda env (--system-site-packages) + the 72e4f7c
# pins (asyncflow cf638d9, rhapsody 1937801 with #125, orbit b10479c, ROSE
# 9cc47a5, digitaltwin 72e4f7c).  Only the venv, paths and result names differ.
# 1. precheck: xGFabric's own tk_fno_eval / tk_pinn_eval on the September
#    archives (needs the fix/pinn-eval branch checked out in $XGF_DIR)
# 2. broker (--plugins dt) + endpoint (concurrent, notify window 0, the only
#    process that sees the GPU) + fake sensor + measuring client, ORBIT data
#    plane as in the September demo; throwaway TLS; isolation check.
# Never uses demo/Sep_04_endpoint.sh: it points at ~/.radical/orbit.
set -uo pipefail
W=/pscratch/sd/m/merzky/dt-pm3
W1=/pscratch/sd/m/merzky/dt-pm2   # round 1: TF conda env, xGFabric checkout (PR #17 branch)
ENV=$W1/xgf/env        # conda base: TF, nvidia wheels
VE=$W/ve2b-xgf          # the stack
PY=$VE/bin/python
export XGF_DIR=$W1/xGFabric
cd $W/digital.twins
X=experiments/dt-paper
E=$X/e6-use-cases
R=$X/results/b3; mkdir -p $R
L=$W/orbit-logs
D=stack2b-20261107
TAG=${TAG:-}
export PATH=$VE/bin:$ENV/bin:$PATH
export TF_CPP_MIN_LOG_LEVEL=1
export PLAYGROUND_DIR=$W/xgf-b3/playground-$SLURM_JOB_ID
mkdir -p $PLAYGROUND_DIR/profiler/pi_profiler $PLAYGROUND_DIR/profiler/nersc_profiler
cp $XGF_DIR/tasks/profiler/pi_profiler/data.csv.sample $PLAYGROUND_DIR/profiler/pi_profiler/data.csv
NV=$(ls -d $ENV/lib/python3.12/site-packages/nvidia/*/lib | paste -sd:)
GPU_LD="$NV${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
echo "xGFabric $(git -C $XGF_DIR rev-parse --short HEAD) ($(git -C $XGF_DIR rev-parse --abbrev-ref HEAD)), playground $PLAYGROUND_DIR"

# 1. precheck
LD_LIBRARY_PATH=$GPU_LD TF_FORCE_GPU_ALLOW_GROWTH=true PLAYGROUND_DIR=$W/xgf-b3/check-$SLURM_JOB_ID \
  $PY $E/p8b_check_eval.py --xgf $XGF_DIR > $R/p8b-check-eval$TAG.log 2>&1
rc=$?; echo "precheck rc=$rc"; grep '^{' $R/p8b-check-eval$TAG.log
[ $rc = 0 ] || { tail -20 $R/p8b-check-eval$TAG.log; exit 5; }

# 2. the twin
PORT=8431
URL=https://127.0.0.1:$PORT
T=$W/tls/p8b-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm3-b3" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
$PY -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
export RADICAL_ORBIT_BROKER_URL=$URL
export DT_STREAM_BACKEND=orbit
export DT_INFERENCE_ENDPOINT=dt_p8b_ep DT_LEARNING_ENDPOINT=dt_p8b_ep
export DT_INFERENCE_BACKEND=concurrent DT_LEARNING_BACKEND=concurrent
export PYTHONPATH=$XGF_DIR

touch $W/orbit-stamp-b3
cd $XGF_DIR
CUDA_VISIBLE_DEVICES= RADICAL_ORBIT_LOG_FILE=$L/broker-b3-$SLURM_JOB_ID.log \
  $PY $VE/bin/radical-orbit-broker.py --host 127.0.0.1 --port $PORT --plugins dt \
  > $W/digital.twins/$R/p8b-broker.console$TAG.log 2>&1 &
BP=$!
sleep 10
kill -0 $BP || { echo "broker died"; tail -20 $W/digital.twins/$R/p8b-broker.console$TAG.log; exit 3; }

LD_LIBRARY_PATH=$GPU_LD RADICAL_ORBIT_LOG_FILE=$L/endpoint-b3-$SLURM_JOB_ID.log \
RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 TF_FORCE_GPU_ALLOW_GROWTH=true \
XGF_WORKSPACE=$PLAYGROUND_DIR \
  $PY $W/digital.twins/$E/p8b_endpoint.py -n dt_p8b_ep -u $URL -p default --tunnel none \
  > $W/digital.twins/$R/p8b-endpoint.console$TAG.log 2>&1 &
EP=$!
sleep 20

CUDA_VISIBLE_DEVICES= RADICAL_ORBIT_LOG_FILE=$L/sensor-b3-$SLURM_JOB_ID.log \
  $PY $W/digital.twins/$E/p8b_sensor.py --interval ${INTERVAL:-1} \
  > $W/digital.twins/$R/p8b-sensor$TAG.log 2>&1 &
SP=$!

CUDA_VISIBLE_DEVICES= RADICAL_ORBIT_LOG_FILE=$L/client-b3-$SLURM_JOB_ID.log \
  $PY $W/digital.twins/$E/p8b_client.py --xgf $XGF_DIR --runtime ${RUNTIME:-1080} \
  --probe ${PROBE:-3} --out $W/digital.twins/$R/p8b-twin-pm$TAG-$D.json \
  > $W/digital.twins/$R/p8b-client$TAG.log 2>&1
echo "client rc=$?"
grep -E "summary|first seen|failed" $W/digital.twins/$R/p8b-client$TAG.log

stop() {  # pid: TERM, then KILL after 15 s (run 4 hung here into the time limit)
  kill -TERM $1 2>/dev/null
  for i in $(seq 15); do kill -0 $1 2>/dev/null || return 0; sleep 1; done
  echo "pid $1 still alive after TERM, killing"; kill -KILL $1 2>/dev/null
}
stop $SP; stop $EP; stop $BP
echo "--- GPU use by the endpoint (TF device lines):"
grep -h -i -E "created device|gpu:0|cuda" $W/digital.twins/$R/p8b-endpoint.console$TAG.log | head -5
echo "--- playground models:"
find $PLAYGROUND_DIR -name "*.tar.gz" | sed "s|$PLAYGROUND_DIR/||"
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $W/orbit-stamp-b3 | tee $W/digital.twins/$R/orbit-isolation-check-p8b$TAG.txt
echo "--- end"
