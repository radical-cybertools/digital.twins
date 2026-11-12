#!/bin/bash
# Round 5 X1-X3 in one 5-node allocation (budget, after the hung X1/X2 jobs):
# r4/run_e3_local.sh three times on the same nodes, each with its own broker,
# endpoints and isolation check.  3 repeats, --tasks 100, 16 threads unless
# noted; every harness run capped at RUN_TIMEOUT.
#   X1  wall, spread N=1-4 and one N=4 (one N=1 is spread N=1), both harnesses
#   X2  wall, spread N=1 and 4, --concurrent 32, both harnesses (c=16 is X1)
#   X3  cpu,  as X1
# Order X1, X3, X2: X2 is the cheapest to lose if the time limit hits.
#SBATCH -J r5-e3-x123
#SBATCH -C cpu
#SBATCH -N 5
#SBATCH -t 00:23:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm5/logs/r5-e3-x123-%j.out
#   sbatch -A m5290 -q regular r5/run_x123.sh
set -uo pipefail
E=/pscratch/sd/m/merzky/dt-pm5/digital.twins/experiments/dt-paper
L=$E/r4/run_e3_local.sh
export ENV_SH=$E/r5/env-r5.sh RUN_TIMEOUT=${RUN_TIMEOUT:-300} REPEATS=${REPEATS:-1 2 3}
echo "=== X1 $(date -u +%T)"
RES=r5/local NS="1 2 3 4" NS_ONE=4 ARGS="--tasks 100 --work wall" bash $L
echo "=== X3 $(date -u +%T)"
RES=r5/cpu NS="1 2 3 4" NS_ONE=4 ARGS="--tasks 100 --work cpu" bash $L
echo "=== X2 $(date -u +%T)"
RES=r5/conc LAYOUTS=spread NS="1 4" CONCS=32 ARGS="--tasks 100 --work wall" bash $L
echo "=== end $(date -u +%T)"
