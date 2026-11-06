#!/bin/bash
#SBATCH -J dt-p7
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm2/logs/p7-%j.out
# P7: E4 model-update propagation on the local pool (pool 8), 3 repeats.
#   sbatch -A m5290 -q regular run_p7.sh
# The cross-node ORBIT variant is run_p7_orbit.sh (P4 layout).
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm2/env.sh
R=$X/results/p7; mkdir -p $R
for k in 1 2 3; do
  f=$R/update-pm-local-pool8-r$k-$D
  python $X/e4-hot-swap/bench_model_update.py --workers 8 \
      --intervals 1,0.1,0.01 --seconds 20 --out $f.json > $f.log 2>&1
  echo "local r$k rc=$?"; grep interval $f.log
done
