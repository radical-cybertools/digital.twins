#!/bin/bash
# Round 3c V1 + V2, one node, one allocation (V2 compares with V1).
#SBATCH -J r3c-v12
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3c-v12-%j.out
#   sbatch -A m5290 -q debug r3c/run_v12.sh      (PARTS="v1 v2" by default)
#   V1  round 2's S1 P1 (s1/run_s1_p1.sh) with --bursts 5: pools 1..256,
#       c = 50, 500, 5 repeats, all rows in one process, default order, the
#       client's GC as it comes.  Repeats are the outer loop.
#   V2  V1's runs at pools 1, 8, 64, c=500, 5 repeats, the client's GC
#       threshold raised to $GCT through r3b/nogc.py --gc-threshold.
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env6.sh}
B=$X/e1-overhead/bench_dt_insitu.py
GCT=${GCT:-100000,50,50}
echo "node $(hostname -s) $(date -u +%FT%TZ)  gc threshold for V2: $GCT"
PARTS=${PARTS:-v1 v2}
has() { case " $PARTS " in *" $1 "*) return 0;; esac; return 1; }
summ() { grep -h 'req/s' $1 | sed 's/.*(\(.*\) req\/s)/\1/' | tr '\n' ' '; }
POOLS=${POOLS:-"1 2 4 8 16 32 64 128 256"}
if has v1; then
  R=$X/results/r3c/v1; mkdir -p $R
  for k in 1 2 3 4 5; do
    for w in $POOLS; do
      for c in 50 500; do
        f=$R/insitu-pm-pool$w-c$c-r$k-$D
        t0=$(date +%s)
        python $B --workers $w --concurrent $c --tasks 1000 --bursts 5 \
            --out $f.json > $f.log 2>&1
        echo "V1 pool $w c $c r$k rc=$? $(( $(date +%s) - t0 ))s $(summ $f.log)"
      done
    done
  done
fi
if has v2; then
  R=$X/results/r3c/v2; mkdir -p $R
  for k in 1 2 3 4 5; do
    for w in 1 8 64; do
      f=$R/insitu-pm-pool$w-c500-r$k-$D
      python $X/r3b/nogc.py --gc-threshold $GCT $B --workers $w --concurrent 500 \
          --tasks 1000 --bursts 5 --out $f.json > $f.log 2>&1
      echo "V2 pool $w c 500 r$k rc=$? $(head -1 $f.log) $(summ $f.log)"
    done
  done
fi
echo "--- end $(date -u +%FT%TZ)"
