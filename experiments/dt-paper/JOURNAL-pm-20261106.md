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

## P4: E1 through ORBIT (done)

- Job 60900891 (regular, 2 nodes nid006479/006481, about 33 min): broker on
  node 0's hsn0 address 10.249.17.199:8131 with `--plugins dt` only (no
  extra plugin needed), per-job TLS in `$W/tls/p4-60900891`, endpoints
  `dt_p4_ep1` (node 1) then `dt_p4_ep0` (node 0), notify window 0. All
  runs rc=0. Isolation check empty.
- Cross-node p50 +0.3 ms over loopback; ORBIT +3 ms over the local pool.
  DT p50 equal to bare within 0.4 ms.
- Agent burst gap reproduces E1 run C (0.65-0.81 x bare). Diagnosis: one
  ORBIT task per request in every row (diag counts), DT code about 1 % of
  py-spy samples. Solo-process runs give 0.88-0.90 x: part of the gap is
  row order. The remainder is unexplained (open question: profile the
  client loop under a burst with the agent row alone). Per the contract
  the result is reported both ways (in-process and solo), not explained
  away.

## Incident: DT session IDs in committed logs (redacted)

- The broker / endpoint console logs committed with P4 (1b8523e), P6
  (420f80b) and P7 (368ce76) contain `session.<8 hex>` IDs. Those in
  `results/p6/broker-p6.console.log` are DT plugin sessions (bearer
  credentials per the page); the endpoint logs carry rhapsody / sysinfo
  plugin sessions. I ran the secret grep after pushing instead of before.
- Exposure: none in practice. Every session belonged to a throwaway broker
  on a compute node (127.0.0.1 or the node-internal hsn0 address), all
  brokers are shut down, and their tokens and keys were never committed
  (checked: no token value from `$W/tls/**` appears in any results file).
- Fix: all six files redacted in place (`session.<redacted>`) in the next
  commit. The IDs remain in the history of `exp/pm-batch-20261106`;
  removing them needs a force-push, which this session may not do.
  Open question for Andre: rewrite that branch's history, or leave it
  (the sessions are dead).
- From here on the secret grep runs before every commit of logs.

## P8: decisions while the GPU job queues

- P8a job 60898696 still pending (Priority) in gpu_regular since P0.
- Decision: `bench_surrogates.py` gets `--budget` (default 240 s per warm /
  reload loop, the count actually run is recorded), so the CPU comparison
  cannot overrun the 2 h job if a CPU field evaluation takes tens of
  seconds. The queued job reads the harness at start, so it picks this up.
- Decision: **P8b skipped.** The real WindField twin
  (`twin_service_real.py`) calls `tk_pinn_eval`, which cannot run (see P0),
  and there is no trained PCR model, so the selector would choose among a
  broken and a missing surrogate. Making it run means fixing xGFabric,
  which the page rules out (no commits there). Open question for Andre:
  fix `tk_pinn_eval` in xGFabric (communicate() on the tar process; file
  and meta-key names) and train / stage a PCR model, then run P8b.
- Update (Andre, 2026-11-06): session IDs are not secrets; a client
  still needs the broker certificate (and token) to use one. The entry
  above is therefore not an incident and the history needs no rewrite;
  the redaction commit cb82078 stays (harmless). Tokens, keys and certs
  remain off limits; those were never committed.
- 04:58 Decision (Andre: "go with option 2"): the 2 h gpu_regular job
  60898696 had waited 1 h 45 min with 338 of about 5,200 pending GPU jobs
  ahead. `run_p8a.sbatch` gets env knobs (DEVS, REPS, CPU_REPS, BUDGET,
  TAG); job 60901615 on gpu_debug (`-q debug -C gpu`, 30 min): GPU x 3
  repeats per model, CPU x 1 with a 60 s budget per loop, files tagged
  `-dbg`. 60898696 stays queued for the full CPU comparison.
- Debug job 60901615 (nid001221, 1:18) failed every run: (1) RecursionError
  in xGFabric's lazy `tasks/do_*/__init__.py` (`__getattr__` doing
  `from . import main`) when the harness did `from tasks.do_fno import
  inference`; fixed in the harness with `importlib.import_module`. (2) TF
  printed "Cannot dlopen some GPU libraries", GPUs: [] (the run was
  correctly flagged as a failed GPU run). Decision: `run_p8a.sbatch` now
  probes the GPU first with full TF logging and, if TF sees none, adds the
  env's own pip CUDA wheel directories (`site-packages/nvidia/*/lib`, not
  `/usr/lib64`) to `LD_LIBRARY_PATH` and probes again; it stops before the
  benchmark if both fail.
- Debug job 60901870 (nid003257, gpu_debug): plain probe no GPU, with the
  env's nvidia wheel libs NGPU 1; FNO / PINN on GPU x 3 and CPU x 1, all
  rc=0, no loop hit its budget. Job 60902010 (gpu_debug): CPU x 3 per
  model (consistent with the single CPU run). Cancelled the 2 h
  gpu_regular job 60898696 (never started).
