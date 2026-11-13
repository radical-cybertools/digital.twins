#!/bin/bash
# Round 6 Y1b: client scaling at the top end, from r3/run_t4c3.sh.
#SBATCH -J r6-y1b
#SBATCH -C cpu
#SBATCH -N 4
#SBATCH -t 02:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm6/logs/r6-y1b-%j.out
#   sbatch -A m5290 -q regular r6/run_clients.sh
# N sessions (one twin each) split over P client processes, alternating
# client nodes 2 and 3; all processes share one load window (--start-at)
# and keep every latency (--dump-lat); r3/t4c_merge.py pools them.  Each
# client records its own CPU over the load window (client_cpu_pct).  One
# broker (--plugins dt, throwaway TLS) on node 0 and one endpoint on node 1
# for the whole job, as in round 3; sessions are dropped after each point.
# Knobs: NS ("128 256 384"), PS ("1 4 8"), PING (RADICAL_ORBIT_PING_TIMEOUT),
#   POINT_TIMEOUT (s per (N, P), 2400), SECONDS_ (load window, 20).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm6/digital.twins/experiments/dt-paper/r6/env-r6.sh}
R=$X/results/${RES:-r6/clients}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
NODES=($(scontrol show hostnames $SLURM_JOB_NODELIST))
N0=$(hostname -s)
OTHERS=($(printf '%s\n' "${NODES[@]}" | grep -v "^$N0$"))
N1=${OTHERS[0]}; N2=${OTHERS[1]}; N3=${OTHERS[2]}
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8152
URL=https://$IP0:$PORT
[ -n "${PING:-}" ] && export RADICAL_ORBIT_PING_TIMEOUT=$PING
echo "node0 $N0 ($IP0) endpoint $N1 clients $N2 $N3  broker $URL  ping ${PING:-default}  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn); echo "ulimit -n soft $(ulimit -Sn)"

T=$W/tls/r6-y1b-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm6" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r6-y1b-$J; touch $STAMP

BL=$L/broker-r6-y1b-$J.log
RADICAL_ORBIT_LOG_FILE=$BL RADICAL_ORBIT_BROKER_URL=$URL \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker.console-$J.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; tail -20 $R/broker.console-$J.log; exit 3; }
EPN=dt_r6_y1b_ep
srun --overlap -N1 -n1 -w $N1 --export=ALL \
  env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r6-y1b-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
      RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
      DT_TEST_ENDPOINT_TAG=$EPN \
  radical-orbit-endpoint.py -n $EPN -u $URL -p default --tunnel none \
  > $R/endpoint.console-$J.log 2>&1 &
EP=$!
sleep 15
# broker sampler: epoch, VmRSS kB, utime+stime ticks, threads, fds
( while kill -0 $BP 2>/dev/null; do
    echo "$(date +%s.%N) $(awk '/VmRSS/{print $2}' /proc/$BP/status) \
$(awk '{print $14+$15}' /proc/$BP/stat) $(awk '/^Threads/{print $2}' /proc/$BP/status) \
$(ls /proc/$BP/fd 2>/dev/null | wc -l)"
    sleep 1
  done ) > $R/broker-proc-$J-$D.txt 2>/dev/null &
SAMP=$!

B=$X/e2-scaling/bench_broker.py
for n in ${NS:-128 256 384}; do
  for p in ${PS:-1 4 8}; do
    per=$((n / p))
    # every process creates its sessions first; generous, so none starts late
    start=$(( $(date +%s) + 60 + n ))
    pids=()
    for k in $(seq 1 $p); do
      node=$N2; [ $((k % 2)) -eq 0 ] && node=$N3
      f=$R/clients-n$n-p$p-k$k-$D
      timeout ${POINT_TIMEOUT:-2400} srun --overlap -N1 -n1 -w $node --export=ALL \
          python $B --broker $URL --inference $EPN --sessions $per \
          --seconds ${SECONDS_:-20} --start-at $start --dump-lat --out $f.json > $f.log 2>&1 &
      pids+=($!)
    done
    wait "${pids[@]}"
    echo "N=$n P=$p done $(date -u +%T) $(grep -h '^N=\|failed to create' $R/clients-n$n-p$p-k*-$D.log | cut -c1-90 | tr '\n' '|')"
  done
done
echo "keepalive ping timeouts in the broker log: $(grep -c 'keepalive ping timeout' $BL)"
srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
kill $SAMP 2>/dev/null
kill -TERM $BP; wait $BP 2>/dev/null
python $X/r6/clients_table.py $R $R/broker-proc-$J-$D.txt | tee $R/clients-table-$J-$D.md
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
