#!/bin/bash
# Round 3b U1: the decay is gone on fca2d54.
#SBATCH -J r3b-u1
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3b-u1-%j.out
#   sbatch -A m5290 -q debug r3b/run_u1.sh
#   A  r3/diag_thread_decay.py on node 0 (no ORBIT), 32-thread backend,
#      20 bursts of 500, without --prune: burst rate and live Task count
#   B  one bare process, 20 bursts of 500, ORBIT cross-node (layout as
#      r3/run_t1d.sh: broker node 0, endpoint node 1, client node 0)
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env5.sh}
R=$X/results/${RES:-r3b/u1}; mkdir -p $R
B=$X/e1-overhead/bench_dt_insitu.py
L=$W/orbit-logs
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -1)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8131
URL=https://$IP0:$PORT
echo "node0 $N0 ($IP0) node1 $N1  broker $URL  $(date -u +%FT%TZ)"
python -c "import digitaltwin, rhapsody, radical.orbit.plugin_rhapsody as p; print(digitaltwin.__file__, p.FINISHED_RETAIN_S)"

# --- A: local repro, no prune
f=$R/thread-decay-c500-b20-$D
python $X/r3/diag_thread_decay.py --bursts 20 --concurrent 500 --out $f.json > $f.log 2>&1
echo "A rc=$?"; cat $f.log

# throwaway credentials for this job (never committed)
T=$W/tls/r3b-u1-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm3" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

STAMP=$W/orbit-stamp-r3b-u1-$SLURM_JOB_ID; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r3b-u1-$SLURM_JOB_ID.log \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker.console-$D.log 2>&1 &
BP=$!
sleep 8
if ! kill -0 $BP 2>/dev/null; then
  echo "broker with --plugins dt died:"; tail -20 $R/broker.console-$D.log
  find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
  exit 3
fi
export RADICAL_ORBIT_LOG_FILE=$L/client-r3b-u1-$SLURM_JOB_ID.log

EPN=dt_r3b_u1_ep1
srun --overlap -N1 -n1 -w $N1 --export=ALL \
  env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r3b-u1-$SLURM_JOB_ID.log \
      RADICAL_ORBIT_BROKER_URL=$URL \
      RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
      RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
  radical-orbit-endpoint.py -n $EPN -u $URL -p default --tunnel none \
  >> $R/endpoint.console-$D.log 2>&1 &
EP=$!
sleep 15

# --- B: decay through ORBIT, one bare process
f=$R/decay-bare-c500-t1000-b20-$D
python $B --broker $URL --endpoint $EPN --tasks 1000 --concurrent 500 \
    --bursts 20 --rows bare --out $f.json > $f.log 2>&1
echo "B rc=$?"; grep -h 'req/s' $f.log

srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
kill -TERM $BP; wait $BP
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
echo "--- end $(date -u +%FT%TZ)"