- Result: warm field FNO 96.8 ms GPU / 122.0 ms CPU, PINN 13.1 / 23.4 ms;
  reload + field 446 / 491 ms and 77.7 / 87.4 ms; cold 8.0 / 6.2 s and
  5.9 / 4.5 s. The "54 s per inference on CPU" is not reproduced (open
  question where it came from). The GPU gains 1.1-1.8x; rebuilding the
  model per call costs 4.6-6x the warm field.
- P8: P8a done, P8b skipped (see above).

## Close-out

| phase | state | headline |
|---|---|---|
| P0 | done | CPU on m5290 (largest balance), GPU on m5290_g |
| P1 | done | DT 0.86-1.04 x bare throughput (median 0.95), p50 +<=0.35 ms; throughput peaks at pool 4 and falls with pool size |
| P2 | done | per-task floor is asyncflow 0.5.1's 10 ms run-loop sleep, not the pool size |
| P3 | done | ex-situ DT/bare 1.00-1.05, same publish latency |
| P4 | done | cross-node +0.3 ms over loopback, ORBIT +3 ms; one ORBIT task per request in every row; agent burst gap reproduces (0.65-0.81 x, 0.88-0.90 solo) |
| P5 | done, preliminary | twins linear to 32 (2.7k req/s), saturate at 64; join about 8k inputs/s |
| P6 | done, preliminary | loss reported after 10.1 s, inference uninterrupted, learning back 2.8 s after restart; reattach 18 ms |
| P7 | done, preliminary | publish -> served in about 1.5 inferences (16 ms local, 22 ms ORBIT) |
| P8 | P8a done, P8b skipped | FNO 97 / 122 ms, PINN 13 / 23 ms (GPU / CPU); reload per call 4.6-6x |
| P9 | done | ff663e3 on radical-experiments/rhapsody 2026_hppss |

**Node-hours** (sacct, all jobs of this session incl. smoke, failed and
cancelled ones): m5290 3.44, m5290_g 0.09, total **3.53 of 100**.
No allocation left running (`squeue -u merzky` empty).

**Fix branches:** none. No bug in `src/` blocked a phase; every fix was in
the harnesses on `exp/pm-batch-20261106`.

**ORBIT isolation:** every ORBIT job's `find ~/.radical/orbit -newer stamp`
was empty, and nothing there is newer than this session's `env.sh`.

