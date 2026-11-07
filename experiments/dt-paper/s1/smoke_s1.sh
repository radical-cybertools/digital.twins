#!/bin/bash
#SBATCH -J s1-smoke
#SBATCH -C cpu
#SBATCH -N 1
#SBATCH -t 00:20:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/s1-smoke-%j.out
# Round 2: tiny runs of every local S1 harness on the paper stack.
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm3/env.sh
S=$W/logs/smoke; mkdir -p $S
python -V
t() { local n=$1; shift; timeout 300 "$@" > $S/$n.log 2>&1; echo "$n rc=$? $(grep -v -E '^\s*$|stop criterion|window' $S/$n.log | tail -1 | cut -c1-150)"; }
t insitu python $X/e1-overhead/bench_dt_insitu.py --workers 8 --tasks 100 --concurrent 50
t learner python $X/e1-overhead/streaming_learner_perf.py --modes engine --feeds inproc,zmq --workers 4 --out $S/learner.json
t exsitu python $X/e1-overhead/bench_dt_exsitu.py --workers 8 --samples 40 --windows 3 --batch-sizes 1,10
t twins python $X/e2-scaling/bench_twins.py --twins 1,4 --seconds 2 --workers 16
t join python $X/e2-scaling/bench_streams_join.py --streams 1,4 --rates 10,100 --seconds 1
t update python $X/e4-hot-swap/bench_model_update.py --workers 8 --intervals 0.1 --seconds 2
