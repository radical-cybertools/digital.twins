#!/bin/bash
# Round 3 T1: why the DT rows lose burst throughput through ORBIT.
#SBATCH -J r3-t1
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 01:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3-t1-%j.out
#   sbatch -A m5290 -q regular r3/run_t1.sh
# Layout as s1/run_s1_p4.sh (2c's P4, cross-node): broker + client on node 0,
# endpoint on node 1, throwaway TLS, notify window 0, broker --plugins dt.
#   A  each row in its own process and all rows in one process, c = 50, 500,
#      5 repeats, row order rotated per repeat, 5 bursts per run (--bursts)
#   C  frames and bytes on the client's ORBIT wire per call (diag_wire.py)
#   B  py-spy --idle on client and endpoint, one run per row at c=500
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env3.sh}
R=$X/results/${RES:-r3/t1}; mkdir -p $R
B=$X/e1-overhead/bench_dt_insitu.py
G=$X/e1-overhead/diag_wire.py
L=$W/orbit-logs
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -1)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8131
URL=https://$IP0:$PORT
echo "node0 $N0 ($IP0) node1 $N1  broker $URL  $(date -u +%FT%TZ)"

# throwaway credentials for this job (never committed)
T=$W/tls/r3-t1-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm3" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

STAMP=$W/orbit-stamp-r3-t1-$SLURM_JOB_ID; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r3-t1-$SLURM_JOB_ID.log \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker.console-$D.log 2>&1 &
BP=$!
sleep 8
if ! kill -0 $BP 2>/dev/null; then
  echo "broker with --plugins dt died:"; tail -20 $R/broker.console-$D.log
  find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
  exit 3
fi
export RADICAL_ORBIT_LOG_FILE=$L/client-r3-t1-$SLURM_JOB_ID.log

EPN=dt_r3_t1_ep1
start_ep() {  # [py-spy output prefix] -> sets EP pid; endpoint on node 1
  local prof=${1:-}
  local cmd=(radical-orbit-endpoint.py -n $EPN -u $URL -p default --tunnel none)
  if [ -n "$prof" ]; then
    cmd=(py-spy record --idle --subprocesses -r 200 -f ${prof##*.} -o $prof -- "${cmd[@]}")
  fi
  srun --overlap -N1 -n1 -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r3-t1-$SLURM_JOB_ID.log \
        RADICAL_ORBIT_BROKER_URL=$URL \
        RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
        RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
    "${cmd[@]}" >> $R/endpoint.console-$D.log 2>&1 &
  EP=$!
  sleep 15
}
stop_ep() {
  # py-spy writes its profile on SIGINT; then the endpoint itself
  srun --overlap -N1 -n1 -w $N1 pkill -INT -u $USER -f "^py-spy record" 2>/dev/null
  sleep 5
  srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
  kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
  sleep 3
}
summ() { grep -h 'req/s' $1 | sed 's/.*(\(.*\) req\/s)/\1/' | tr '\n' ' '; }

start_ep
ORDERS=("bare investigator agent" "investigator agent bare" "agent bare investigator" \
        "bare agent investigator" "agent investigator bare")
# --- A: solo vs in-process, c = 50 and 500, 5 repeats, 5 bursts per run
for k in 1 2 3 4 5; do
  for c in 50 500; do
    for row in ${ORDERS[$((k-1))]}; do
      f=$R/insitu-pm-orbit-cross-c$c-solo-$row-r$k-$D
      python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent $c \
          --bursts 5 --rows $row --out $f.json > $f.log 2>&1
      echo "A c$c r$k solo $row rc=$? $(date -u +%T) $(summ $f.log)"
    done
    f=$R/insitu-pm-orbit-cross-c$c-inproc-r$k-$D
    python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent $c \
        --bursts 5 --out $f.json > $f.log 2>&1
    echo "A c$c r$k inproc rc=$? $(date -u +%T) $(summ $f.log)"
  done
done
# --- C: wire frames per call, each row solo
for c in 50 500; do
  for row in bare investigator agent; do
    f=$R/wire-cross-c$c-$row-$D
    python $G --broker $URL --endpoint $EPN --tasks 200 --concurrent $c \
        --rows $row --wire-out $f.json > $f.log 2>&1
    echo "C c$c $row rc=$?"; grep -h '^WIRE' $f.log
  done
done
stop_ep
# --- B: py-spy on both sides, one solo run per row at c=500
for row in bare investigator agent; do
  for fmt in raw speedscope; do
    ext=$fmt; [ $fmt = raw ] && ext=folded
    p=$R/pyspy-$row-c500-cross
    start_ep $p-endpoint-$D.$ext
    py-spy record --idle -r 200 -f $fmt -o $p-client-$D.$ext -- \
        python $B --broker $URL --endpoint $EPN --tasks 1000 \
        --concurrent 500 --bursts 5 --rows $row >> $p-$D.log 2>&1
    echo "B $row $fmt rc=$? $(date -u +%T)"
    stop_ep
    ls -la $p-*-$D.$ext
  done
done

kill -TERM $BP; wait $BP
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
echo "--- end $(date -u +%FT%TZ)"