**Tools added:** `py-spy 0.4.3` (E1 venv); the P8 env `$W/xgf/env` (clone of
cfdaai + `tensorflow[and-cuda]`, the four pins, `.[service,learn]`,
xgboost, scikit-learn, python-dotenv). `esprima` in
`$W/cache/jslib` (only to syntax-check the page's chart script).

**Open questions for Andre**

1. radical.asyncflow 0.5.1's 10 ms run-loop sleep (`workflow_manager.py`)
   sets an 11 ms floor on every task (P2). Report upstream? And why does the
   laptop not show it (check its asyncflow / ROSE versions)?
2. The agent's ORBIT burst gap (P4): about 10 % remains even in its own
   process, with one remote task per request and 1 % of client samples in
   DT code. Profile the client loop under a burst with the agent alone?
3. Why burst throughput falls with pool size above 4 (P1)? Not profiled.
4. Slurm steps from login20 into a `salloc --no-shell` allocation hung
   today (worked 2026-11-05). All phases ran via sbatch instead.
5. `~/.conda/pkgs` is 21 GiB of the 40 GiB home quota; `conda clean --all`?
6. xGFabric: `tk_pinn_eval` cannot run (no `communicate()` on its tar
   process; wrong file and meta-key names), no PCR model is staged, and
   `tk_*_eval` rebuilds the model per call (4.6-6x cost). Fix and train,
   then run P8b?
7. Where did September's "54 s per inference on CPU" come from? Not
   reproduced (0.5 s with a per-call rebuild).
8. P5-P7 are preliminary (one node, no-op work). Repeat at scale for the
   paper?

## P8b: the WindField twin with real surrogates (after Andre's "go")

- Andre (2026-11-06): fix P8b; push the xGFabric fix as a branch **with
  PR** (overrides the page's "no commits there" for this fix).
- xGFabric `fix/pinn-eval` (0ac3f59, off feature/dt-framework d9b6db5):
  `tk_pinn_eval` waits for its tar process, loads `pinn.weights.h5` /
  `pinn.model_meta.json`, reads `hidden_dim` / `n_hidden_layers` /
  `best_val_loss`. Verified in job 60902704's precheck: xGFabric's own
  `tk_pinn_eval` on the September `pinn.tar.gz` returns three 38 x 85
  fields (0.29 s); `tk_fno_eval` too. Pushed; PR
  radical-collaboration/xGFabric#17 into feature/dt-framework.
- Finding: the "no PCR model" blocker does not apply: the twin trains FNO,
  PINN and PCR itself from 16-reading sensor batches, with simulations
  taken from 72 precalculated CSVs (`/global/cfs/cdirs/m5290/precalc_sims`).
- Harness (`e6-use-cases/`): `p8b_check_eval.py` (precheck),
  `p8b_sensor.py` (xGFabric's fake Davis records, `--interval`, 1 s
  instead of 5 s), `p8b_client.py` (imports `twin_service_real.py`
  unchanged, builds its graph, probes `get_inference` every 3 s and
  records latency and the answering `arch`), `run_p8b.sbatch` (one GPU
  node: broker `--plugins dt`, endpoint concurrent + notify window 0 +
  the env's CUDA wheel libs + `TF_FORCE_GPU_ALLOW_GROWTH`, ORBIT data plane
  as in the demo, throwaway TLS, playground in `$W/xgf/`, isolation check;
  `demo/Sep_04_endpoint.sh` is not used because it points at
  `~/.radical/orbit`).
- Run 1, job 60902704 (gpu_debug, 9 min): twin `failed` at 456 s, before
  any model was published (152 probes, all `na`, 25 ms p50). FNO
  training (GPU, epoch 0 done) and PINN training started 4 s apart and
  crashed TensorFlow ("Input to reshape is a tensor with 1 values, but the
  requested shape has 20736"). Cause: the endpoint's rhapsody plugin builds
  `ConcurrentExecutionBackend()` without an executor, i.e. a
  `ThreadPoolExecutor`, so concurrent Keras trainings share one process;
  September ran on dragon, one process per task. PCR's data preparation
  finished (7 min 32 s). Isolation check empty.
- Decision: no dragon (page rule), no installed change: new
  `p8b_endpoint.py` runs `radical-orbit-endpoint.py` unchanged but gives
  the backend a spawn-based `ProcessPoolExecutor` (8 workers) when none is
  passed. Run 2 uses it.
- Run 2, job 60902985 (gpu_debug, 8.5 min): FNO and PINN trained on the GPU
  inside the twin (both archives written), the agent served its first
  real FNO inference at 363 s (846 ms), then the twin failed at 375 s:
  `FileNotFoundError .../WindField/fno/INFERENCE/interim`. Cause (xGFabric):
  every `tk_*_eval` call extracts into the same INFERENCE interim dir and
  `close_task(clean=True)` deletes it, so overlapping evals race (here:
  stream-driven inferences at the 1 s sensor cadence plus the 3 s probes;
  September's 5 s cadence made overlaps rare).
- Fix, local only so far: xGFabric commit 56490dc on fix/pinn-eval, a
  `tempfile.mkdtemp` interim dir per eval call in tk_fno/pinn/pcr_eval.
  Not pushed: it goes beyond the approved PINN fix; asking Andre whether
  it joins PR #17. The precheck now also runs 2 x 4 overlapping evals per
  model in separate processes. Run 3 uses both.
- Run 3, job 60903642 (gpu_debug, 10 min, xGFabric 56490dc): precheck
  passes incl. 2 x 8 overlapping evals per model in separate processes;
  no interim-dir error. 3 real FNO inferences from 417 s (8.0-9.2 s each:
  each lands on a fresh spawn worker that imports TF first). Twin failed at
  443 s in the PCR investigator: `tk_pcr_partition`'s ~10 MB return value
  exceeds the ORBIT rhapsody plugin's 2 MiB limit (endpoint log:
  "return_value too large: 9938047 wire bytes exceed the 2097152 byte
  limit -- stage the result to a file instead"), so `do_train` got None.
  The September playground shows the same: partition finished, no PCR model.
- Fix, local only: xGFabric 438d0d3, the partition writes `machine_<i>.pkl`
  to its OUTPUT_DIR and returns the paths; `tk_do_pcr` loads its file (a
  dict is still accepted). Run 4 uses it.
- Run 4, job 60904329 (gpu_debug, xGFabric 438d0d3): the twin ran the full
  20 min without failing. All three surrogates trained inside the twin on
  the GPU node: FNO x 4, PINN x 3, PCR x 3 (the first PCR models through
  ORBIT; 8 machines, machine 0 R^2 0.915). 274 probes answered `fno`, p50
  727 ms (674-9398, the long ones land on cold spawn workers). The job hit
  its 30 min limit during teardown (after the client finished), so the
  in-script isolation check did not run; checked by hand: `find
  ~/.radical/orbit -newer orbit-stamp-p8b` empty, queue empty.
- But the selector never chose: the agent's profiling loop stalls on its
  first model. `EndpointInvestigator` (the Pi runtime predictor) trains via
  an *executable* task (`python3 -m tasks.profiler.endpoint_trainer ...`).
  radical.orbit 0.7.0's rhapsody plugin sends completion notifications
  without stdout (`_NOTIFICATION_KEYS`, "clients needing stdout can fetch
  GET /task/{sid}/{uid}"); rhapsody's ORBIT backend (e491cd2) passes the
  notification on; asyncflow 0.5.1 `handle_task_success` does
  `task_fut.set_result(task["stdout"])` -> `KeyError: 'stdout'` in the
  callback, the future never resolves, the predictor never publishes a
  model, the agent's `get_inference(profile, pi_PREDICT_RUNTIME)` waits
  forever, its model list stays empty, and `model_select` returns 0 (FNO)
  for every request. Present in all four runs (one KeyError each). This is
  a framework bug: no executable task can complete through ORBIT with the
  pinned stack; the integration tests only use function tasks.
