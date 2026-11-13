#!/bin/bash
# Round 7: E2 per-session cost, from r6/run_broker.sh.
#SBATCH -J r7-broker
#SBATCH -C cpu
#SBATCH -N 3
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm7/logs/r7-broker-%j.out
#   sbatch -A m5290 -q regular --export=ALL,RES=r7/notel,TELEMETRY=0 r7/run_broker.sh
# As round 6: broker (--plugins dt, throwaway TLS) on node 0, endpoint on
# node 1, bench_broker.py from node 2, a fresh broker and endpoint per
# repeat, the broker sampled from /proc every second.  New in round 7:
#  - the endpoint process is sampled from /proc the same way, on node 1
#    (endpoint-proc-<tag>-$D.txt: epoch, VmRSS kB, CPU ticks, threads, fds);
#  - TELEMETRY sets RADICAL_ORBIT_RHAPSODY_TELEMETRY on the endpoint (as r6);
#  - PROFILE=1 (Z2, one N): the broker runs under r7/frame_counter.py
#    (frames per second by kind into frames-<tag>-$D.jsonl), and once the
#    client's load phase starts (--load-marker) py-spy dumps, then records
#    PROFILE_S seconds (30) at --rate 100 --idle, of the broker and the
#    endpoint, folded (raw) and speedscope; SECONDS_ must cover it (40).
# Knobs: REPEATS ("1 2"), SESSIONS (spaces: "1 4 16 64 128 256 384"),
#   SECONDS_ (20), PING, TELEMETRY, STEP_TIMEOUT (s per repeat, 2400),
#   BENCH_ARGS (e.g. --twins-per-session 4), PROFILE, PROFILE_S, PORT (8161).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm7/digital.twins/experiments/dt-paper/r7/env-r7.sh}
R=$X/results/${RES:-r7/notel}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
N2=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 2p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8161}
URL=https://$IP0:$PORT
[ -n "${PING:-}" ] && export RADICAL_ORBIT_PING_TIMEOUT=$PING
SES=${SESSIONS:-1 4 16 64 128 256 384}; SES=${SES// /,}
PS=${PROFILE_S:-30}
echo "node0 $N0 ($IP0) node1 $N1 node2 $N2  broker $URL  ping ${PING:-default}  telemetry ${TELEMETRY:-default}  profile ${PROFILE:-0}  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
echo "ulimit -n soft $(ulimit -Sn)"; for n in $N1 $N2; do srun --overlap -N1 -n1 -w $n bash -c 'echo "$(hostname -s) soft $(ulimit -Sn) hard $(ulimit -Hn)"'; done
PYSPY=$(command -v py-spy)

T=$W/tls/r7-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm7" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r7-$J; touch $STAMP

SAMPLER=$PWD/$X/r7/proc_sampler.sh     # epoch, VmRSS kB, CPU ticks, threads, fds

for r in ${REPEATS:-1 2}; do
  tag=r$r-$J
  BL=$L/broker-r7-$tag.log
  bcmd=(radical-orbit-broker.py)
  if [ "${PROFILE:-0}" = 1 ]; then
    bcmd=(python $X/r7/frame_counter.py "$(command -v radical-orbit-broker.py)")
    export FRAME_COUNT_FILE=$PWD/$R/frames-$tag-$D.jsonl
  fi
  RADICAL_ORBIT_LOG_FILE=$BL RADICAL_ORBIT_BROKER_URL=$URL \
    "${bcmd[@]}" --host $IP0 --port $PORT --plugins dt \
    > $R/broker.console-$tag.log 2>&1 &
  BP=$!
  unset FRAME_COUNT_FILE
  sleep 8
  kill -0 $BP 2>/dev/null || { echo "r$r: broker died"; tail -20 $R/broker.console-$tag.log; continue; }
  EPN=dt_r7_ep_$r
  envs=(RADICAL_ORBIT_LOG_FILE=$L/endpoint-r7-$tag.log RADICAL_ORBIT_BROKER_URL=$URL
        RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0
        DT_TEST_ENDPOINT_TAG=$EPN)
  [ -n "${TELEMETRY:-}" ] && envs+=(RADICAL_ORBIT_RHAPSODY_TELEMETRY=$TELEMETRY)
  srun --overlap -N1 -n1 -w $N1 --export=ALL env "${envs[@]}" \
    radical-orbit-endpoint.py -n $EPN -u $URL -p default --tunnel none \
    > $R/endpoint.console-$tag.log 2>&1 &
  EP=$!
  sleep 15
  $SAMPLER $BP > $R/broker-proc-$tag-$D.txt 2>/dev/null &
  SAMP=$!
  # endpoint sampler on node 1: the endpoint's python process
  srun --overlap -N1 -n1 -w $N1 $SAMPLER -f "radical-orbit-endpoint.py -n $EPN" \
    > $R/endpoint-proc-$tag-$D.txt 2> $R/endpoint-proc-$tag-$D.err &
  ESAMP=$!
  f=$R/broker-capacity-$tag-$D
  marker=()
  if [ "${PROFILE:-0}" = 1 ]; then
    M=$PWD/$R/load-$tag; marker=(--load-marker $M)
    ( n1=${SES%%,*}
      while [ ! -f $M.n$n1 ]; do sleep 0.5; done; sleep 2
      P=$PWD/$R/pyspy-$tag
      timeout 60 $PYSPY dump --pid $BP > $P-broker-dump.txt 2>&1
      timeout $((PS + 30)) $PYSPY record --pid $BP --rate 100 --idle --duration $PS --format raw -o $P-broker.folded > $P-broker-record.log 2>&1 &
      srun --overlap -N1 -n1 -w $N1 bash -c "p=\$(pgrep -u $USER -o -f 'radical-orbit-endpoint.py -n $EPN'); \
        timeout 60 $PYSPY dump --pid \$p > $P-endpoint-dump.txt 2>&1; \
        timeout $((PS + 30)) $PYSPY record --pid \$p --rate 100 --idle --duration $PS --format raw -o $P-endpoint.folded > $P-endpoint-record.log 2>&1"
      wait
      echo "py-spy done $(date -u +%T)" ) > $R/pyspy-$tag.log 2>&1 &
  fi
  timeout ${STEP_TIMEOUT:-2400} srun --overlap -N1 -n1 -w $N2 --export=ALL \
      python $X/e2-scaling/bench_broker.py --broker $URL --inference $EPN \
      --sessions $SES --seconds ${SECONDS_:-20} \
      --keep-going --create-threads 16 ${BENCH_ARGS:-} "${marker[@]}" --out $f.json > $f.log 2>&1
  echo "r$r rc=$? $(date -u +%T)"; grep -E "^N=|failed|Traceback" $f.log | cut -c1-200
  [ "${PROFILE:-0}" = 1 ] && { sleep 5; cat $R/pyspy-$tag.log; }
  echo "r$r keepalive ping timeouts in the broker log: $(grep -c 'keepalive ping timeout' $BL 2>/dev/null)"
  srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
  kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
  kill $SAMP $ESAMP 2>/dev/null
  kill -TERM $BP; wait $BP 2>/dev/null
  grep -c 'keepalive ping timeout' $BL > $R/keepalive-timeouts-$tag.txt 2>/dev/null
  sleep 3
done

echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
