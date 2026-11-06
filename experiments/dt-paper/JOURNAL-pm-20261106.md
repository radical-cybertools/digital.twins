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

## P2: learner engine slowdown (done)

- Harness change (commit 5680c09): `streaming_learner_perf.py` gets
  `--workers`, `--modes`, `--feeds`, `--out`, provenance; defaults unchanged.
- Job 60899665 (nid004706, regular, m5290): engine mode, both feeds, all
  batch sizes, pool 4/8/32/128/256/default x 3 repeats, then py-spy
  (speedscope + folded) on engine/inproc at pool default and 8.
- Result: **pool size is not the cause.** All pools give 42-45 msg/s at
  batch 1 and 4.1-4.7k msg/s at batch 100; pool 256 / default are, if
  anything, 3-8% faster. A window costs about 23 ms = 2 tasks x 11.6 ms,
  the same per-task cost as the E1 in-situ p50.
- py-spy: only 553 active samples over the pool-8 run (about 20 s at
  200 Hz): the main process is idle, waiting, most of the time.
- Cause found in radical.asyncflow 0.5.1 `workflow_manager.py`: the
  run loop's `else: await asyncio.sleep(0.01)` after any iteration that
  submitted or completed something.
- Decision: confirm causality without touching the pins. New
  `e1-overhead/diag_asyncflow_poll.py` swaps the `asyncio` name inside
  `radical.asyncflow.workflow_manager` for a proxy whose `sleep(0.01)` sleeps
  `--poll` instead, then runs a harness unchanged. Job 60900302 (debug):
  learner engine pool 8 and `bench_dt_insitu.py` pool 8 c=50 at poll 0.01
  (control, same wrapper), 0.001, 0, 2 repeats. Learner engine/inproc
  b=100: 4,346 / 30,422 / 68,099 msg/s; in-situ bare p50 11.32 / 1.61 /
  0.62 ms. At 0.001 the learner matches the laptop (30,417). DT rows stay
  within 0.3 ms of bare at every setting.
- Open question for Andre: report the 10 ms run-loop sleep to
  radical.asyncflow (I did not comment on GitHub). Why the laptop does not
  show it is unexplained; the laptop's asyncflow / ROSE versions for the
  2026-11-02 run should be checked.

## P3: E1 ex-situ (done)

- New harness `e1-overhead/bench_dt_exsitu.py` (commit 77fb67b). Two smoke
  runs (debug jobs 60899842, 60900031, 60900108) before the real one:
  1. the dt row first published samples on the twin's internal dtype
     topic, which nothing subscribes to: no sample reached the learner.
     Fixed by feeding through the input edge (`add_input` + an external
     `ChannelPublisher`), which is also the realistic sensor path.
  2. the publish latency under the saturating throughput feed was mostly
     backlog (it grows with the window index: 715 ms p50 at batch 1).
     Decision: keep it as `publish_latency_saturated` but report a paced
     run (feed one window, wait for its publish, 20 windows) as
     `publish_latency`.
- Decision: pool 8 for both rows (P2 found no pool effect; the page says
  8 in that case). `conflate=False`, `max_wait=None` in both rows so no
  sample is dropped and windows form by size only; the harness asserts
  equal sample counts (400 per throughput run, 20 x batch per paced run).
- Job 60900315 (debug, m5290), 5 repeats: dt/bare throughput 0.995-1.052,
  paced publish p50 bare 35.1-35.3 ms, dt 32.4-33.9 ms. Both on the
  asyncflow floor (3 tasks per window x about 11.7 ms). The dt row is
  slightly faster; not explained, most likely phase relative to the 10 ms
  poll. Reported as measured.
- Note: P1 jobs record `digital_twins_commit` per run; it moves as I commit
  harness files, but `bench_dt_insitu.py` itself is unchanged since bd11708.
- Note: P4 job 60899935 was submitted before the per-job TLS directory
  change to `run_p4.sh` (commit after eff5dc6); sbatch keeps the submitted
  copy, so that job uses `$W/tls/` directly. No other job uses that path.

## P4: first attempt failed

