#!/bin/bash
# Round 3b U4c (diagnostic, decided in the session): U4b's slow bursts sit at
# fixed positions in the process, the same in every repeat.  Same runs as
# U4b's default order (pool 8, c=500, --tasks 1000, 5 bursts per row), with
# the client's cyclic GC on (control) and off (r3b/nogc.py), 3 repeats each.
#SBATCH -J r3b-u4c
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:10:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3b-u4c-%j.out
#   sbatch -A m5290 -q debug r3b/run_u4c.sh
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env5.sh}
R=$X/results/${RES:-r3b/u4/gc}; mkdir -p $R
B=$X/e1-overhead/bench_dt_insitu.py
echo "node $(hostname -s) $(date -u +%FT%TZ)"
summ() { grep -h 'req/s' $1 | sed 's/.*(\(.*\) req\/s)/\1/' | tr '\n' ' '; }
for k in 1 2 3; do
  for gc in on off; do
    f=$R/insitu-pm-pool8-c500-gc$gc-r$k-$D
    pre=(); [ $gc = off ] && pre=($X/r3b/nogc.py)
    python "${pre[@]}" $B --workers 8 --concurrent 500 --tasks 1000 --bursts 5 \
        --out $f.json > $f.log 2>&1
    echo "gc $gc r$k rc=$? $(summ $f.log)"
  done
done
echo "--- end $(date -u +%FT%TZ)"
