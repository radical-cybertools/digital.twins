#!/bin/bash
#SBATCH -J r4-e3-local
#SBATCH -C cpu
#SBATCH -N 5
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm4/logs/r4-e3-local-%j.out
# Round 4, E3 on Perlmutter only: node 0 runs the broker (dt plugin) and the
# client, nodes 1-4 are the four sites, one rhapsody endpoint each, tagged
# with its name.  bench_sites.py (one twin through the DT service) and
# xgf_sites.py (hand-wired) in both layouts, N = 1-4, 3 repeats.
#   sbatch -A m5290 -q regular r4/run_e3_local.sh   (ENV_SH, RES optional)
# Round 4 knobs (defaults as before): REPEATS ("1 2 3"), LAYOUTS ("spread one"),
# HARNESSES ("dt xgf"), NS (1,2,3,4), CONCS ("": the harness default 16;
# else one run per value, tagged -c<C>), NSITES (4: site endpoints on nodes
# 1..NSITES), ARGS (extra harness arguments, e.g. for a smoke test).
# Throwaway TLS as in s1/run_s1_p4.sh; ~/.radical/orbit checked before/after.
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm4/digital.twins/experiments/dt-paper/r4/env-r4.sh}
R=$X/results/${RES:-r4/local}; mkdir -p $R
E3=$X/e3-portability
L=$W/orbit-logs
N0=$(hostname -s)
NSITES=${NSITES:-4}
SITES_NODES=($(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -$NSITES))
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=8141
URL=https://$IP0:$PORT
echo "node0 $N0 ($IP0)  sites ${SITES_NODES[*]}  broker $URL"

T=$W/tls/r4-$SLURM_JOB_ID; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm3" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem
export RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)

STAMP=$W/orbit-stamp-r4-local-$SLURM_JOB_ID; touch $STAMP
# the dt plugin builds its rhapsody client from the broker URL
RADICAL_ORBIT_LOG_FILE=$L/broker-r4-$SLURM_JOB_ID.log RADICAL_ORBIT_BROKER_URL=wss://$IP0:$PORT \
DT_STREAM_BACKEND=orbit \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt \
  > $R/broker-r4-$D.console.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; tail -20 $R/broker-r4-$D.console.log; exit 3; }
export RADICAL_ORBIT_LOG_FILE=$L/client-r4-$SLURM_JOB_ID.log

EPS=()
for k in $(seq 0 $((NSITES - 1))); do
  name=e3_s$k
  srun --overlap -N1 -n1 -w ${SITES_NODES[$k]} --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-$name-$SLURM_JOB_ID.log RADICAL_ORBIT_BROKER_URL=$URL \
        RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
        DT_TEST_ENDPOINT_TAG=$name \
    radical-orbit-endpoint.py -n $name -u $URL -p default --tunnel none \
    > $R/endpoint-$name-$D.console.log 2>&1 &
  EPS+=($!)
done
sleep 20
EP_LIST=$(seq -s, -f "e3_s%g" 0 $((NSITES - 1)))

CONCS=${CONCS:-}
for r in ${REPEATS:-1 2 3}; do
  for lay in ${LAYOUTS:-spread one}; do
    for c in ${CONCS:-default}; do
      ctag=; carg=()
      [ $c != default ] && ctag=-c$c && carg=(--concurrent $c)
      for h in ${HARNESSES:-dt xgf}; do
        if [ $h = dt ]; then H=bench_sites.py; f=$R/sites-$lay$ctag-r$r-r4-$D
        else H=xgf_sites.py; f=$R/xgf-$lay$ctag-r$r-r4-$D; fi
        python $E3/$H --broker $URL --endpoints $EP_LIST --n ${NS:-1,2,3,4} \
            --layout $lay "${carg[@]}" ${ARGS:-} --out $f.json > $f.log 2>&1
        echo "$h $lay$ctag r$r rc=$? $(date -u +%T) $(grep -h 'req/s' $f.log | tr '\n' '|')"
      done
    done
  done
done

kill -TERM ${EPS[@]}; wait ${EPS[@]} 2>/dev/null
kill -TERM $BP; wait $BP
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
echo "--- end"
