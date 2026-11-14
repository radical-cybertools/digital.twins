#!/bin/bash
# Round 8 (optional): profile the broker at its ceiling.
#SBATCH -J r8-bprof
#SBATCH -C cpu
#SBATCH -N 3
#SBATCH -t 00:35:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-bprof-%j.out
#   sbatch -A m5290 -q regular r8/run_broker_profile.sh
# R8-2's setup (broker on node 0, one Dragon endpoint on node 1, the client
# r8/bench_engine.py on node 2) at 256 twins in one session, no-op tasks,
# 60 s of closed loop.  Two runs, a fresh broker and endpoint each:
#   plain     /proc samplers only (the undisturbed rate)
#   profiled  the broker under r8/frame_counter.py (frames per second by
#             kind) and, 5 s into the load window, py-spy dump plus
#             `py-spy record --rate 20 --idle --nonblocking` for 30 s on
#             the broker (folded); r8/folded_top.py summarizes it.
# Knobs: TWINS (256), SECONDS_ (60), PORT (8261).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8/env-r8.sh}
R=$X/results/${RES:-r8/broker-profile}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
N2=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 2p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8261}
URL=https://$IP0:$PORT
SAMPLER=$PWD/$X/r8/proc_sampler.sh
PYSPY=$(command -v py-spy)
echo "node0 $N0 ($IP0) endpoint $N1 client $N2  broker $URL  py-spy $($PYSPY --version)  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8bp-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r8bp-$J; touch $STAMP
for run in plain profiled; do
  tag=$run-$J
  bcmd=(radical-orbit-broker.py)
  if [ $run = profiled ]; then
    bcmd=(python $X/r8/frame_counter.py "$(command -v radical-orbit-broker.py)")
    export FRAME_COUNT_FILE=$PWD/$R/frames-$tag-$D.jsonl
  fi
  RADICAL_ORBIT_LOG_FILE=$L/broker-r8bp-$tag.log RADICAL_ORBIT_BROKER_URL=$URL \
    "${bcmd[@]}" --host $IP0 --port $PORT --plugins dt > $R/broker.console-$tag.log 2>&1 &
  BP=$!
  unset FRAME_COUNT_FILE
  sleep 8
  kill -0 $BP 2>/dev/null || { echo "$run: broker died"; continue; }
  EPN=r8bp_ep_$run
  srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8bp-$tag.log RADICAL_ORBIT_BROKER_URL=$URL \
        RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
        DT_TEST_ENDPOINT_TAG=$EPN \
    bash -c "ulimit -Sn \$(ulimit -Hn); exec dragon -s $(command -v radical-orbit-endpoint.py) -n $EPN -u $URL -p default --tunnel none" \
    > $R/endpoint.console-$tag.log 2>&1 &
  EP=$!
  echo "$run endpoint up after $(timeout 330 python $X/r8/wait_endpoint.py $URL $EPN 300) s"
  $SAMPLER $BP > $R/broker-proc-$tag-$D.txt 2>/dev/null &
  SAMP=$!
  srun --overlap -N1 -n1 -w $N1 $SAMPLER -f "radical-orbit-endpoint.py -n $EPN" \
    > $R/endpoint-proc-$tag-$D.txt 2> $R/endpoint-proc-$tag-$D.err &
  ESAMP=$!
  M=$PWD/$R/load-$tag; f=$R/engine-$tag-$D
  if [ $run = profiled ]; then
    ( n=${TWINS:-256}
      until [ -f $M.n$n ]; do sleep 0.5; done; sleep 5
      P=$PWD/$R/pyspy-$tag
      timeout 60 $PYSPY dump --pid $BP > $P-broker-dump.txt 2>&1
      timeout 240 $PYSPY record --pid $BP --rate 20 --idle --nonblocking --duration 30 \
        --format raw -o $P-broker.folded > $P-broker-record.log 2>&1
      echo "py-spy done $(date -u +%T)" ) > $R/pyspy-$tag.log 2>&1 &
  fi
  timeout 900 srun --overlap -N1 -n1 -w $N2 --export=ALL \
    python $X/r8/bench_engine.py --broker $URL --endpoint $EPN --work-ms 0 --per-session 0 \
    --twins ${TWINS:-256} --seconds ${SECONDS_:-60} --load-marker $M --out $f.json > $f.log 2>&1
  echo "[$(date -u +%T)] $run rc=$? $(grep '^N=' $f.log | cut -c1-220)"
  [ $run = profiled ] && { sleep 5; cat $R/pyspy-$tag.log; }
  srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
  sleep 10; kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
  kill $SAMP $ESAMP 2>/dev/null
  srun --overlap -N1 -n1 -w $N1 dragon-cleanup > /dev/null 2>&1
  kill -TERM $BP; wait $BP 2>/dev/null
  sleep 3
done
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
