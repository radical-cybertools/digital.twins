#!/bin/bash
#SBATCH -J dt-p2
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm2/logs/p2-%j.out
# P2: does the default 256-worker pool slow the learner's engine rows?
#   sbatch -A m5290 -q regular run_p2.sh
# Engine mode, both feeds, all batch sizes; pool 4 8 32 128 256 and the
# unchanged default (ProcessPoolExecutor()); 3 repeats, repeats outermost.
# Then py-spy on engine/inproc at the default pool and at 8 workers.
# One run at a time: the harness uses fixed ZMQ ports 5100/5101.
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm2/env.sh
R=$X/results/p2; mkdir -p $R
H=$X/e1-overhead/streaming_learner_perf.py
nproc; python -c "import os; print('cpu_count', os.cpu_count())"
for k in 1 2 3; do
  for w in 4 8 32 128 256 default; do
    f=$R/learner-engine-pool$w-r$k-$D
    a="--workers $w"; [ $w = default ] && a=""
    t0=$(date +%s)
    python $H --modes engine $a --out $f.json > $f.log 2>&1
    echo "pool $w r$k rc=$? $(( $(date +%s) - t0 ))s"
  done
done
for w in default 8; do
  f=$R/pyspy-engine-inproc-pool$w-$D
  a="--workers $w"; [ $w = default ] && a=""
  py-spy record -r 200 -f speedscope -o $f.speedscope.json -- \
      python $H --modes engine --feeds inproc $a --out $f.json > $f.log 2>&1
  echo "py-spy speedscope pool $w rc=$?"
  py-spy record -r 200 -f raw -o $f.folded -- \
      python $H --modes engine --feeds inproc $a --out $f.json >> $f.log 2>&1
  echo "py-spy folded pool $w rc=$?"
done
