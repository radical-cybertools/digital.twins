#!/bin/bash
# Round 8d, D2b: round 8c's service row itself (s3/s3_service.py, OffsetModel: one
# task whose argument is a pickled TypedData) against radical.3:8010, a
# dragon_native and a concurrent endpoint in one job, order dn conc conc dn.
# D2 (r8d/service_split.py, R8Investigator: a float argument) found no extra
# round trip on either backend; this checks the graph round 8c measured.
#SBATCH -J r8d-d2b
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:25:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8d-d2b-%j.out
#   sbatch -A m5290 -q regular r8d/run_d2b.sh
# Knobs: N (50), REPS (3).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8c/env-r8c.sh}
R=$X/results/r8d/d2b; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
R3=https://95.217.193.116:8010
STAMP=$W/orbit-stamp-r8d-d2b-$J; touch $STAMP
echo "node0 $N0 endpoint $N1 $(date -u +%FT%TZ); radical.3 http $(curl -sk -o /dev/null -m 10 -w '%{http_code}' $R3/)"
ulimit -Sn $(ulimit -Hn)
# radical.3's default credentials (read only); never the throwaway pair here
unset RADICAL_ORBIT_BROKER_CERT RADICAL_ORBIT_BROKER_KEY RADICAL_ORBIT_BROKER_TOKEN
export RADICAL_ORBIT_LOG_FILE=$L/client-r8d-d2b-$J.log
start_ep() {  # name backend
  local n=$1 b=$2 cmd
  if [ $b = dragon_native ]; then cmd="exec dragon -s $(command -v radical-orbit-endpoint.py)"; else cmd="exec $(command -v radical-orbit-endpoint.py)"; fi
  srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w $N1 --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8d-d2b-$n-$J.log RADICAL_ORBIT_BROKER_URL=$R3 \
        RADICAL_ORBIT_RHAPSODY_BACKEND=$b RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 DT_TEST_ENDPOINT_TAG=$n \
    bash -c "ulimit -Sn \$(ulimit -Hn); $cmd -n $n -u $R3 -p default --tunnel none" \
    > $R/endpoint.console-$n-$J.log 2>&1 &
  echo "endpoint $n ($b) up after $(timeout 330 python $X/r8/wait_endpoint.py $R3 $n 300) s"
}
stop_ep() {
  srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $1" 2>/dev/null
  sleep 10
  srun --overlap -N1 -n1 -w $N1 dragon-cleanup > /dev/null 2>&1
}
i=0
for b in dragon_native concurrent concurrent dragon_native; do
  i=$((i+1)); n=pm_r8d_d2b_${b%%_*}_$J
  start_ep $n $b
  f=$R/service-$b-o$i-$J-$D
  E5_BACKEND=$b R8_BACKEND=$b timeout 900 python $X/s3/s3_service.py --broker $R3 --inference $n \
    --n ${N:-50} --repeats ${REPS:-3} --reattaches 0 --out $f.json > $f.log 2>&1
  echo "[$(date -u +%T)] $i $b rc=$? $(grep -E '^repeat' $f.log | tr '\n' '|' | cut -c1-300)"
  stop_ep $n
done
echo "WAN connect s (median of 20): $(for k in $(seq 20); do curl -sk -o /dev/null -m 10 -w '%{time_connect}\n' $R3/; done | sort -n | sed -n 10p)"
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
