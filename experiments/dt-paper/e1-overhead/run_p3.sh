#!/bin/bash
#SBATCH -J dt-p3
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm2/logs/p3-%j.out
# P3: E1 ex-situ, ROSE learner bare vs through DT, pool 8, 5 repeats.
#   sbatch -A m5290 -q debug run_p3.sh
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm2/env.sh
R=$X/results/p3; mkdir -p $R
for k in 1 2 3 4 5; do
  f=$R/exsitu-pm-pool8-r$k-$D
  python $X/e1-overhead/bench_dt_exsitu.py --workers 8 --samples 400 \
      --windows 20 --out $f.json > $f.log 2>&1
  echo "r$k rc=$? $(grep -c 'msg/s' $f.log) rows"
done
