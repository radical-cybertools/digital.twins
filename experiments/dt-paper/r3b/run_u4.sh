#!/bin/bash
# Round 3b U4: round 2's S1 P1 (s1/run_s1_p1.sh) unchanged on fca2d54, then
# each row in its own process at pools 1, 8 and 64, c=500.
#SBATCH -J r3b-u4
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3b-u4-%j.out
#   sbatch -A m5290 -q debug r3b/run_u4.sh            (PARTS="p1 solo" by default)
#   P1    pools 1..256 x c 50, 500 x 5 repeats, all three rows in one
#         process, --tasks 1000, one burst (the S1 P1 runs)
#   solo  rows bare, investigator, agent each in its own process, pools 1,
#         8, 64, c=500, 5 repeats with rotated order, 5 bursts
# Repeats are the outer loop so slow drift spreads over all cells.
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env5.sh}
R=$X/results/${RES:-r3b/u4}; mkdir -p $R
B=$X/e1-overhead/bench_dt_insitu.py
echo "node $(hostname -s) $(date -u +%FT%TZ)"
PARTS=${PARTS:-p1 solo}
has() { case " $PARTS " in *" $1 "*) return 0;; esac; return 1; }
summ() { grep -h 'req/s' $1 | sed 's/.*(\(.*\) req\/s)/\1/' | tr '\n' ' '; }
POOLS=${POOLS:-"1 2 4 8 16 32 64 128 256"}
CONCS=${CONCS:-"50 500"}
has p1 && for k in ${KS:-1 2 3 4 5}; do
  for w in $POOLS; do
    for c in $CONCS; do
      f=$R/insitu-pm-pool$w-c$c-r$k-$D
      t0=$(date +%s)
      python $B --workers $w --concurrent $c --tasks 1000 --out $f.json > $f.log 2>&1
      echo "pool $w c $c r$k rc=$? $(( $(date +%s) - t0 ))s"
    done
  done
done
ORDERS=("bare investigator agent" "investigator agent bare" "agent bare investigator" \
        "bare agent investigator" "investigator bare agent")
has solo && for k in 1 2 3 4 5; do
  for w in 1 8 64; do
    for row in ${ORDERS[$((k-1))]}; do
      f=$R/insitu-pm-pool$w-c500-solo-$row-r$k-$D
      python $B --workers $w --tasks 1000 --concurrent 500 --bursts 5 \
          --rows $row --out $f.json > $f.log 2>&1
      echo "solo pool $w $row r$k rc=$? $(date -u +%T) $(summ $f.log)"
    done
  done
done
echo "--- end $(date -u +%FT%TZ)"
