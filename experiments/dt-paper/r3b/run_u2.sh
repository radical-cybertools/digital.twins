#!/bin/bash
# Round 3b U2: round 3 T3 unchanged on fca2d54 (r3/run_t3.sh), then the
# rows in one process (round 2's way), ORBIT cross-node.
#SBATCH -J r3b-u2
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3b-u2-%j.out
#   sbatch -A m5290 -q regular r3b/run_u2.sh
# Rows bare, investigator, agent, xgf, each in its own process, 5 repeats
# with rotated order, 5 bursts per run:
#   L  local process pool 8 on node 0, c = 50 and 500 (before the broker)
#   O  ORBIT cross-node, layout as r3/run_t1.sh (unpatched endpoint: the
#      paper stack), c = 1, 50 and 500
#   I  ORBIT cross-node, all four rows in one process (--rows
#      bare,investigator,agent,xgf), c = 50 and 500, 5 repeats, 5 bursts
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env5.sh}
R=$X/results/${RES:-r3b/u2}; mkdir -p $R
B=$X/e1-overhead/bench_dt_insitu.py
G=$X/e1-overhead/diag_wire.py
L=$W/orbit-logs
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -1)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8131
URL=https://$IP0:$PORT
echo "node0 $N0 ($IP0) node1 $N1  broker $URL  $(date -u +%FT%TZ)"

summ() { grep -h 'req/s' $1 | sed 's/.*(\(.*\) req\/s)/\1/' | tr '\n' ' '; }
ORDERS=("bare investigator agent xgf" "investigator agent xgf bare" "agent xgf bare investigator" \
        "xgf bare investigator agent" "bare agent xgf investigator")
# --- L: local process pool 8
for k in 1 2 3 4 5; do
  for c in 50 500; do
    for row in ${ORDERS[$((k-1))]}; do
      f=$R/insitu-pm-pool8-c$c-solo-$row-r$k-$D
      python $B --workers 8 --tasks 1000 --concurrent $c --bursts 5 \
          --rows $row --out $f.json > $f.log 2>&1
      echo "L c$c r$k $row rc=$? $(date -u +%T) $(summ $f.log)"
    done
  done
done

# throwaway credentials for this job (never committed)
T=$W/tls/r3b-u2-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm3" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

STAMP=$W/orbit-stamp-r3b-u2-$SLURM_JOB_ID; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r3b-u2-$SLURM_JOB_ID.log \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker.console-$D.log 2>&1 &
BP=$!
sleep 8
if ! kill -0 $BP 2>/dev/null; then
  echo "broker with --plugins dt died:"; tail -20 $R/broker.console-$D.log
  find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
  exit 3
fi
export RADICAL_ORBIT_LOG_FILE=$L/client-r3b-u2-$SLURM_JOB_ID.log

EPN=dt_r3b_u2_ep1
start_ep() {  # [py-spy output prefix] -> sets EP pid; endpoint on node 1
  local prof=${1:-}
  local cmd=(radical-orbit-endpoint.py -n $EPN -u $URL -p default --tunnel none)
  if [ -n "$prof" ]; then
    cmd=(py-spy record --idle --subprocesses -r 200 -f ${prof##*.} -o $prof -- "${cmd[@]}")
  fi
  srun --overlap -N1 -n1 -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r3b-u2-$SLURM_JOB_ID.log \
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
# --- O: ORBIT cross-node
for k in 1 2 3 4 5; do
  for c in 1 50 500; do
    for row in ${ORDERS[$((k-1))]}; do
      f=$R/insitu-pm-orbit-cross-c$c-solo-$row-r$k-$D
      python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent $c \
          --bursts 5 --rows $row --out $f.json > $f.log 2>&1
      echo "O c$c r$k $row rc=$? $(date -u +%T) $(summ $f.log)"
    done
  done
done
# --- I: all rows in one process
for k in 1 2 3 4 5; do
  for c in 50 500; do
    f=$R/insitu-pm-orbit-cross-c$c-inproc-r$k-$D
    python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent $c \
        --bursts 5 --rows bare,investigator,agent,xgf --out $f.json > $f.log 2>&1
    echo "I c$c r$k rc=$? $(date -u +%T) $(summ $f.log)"
  done
done
stop_ep

kill -TERM $BP; wait $BP
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
echo "--- end $(date -u +%FT%TZ)"
