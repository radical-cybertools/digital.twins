#!/bin/bash
# Round 8d, D3: local dragon_native per-task cost by pool size (r8d/hop_local.py, from the page).
#SBATCH -J r8d-d3
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:15:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8d-d3-%j.out
#   sbatch -A m5290 -q debug r8d/run_d3.sh
# One CPU node: no-op tasks, sequential (400 after 50 warm-up), under `dragon -s`
# with W = 4, 16, 32, 64, 128 workers, and without Dragon for thread and
# procpool (4 workers). Knobs: WS ("4 16 32 64 128"), REPEATS (2).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8c/env-r8c.sh}
R=$X/results/r8d/d3; mkdir -p $R
J=$SLURM_JOB_ID
H=$X/r8d/hop_local.py
echo "node $(hostname -s) $(date -u +%FT%TZ) $(python -c 'import importlib.metadata as m; print("rhapsody", m.version("rhapsody-py"), "dragonhpc", m.version("dragonhpc"))')"
ulimit -Sn $(ulimit -Hn)
for k in $(seq 1 ${REPEATS:-2}); do
  for w in ${WS:-4 16 32 64 128}; do
    f=$R/hop-dragon-w$w-r$k-$J-$D.log
    W=$w timeout 300 dragon -s $H dragon > $f 2>&1
    echo "r$k W=$w rc=$? $(grep 'total p50' $f)"
    dragon-cleanup > /dev/null 2>&1 || true
  done
  for which in thread procpool; do
    f=$R/hop-$which-r$k-$J-$D.log
    timeout 300 python $H $which > $f 2>&1
    echo "r$k $which rc=$? $(grep 'total p50' $f)"
  done
done
echo "--- end $(date -u +%FT%TZ)"
