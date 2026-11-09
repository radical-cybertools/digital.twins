#!/bin/bash
# Round 3 T1b: follow-up to T1 (job 61056507), same layout.
#SBATCH -J r3-t1b
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3-t1b-%j.out
#   sbatch -A m5290 -q debug r3/run_t1b.sh
# Layout as r3/run_t1.sh.  The broker runs under py-spy (speedscope, 50 Hz).
#   D1  decay: burst throughput over 20 bursts in one process, with and
#       without the 1000-request sequential phase (--tasks 1)
#   D2  modes: diag_wire.py per burst at c=50 (submit requests per burst)
#   D3  py-spy on the endpoint (speedscope, 100 Hz) for a bare c=500 run
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env3.sh}
R=$X/results/${RES:-r3/t1/t1b}; mkdir -p $R
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
T=$W/tls/r3-t1b-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm3" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

STAMP=$W/orbit-stamp-r3-t1b-$SLURM_JOB_ID; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r3-t1b-$SLURM_JOB_ID.log \
  py-spy record --idle -r 50 -f speedscope -o $R/pyspy-broker-$D.speedscope -- \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker.console-$D.log 2>&1 &
BP=$!
sleep 8
if ! kill -0 $BP 2>/dev/null; then
  echo "broker with --plugins dt died:"; tail -20 $R/broker.console-$D.log
  find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
  exit 3
fi
export RADICAL_ORBIT_LOG_FILE=$L/client-r3-t1b-$SLURM_JOB_ID.log

EPN=dt_r3_t1b_ep1
start_ep() {  # [py-spy output prefix] -> sets EP pid; endpoint on node 1
  local prof=${1:-}
  local cmd=(radical-orbit-endpoint.py -n $EPN -u $URL -p default --tunnel none)
  if [ -n "$prof" ]; then
    cmd=(py-spy record --idle -r 100 -f speedscope -o $prof -- "${cmd[@]}")
  fi
  srun --overlap -N1 -n1 -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r3-t1b-$SLURM_JOB_ID.log \
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
# --- D1: decay over 20 bursts
for k in 1 2; do
  for t in 1000 1; do
    f=$R/decay-bare-c500-t$t-r$k-$D
    python $B --broker $URL --endpoint $EPN --tasks $t --concurrent 500 \
        --bursts 20 --rows bare --out $f.json > $f.log 2>&1
    echo "D1 bare t$t r$k rc=$? $(summ $f.log)"
  done
done
f=$R/decay-agent-c500-t1000-r1-$D
python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent 500 \
    --bursts 20 --rows agent --out $f.json > $f.log 2>&1
echo "D1 agent t1000 r1 rc=$? $(summ $f.log)"
# --- D2: frames per burst at c=50
for k in 1 2; do
  for row in bare investigator agent; do
    f=$R/wire-bursts-c50-$row-r$k-$D
    python $G --broker $URL --endpoint $EPN --tasks 1000 --concurrent 50 \
        --bursts 10 --rows $row --wire-out $f.json > $f.log 2>&1
    echo "D2 $row r$k rc=$?"; grep -h '^BURST' $f.log | cut -c1-80
  done
done
stop_ep
# --- D3: endpoint profile, bare c=500
start_ep $R/pyspy-endpoint-bare-c500-$D.speedscope
f=$R/pyspy-endpoint-bare-c500-$D
python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent 500 \
    --bursts 10 --rows bare --out $f.json > $f.log 2>&1
echo "D3 rc=$? $(summ $f.log)"
stop_ep
ls -la $R/pyspy-*

kill -INT $BP; sleep 10; kill -TERM $BP 2>/dev/null; wait $BP
pkill -TERM -u $USER -f "radical-orbit-broker.py --host $IP0" 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
echo "--- end $(date -u +%FT%TZ)"
