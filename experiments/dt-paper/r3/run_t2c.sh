#!/bin/bash
# Round 3 T2c: the ex-situ rows on the 52926e6 stack, digitaltwin as
# installed (stack) and with fix/pm-message-path (DT_SRC=$W/dt-fix/src):
# skip unconsumed streamed inference, inline ON_INPUT for the learner,
# no gather for one component, lazy logging.  As r3/run_t2.sh, 5 repeats.
#SBATCH -J r3-t2c
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3-t2c-%j.out
#   sbatch -A m5290 -q debug r3/run_t2c.sh
set -uo pipefail
W=/pscratch/sd/m/merzky/dt-pm3
for variant in stack msgpath; do
  if [ $variant = msgpath ]; then export DT_SRC=$W/dt-fix/src; else unset DT_SRC; fi
  source $W/env4.sh
  R=$X/results/r3/t2c; mkdir -p $R
  python -c "import digitaltwin; print('$variant', digitaltwin.__file__)"
  for k in 1 2 3 4 5; do
    f=$R/exsitu-pm-pool8-$variant-r$k-$D
    python $X/e1-overhead/bench_dt_exsitu.py --workers 8 --samples 400 --windows 20 \
        --rows bare,zmq,dt,dt-batched --out $f.json > $f.log 2>&1
    echo "$variant r$k rc=$? $(grep -c 'msg/s' $f.log) rows $(date -u +%T)"
  done
done
echo "--- end $(date -u +%FT%TZ)"
