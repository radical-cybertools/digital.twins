#!/bin/bash
#SBATCH -J dt-p1
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 02:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm2/logs/p1-%j.out
# P1: E1 pool-size sweep, all three rows, 5 repeats, on one CPU node.
#   sbatch -A m5290 -q regular run_p1.sh
# (salloc + srun steps from the login node hung on 2026-11-06; see journal)
# Repeats are the outer loop so slow drift spreads over all cells.
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm2/env.sh
R=$X/results/p1; mkdir -p $R
POOLS=${POOLS:-"1 2 4 8 16 32 64 128 256"}
CONCS=${CONCS:-"50 500"}
for k in 1 2 3 4 5; do
  for w in $POOLS; do
    for c in $CONCS; do
      f=$R/insitu-pm-pool$w-c$c-r$k-$D
      t0=$(date +%s)
      python $X/e1-overhead/bench_dt_insitu.py --workers $w --concurrent $c \
          --tasks 1000 --out $f.json > $f.log 2>&1
      echo "pool $w c $c r$k rc=$? $(( $(date +%s) - t0 ))s"
    done
  done
done
