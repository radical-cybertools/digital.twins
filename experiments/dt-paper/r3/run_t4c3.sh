#!/bin/bash
# Round 3 T4-C again: job 61061605 started the broker without
# RADICAL_ORBIT_BROKER_URL, and a twin in its dt plugin needs it for its
# engine ("Broker URL required"); only part C here.
# r3-t4c3: client scaling.  N sessions split over P client processes
# (P = 1, 2, 4, 8, alternating client nodes 2 and 3), one shared 20 s load
# window per (N, P) via --start-at; pooled by r3/t4c_merge.py.
#SBATCH -J r3-t4c3
#SBATCH -C cpu
#SBATCH -N 4
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3-t4c3-%j.out
#   sbatch -A m5290 -q debug r3/run_t4c3.sh
# Broker (--plugins dt, throwaway TLS) on node 0, endpoint on node 1 (as
# r3/run_t1.sh, unpatched: the paper stack).
#   C  bench_broker.py from node 2: N service sessions, one twin each,
#      c=1 per twin; broker RSS and CPU sampled from /proc every second
#   A  bench_swap.py cross-node from node 0, c = 1 and 50, 5 repeats
#   P7 bench_model_update.py cross-node from node 0, 5 repeats (round 2's
#      P7 ORBIT had 3)
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env3.sh}
R=$X/results/${RES:-r3/t4c3}; R4=$X/results/r3/t4; R5=$X/results/r3/t5; mkdir -p $R4 $R5; mkdir -p $R
B=$X/e1-overhead/bench_dt_insitu.py
G=$X/e1-overhead/diag_wire.py
L=$W/orbit-logs
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
N2=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 2p)
N3=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 3p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8131
URL=https://$IP0:$PORT
echo "node0 $N0 ($IP0) node1 $N1 node2 $N2  broker $URL  $(date -u +%FT%TZ)"

# throwaway credentials for this job (never committed)
T=$W/tls/r3-t4c3-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm3" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

STAMP=$W/orbit-stamp-r3-t4c3-$SLURM_JOB_ID; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r3-t4c-$SLURM_JOB_ID.log \
RADICAL_ORBIT_BROKER_URL=$URL \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker.console-$D.log 2>&1 &
BP=$!
sleep 8
if ! kill -0 $BP 2>/dev/null; then
  echo "broker with --plugins dt died:"; tail -20 $R/broker.console-$D.log
  find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
  exit 3
fi
export RADICAL_ORBIT_LOG_FILE=$L/client-r3-t4c-$SLURM_JOB_ID.log

EPN=dt_r3_t4c_ep1
start_ep() {  # [py-spy output prefix] -> sets EP pid; endpoint on node 1
  local prof=${1:-}
  local cmd=(radical-orbit-endpoint.py -n $EPN -u $URL -p default --tunnel none)
  if [ -n "$prof" ]; then
    cmd=(py-spy record --idle --subprocesses -r 200 -f ${prof##*.} -o $prof -- "${cmd[@]}")
  fi
  srun --overlap -N1 -n1 -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r3-t4c-$SLURM_JOB_ID.log \
        RADICAL_ORBIT_BROKER_URL=$URL \
        RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
        RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
        DT_TEST_ENDPOINT_TAG=$EPN \
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
# broker sampler: epoch, VmRSS kB, utime+stime ticks
( while kill -0 $BP 2>/dev/null; do
    echo "$(date +%s.%N) $(awk '/VmRSS/{print $2}' /proc/$BP/status) \
$(awk '{print $14+$15}' /proc/$BP/stat)"
    sleep 1
  done ) > $R/broker-proc-$SLURM_JOB_ID-$D.txt 2>/dev/null &
SAMP=$!
# --- C3: client scaling
B=$X/e2-scaling/bench_broker.py
for n in 4 16 64; do
  for p in 1 2 4 8; do
    [ $p -gt $n ] && continue
    per=$((n / p)); start=$(( $(date +%s) + 30 + n / 2 ))
    pids=()
    for k in $(seq 1 $p); do
      node=$N2; [ $((k % 2)) -eq 0 ] && node=$N3
      f=$R/clients-n$n-p$p-k$k-$D
      srun --overlap -N1 -n1 -w $node --export=ALL \
          python $B --broker $URL --inference $EPN --sessions $per \
          --seconds 20 --start-at $start --dump-lat --out $f.json > $f.log 2>&1 &
      pids+=($!)
    done
    wait "${pids[@]}"
    echo "C3 N=$n P=$p done $(date -u +%T) $(grep -h '^N=\|failed to create' $R/clients-n$n-p$p-k*-$D.log | cut -c1-90 | tr '\n' '|')"
  done
done
stop_ep
kill $SAMP 2>/dev/null

kill -TERM $BP; wait $BP
python $X/r3/t4c_merge.py $R $R/broker-proc-$SLURM_JOB_ID-$D.txt | tee $R/t4c3-table-$D.md
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
echo "--- end $(date -u +%FT%TZ)"
