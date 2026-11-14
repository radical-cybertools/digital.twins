#!/bin/bash
#SBATCH -J r8-e
#SBATCH -C gpu
#SBATCH -N 1
#SBATCH -t 01:15:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-e-%j.out
# Round 8, R8-E: WindField decomposed.  P8b (e6-use-cases/run_b3.sbatch) on
# the round 8 stack with the engines as intended: inference and learning on
# dragon_native, one A100 node, the September weights for the precheck,
# REPEATS runs of RUNTIME s each (fresh broker, endpoint, sensor, client per
# run; dragon-cleanup after each).
#   sbatch -A m5290_g -q regular r8/run_r8e.sbatch          (WARM=0 or 1)
# venv ve8-xgf (TF conda env + round 8 pins); xGFabric = dt-pm8/xGFabric on
# the local branch r8/timings (3adefa8 + task timings; + the warm-model
# cache, active with WARM=1 -> R8_WARM_MODEL=1).  The endpoint runs inside a
# single-node Dragon runtime (`dragon -s radical-orbit-endpoint.py`), and the
# twin's engines name dragon_native (DT_*_BACKEND, twin_service_real's
# knobs).  Task-side times go to $R8_TIMING_DIR (one jsonl per process) and
# with each answer ("t"); the client records send / receive epochs.
set -uo pipefail
W=/pscratch/sd/m/merzky/dt-pm8
ENV=/pscratch/sd/m/merzky/dt-pm2/xgf/env
VE=$W/ve8-xgf
PY=$VE/bin/python
export XGF_DIR=$W/xGFabric
cd $W/digital.twins
X=experiments/dt-paper
E=$X/e6-use-cases
WARM=${WARM:-0}
R=$X/results/r8/r8-e/warm$WARM; mkdir -p $R
L=$W/orbit-logs
D=stack-r8-20261114
J=$SLURM_JOB_ID
export PATH=$VE/bin:$ENV/bin:$PATH
export TF_CPP_MIN_LOG_LEVEL=1 R8_FS=/pscratch R8_BACKEND=dragon_native
NV=$(ls -d $ENV/lib/python3.12/site-packages/nvidia/*/lib | paste -sd:)
GPU_LD="$NV${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
echo "xGFabric $(git -C $XGF_DIR rev-parse --short HEAD) ($(git -C $XGF_DIR rev-parse --abbrev-ref HEAD)) warm=$WARM  $(nvidia-smi -L | head -1)"
ulimit -Sn $(ulimit -Hn)

# precheck once per job: xGFabric's own evals on the September archives
LD_LIBRARY_PATH=$GPU_LD TF_FORCE_GPU_ALLOW_GROWTH=true PLAYGROUND_DIR=$W/xgf/check-$J \
  $PY $E/p8b_check_eval.py --xgf $XGF_DIR --concurrent 1 > $R/check-eval-$J.log 2>&1
rc=$?; echo "precheck rc=$rc"; grep '^{' $R/check-eval-$J.log
[ $rc = 0 ] || { tail -20 $R/check-eval-$J.log; exit 5; }

stop() {  # pid: TERM, then KILL after 15 s
  kill -TERM $1 2>/dev/null
  for i in $(seq 15); do kill -0 $1 2>/dev/null || return 0; sleep 1; done
  echo "pid $1 still alive after TERM, killing"; kill -KILL $1 2>/dev/null
}

for r in $(seq 1 ${REPEATS:-3}); do
  tag=r$r-$J
  PG=$W/xgf/playground-$tag
  TD=$R/timing-$tag; mkdir -p $TD $PG/profiler/pi_profiler $PG/profiler/nersc_profiler
  cp $XGF_DIR/tasks/profiler/pi_profiler/data.csv.sample $PG/profiler/pi_profiler/data.csv
  PORT=$((8440 + r))
  URL=https://127.0.0.1:$PORT
  T=$W/tls/r8e-$tag; mkdir -p $T; chmod 700 $W/tls $T
  openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8-r8e" \
      -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
      -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
  $PY -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
  chmod 600 $T/*
  (
  export PLAYGROUND_DIR=$PG R8_TIMING_DIR=$PWD/$TD
  [ $WARM = 1 ] && export R8_WARM_MODEL=1
  export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
  export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token) RADICAL_ORBIT_BROKER_URL=$URL
  export DT_STREAM_BACKEND=orbit
  export DT_INFERENCE_ENDPOINT=dt_r8e_ep DT_LEARNING_ENDPOINT=dt_r8e_ep
  export DT_INFERENCE_BACKEND=dragon_native DT_LEARNING_BACKEND=dragon_native
  export PYTHONPATH=$XGF_DIR
  STAMP=$W/orbit-stamp-r8e-$tag; touch $STAMP
  cd $XGF_DIR
  CUDA_VISIBLE_DEVICES= RADICAL_ORBIT_LOG_FILE=$L/broker-r8e-$tag.log \
    $PY $VE/bin/radical-orbit-broker.py --host 127.0.0.1 --port $PORT --plugins dt \
    > $W/digital.twins/$R/broker.console-$tag.log 2>&1 &
  BP=$!
  sleep 10
  kill -0 $BP || { echo "r$r: broker died"; exit 3; }
  LD_LIBRARY_PATH=$GPU_LD RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8e-$tag.log \
  RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 TF_FORCE_GPU_ALLOW_GROWTH=true \
  XGF_WORKSPACE=$PG \
    dragon -s $VE/bin/radical-orbit-endpoint.py -n dt_r8e_ep -u $URL -p default --tunnel none \
    > $W/digital.twins/$R/endpoint.console-$tag.log 2>&1 &
  EP=$!
  w=$(timeout 200 $PY $W/digital.twins/$X/r8/wait_endpoint.py $URL dt_r8e_ep 180); echo "r$r: endpoint up after $w s"
  CUDA_VISIBLE_DEVICES= RADICAL_ORBIT_LOG_FILE=$L/sensor-r8e-$tag.log \
    $PY $W/digital.twins/$E/p8b_sensor.py --interval ${INTERVAL:-1} \
    > $W/digital.twins/$R/sensor-$tag.log 2>&1 &
  SP=$!
  CUDA_VISIBLE_DEVICES= RADICAL_ORBIT_LOG_FILE=$L/client-r8e-$tag.log \
    timeout $(( ${RUNTIME:-1200} + 300 )) $PY $W/digital.twins/$E/p8b_client.py --xgf $XGF_DIR \
    --runtime ${RUNTIME:-1200} --probe ${PROBE:-3} --out $W/digital.twins/$R/twin-$tag-$D.json \
    > $W/digital.twins/$R/client-$tag.log 2>&1
  echo "r$r: client rc=$? $(grep -h 'summary' $W/digital.twins/$R/client-$tag.log | cut -c1-400)"
  stop $SP; stop $EP; stop $BP
  dragon-cleanup > /dev/null 2>&1
  ( cd $PG && find . -name "*.tar.gz" -o -name "*partition*" | xargs -r ls -l ) > $W/digital.twins/$R/archives-$tag.txt 2>&1
  echo "r$r: archives $(wc -l < $W/digital.twins/$R/archives-$tag.txt)"
  echo "--- ~/.radical/orbit newer than stamp (must be empty):"
  find ~/.radical/orbit -newer $STAMP | tee $W/digital.twins/$R/orbit-isolation-check-$tag.txt
  )
done
echo "--- end $(date -u +%FT%TZ)"
