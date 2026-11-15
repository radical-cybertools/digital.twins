#!/bin/bash
# Round 8c, C3: the E1 paths figure (round 3b U2, U3; round 2 S3) on dragon_native.
#SBATCH -J r8c-c3
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:45:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8c-c3-%j.out
#   sbatch -A m5290 -q regular r8c/run_c3.sh
# e1-overhead/bench_dt_insitu.py, 0.58 ms task, rows bare / investigator /
# agent / xgf each in its own process (round 3b's rotated orders), 5 repeats;
# each process: --tasks sequential requests (p50) and --bursts bursts of
# --concurrent (throughput: median of bursts 2-5).
#   L  local dragon_native pool on node 0 (harness under dragon -s; the
#      twin's stream client to this job's broker, as R8-1)
#   O  ORBIT cross-node: broker and client on node 0, Dragon endpoint on node 1
#   R  through radical.3:8010 (default credentials, read only): a Dragon
#      endpoint on node 1 registered there, client on node 0, c = 1, rows
#      bare,investigator,agent in one process (round 3b U3's way)
#   S  the service row: s3/s3_service.py, a twin in radical.3's DT plugin with
#      its inference engine on that endpoint (round 2 S3)
# Knobs: REPEATS (5), TASKS (1000), CONC (500), BURSTS (5), PARTS ("L O R S"), PORT (8831).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8c/env-r8c.sh}
R=$X/results/${RES:-r8c/c3}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8831}
URL=https://$IP0:$PORT
R3=https://95.217.193.116:8010
H=$X/e1-overhead/bench_dt_insitu.py
export R8_BACKEND=dragon_native
echo "node0 $N0 ($IP0) endpoint $N1  broker $URL  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8c-c3-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r8c-c3-$J; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r8c-c3-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$J.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; exit 3; }
export RADICAL_ORBIT_LOG_FILE=$L/client-r8c-c3-$J.log
start_ep() {  # name url
  local n=$1 u=$2
  srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8c-c3-$n-$J.log RADICAL_ORBIT_BROKER_URL=$u \
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
r3() {  # radical.3 with its default credentials (read only), as round 2 S2 / round 8 R8-A
  ( unset RADICAL_ORBIT_BROKER_CERT RADICAL_ORBIT_BROKER_KEY RADICAL_ORBIT_BROKER_TOKEN
    export RADICAL_ORBIT_LOG_FILE=$L/client-r8c-c3-r3-$J.log
    "$@" )
}
summ() { grep -E 'p50=|req/s' $1 | sed 's/  */ /g' | cut -c1-80 | tr '\n' '|'; }
ORDERS=("bare investigator agent xgf" "investigator agent xgf bare" "agent xgf bare investigator" \
        "xgf bare investigator agent" "bare agent xgf investigator")
on() { [[ " ${PARTS:-L O R S} " == *" $1 "* ]]; }
ARGS="--work-ms 0.58 --tasks ${TASKS:-1000} --concurrent ${CONC:-500} --bursts ${BURSTS:-5}"
if on L; then
  for k in $(seq 1 ${REPEATS:-5}); do for row in ${ORDERS[$((k-1))]}; do
    f=$R/insitu-local-dragon-c${CONC:-500}-solo-$row-r$k-$J-$D
    timeout 600 dragon -s $H --local-backend dragon_native --stream-broker $URL --rows $row $ARGS \
      --out $f.json > $f.log 2>&1
    echo "[$(date -u +%T)] L r$k $row rc=$? $(summ $f.log)"
    dragon-cleanup > /dev/null 2>&1 || true
    kill -0 $BP 2>/dev/null || { echo "broker died after dragon-cleanup"; exit 4; }
  done; done
fi
if on O; then
  EPN=r8c_c3_ep; start_ep $EPN $URL
  for k in $(seq 1 ${REPEATS:-5}); do for row in ${ORDERS[$((k-1))]}; do
    f=$R/insitu-orbit-dragon-c${CONC:-500}-solo-$row-r$k-$J-$D
    timeout 600 python $H --broker $URL --endpoint $EPN --backends dragon_native --rows $row $ARGS \
      --out $f.json > $f.log 2>&1
    echo "[$(date -u +%T)] O r$k $row rc=$? $(summ $f.log)"
  done; done
  stop_ep $EPN
fi
if on R || on S; then
  R3OK=$(curl -sk -o /dev/null -m 10 -w '%{http_code}' $R3/)
  echo "radical.3:8010 http $R3OK; connect s (median of 20): $(for i in $(seq 20); do curl -sk -o /dev/null -m 10 -w '%{time_connect}\n' $R3/; done | sort -n | sed -n 10p)"
  if [ "$R3OK" = 200 ]; then
    EPR=pm_r8c_c3_$J
    r3 start_ep $EPR $R3
    if on R; then
      for k in $(seq 1 ${REPEATS:-5}); do
        f=$R/insitu-remote-dragon-c1-r$k-$J-$D
        r3 timeout 900 python $H --broker $R3 --endpoint $EPR --backends dragon_native \
          --rows bare,investigator,agent --work-ms 0.58 --tasks 100 --concurrent 1 --bursts 1 \
          --out $f.json > $f.log 2>&1
        echo "[$(date -u +%T)] R r$k rc=$? $(summ $f.log)"
      done
    fi
    if on S; then
      f=$R/service-remote-dragon-$J-$D
      E5_BACKEND=dragon_native r3 timeout 900 python $X/s3/s3_service.py --broker $R3 --inference $EPR \
        --n 100 --repeats 3 --reattaches 10 --out $f.json > $f.log 2>&1
      echo "[$(date -u +%T)] S rc=$? $(tail -3 $f.log | tr '\n' '|' | cut -c1-300)"
    fi
    r3 stop_ep $EPR
  fi
fi
kill -TERM $BP; wait $BP 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
