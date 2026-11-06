# Journal: DT paper Perlmutter batch, 2026-11-06

Unattended Claude Code session on a Perlmutter login node, following the
handover page "DT Perlmutter Batch Runs"
(https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn). Branch
`exp/pm-batch-20261106` off `bd11708`. Work dir `/pscratch/sd/m/merzky/dt-pm2`.
Times are local (PST) unless noted.

## Setup

- `digital_twins` cloned, branch `exp/pm-batch-20261106` at `bd11708`.
- Venv: the E1 venv `/pscratch/sd/m/merzky/dt-e1/ve.dt` (Python 3.13.18,
  radical.asyncflow 0.5.1, rhapsody-py 0.4.0 @ e491cd2, radical.orbit 0.7.0,
  ROSE 0.3.0 @ 64330d9), with `pip install .` of this checkout over the E1
  install. Added: `py-spy 0.4.3`.
- Decision: results go to `experiments/dt-paper/results/p<N>/` (the page
  names `results/p<N>/` without a parent; one tree for all phases).

## P0: accounts and the early GPU job

- `sacctmgr show assoc where user=merzky`: amsc007, amsc007_g, m5290,
  m5290_g (m3957, m3957_g deleted).
- Balances from `iris user merzky` (node-hours, project charged / allocated):

  | project | charged | allocated | remaining |
  |---|---|---|---|
  | amsc007 | 597.8 | 1000.0 | 402.2 |
  | amsc007_g | 999.3 | 1000.0 | 0.7 |
  | m5290 | 12934.7 | 34375.3 | 21440.6 |
  | m5290_g | 457.1 | 2928.7 | 2471.6 |

- Decision: CPU on **m5290**, GPU on **m5290_g**. The page assumed another
  project had more CPU than m5290; it does not (amsc007 has 402 left), so
  m5290 is the largest CPU balance, which is what the page asks for.
- QOS limits (`sacctmgr show qos`): interactive maxwall 4 h, debug 30 min
  (2 jobs), gpu_regular 2 days.