- Job 60899935 (2 nodes, nid004991-2) failed after 20 s: `hsn0` carries two
  IPv4 addresses (10.249.6.35 and 128.55.73.230), the script passed both to
  `--host`. Fix: take the first (`head -1`, the 10.249.x HSN address).
  The isolation check ran (`find ~/.radical/orbit -newer stamp` empty).
  Resubmitted as job 60900891 (with the per-job TLS directory).

## P5: E2 scaling (done, preliminary)

- New harnesses (commit 25167fe): `e2-scaling/bench_twins.py` (N
  `DTRuntime`s with one `Inv` each, shared ZMQ broker and engine, one
  closed-loop client per twin, 10 s per point) and
  `e2-scaling/bench_streams_join.py` (K `ChannelPublisher`s, `add_input`
  per stream, `add_data_join`, `UtilityTask` sink).
- Decisions: E2a pool fixed at 64 for all N (the offered concurrency is N,
  up to 64). E2b: the join is clear from the code (`_JoinComponent`, depth-1
  queues, lockstep), so no barrier fallback was needed; producers publish
  in rounds; the join's consumer is a `UtilityTask` sink, not an agent, so
  the number measures the join and the stream path rather than the
  agent's selection; "latency doubles" is against the p50 at 10 rounds/s.
- Job 60900350 (regular, nid007066), 3 repeats each. E2a: linear to 32
  twins (2,681 req/s, p50 11.07 ms), saturates at 64 (2,812 req/s, p50
  20.9 ms). E2b: max sustainable about 8k inputs/s total for K = 4-16,
  5k at K=1, 6.4k at K=32; no tuple dropped or misaligned at any rate.

## P7: E4 model-update propagation (done, preliminary)

- New harness `e4-hot-swap/bench_model_update.py`. Decision: the model
  publisher is the investigator's own main loop (no learner), so only the
  publish -> inference half is timed; the learner half is P3.
- Local: job 60900442 (regular, pool 8, 3 repeats): answered p50 16.2-16.7
  ms at 1 s / 100 ms / 10 ms intervals; at 10 ms 93.6 % of versions seen.
- ORBIT: `run_p7_orbit.sh` (P4 layout, broker `--plugins dt`, per-job TLS,
  own stamp), job 60901098 (2 nodes, nid007062/007071): cross-node 21.9-22.4
  ms, loopback 21.1-22.2 ms, inference 14.5-15.0 ms; at 10 ms 66-68 % seen.
  Isolation check empty.

## P6: E5 endpoint and client loss (done, preliminary)

- New harness `e5-persistence/bench_endpoint_loss.py`, batch script
  `run_p6.sh`. Decisions: the twins are the integration tests' R8 pair;
  loss is "twin `failed` with `last_error`" (that is what the service
  reports); since a lost engine poisons its session (R8 test), recovery =
  endpoint restart + new session + new learner twin until it serves a
  learned model; probes every 0.5 s on both twins during the loss window.
- Smoke 1 (job 60900385): every twin failed to initialize, "Broker URL
  required": the broker's `dt` plugin needs `RADICAL_ORBIT_BROKER_URL` in
  its own environment (the integration conftest sets it too). Fixed in
  `run_p6.sh`. Smoke 2 (job 60901042, 1 kill + 1 reattach) passed.
- Full run job 60901152 (regular, nid006920): 10/10 kills, 10/10
  reattaches. Detect 10.09 s (10.05-10.16), all 200 probes per twin
  answered during the window, endpoint up 1.25 s, learning resumed 2.82 s
  (2.81-3.07), reattach 18 ms, first answer 26 ms. Isolation check empty.

## P1: E1 pool-size sweep (done)

- Job 60899550 (regular, nid004587, 57 min): 9 pools x c 50/500 x 5
  repeats = 90 runs, all rc=0, about 38 s each; nothing dropped (no run
  over a minute).
- DT/bare throughput 0.86-1.04 (median about 0.95), p50 delta <= 0.35 ms;
  pool 256 p50 bimodal (10.5 / 12.0 ms). Burst throughput peaks at pool 4
  and falls monotonically with pool size in all rows: that, not the DT,
  is why pool 64 is slower than pool 8. Cause of the decline not profiled.
- Consistent with E1 run A, so no rerun.
