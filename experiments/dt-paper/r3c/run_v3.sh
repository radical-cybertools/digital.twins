#!/bin/bash
# Round 3c V3: the rare slow first burst through ORBIT -- the collector?
#SBATCH -J r3c-v3
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3c-v3-%j.out
#   sbatch -A m5290 -q debug r3c/run_v3.sh
# U2's ORBIT cross-node layout (broker and client node 0, endpoint node 1),
# c=50, rows bare, investigator, agent each in its own process, 10 repeats
# per row, 5 bursts each, in four settings (client GC / endpoint GC):
# on/on, off/on, on/off, off/off.  GC off = r3b/nogc.py (gc.disable()).
# A fresh endpoint per setting; rows rotated per repeat.
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env6.sh}
R=$X/results/${RES:-r3c/v3}; mkdir -p $R
B=$X/e1-overhead/bench_dt_insitu.py
L=$W/orbit-logs
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -1)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8131
URL=https://$IP0:$PORT
EPBIN=$VIRTUAL_ENV/bin/radical-orbit-endpoint.py
echo "node0 $N0 ($IP0) node1 $N1  broker $URL  $(date -u +%FT%TZ)"
summ() { grep -h 'req/s' $1 | sed 's/.*(\(.*\) req\/s)/\1/' | tr '\n' ' '; }
ORDERS=("bare investigator agent" "investigator agent bare" "agent bare investigator")

# throwaway credentials for this job (never committed)
T=$W/tls/r3c-v3-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm3" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

STAMP=$W/orbit-stamp-r3c-v3-$SLURM_JOB_ID; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r3c-v3-$SLURM_JOB_ID.log \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker.console-$D.log 2>&1 &
BP=$!
sleep 8
if ! kill -0 $BP 2>/dev/null; then
  echo "broker with --plugins dt died:"; tail -20 $R/broker.console-$D.log
  find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
  exit 3
fi
export RADICAL_ORBIT_LOG_FILE=$L/client-r3c-v3-$SLURM_JOB_ID.log

EPN=dt_r3c_v3_ep1
start_ep() {  # on|off (endpoint GC) -> sets EP pid; endpoint on node 1
  local cmd=($EPBIN -n $EPN -u $URL -p default --tunnel none)
  [ $1 = off ] && cmd=(python $X/r3b/nogc.py "${cmd[@]}")
  echo "--- endpoint gc $1: ${cmd[*]}" >> $R/endpoint.console-$D.log
  srun --overlap -N1 -n1 -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r3c-v3-$SLURM_JOB_ID.log \
        RADICAL_ORBIT_BROKER_URL=$URL \
        RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
        RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
    "${cmd[@]}" >> $R/endpoint.console-$D.log 2>&1 &
  EP=$!
  sleep 15
}
stop_ep() {
  srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
  kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
  sleep 3
}

for setting in on/on off/on on/off off/off; do
  cgc=${setting%/*}; egc=${setting#*/}
  start_ep $egc
  pre=(); [ $cgc = off ] && pre=($X/r3b/nogc.py)
  for k in $(seq 10); do
    for row in ${ORDERS[$(( (k-1) % 3 ))]}; do
      f=$R/insitu-pm-orbit-cross-c50-solo-$row-cgc$cgc-egc$egc-r$k-$D
      python "${pre[@]}" $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent 50 \
          --bursts 5 --rows $row --out $f.json > $f.log 2>&1
      echo "V3 client-gc $cgc endpoint-gc $egc r$k $row rc=$? $(date -u +%T) $(summ $f.log)"
    done
  done
  stop_ep
done

kill -TERM $BP; wait $BP
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
echo "--- end $(date -u +%FT%TZ)"
