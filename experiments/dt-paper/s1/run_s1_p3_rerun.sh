#!/bin/bash
# Round 2 (S1): generated from e1-overhead/run_p3.sh for the paper stack; only paths and names differ.
# Unchanged rerun of run_s1_p3.sh (the contract: a result that contradicts E1 is rerun once).
#SBATCH -J s1-p3re
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/s1-p3re-%j.out
# P3: E1 ex-situ, ROSE learner bare vs through DT, pool 8, 5 repeats.
#   sbatch -A m5290 -q debug run_p3.sh
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm3/env.sh
R=$X/results/s1/p3-rerun; mkdir -p $R
for k in 1 2 3 4 5; do
  f=$R/exsitu-pm-pool8-r$k-$D
  python $X/e1-overhead/bench_dt_exsitu.py --workers 8 --samples 400 \
      --windows 20 --out $f.json > $f.log 2>&1
  echo "r$k rc=$? $(grep -c 'msg/s' $f.log) rows"
done
