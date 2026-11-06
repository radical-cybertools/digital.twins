#!/bin/bash
#SBATCH -J dt-p2diag
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm2/logs/p2diag-%j.out
# P2 diagnosis: asyncflow's 10 ms run-loop sleep, patched at run time only.
#   sbatch -A m5290 -q debug run_p2diag.sh
# Learner engine rows (pool 8) and the E1 in-situ rows (pool 8, c=50) with
# the sleep at 0.01 (control, through the same wrapper), 0.001 and 0.
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm2/env.sh
R=$X/results/p2; mkdir -p $R
G=$X/e1-overhead/diag_asyncflow_poll.py
for k in 1 2; do
  for poll in 0.01 0.001 0; do
    f=$R/diag-poll$poll-learner-engine-pool8-r$k-$D
    python $G --poll $poll streaming_learner_perf.py -- --modes engine \
        --workers 8 --out $f.json > $f.log 2>&1
    echo "learner poll=$poll r$k rc=$? $(grep 'batch= 100' $f.log | tr -s ' ' | tr '\n' '|')"
    f=$R/diag-poll$poll-insitu-pool8-c50-r$k-$D
    python $G --poll $poll bench_dt_insitu.py -- --workers 8 --concurrent 50 \
        --tasks 1000 --out $f.json > $f.log 2>&1
    echo "insitu poll=$poll r$k rc=$? $(grep -E 'p50|req/s' $f.log | tr -s ' ' | tr '\n' '|')"
  done
done
