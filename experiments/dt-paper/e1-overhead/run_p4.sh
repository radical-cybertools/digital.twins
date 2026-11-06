#!/bin/bash
#SBATCH -J dt-p4
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 01:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm2/logs/p4-%j.out
# P4: E1 through ORBIT, cross-node and loopback, in one 2-node allocation.
#   sbatch -A m5290 -q regular run_p4.sh
# Broker + client on node 0 (the batch node), endpoint on node 1 (cross) or
# node 0 (loopback).  Throwaway TLS in $W/tls, generated here so the SANs
# carry node 0's name and hsn0 address.  Broker: --plugins dt only.
# ~/.radical/orbit is checked against a stamp before and after.
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm2/env.sh
R=$X/results/p4; mkdir -p $R
B=$X/e1-overhead/bench_dt_insitu.py
S=$X/e1-overhead/bench_streams.py
G=$X/e1-overhead/diag_orbit_tasks.py
L=$W/orbit-logs
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -1)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8131
URL=https://$IP0:$PORT
echo "node0 $N0 ($IP0) node1 $N1  broker $URL"

# throwaway credentials for this job (never committed)
T=$W/tls/p4-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm2" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

touch $W/orbit-stamp
RADICAL_ORBIT_LOG_FILE=$L/broker-p4.log \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker-p4.console.log 2>&1 &
BP=$!
sleep 8
if ! kill -0 $BP 2>/dev/null; then
  echo "broker with --plugins dt died:"; tail -20 $R/broker-p4.console.log
  find ~/.radical/orbit -newer $W/orbit-stamp | tee $R/orbit-isolation-check-$D.txt
  exit 3
fi
# every client process logs here, not to ~/.radical/orbit/logs
export RADICAL_ORBIT_LOG_FILE=$L/client-p4.log

start_ep() {  # node name -> sets EP pid
  local node=$1 name=$2
  srun --overlap -N1 -n1 -w $node --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-$name.log \
        RADICAL_ORBIT_BROKER_URL=$URL \
        RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
        RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
    radical-orbit-endpoint.py -n $name -u $URL -p default --tunnel none \
    > $R/endpoint-$name.console.log 2>&1 &
  EP=$!
  sleep 15
}

series() {  # layout endpoint
  local lay=$1 ep=$2
  for k in 1 2 3 4 5; do
    for c in 1 50 500; do
      f=$R/insitu-pm-orbit-$lay-c$c-r$k-$D
      python $B --broker $URL --endpoint $ep --tasks 1000 --concurrent $c \
          --out $f.json > $f.log 2>&1
      echo "$lay c$c r$k rc=$? $(grep -h 'req/s' $f.log | sed 's/  */ /g' | tr '\n' '|')"
    done
  done
  for row in bare investigator agent; do       # each row in its own process
    f=$R/insitu-pm-orbit-$lay-c50-solo-$row-$D
    python $B --broker $URL --endpoint $ep --tasks 1000 --concurrent 50 \
        --rows $row --out $f.json > $f.log 2>&1
    echo "$lay solo $row rc=$? $(grep -h 'req/s' $f.log | sed 's/  */ /g')"
  done
  for row in bare investigator agent; do       # ORBIT tasks per request
    f=$R/diag-tasks-$lay-$row-$D
    python $G --broker $URL --endpoint $ep --tasks 200 --concurrent 50 \
        --rows $row > $f.log 2>&1
    echo "$lay diag $row rc=$? $(grep -h '^DIAG' $f.log)"
  done
}

# --- cross-node: endpoint on node 1
start_ep $N1 dt_p4_ep1
series cross dt_p4_ep1
# py-spy on the client, c=50: agent (speedscope + folded) and bare (folded)
for row in agent bare; do
  f=$R/pyspy-$row-c50-cross-$D
  for fmt in speedscope raw; do
    ext=$fmt; [ $fmt = raw ] && ext=folded
    py-spy record -r 200 -f $fmt -o $f.$ext -- \
        python $B --broker $URL --endpoint dt_p4_ep1 --tasks 1000 \
        --concurrent 50 --rows $row >> $f.log 2>&1
    echo "py-spy $row $fmt rc=$?"
  done
done
# streams across the network: client on node 1, broker on node 0
srun --overlap -N1 -n1 -w $N1 --export=ALL \
    python $S both --broker $URL > $R/streams-cross-$D.log 2>&1
echo "streams cross rc=$?"
kill -TERM $EP; wait $EP

# --- loopback: endpoint on node 0, same broker
start_ep $N0 dt_p4_ep0
series loop dt_p4_ep0
python $S both --broker $URL > $R/streams-loop-$D.log 2>&1
echo "streams loop rc=$?"
kill -TERM $EP; wait $EP

kill -TERM $BP; wait $BP
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $W/orbit-stamp | tee $R/orbit-isolation-check-$D.txt
echo "--- end"
