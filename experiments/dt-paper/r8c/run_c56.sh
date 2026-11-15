#!/bin/bash
# Round 8c, C5 and C6 in one allocation.
#SBATCH -J r8c-c56
#SBATCH -C cpu
#SBATCH -N 3
#SBATCH -t 00:25:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8c-c56-%j.out
#   sbatch -A m5290 -q debug r8c/run_c56.sh
# C5 (node 0): e2-scaling/bench_streams_join.py (K = 1..32 streams joined)
#   and bench_agents.py (M = 1..16 agents, side and chain), round 3 T4's
#   arguments, once each: both run no task on any engine (DTRuntime(None, ...),
#   pass-through inferences), so the backend cannot matter; the page asks
#   for one run on the current stack in that case.
# C6: r8c/bench_build_steps.py, 16 twins built one after another in one
#   session, shared stream on (the default); broker on node 0, inference
#   endpoint on node 1, learning endpoint on node 2 (dragon_native).
# Knobs: PARTS ("C5 C6"), TWINS (16), PORT (8861).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8c/env-r8c.sh}
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
SN=($(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -2))
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8861}
URL=https://$IP0:$PORT
on() { [[ " ${PARTS:-C5 C6} " == *" $1 "* ]]; }
echo "node0 $N0 ($IP0) endpoints ${SN[*]}  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
if on C5; then
  R=$X/results/r8c/c5; mkdir -p $R
  f=$R/join-pm-r1-$J-$D
  timeout 900 python $X/e2-scaling/bench_streams_join.py --out $f.json > $f.log 2>&1
  echo "[$(date -u +%T)] C5 join rc=$? $(tail -2 $f.log | tr '\n' '|' | cut -c1-200)"
  f=$R/agents-pm-r1-$J-$D
  timeout 900 python $X/e2-scaling/bench_agents.py --agents 1,2,4,8,16 --modes side,chain \
    --seconds 3 --out $f.json > $f.log 2>&1
  echo "[$(date -u +%T)] C5 agents rc=$? $(tail -2 $f.log | tr '\n' '|' | cut -c1-200)"
fi
if on C6; then
  R=$X/results/r8c/c6; mkdir -p $R
  T=$W/tls/r8c-c6-$J; mkdir -p $T; chmod 700 $W/tls $T
  openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
      -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
      -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
  python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
  chmod 600 $T/*
  export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
  export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token) RADICAL_ORBIT_BROKER_URL=$URL
  export DT_STREAM_BACKEND=orbit R8_BACKEND=dragon_native
  STAMP=$W/orbit-stamp-r8c-c6-$J; touch $STAMP
  RADICAL_ORBIT_LOG_FILE=$L/broker-r8c-c6-$J.log \
    radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$J.log 2>&1 &
  BP=$!
  sleep 8
  kill -0 $BP 2>/dev/null || { echo "broker died"; exit 3; }
  names=(r8c6_inf r8c6_l0); EPIDS=()
  for k in 0 1; do
    srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w ${SN[$k]} --export=ALL \
      env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8c-c6-${names[$k]}-$J.log \
          RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
          DT_TEST_ENDPOINT_TAG=${names[$k]} \
      bash -c "ulimit -Sn \$(ulimit -Hn); exec dragon -s $(command -v radical-orbit-endpoint.py) -n ${names[$k]} -u $URL -p default --tunnel none" \
      > $R/endpoint.console-${names[$k]}-$J.log 2>&1 &
    EPIDS+=($!)
  done
  for n in ${names[@]}; do echo "$n up after $(timeout 330 python $X/r8/wait_endpoint.py $URL $n 300) s"; done
  export RADICAL_ORBIT_LOG_FILE=$L/client-r8c-c6-$J.log
  f=$R/build-steps-$J-$D
  timeout 900 python $X/r8c/bench_build_steps.py --broker $URL --inference ${names[0]} \
    --learning ${names[1]} --twins ${TWINS:-16} --out $f.json > $f.log 2>&1
  echo "[$(date -u +%T)] C6 rc=$?"; tail -3 $f.log | cut -c1-400
  ps=(); for k in 0 1; do srun --overlap -N1 -n1 -w ${SN[$k]} pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n ${names[$k]}" 2>/dev/null & ps+=($!); done; wait ${ps[@]}
  sleep 10; kill -TERM ${EPIDS[@]} 2>/dev/null; wait ${EPIDS[@]} 2>/dev/null
  ps=(); for k in 0 1; do srun --overlap -N1 -n1 -w ${SN[$k]} dragon-cleanup > /dev/null 2>&1 & ps+=($!); done; wait ${ps[@]}
  kill -TERM $BP; wait $BP 2>/dev/null
  echo "--- ~/.radical/orbit newer than stamp (must be empty):"
  find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
fi
echo "--- end $(date -u +%FT%TZ)"
