#!/bin/bash
# Round 3 T4-D and T5-C (local part): round 2's E2a, E2b and P7 (local) with
# 5 repeats instead of 3, arguments as s1/run_s1_p5.sh and s1/run_s1_p7.sh.
#SBATCH -J r3-t45r
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3-t45r-%j.out
#   sbatch -A m5290 -q regular r3/run_t45_reruns.sh
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env3.sh}
R4=$X/results/r3/t4; R5=$X/results/r3/t5; mkdir -p $R4 $R5
echo "node $(hostname -s) $(date -u +%FT%TZ)"
for k in 1 2 3 4 5; do
  f=$R4/twins-pm-pool64-r$k-$D
  python $X/e2-scaling/bench_twins.py --twins 1,2,4,8,16,32,64 --workers 64 \
      --seconds 10 --out $f.json > $f.log 2>&1
  echo "twins r$k rc=$? $(date -u +%T)"
done
for k in 1 2 3 4 5; do
  f=$R4/join-pm-r$k-$D
  python $X/e2-scaling/bench_streams_join.py --streams 1,2,4,8,16,32 \
      --seconds 5 --out $f.json > $f.log 2>&1
  echo "join r$k rc=$? $(date -u +%T)"; grep -E "ok=False|doubled=True" $f.log
done
for k in 1 2 3 4 5; do
  f=$R5/update-pm-local-pool8-r$k-$D
  python $X/e4-hot-swap/bench_model_update.py --workers 8 \
      --intervals 1,0.1,0.01 --seconds 20 --out $f.json > $f.log 2>&1
  echo "update local r$k rc=$? $(date -u +%T)"; grep interval $f.log
done
echo "--- end $(date -u +%FT%TZ)"
