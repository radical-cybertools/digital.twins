#!/bin/bash
#SBATCH -J dt-p7o
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:45:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm2/logs/p7o-%j.out
# P7 (ORBIT): E4 model-update propagation through the P4 layout
# (broker + client on node 0, endpoint on node 1, then on node 0).
#   sbatch -A m5290 -q regular run_p7_orbit.sh
# Setup copied from e1-overhead/run_p4.sh.
# Broker + client on node 0 (the batch node), endpoint on node 1 (cross) or
# node 0 (loopback).  Throwaway TLS in $W/tls, generated here so the SANs
# carry node 0's name and hsn0 address.  Broker: --plugins dt only.
# ~/.radical/orbit is checked against a stamp before and after.
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm2/env.sh
R=$X/results/p7; mkdir -p $R
M=$X/e4-hot-swap/bench_model_update.py
L=$W/orbit-logs
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -1)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8331
URL=https://$IP0:$PORT
echo "node0 $N0 ($IP0) node1 $N1  broker $URL"

# throwaway credentials for this job (never committed)
T=$W/tls/p7-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm2" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

touch $W/orbit-stamp-p7
RADICAL_ORBIT_LOG_FILE=$L/broker-p7.log \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker-p7.console.log 2>&1 &
BP=$!
sleep 8
if ! kill -0 $BP 2>/dev/null; then
  echo "broker with --plugins dt died:"; tail -20 $R/broker-p7.console.log
  find ~/.radical/orbit -newer $W/orbit-stamp-p7 | tee $R/orbit-isolation-check-$D.txt
  exit 3
fi
# every client process logs here, not to ~/.radical/orbit/logs
export RADICAL_ORBIT_LOG_FILE=$L/client-p7.log

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

upd() {  # layout endpoint
  for k in 1 2 3; do
    f=$R/update-pm-orbit-$1-r$k-$D
    python $M --broker $URL --endpoint $2 --intervals 1,0.1,0.01 --seconds 20 \
        --out $f.json > $f.log 2>&1
    echo "$1 r$k rc=$?"; grep interval $f.log
  done
}
start_ep $N1 dt_p7_ep1
upd cross dt_p7_ep1
kill -TERM $EP; wait $EP
start_ep $N0 dt_p7_ep0
upd loop dt_p7_ep0
kill -TERM $EP; wait $EP
kill -TERM $BP; wait $BP
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $W/orbit-stamp-p7 | tee $R/orbit-isolation-check-$D.txt
echo "--- end"
