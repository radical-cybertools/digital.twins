# E6 Use cases

Show extensibility qualitatively.  (Outline, 2026-10-02.)

- xGFabric WindField: three investigators (PCR, PINN, FNO) and
  resource-aware model selection.
- M3D-C1 DT on Perlmutter (dt-complete).
- Heat-flux surrogate on NSTX-U geometry.
- Needs a GPU surrogate run; on CPU the xGFabric surrogates took 54 s per
  inference.

Not started.

## Perlmutter batch 2026-11-06 (P8a): WindField surrogate inference cost

`bench_surrogates.py` / `run_p8a.sbatch`, one A100 node (gpu_debug, account
m5290_g).  Models: FNO2D and PINN as trained by the September demo
(`/pscratch/sd/m/merzky/xgf_playground/WindField/`); PCR has no trained
model and is numpy-only, so it is not measured.  One field evaluation =
what `tk_<model>_eval` computes: the 85 x 38 speed field at z = 1, 3, 5 m.
Environment: a clone of Ben's `cfdaai` (TF 2.21.0, Python 3.12.13) plus
`tensorflow[and-cuda]` wheels; TF finds the GPU only with the env's own
`site-packages/nvidia/*/lib` on `LD_LIBRARY_PATH` (the job probes for it).
CPU = same node, `CUDA_VISIBLE_DEVICES=`, 128 cores.  3 process repeats
each; warm = median of 50 field evaluations, reload = prepare + field
(median of 10 GPU / 5 CPU).

| per call | FNO GPU | FNO CPU | PINN GPU | PINN CPU |
|---|---|---|---|---|
| warm field | 96.8 ms (96.4-97.9) | 122.0 ms (121.9-122.9) | 13.1 ms (13.0-13.2) | 23.4 ms (23.1-23.5) |
| reload + field (what `tk_*_eval` pays) | 446 ms (445-453) | 491 ms (487-494) | 77.7 ms (77.7-78.3) | 87.4 ms (86.8-88.2) |
| cold: process start to first field | 8.0 s (7.5-9.6) | 6.2 s (5.7-6.3) | 5.9 s (5.8-5.9) | 4.5 s (4.4-4.5) |

- **The surrogates are cheap, on CPU too.** Nothing here comes near the
  "54 s per inference on CPU" from the September demo; with these
  weights a full field costs 0.1 s (FNO) and 0.02 s (PINN) warm, under
  0.5 s even when rebuilt per call.  Where the 54 s came from is open
  (candidates: the tar extraction and staging in `tk_*_eval`, the dragon
  task path, or per-task CPU binding on the endpoint).
- **The GPU helps little:** 1.26x (FNO) and 1.8x (PINN) on a warm field,
  1.1x on a reload; the fields are small (48 x 24 FNO grid, 3230 PINN
  points), so kernel launch and the numpy interpolation around the model
  dominate.  The GPU cold start is slower (CUDA initialisation adds
  1.3-3.7 s to `prepare`).
- **What does matter is the reload:** `tk_*_eval` rebuilds the model from
  its weights on every call, 4.6x (FNO) and 6x (PINN) the warm cost.
  Keeping the loaded model in the investigator's process would gain more
  than moving to a GPU.
- Cold start is dominated by the TensorFlow import (4.2-5.2 s).

P8b (the twin end to end with real surrogates) was not run in round 1:
`tk_pinn_eval` in xGFabric could not run as is (see the journal) and there
was no PCR model.  It ran later: round 2b B3 (`run_b3.sbatch`, xGFabric PR
#17 `fix/pinn-eval`) end to end on the concurrent backend, and round 8
R8-E (`r8/run_r8e.sbatch`) on `dragon_native`, decomposed per answer.

## Round 8 R8-E (2026-11-13): WindField decomposed, on dragon_native

One A100 node, both engines on `dragon_native` (endpoint inside a Dragon
runtime), 3 runs of 1,200 s per variant.  Medians per answer
(`results/r8/r8-e/`, journal `JOURNAL-pm-20261114.md`):

| model | variant | total | framework in / out | tar extract | model reload | field |
|---|---|---|---|---|---|---|
| PINN | reload per call (xGFabric as is) | 155 ms | 16 / 4 ms | 31 ms | 82 ms | 17 ms |
| PINN | warm model per worker (local patch) | 43 ms | 17 / 4 ms | 0 | 0 | 18 ms |
| FNO | reload per call | 818 ms | 15 / 6 ms | 116 ms | 563 ms | 115 ms |
| FNO | warm model per worker | 179 ms | 16 / 6 ms | 0 | 0 | 115 ms |

The reload, not the framework, is the cost; a warm model cuts the answer
3.6x (PINN) and 4.6x (FNO).  The tail (15-24 s) is a pool worker's first
call: TensorFlow import plus CUDA initialization.  Models: FNO 8.9 MB,
PINN 0.25 MB, PCR 0.8-1.7 MB.  Training: FNO about 250 s, PINN about 330 s,
PCR partition about 275 s.
