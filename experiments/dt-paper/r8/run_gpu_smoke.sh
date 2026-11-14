#!/bin/bash
# Round 8, R8-0 GPU check: TF in a dragon_native worker on one A100 node.
#SBATCH -J r8-gpu-smoke
#SBATCH -C gpu
#SBATCH -N 1
#SBATCH -t 00:20:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-gpu-smoke-%j.out
#   sbatch -A m5290_g -q debug r8/run_gpu_smoke.sh
# venv ve8-xgf (round 1's TF conda env + the round 8 pins), xGFabric
# dt-pm2/xGFabric (fix/pinn-eval), September archives; nvidia wheel
# libraries first on LD_LIBRARY_PATH (as run_b3.sbatch), never /usr/lib64.
set -uo pipefail
W=/pscratch/sd/m/merzky/dt-pm8
ENV=/pscratch/sd/m/merzky/dt-pm2/xgf/env
VE=$W/ve8-xgf
export PATH=$VE/bin:$PATH
export XGF_DIR=/pscratch/sd/m/merzky/dt-pm2/xGFabric
cd $W/digital.twins
X=experiments/dt-paper
R=$X/results/r8/r8-0; mkdir -p $R
D=stack-r8-20261114
export TF_CPP_MIN_LOG_LEVEL=1 TF_FORCE_GPU_ALLOW_GROWTH=true
export PLAYGROUND_DIR=$W/xgf/check-$SLURM_JOB_ID; mkdir -p $PLAYGROUND_DIR
NV=$(ls -d $ENV/lib/python3.12/site-packages/nvidia/*/lib | paste -sd:)
export LD_LIBRARY_PATH="$NV${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export R8_FS=/pscratch
echo "xGFabric $(git -C $XGF_DIR rev-parse --short HEAD) ($(git -C $XGF_DIR rev-parse --abbrev-ref HEAD)); $(nvidia-smi -L | head -4)"
ulimit -Sn $(ulimit -Hn)
timeout 1000 dragon -s $X/r8/gpu_smoke.py --out $R/gpu-smoke-$SLURM_JOB_ID-$D.json \
  > $R/gpu-smoke-$SLURM_JOB_ID-$D.log 2>&1
echo "rc=$? $(tail -1 $R/gpu-smoke-$SLURM_JOB_ID-$D.log | cut -c1-800)"
dragon-cleanup > /dev/null 2>&1
echo "--- end $(date -u +%FT%TZ)"
