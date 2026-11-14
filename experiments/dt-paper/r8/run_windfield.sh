#!/bin/bash
# Round 8, R8-C: WindField-like twins at scale on one broker.
#SBATCH -J r8-c
#SBATCH -C cpu
#SBATCH -N 6
#SBATCH -t 01:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-c-%j.out
#   sbatch -A m5290 -q regular r8/run_windfield.sh
# Node 0: broker (--plugins dt, throwaway TLS, ORBIT data plane), the
# client with the twins' stream publishers and probes
# (r8/bench_windfield_scale.py); node 1: the inference endpoint; nodes 2-5:
# four learning endpoints; every endpoint in a single-node Dragon runtime
# on its whole node (dragon_native, 128 workers).  One row per repeat since
# 2026-11-14: all twins in one DT service session (one experiment), N = 1 ..
# 1024 until the break (job 61258719 ran session groups of 16 before the
# change: its N <= 16 points were one session anyway).  A fresh broker and endpoints per
# repeat; broker and inference endpoint sampled from /proc.
# Knobs: REPEATS ("1 2"), TWINS (1,4,16,64,128,256), MODEL_MB (10), PORT (8241).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8/env-r8.sh}
R=$X/results/${RES:-r8/r8-c}; mkdir -p $R $W/models
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
SN=($(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -5))
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8241}
URL=https://$IP0:$PORT
SAMPLER=$PWD/$X/r8/proc_sampler.sh
MB=${MODEL_MB:-10}
MP=$W/models/r8-model-${MB}MB.bin
[ -s $MP ] || head -c $(python3 -c "print(int($MB * 2**20))") /dev/urandom > $MP
export DT_STREAM_BACKEND=orbit R8_BACKEND=dragon_native
echo "node0 $N0 ($IP0) inference ${SN[0]} learning ${SN[*]:1}  broker $URL  model $MP  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8c-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token) RADICAL_ORBIT_BROKER_URL=$URL
STAMP=$W/orbit-stamp-r8c-$J; touch $STAMP
for r in ${REPEATS:-1 2}; do
  tag=r$r-$J
  RADICAL_ORBIT_LOG_FILE=$L/broker-r8c-$tag.log \
    radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$tag.log 2>&1 &
  BP=$!
  sleep 8
  kill -0 $BP 2>/dev/null || { echo "r$r: broker died"; continue; }
  EPIDS=()
  names=(r8c_inf_$r r8c_l0_$r r8c_l1_$r r8c_l2_$r r8c_l3_$r)
  for k in 0 1 2 3 4; do
    srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w ${SN[$k]} --export=ALL \
      env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8c-${names[$k]}-$J.log \
          RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
          DT_TEST_ENDPOINT_TAG=${names[$k]} \
      bash -c "ulimit -Sn \$(ulimit -Hn); exec dragon -s $(command -v radical-orbit-endpoint.py) -n ${names[$k]} -u $URL -p default --tunnel none" \
      > $R/endpoint.console-${names[$k]}-$J.log 2>&1 &
    EPIDS+=($!)
  done
  for n in ${names[@]}; do echo "r$r $n up after $(timeout 330 python $X/r8/wait_endpoint.py $URL $n 300) s"; done
  $SAMPLER $BP > $R/broker-proc-$tag-$D.txt 2>/dev/null &
  SAMP=$!
  srun --overlap -N1 -n1 -w ${SN[0]} $SAMPLER -f "radical-orbit-endpoint.py -n ${names[0]}" \
    > $R/endpoint-proc-$tag-$D.txt 2>/dev/null &
  ESAMP=$!
  export RADICAL_ORBIT_LOG_FILE=$L/client-r8c-$tag.log
  # 2026-11-14 (page, Andre): all twins in one DT session (one experiment);
  # no session groups, no one-session-per-twin row; twins up to 1024
  for row in "onesession 0 ${TWINS:-1,4,16,64,128,256,512,1024}"; do
    set -- $row
    f=$R/windfield-$1-$tag-$D
    timeout ${ROW_TIMEOUT:-1800} python $X/r8/bench_windfield_scale.py --broker $URL --inference ${names[0]} \
      --learning ${names[1]},${names[2]},${names[3]},${names[4]} --twins $3 --per-session $2 \
      --model-path $MP --out $f.json > $f.log 2>&1
    echo "[$(date -u +%T)] r$r $1 rc=$?"; grep "^N=" $f.log | cut -c1-260
  done
  echo "r$r keepalive ping timeouts in the broker log: $(grep -c 'keepalive ping timeout' $L/broker-r8c-$tag.log 2>/dev/null)"
  ps=(); for k in 0 1 2 3 4; do srun --overlap -N1 -n1 -w ${SN[$k]} pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n ${names[$k]}" 2>/dev/null & ps+=($!); done; wait ${ps[@]}
  sleep 10; kill -TERM ${EPIDS[@]} 2>/dev/null; wait ${EPIDS[@]} 2>/dev/null
  kill $SAMP $ESAMP 2>/dev/null
  ps=(); for k in 0 1 2 3 4; do srun --overlap -N1 -n1 -w ${SN[$k]} dragon-cleanup > /dev/null 2>&1 & ps+=($!); done; wait ${ps[@]}
  kill -TERM $BP; wait $BP 2>/dev/null
  sleep 3
done
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
