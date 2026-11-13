#!/bin/bash
# Round 6: E2 broker capacity on the #170 stack, from r3/run_t4c.sh part C.
#SBATCH -J r6-broker
#SBATCH -C cpu
#SBATCH -N 3
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm6/logs/r6-broker-%j.out
#   sbatch -A m5290 -q regular --export=ALL,RES=r6/t3s r6/run_broker.sh
# Broker (--plugins dt, throwaway TLS) on node 0, endpoint on node 1,
# bench_broker.py from node 2: N service sessions, one twin each, c=1 per
# twin.  A fresh broker and endpoint per repeat.  Broker RSS, CPU ticks,
# threads and fds sampled from /proc every second.
# Knobs: REPEATS ("1 2"), SESSIONS (1,4,16,64,128,256,384), SECONDS_ (20; not
#   SECONDS, a bash built-in),
#   PING (RADICAL_ORBIT_PING_TIMEOUT for broker, endpoint and client; unset:
#   the default 3 s), TELEMETRY (RADICAL_ORBIT_RHAPSODY_TELEMETRY on the
#   endpoint; unset: default), STEP_TIMEOUT (s per repeat, 1500).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm6/digital.twins/experiments/dt-paper/r6/env-r6.sh}
R=$X/results/${RES:-r6/t3s}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
N2=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 2p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8151
URL=https://$IP0:$PORT
[ -n "${PING:-}" ] && export RADICAL_ORBIT_PING_TIMEOUT=$PING
echo "node0 $N0 ($IP0) node1 $N1 node2 $N2  broker $URL  ping ${PING:-default}  telemetry ${TELEMETRY:-default}  $(date -u +%FT%TZ)"
# fds: the broker holds about 4.4k at 256 sessions, 6.6k at 384
echo "ulimit -n before: soft $(ulimit -Sn) hard $(ulimit -Hn)"
ulimit -Sn $(ulimit -Hn)
echo "ulimit -n now: soft $(ulimit -Sn)"; for n in $N1 $N2; do srun --overlap -N1 -n1 -w $n bash -c 'echo "$(hostname -s) soft $(ulimit -Sn) hard $(ulimit -Hn)"'; done

T=$W/tls/r6-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm6" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r6-$J; touch $STAMP

for r in ${REPEATS:-1 2}; do
  tag=r$r-$J
  BL=$L/broker-r6-$tag.log
  RADICAL_ORBIT_LOG_FILE=$BL RADICAL_ORBIT_BROKER_URL=$URL \
    radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
    > $R/broker.console-$tag.log 2>&1 &
  BP=$!
  sleep 8
  kill -0 $BP 2>/dev/null || { echo "r$r: broker died"; tail -20 $R/broker.console-$tag.log; continue; }
  EPN=dt_r6_ep_$r
  envs=(RADICAL_ORBIT_LOG_FILE=$L/endpoint-r6-$tag.log RADICAL_ORBIT_BROKER_URL=$URL
        RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0
        DT_TEST_ENDPOINT_TAG=$EPN)
  [ -n "${TELEMETRY:-}" ] && envs+=(RADICAL_ORBIT_RHAPSODY_TELEMETRY=$TELEMETRY)
  srun --overlap -N1 -n1 -w $N1 --export=ALL env "${envs[@]}" \
    radical-orbit-endpoint.py -n $EPN -u $URL -p default --tunnel none \
    > $R/endpoint.console-$tag.log 2>&1 &
  EP=$!
  sleep 15
  # broker sampler: epoch, VmRSS kB, utime+stime ticks, threads, fds
  ( while kill -0 $BP 2>/dev/null; do
      echo "$(date +%s.%N) $(awk '/VmRSS/{print $2}' /proc/$BP/status) \
$(awk '{print $14+$15}' /proc/$BP/stat) $(awk '/^Threads/{print $2}' /proc/$BP/status) \
$(ls /proc/$BP/fd 2>/dev/null | wc -l)"
      sleep 1
    done ) > $R/broker-proc-$tag-$D.txt 2>/dev/null &
  SAMP=$!
  f=$R/broker-capacity-$tag-$D
  timeout ${STEP_TIMEOUT:-1500} srun --overlap -N1 -n1 -w $N2 --export=ALL \
      python $X/e2-scaling/bench_broker.py --broker $URL --inference $EPN \
      --sessions ${SESSIONS:-1,4,16,64,128,256,384} --seconds ${SECONDS_:-20} \
      --keep-going --create-threads 16 --out $f.json > $f.log 2>&1
  echo "r$r rc=$? $(date -u +%T)"; grep -E "^N=|failed|Traceback" $f.log | cut -c1-200
  echo "r$r keepalive ping timeouts in the broker log: $(grep -c 'keepalive ping timeout' $BL 2>/dev/null)"
  srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
  kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
  kill $SAMP 2>/dev/null
  kill -TERM $BP; wait $BP 2>/dev/null
  grep -c 'keepalive ping timeout' $BL > $R/keepalive-timeouts-$tag.txt 2>/dev/null
  sleep 3
done

echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
