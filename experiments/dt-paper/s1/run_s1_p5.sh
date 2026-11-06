#!/bin/bash
# Round 2 (S1): generated from e2-scaling/run_p5.sh for the paper stack; only paths and names differ.
#SBATCH -J s1-p5
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/s1-p5-%j.out
# P5: E2a (N twins, one engine) and E2b (K joined streams), 3 repeats each.
#   sbatch -A m5290 -q debug run_p5.sh
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm3/env.sh
R=$X/results/s1/p5; mkdir -p $R
for k in 1 2 3; do
  f=$R/twins-pm-pool64-r$k-$D
  python $X/e2-scaling/bench_twins.py --twins 1,2,4,8,16,32,64 --workers 64 \
      --seconds 10 --out $f.json > $f.log 2>&1
  echo "twins r$k rc=$?"; grep twins= $f.log
done
for k in 1 2 3; do
  f=$R/join-pm-r$k-$D
  python $X/e2-scaling/bench_streams_join.py --streams 1,2,4,8,16,32 \
      --seconds 5 --out $f.json > $f.log 2>&1
  echo "join r$k rc=$?"; grep -E "ok=False|doubled=True" $f.log
done
