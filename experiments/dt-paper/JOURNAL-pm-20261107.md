# Journal: DT paper Perlmutter round 2, the paper stack (2026-11-06/07)

Unattended Claude Code session following the handover page's "Round 2"
section (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn). Branch
`exp/pm-stack-20261107` off `d885899` (digital.twins `paper/dtaas`). Work dir
`/pscratch/sd/m/merzky/dt-pm3`. Round 1: `JOURNAL-pm-20261106.md`. Times PST.

## Node-hour ledger (round 2 budget: 100, CPU + GPU)

Updated after every job (sacct elapsed x nodes).

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|

## S0: build the stack (done)

- `git clone -b paper/dtaas`, branch `exp/pm-stack-20261107` at `d885899`
  ("paper stack: pin install.sh to the paper/dtaas commits, add STACK.md").
- Python: `module load cray-python/3.12.12`, Python **3.12.12** (radical.3 has
  3.12.3; the DT service compares minor versions only).
- `DT_PYTHON=python3.12 DT_REF=d885899 ./deploy/install.sh endpoint $W/ve`:
  rc 0, first try (log `$W/logs/install.log`). Installed, matching STACK.md:

  | package | version | commit |
  |---|---|---|
  | radical.asyncflow | 0.6.0 | 41e49145 |
  | rhapsody-py | 0.6.0 | 36969986 |
  | radical.orbit | 0.8.0 | b10479c3 |
  | rose-surrogate-explorer | 0.3.0 | 9cc47a59 |
  | digitaltwin | 0.0.1 | d8858993 |

  Added: `py-spy 0.4.3`. `PIP_CACHE_DIR=$W/cache/pip` (not home).
- Note: the stack's rhapsody (3696998) does not contain round 1's
  rhapsody#125 (executable stdout over ORBIT). None of the S1 harnesses use
  executable tasks.
- The round-1 harnesses are in this checkout (merge of exp/pm-batch-20261106,
  learner harnesses ported to ROSE's Stream API in b416ea8).
- Decision: S1 runs round 1's batch scripts unchanged except for paths and
  names, generated into `experiments/dt-paper/s1/run_s1_<phase>.sh`
  (dt-pm2 -> dt-pm3, `results/pN` -> `results/s1/pN`, job names `s1-*`, logs
  `$W/logs/s1-*`); `env.sh` sets `D=stack-20261107`, so files are named
  `...-stack-20261107.json` as the page asks. Same harnesses, sizes and
  repeats as round 1. Jobs run via sbatch, as in round 1 (salloc + srun steps
  from the login node hung there).
- orbit 0.8 keeps the CLI flags the scripts use (`--plugins`, `--host`,
  `--port`; endpoint `-n -u -p --tunnel none`).
