#!/bin/bash
#SBATCH -J dt-p8a
#SBATCH -C gpu
#SBATCH -q regular
#SBATCH -N 1
#SBATCH -t 02:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm2/logs/p8a-%j.out
# E6 / P8a: per-surrogate inference cost, GPU vs CPU, on one A100 node.
# Submit from the digital_twins checkout:  sbatch -A m5290_g run_p8a.sbatch
set -uo pipefail

W=/pscratch/sd/m/merzky/dt-pm2
ENV=$W/xgf/env
export XGF_DIR=$W/xGFabric
export TF_CPP_MIN_LOG_LEVEL=1
# the env's own pip CUDA wheels (tensorflow[and-cuda]); nothing prepended to
# LD_LIBRARY_PATH, no cudatoolkit module
module unload cudatoolkit 2>/dev/null || true
cd $W/digital_twins
X=experiments/dt-paper
R=$X/results/p8
mkdir -p $R
nvidia-smi -L | tee $R/nvidia-smi-$SLURM_JOB_ID.txt

run() {  # model device rep
  local m=$1 dev=$2 k=$3 log=$R/surrogate-$1-$2-r$3.log
  if [ "$dev" = cpu ]; then
    CUDA_VISIBLE_DEVICES= srun -N1 -n1 -c 128 --cpu-bind=none --gpus=0 \
      $ENV/bin/python $X/e6-use-cases/bench_surrogates.py --model $m \
      --warm 50 --reload 5 --out $R/surrogate-$m-$dev-r$k.json > $log 2>&1
  else
    srun -N1 -n1 -c 32 --gpus=1 \
      $ENV/bin/python $X/e6-use-cases/bench_surrogates.py --model $m \
      --warm 50 --reload 10 --out $R/surrogate-$m-$dev-r$k.json > $log 2>&1
  fi
  local rc=$?
  if [ "$dev" = gpu ] && grep -qi "could not find cuda drivers\|GPUs: \[\]" $log; then
    echo "P8a $m $dev r$k: GPU NOT USED (failed GPU run)"; rc=99
  fi
  echo "P8a $m $dev r$k rc=$rc: $(tail -1 $log)"
}

for dev in gpu cpu; do
  for m in fno pinn; do
    for k in 1 2 3; do run $m $dev $k; done
  done
done
echo done
