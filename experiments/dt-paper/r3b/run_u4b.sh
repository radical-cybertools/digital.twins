#!/bin/bash
# Round 3b U4b (diagnostic, decided in the session): U4's in-process P1
# runs at c=500 lose about 27% on the third row (agent), while the solo
# rows are within 10% of bare and round 2 lost on the second row instead.
# Position or row?  Pool 8, c=500, --tasks 1000, all three rows in one
# process in three orders, 5 repeats, 5 bursts per row.
#SBATCH -J r3b-u4b
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:15:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3b-u4b-%j.out
#   sbatch -A m5290 -q debug r3b/run_u4b.sh
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env5.sh}
R=$X/results/${RES:-r3b/u4/order}; mkdir -p $R
B=$X/e1-overhead/bench_dt_insitu.py
echo "node $(hostname -s) $(date -u +%FT%TZ)"
summ() { grep -h 'req/s' $1 | sed 's/.*(\(.*\) req\/s)/\1/' | tr '\n' ' '; }
for k in 1 2 3 4 5; do
  for order in bare,investigator,agent agent,investigator,bare investigator,agent,bare; do
    f=$R/insitu-pm-pool8-c500-order-${order//,/_}-r$k-$D
    python $B --workers 8 --concurrent 500 --tasks 1000 --bursts 5 --rows $order \
        --out $f.json > $f.log 2>&1
    echo "order $order r$k rc=$? $(summ $f.log)"
  done
done
echo "--- end $(date -u +%FT%TZ)"
