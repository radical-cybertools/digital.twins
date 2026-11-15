#!/bin/bash
# Round 8b, B1: the broker's ceiling, closed loop (R8-2's noop-one row).
#SBATCH -J r8b-b1
#SBATCH -C cpu
#SBATCH -N 3
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8b-b1-%j.out
# Knobs (round 8c): CELL_ENV (env script), CELL_RES (results dir under results/).
#   CELLS="..." sbatch -A m5290 -q debug r8b/run_b1.sh
# Runs r8/run_engine.sh once per cell in this allocation, same three nodes
# (broker node 0, Dragon endpoint node 1, client node 2), fresh broker and
# endpoint per repeat.  A cell is "label venv compression twins": venv ve8
# (round 8, 'Online run' at INFO) or ve8b (#63, at debug); compression
# on / off for every runtime and the broker (r8b/env-r8b.sh).
set -uo pipefail
E=/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper
for cell in ${CELLS:?}; do
  IFS=: read -r lab ve comp tw <<< "$cell"
  echo "=== cell $lab: venv $ve compression $comp twins $tw  $(date -u +%T)"
  VE=/pscratch/sd/m/merzky/dt-pm8/$ve RADICAL_ORBIT_WS_COMPRESSION=$comp \
  ENV_SH=${CELL_ENV:-$E/r8b/env-r8b.sh} RES=${CELL_RES:-r8b/b1} REPEATS="${lab}1 ${lab}2" ROWS="noop-one 0 0 $tw" \
  SECONDS_=15 WS_CHECK=1 PORT=$((8300 + RANDOM % 300)) \
    bash $E/r8/run_engine.sh
done
echo "--- end $(date -u +%FT%TZ)"
