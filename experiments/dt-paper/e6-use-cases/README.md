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

P8b (the twin end to end with real surrogates) was not run:
`tk_pinn_eval` in xGFabric cannot run as is (see the journal) and there is
no PCR model.

## P8b: the WindField twin end to end with real surrogates

`run_p8b.sbatch` on one A100 node (gpu_debug): ORBIT broker (`--plugins
dt`), one endpoint for inference and learning, the fake Davis sensor at
1 s, and `p8b_client.py`, which builds `twin_service_real.py`'s graph and
probes the agent every 3 s.  The twin trains its own surrogates from
16-reading batches (simulations from 72 precalculated CSVs), profiles each
published model, predicts its runtime with the Pi predictor and selects the
cheapest.  Run 6 (job 60917837), 18 min:

| surrogate | selected from | probes answered | p50 latency |
|---|---|---|---|
| (none yet) | 0 s | 99 | 24 ms |
| FNO | 297 s | 19 | 731 ms |
| PCR | 372 s | 1 | 19.4 s |
| PINN | 392 s (to the end) | 228 | 194 ms |

The selector settles on PINN, which is also the cheapest by measurement
(PINN 194 ms < FNO 731 ms < PCR 19 s per field through the twin).  0 errors
in 347 probes; all three models retrained 3-4 times; the Pi predictor
retrained 3 times (MAE 0.47-0.53).

Getting there took six runs and fixes on three layers (journal for all):

- xGFabric (PR radical-collaboration/xGFabric#17): `tk_pinn_eval` could not
  run; overlapping evals deleted each other's model; the PCR partition
  returned 10 MB, over ORBIT's 2 MiB return limit; the in-process profiler
  omitted `sys_write_bytes` (the last one, 3adefa8, is local only so far).
- rhapsody: the ORBIT backend never delivered an executable task's stdout
  (ORBIT's notifications leave it out, asyncflow needs it), so the Pi
  predictor's executable tasks never completed.  Fixed on branch
  `fix/orbit-exec-stdout`; P8b ran on e491cd2 + that fix, installed into the
  P8b env only.
- this harness: the endpoint runs tasks in a spawn process pool
  (`p8b_endpoint.py`); with rhapsody's default thread pool, concurrent Keras
  trainings crash in one process.
