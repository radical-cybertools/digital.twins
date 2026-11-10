#!/bin/bash
# Round 3 T4-A, T4-B, T5-A (local), T5-B: the new harnesses on the local
# process pool 8 (one node), 5 repeats each.
#SBATCH -J r3-t45l
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3-t45l-%j.out
#   sbatch -A m5290 -q regular r3/run_t45_local.sh
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env3.sh}
R4=$X/results/r3/t4; R5=$X/results/r3/t5; mkdir -p $R4 $R5
echo "node $(hostname -s) $(date -u +%FT%TZ)"
for k in 1 2 3 4 5; do
  f=$R4/agents-pm-r$k-$D
  python $X/e2-scaling/bench_agents.py --agents 1,2,4,8,16 --modes side,chain \
      --seconds 3 --out $f.json > $f.log 2>&1
  echo "agents r$k rc=$? $(date -u +%T)"; grep -E "ok=False|doubled=True" $f.log
done
for k in 1 2 3 4 5; do
  f=$R4/publish-pm-pool8-c1-r$k-$D
  python $X/e2-scaling/bench_publish.py --workers 8 --concurrency 1 \
      --rates 0,1,10,100,1000,max --seconds 10 --out $f.json > $f.log 2>&1
  echo "publish c1 r$k rc=$? $(date -u +%T)"; grep rate= $f.log
done
for k in 1 2 3 4 5; do
  f=$R5/dip-pm-pool8-c50-r$k-$D
  python $X/e2-scaling/bench_publish.py --workers 8 --concurrency 50 \
      --rates 0,1,10,100 --seconds 10 --out $f.json > $f.log 2>&1
  echo "dip c50 r$k rc=$? $(date -u +%T)"; grep rate= $f.log
done
for k in 1 2 3 4 5; do
  for c in 1 50; do
    f=$R5/swap-pm-pool8-c$c-r$k-$D
    python $X/e4-hot-swap/bench_swap.py --workers 8 --concurrency $c \
        --swaps 20 --interval 0.5 --out $f.json > $f.log 2>&1
    echo "swap c$c r$k rc=$? $(grep -h swaps= $f.log)"
  done
done
echo "--- end $(date -u +%FT%TZ)"