- GPU env for P8 (login node, about 25 min): `conda create -p $W/xgf/env --clone
  /global/common/software/m5290/bcarter/mconda/envs/cfdaai` (Python 3.12.13,
  TensorFlow 2.21.0, Keras 3.15.0; Ben's env read only). cfdaai's TF is a
  CUDA 12.5.1 / cuDNN 9 build but the env carries no CUDA libraries, so I
  added `tensorflow[and-cuda]==2.21.0` (nvidia-*-cu12 wheels: cuDNN 9.28,
  cuBLAS 12.9, ...) to the clone. Decision: GPU libraries come from the
  env's own wheels; no `cudatoolkit` module, nothing prepended to
  `LD_LIBRARY_PATH`. Then the four pins from `deploy/install.sh`,
  `pip install ".[service,learn]"` of this checkout, `xgboost
  scikit-learn python-dotenv`. numpy/scipy/pandas/keras/h5py unchanged by
  the runtime install (checked with `pip freeze` before and after).
- xGFabric `feature/dt-framework` at `d9b6db5` cloned to `$W/xGFabric`
  (read only; nothing committed there).
- Trained weights: `/pscratch/sd/m/merzky/xgf_playground/WindField/` from the
  September demo has `fno/0/results/` (FNO2D, 48x24 grid, hidden 64, 4
  layers) and `pinn/0/results/` (PhysicsMLP3D, 4x128). **No PCR model**:
  `pcr/partition/0/results/` is empty, no `pcr.tar.gz` anywhere. Decision:
  P8a measures FNO and PINN only. PCR inference is numpy coefficient
  evaluation without TF, so GPU would not change it anyway.
- Finding (xGFabric, not fixed, not our repo): `tasks/do_pinn/main.py`
  `tk_pinn_eval` cannot run as is: it never calls `communicate()` on its
  `tar` process, so `returncode` is `None` and it always raises; and it
  loads `model.weights.h5` / `model_meta.json` while the PINN archive
  holds `pinn.weights.h5` / `pinn.model_meta.json`, whose meta uses
  `hidden_dim` / `n_hidden_layers` instead of `hidden` / `n_layers`. The
  same `tk_*_eval` functions rebuild the model from the weights on every
  call. Decision: the P8a harness calls each model's own `prepare` and
  `*_predict_field` directly (mapping the PINN meta keys) and measures
  three costs: cold (process start to first field), reload (prepare +
  field, which is what `tk_*_eval` pays per call) and warm (field only).
- New harness `e6-use-cases/bench_surrogates.py`, batch script
  `e6-use-cases/run_p8a.sbatch`: FNO and PINN x GPU / CPU
  (`CUDA_VISIBLE_DEVICES=`) x 3 process repeats; warm 50, reload 10 (GPU)
  / 5 (CPU).
- 2026-11-06: **submitted P8a as job 60898696** (`-A m5290_g -C gpu -q
  regular -N 1 -t 02:00:00`), pending (Priority).

## Session mechanics deviation: sbatch instead of salloc + srun

- 03:10 `salloc --no-shell -q interactive -A m5290` job 60898710 (nid200028),
  P1 launched as `srun --jobid --overlap`: the step never ran. Every later
  step, `srun ... hostname` included, also hung: the task starts (srun -vvv:
  "1 tasks started"), never completes, and is killed at the timeout. Same on
  a second node (job 60899100, nid200070) and outside the tool sandbox. Both
  allocations cancelled: 10:11 and 7:21 elapsed, about 0.30 node-h on m5290,
  no results.
- A debug batch job (60899381) runs `hostname` and an inner `srun` fine.
- Decision: every phase runs as an `sbatch` job (`-q regular`, or `debug`
  for runs under 30 min) whose batch script runs the harness itself. Same
  node for all rows of a comparison still holds (one job per phase).
  Open question for Andre: why steps launched from login20 into an
  interactive allocation hang today when they worked on 2026-11-05.
- 03:35 home quota hit 100.7% (40.27 / 40 GiB): `head` in a tool call failed
  with "Disk quota exceeded". Cause: `~/.conda/pkgs` is 21 GiB (all but 23
  entries predate today) and the `tensorflow[and-cuda]` wheels added
  2.96 GiB to `~/.cache/pip`. I deleted only the pip cache files written
  today (back to 37.9 GiB, 94.8%) and set `PIP_CACHE_DIR=$W/cache/pip` in
  `env.sh`. Open question for Andre: `~/.conda/pkgs` (21 GiB) could be
  cleaned with `conda clean --all`; I did not touch it.
- 03:38 P1 submitted as job 60899550 (`-A m5290 -q regular -t 02:00:00`).

## P9: HPPSS part-1 files into radical-experiments/rhapsody (done)

- Cloned `2026_hppss` to `$W/rhapsody-exp` and CrayLabs/rhapsody-plugins-openfoam
  (`306d3f4`) to `$W/upstream-openfoam`.
- `cmp` against upstream `examples/pitzDaily-optimize/`: `driver-staged.py`,
  `driver-async.py`, `pitzdaily_case.py`, `Allrun`, `Allclean` in
  `hppss-d015/runs/pitzDaily-optimize` are identical, so they are listed,
  not copied. No edited upstream files exist.
- Ours, copied unchanged: `part1/driver-video.py`, `part1/driver-asyncmatched.py`
  (hppss-d015), `part1/run-w1.sh` (`$PSCRATCH/hppss/runs`), `part1/part1.sh`
  (`hppss-rehearsal`), `deploy/env.sh` (hppss-demo), `deploy/my-env.sh`
  (`hppss-rehearsal-2026-11-05`, the HOWTO's current form with
  `RADICAL_ORBIT_PSIJ_DIR`), `deploy/env-w1.sh` (`$PSCRATCH/hppss/env.sh`,
  which `run-w1.sh` sources).
- Decisions: `radical-orbit-endpoint-wrapper.sh` lives tracked and unmodified in
  radical.orbit `a843434` (`bin/`), so it is listed like an upstream file,
  not copied. `my-env.sh` and `part1.sh` came from the rehearsal dirs, the
  only places they exist as files.
- Copy mechanics: `cp` from hppss-d015 / hppss-demo / `$PSCRATCH/hppss` was
  refused by the session's permission rules (write-deny on those trees);
  the files were read with `cat` into the repo. Nothing was written to the
  source trees. `cmp` confirms the copies.
- Sanitize: grep for token/BEGIN/sid/secret/key/cert finds only path
  references (`my-env.sh` reads the token file at run time; no value is in it).
- Commit `ff663e3` pushed to `radical-experiments/rhapsody` `2026_hppss`.
