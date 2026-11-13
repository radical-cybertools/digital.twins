#!/bin/bash
# Round 8, R8-2: N twins on one dragon_native engine.
#SBATCH -J r8-2
#SBATCH -C cpu
#SBATCH -N 3
#SBATCH -t 00:50:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-2-%j.out
#   sbatch -A m5290 -q regular r8/run_engine.sh
# As round 7's r7/run_broker.sh: broker (--plugins dt, throwaway TLS) on
# node 0, one Dragon endpoint (whole node, dragon_native) on node 1, the
# client (r8/bench_engine.py) on node 2; a fresh broker and endpoint per
# repeat; broker and endpoint sampled from /proc every second
# (r8/proc_sampler.sh: epoch, RSS kB, CPU ticks, threads, fds).  Rows per
# repeat: no-op tasks and 20 ms tasks with all twins in one session (one
# pool), then one session per twin up to 16 sessions (R8-0's safe count).
# Knobs: REPEATS ("1 2 3"), TWINS (1,4,16,64,256,1024), SECONDS_ (15), PORT (8221).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8/env-r8.sh}
R=$X/results/${RES:-r8/r8-2}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
N2=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 2p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8221}
URL=https://$IP0:$PORT
SAMPLER=$PWD/$X/r8/proc_sampler.sh
echo "node0 $N0 ($IP0) endpoint $N1 client $N2  broker $URL  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8-2-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r8-2-$J; touch $STAMP
for r in ${REPEATS:-1 2 3}; do
  tag=r$r-$J
  RADICAL_ORBIT_LOG_FILE=$L/broker-r8-2-$tag.log RADICAL_ORBIT_BROKER_URL=$URL \
    radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$tag.log 2>&1 &
  BP=$!
  sleep 8
  kill -0 $BP 2>/dev/null || { echo "r$r: broker died"; continue; }
  EPN=r8_2_ep_$r
  srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8-2-$tag.log RADICAL_ORBIT_BROKER_URL=$URL \
        RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
        DT_TEST_ENDPOINT_TAG=$EPN \
    bash -c "ulimit -Sn \$(ulimit -Hn); exec dragon -s $(command -v radical-orbit-endpoint.py) -n $EPN -u $URL -p default --tunnel none" \
    > $R/endpoint.console-$tag.log 2>&1 &
  EP=$!
  echo "r$r endpoint up after $(timeout 330 python $X/r8/wait_endpoint.py $URL $EPN 300) s"
  $SAMPLER $BP > $R/broker-proc-$tag-$D.txt 2>/dev/null &
  SAMP=$!
  srun --overlap -N1 -n1 -w $N1 $SAMPLER -f "radical-orbit-endpoint.py -n $EPN" \
    > $R/endpoint-proc-$tag-$D.txt 2> $R/endpoint-proc-$tag-$D.err &
  ESAMP=$!
  for row in "noop-one 0 0 ${TWINS:-1,4,16,64,256,1024}" "w20-one 20 0 ${TWINS:-1,4,16,64,256,1024}" "noop-persession 0 1 1,4,16"; do
    set -- $row
    f=$R/engine-$1-$tag-$D
    timeout ${ROW_TIMEOUT:-1500} srun --overlap -N1 -n1 -w $N2 --export=ALL \
      python $X/r8/bench_engine.py --broker $URL --endpoint $EPN --work-ms $2 --per-session $3 \
      --twins $4 --seconds ${SECONDS_:-15} --out $f.json > $f.log 2>&1
    echo "[$(date -u +%T)] r$r $1 rc=$?"; grep "^N=" $f.log | cut -c1-200
  done
  echo "r$r keepalive ping timeouts in the broker log: $(grep -c 'keepalive ping timeout' $L/broker-r8-2-$tag.log 2>/dev/null)"
  srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
  sleep 10; kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
  kill $SAMP $ESAMP 2>/dev/null
  srun --overlap -N1 -n1 -w $N1 dragon-cleanup > /dev/null 2>&1
  kill -TERM $BP; wait $BP 2>/dev/null
  sleep 3
done
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
