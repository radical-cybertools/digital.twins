#!/bin/bash
# Round 3 T2: why the ex-situ learner falls behind at large windows.
#SBATCH -J r3-t2
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/r3-t2-%j.out
#   sbatch -A m5290 -q debug r3/run_t2.sh
# As s1/run_s1_p3.sh (pool 8, 400 samples, 20 paced windows, 5 repeats),
# with the round 3 rows: bare, zmq (the same ZMQ hop, no twin), dt,
# dt-batched (one channel message per window).  Then py-spy on the dt and
# zmq rows at window 100: on-CPU and --idle, folded and speedscope.
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm3/env3.sh}
R=$X/results/${RES:-r3/t2}; mkdir -p $R
E=$X/e1-overhead/bench_dt_exsitu.py
echo "node $(hostname -s) $(date -u +%FT%TZ)"
for k in 1 2 3 4 5; do
  f=$R/exsitu-pm-pool8-r$k-$D
  python $E --workers 8 --samples 400 --windows 20 \
      --rows bare,zmq,dt,dt-batched --out $f.json > $f.log 2>&1
  echo "r$k rc=$? $(grep -c 'msg/s' $f.log) rows $(date -u +%T)"
done
for row in dt zmq; do
  for idle in "" --idle; do
    for fmt in raw speedscope; do
      ext=$fmt; [ $fmt = raw ] && ext=folded
      f=$R/pyspy-$row-w100${idle:+-idle}-$D
      py-spy record $idle -r 200 -f $fmt -o $f.$ext -- \
          python $E --workers 8 --samples 2000 --windows 20 \
          --batch-sizes 100 --rows $row >> $f.log 2>&1
      echo "py-spy $row ${idle:-oncpu} $fmt rc=$?"
    done
  done
done
echo "--- end $(date -u +%FT%TZ)"
