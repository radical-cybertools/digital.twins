#!/bin/bash
# Round 3b U5: round 3 T2's ex-situ run unchanged on fca2d54 (the lighter
# per-message path, DT #60): rows bare, zmq, dt, dt-batched; windows 1-100;
# pool 8; 400 samples; 5 repeats (r3/run_t2.sh without the py-spy part,
# as r3/run_t2c.sh).
#SBATCH -J r3b-u5
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:20:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3b-u5-%j.out
#   sbatch -A m5290 -q debug r3b/run_u5.sh
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env5.sh}
R=$X/results/${RES:-r3b/u5}; mkdir -p $R
E=$X/e1-overhead/bench_dt_exsitu.py
echo "node $(hostname -s) $(date -u +%FT%TZ)"
python -c "import digitaltwin; print(digitaltwin.__file__)"
for k in 1 2 3 4 5; do
  f=$R/exsitu-pm-pool8-r$k-$D
  python $E --workers 8 --samples 400 --windows 20 \
      --rows bare,zmq,dt,dt-batched --out $f.json > $f.log 2>&1
  echo "r$k rc=$? $(grep -c 'msg/s' $f.log) rows $(date -u +%T)"
done
echo "--- end $(date -u +%FT%TZ)"
