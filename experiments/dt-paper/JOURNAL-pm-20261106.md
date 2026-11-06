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
