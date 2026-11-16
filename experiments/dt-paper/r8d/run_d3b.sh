#!/bin/bash
# Round 8d, D3b: the idle-worker order test (r8d/hop_local_order.py), one CPU node.
#SBATCH -J r8d-d3b
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:15:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8d-d3b-%j.out
#   sbatch -A m5290 -q debug r8d/run_d3b.sh
# W = 4 and 128, stock FIFO and patched LIFO idle order, alternating, 3 repeats.
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8c/env-r8c.sh}
R=$X/results/r8d/d3b; mkdir -p $R
J=$SLURM_JOB_ID
H=$X/r8d/hop_local_order.py
echo "node $(hostname -s) $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
for k in 1 2 3; do
  for w in 128 4; do
    for o in fifo lifo; do
      f=$R/hop-w$w-$o-r$k-$J-$D.log
      W=$w ORDER=$o timeout 300 dragon -s $H > $f 2>&1
      echo "r$k rc=$? $(grep 'total p50' $f)"
      dragon-cleanup > /dev/null 2>&1 || true
    done
  done
done
echo "--- end $(date -u +%FT%TZ)"
