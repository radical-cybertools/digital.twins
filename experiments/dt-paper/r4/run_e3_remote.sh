#!/bin/bash
#SBATCH -J r4-e3-remote
#SBATCH -C cpu
#SBATCH -N 4
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm4/logs/r4-e3-remote-%j.out
# Round 4, E3 across facilities: the broker and the dt service are
# radical.3's :8010 (shared, never restart it; never touch :8011, the E5
# 30-day run).  Sites: three Perlmutter endpoints on nodes 1-3 and
# `r3_site`, an endpoint on radical.3 that the laptop session starts before
# this job (check: it is in the broker's topology, see README).  The client
# runs on node 0.  bench_sites.py and xgf_sites.py, spread and one, N = 1-4
# with radical.3 as the fourth site, 3 repeats.
#   sbatch -A m5290 -q regular r4/run_e3_remote.sh
# Round 4 knobs (defaults as before): REPEATS ("1 2 3"), LAYOUTS ("spread one"),
# HARNESSES ("dt xgf").  The job stops (exit 6) if r3_site is not in the
# broker's topology.
# Credentials: the default pair and token in ~/.radical/orbit, read only
# (round 2's S2 rule); the throwaway variables are unset.
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm4/digital.twins/experiments/dt-paper/r4/env-r4.sh}
unset RADICAL_ORBIT_BROKER_CERT RADICAL_ORBIT_BROKER_KEY RADICAL_ORBIT_BROKER_TOKEN
R=$X/results/${RES:-r4/remote}; mkdir -p $R
E3=$X/e3-portability
L=$W/orbit-logs
URL=https://95.217.193.116:8010
export RADICAL_ORBIT_BROKER_URL=$URL
N0=$(hostname -s)
SITES_NODES=($(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | head -3))
echo "client $N0  sites ${SITES_NODES[*]} + r3_site  broker $URL"
for i in $(seq 20); do curl -sk -o /dev/null -w '%{time_connect}\n' $URL/; done \
    > $R/wan-rtt-$SLURM_JOB_ID-$D.txt

STAMP=$W/orbit-stamp-r4-remote-$SLURM_JOB_ID; touch $STAMP
# r3_site must already be there (the laptop session starts it); else skip W3
RADICAL_ORBIT_LOG_FILE=$L/client-r4-topology-$SLURM_JOB_ID.log \
  python $X/r4/check_topology.py --broker $URL --name r3_site --wait 30 \
  | tee $R/topology-check-$SLURM_JOB_ID-$D.txt
if [ ${PIPESTATUS[0]} != 0 ]; then
  echo "r3_site is not in the broker's topology: skipping W3"
  find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
  exit 6
fi
export RADICAL_ORBIT_LOG_FILE=$L/client-r4-remote-$SLURM_JOB_ID.log
EPS=()
for k in 0 1 2; do
  name=pm_e3_s${k}_$SLURM_JOB_ID
  srun --overlap -N1 -n1 -w ${SITES_NODES[$k]} --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-$name.log \
        RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
        DT_TEST_ENDPOINT_TAG=$name \
    radical-orbit-endpoint.py -n $name -u $URL -p default --tunnel none \
    > $R/endpoint-$name-$D.console.log 2>&1 &
  EPS+=($!)
done
sleep 30
EP_LIST=pm_e3_s0_$SLURM_JOB_ID,pm_e3_s1_$SLURM_JOB_ID,pm_e3_s2_$SLURM_JOB_ID,r3_site

for r in ${REPEATS:-1 2 3}; do
  for lay in ${LAYOUTS:-spread one}; do
    for h in ${HARNESSES:-dt xgf}; do
      if [ $h = dt ]; then H=bench_sites.py; f=$R/sites-$lay-r$r-r4-$D
      else H=xgf_sites.py; f=$R/xgf-$lay-r$r-r4-$D; fi
      python $E3/$H --broker $URL --endpoints $EP_LIST --n 1,2,3,4 \
          --layout $lay --tasks 100 --out $f.json > $f.log 2>&1
      echo "$h $lay r$r rc=$? $(date -u +%T) $(grep -h 'req/s' $f.log | tr '\n' '|')"
    done
  done
done

kill -TERM ${EPS[@]}; wait ${EPS[@]} 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$D.txt
echo "--- end"
