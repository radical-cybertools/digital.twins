#!/bin/bash
# Round 3 T1d: T1c again on the 52926e6 paper stack (finished tasks released
# upstream), plain endpoint -- no harness-side prune.
#SBATCH -J r3-t1d
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3-t1d-%j.out
#   sbatch -A m5290 -q debug r3/run_t1d.sh
#   P1  decay: 20 bursts at c=500, each row solo
#   P2  in-process, all rows, c=500 and c=50, 5 bursts, 3 repeats
#   P3  c=50 solo, 10 bursts per row, 2 repeats (the modes)
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env4.sh}
R=$X/results/${RES:-r3/t1/t1d}; mkdir -p $R
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
T=$W/tls/r3-t1d-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm3" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

STAMP=$W/orbit-stamp-r3-t1d-$SLURM_JOB_ID; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r3-t1d-$SLURM_JOB_ID.log \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker.console-$D.log 2>&1 &
BP=$!
sleep 8
if ! kill -0 $BP 2>/dev/null; then
  echo "broker with --plugins dt died:"; tail -20 $R/broker.console-$D.log
  find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
  exit 3
fi
export RADICAL_ORBIT_LOG_FILE=$L/client-r3-t1d-$SLURM_JOB_ID.log

EPN=dt_r3_t1d_ep1
start_ep() {  # [py-spy output prefix] -> sets EP pid; endpoint on node 1
  local prof=${1:-}
  local cmd=(radical-orbit-endpoint.py -n $EPN -u $URL -p default --tunnel none)
  if [ -n "$prof" ]; then
    cmd=(py-spy record --idle --subprocesses -r 200 -f ${prof##*.} -o $prof -- "${cmd[@]}")
  fi
  srun --overlap -N1 -n1 -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r3-t1d-$SLURM_JOB_ID.log \
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
grep -q "registered\|Registered\|connected" $R/endpoint.console-$D.log || tail -5 $R/endpoint.console-$D.log
# --- P1: decay, each row solo, 20 bursts at c=500
for row in bare investigator agent bare; do
  f=$R/decay-$row-c500-t1000-$D-$RANDOM
  python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent 500 \
      --bursts 20 --rows $row --out $f.json > $f.log 2>&1
  echo "P1 $row rc=$? $(summ $f.log)"
done
# --- P2: in-process, all rows
for k in 1 2 3; do
  for c in 500 50; do
    f=$R/insitu-pm-orbit-cross-c$c-inproc-r$k-$D
    python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent $c \
        --bursts 5 --out $f.json > $f.log 2>&1
    echo "P2 c$c r$k inproc rc=$? $(summ $f.log)"
  done
done
# --- P3: c=50 solo, 10 bursts
for k in 1 2; do
  for row in bare investigator agent; do
    f=$R/insitu-pm-orbit-cross-c50-solo-$row-r$k-$D
    python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent 50 \
        --bursts 10 --rows $row --out $f.json > $f.log 2>&1
    echo "P3 c50 $row r$k rc=$? $(summ $f.log)"
  done
done
stop_ep

kill -TERM $BP; wait $BP
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
echo "--- end $(date -u +%FT%TZ)"
