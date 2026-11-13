# Perlmutter round 8: limit study on Dragon (started 2026-11-13 14:20 PST)

Unattended session on a Perlmutter login node, from the round 8 page
(https://claude.ai/artifact/Erj5aEKRsHjDwQmjk7e1EC). Rules: the round 1-2c
page's autonomy contract, session mechanics, ORBIT isolation and known
traps; `notes/dragon-perlmutter-pitfalls.md`. Branch `exp/pm-round8-20261114`
off `49bd91f`, merged into `paper/dtaas` at the end. Work dir
`/pscratch/sd/m/merzky/dt-pm8`. Budget 42 CPU node-h (m5290), 3 GPU node-h
(m5290_g). Ledger: `python s1/ledger.py 8`. Never radical.3 port 8011.

## Node-hour ledger (round 8 budget: 42 CPU m5290, 3 GPU m5290_g)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 8`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 61245985 | r8-smoke | m5290 | 2 | 00:09:15 | 0.308 | 0.31 | 0.00 |
| 61246055 | r8-gpu-smoke | m5290_g | 1 | 00:00:23 | 0.006 | 0.31 | 0.01 |
| 61246494 | r8-smoke-b | m5290 | 2 | 00:10:42 | 0.357 | 0.67 | 0.01 |
| 61246506 | r8-gpu-smoke | m5290_g | 1 | 00:00:39 | 0.011 | 0.67 | 0.02 |
| 61246837 | r8-b-smoke | m5290 | 5 | 00:07:30 | 0.625 | 1.29 | 0.02 |
| 61247053 | r8-b-smoke | m5290 | 5 | 00:01:32 | 0.128 | 1.42 | 0.02 |

## R8-0: setup (2026-11-13 14:20 PST)

- `/pscratch` healthy: work dir `dt-pm8` there.
- `ve8`: `DT_PYTHON=python3.12 DT_REF=49bd91f94a001c944ed133efb4cf75c4f47d4841
  RHAPSODY_EXTRAS=telemetry,dragon deploy/install.sh endpoint dt-pm8/ve8`
  (cray-python 3.12.12). The pins match `STACK.md`: asyncflow `24667a5`,
  rhapsody `5abecd6`, orbit `adf2548`, ROSE `9cc47a5`, digitaltwin `49bd91f`,
  dragonhpc 0.15.0. `rhapsody.backends.execution.dragon_native` imports;
  `pip check` clean. Log `dt-pm8/logs/install-ve8.log`.
- `ve8-xgf` (GPU): round 1's TF conda env `dt-pm2/xgf/env` (Python 3.12.13,
  TF 2.21.0, numpy 2.5.0) as base, `--system-site-packages`, with the same
  pins, rhapsody `[telemetry,dragon]`, built as round 2b's `ve2b-xgf`. Log
  `dt-pm8/logs/ve8-xgf.log`.
- **Finding, backend selection:** the DT service always names its rhapsody
  backend in the remote session (`session.py`: `backends=cfg.get("backends")
  or DEFAULT_BACKENDS`, `DEFAULT_BACKENDS = ["concurrent"]`). radical.orbit
  uses the endpoint's `RADICAL_ORBIT_RHAPSODY_BACKEND` only when the client
  names none (`plugin_rhapsody._backend_names`). So
  `RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native` on an endpoint alone keeps
  DT sessions on `concurrent`. A harness must put `"backends": ["dragon_native"]`
  in each engine config (allowed: a harness change). Round 8 harnesses
  do; the endpoint also sets the variable.
- **Pool size:** `DragonNativeExecutionBackend(workers_per_node=None)` makes
  one worker per physical core of each node's `Node.cpus`. orbit's plugin
  calls `rh.get_backend(name)` with no arguments, so there is no config path
  for `workers_per_node`. R8-0 checks whether a `taskset` on the launch
  changes `Node.cpus`.
- **Launch:** each endpoint is `srun -N1 -n1 -c 256 --cpu-bind=none -w <node>
  ... dragon -s radical-orbit-endpoint.py ...`: one single-node Dragon
  runtime per endpoint, with the whole node's CPUs. Without `-c`, the step's
  CPU binding could shrink `Node.cpus`. `ulimit -n` is raised to the hard
  limit, since dragon_native warns about Local Services' descriptors.
- Harness in `r8/`:
  - `env-r8.sh`; `r8_components.py` (one investigator whose inference runs
    a function task, an executable task, or a burst of K function tasks of
    M ms CPU);
  - `smoke_dragon.py` (steps basic, gil, reattach, remote, sessions, pool);
  - `run_smoke.sh` (the R8-0 job), `wait_endpoint.py`, `node_probe.sh`
    (Dragon native processes, user processes and threads, memory);
  - `prov.py` (provenance: commits of the five packages from pip's
    `direct_url.json`, backend, workers per node, telemetry, file system);
  - round 7's `proc_sampler.sh`, `broker_table.py`, `folded_top.py`,
    `frame_counter.py` copied.
- Decision, GIL probe: the page asks that the endpoint answer "a submit and
  a twin_list within 1 s" while every pool worker runs a 10 s CPU task. A
  function-task probe would wait for a free worker, so the probe is an
  executable task (a native Process outside the pool) plus `twin_list()`.

### R8-0 smoke, run 1 (job 61245985, debug, 2 nodes, about 10 min)

Broker and client on nid005592; endpoint `r8_ep` in a single-node Dragon
runtime on nid005593 (128 physical cores). Results in `results/r8/r8-0/`.

- **Gate passed: dragon_native runs function tasks through ORBIT.**
  - Endpoint up 12 s after launch.
  - Twin ready 3.5 s after session open.
  - Function task: 5.0-6.0 ms round trip (10 calls), each on a different
    pool worker.
  - Executable task (`/bin/hostname`, a native Process): 31-37 ms;
    returns the stdout.
  - 1,000 empty function tasks in one burst: 1.15 s, **873 tasks/s**
    through ORBIT, on 128 worker pids.
- **GIL case:** 128 function tasks of 10 s CPU each (one per worker) took
  10.09 s. During the burst `twin_list()` answered in at most 2.2 ms, and an
  executable task in at most 49 ms (17 probes, all under 1 s). The endpoint
  stays responsive: the CPU work runs in worker processes, not in its
  threads.
- **Kill:** `pkill -KILL -f dragon` on the endpoint node plus `dragon-cleanup`
  took 2.9 s and left 0 processes (from 130 Dragon native processes). The
  restarted endpoint was in the topology at once (0.0 s: the broker still
  held the old one).
  - **Reattach failed:** for 180 s (88 tries) every get_inference returned
    `HTTP 409 ... get_inference: RuntimeError: HTTP 404 — [r8_ep/rhapsody]
    submit 1 task(s) — unknown session id: session.67f77076`.
  - The DT session's backend keeps the remote rhapsody session id, which
    died with the runtime, and does not create a new one on the restarted
    endpoint.
  - The restart came within about 3 s of the kill, likely before the broker
    detected the loss.
  - Rerun once (run 2) with the restart delayed until the broker no longer
    holds the endpoint as present.
- **radical.3:8010 → r3_site** (read-only use of the default credentials in
  `~/.radical/orbit`, as round 2 S2; client log to a file):
  - session ready 2.7 s;
  - function task round trip p50 **434 ms** (10 calls, 431-437);
  - executable task 453 ms, stdout `three`;
  - 64 × 100 ms CPU on 32 workers: 0.38 s at the service, 0.56 s at the
    client (ideal 0.2 s).
- **Pool size follows the launch's CPU restriction, in physical cores.**
  `taskset -c 0-15 dragon ...` gave a pool of **16** workers, not 8:
  Perlmutter numbers CPUs 0-127 as the first hardware thread of each
  physical core and 128-255 as the second, so 0-15 is 16 cores. 8 workers
  need `taskset -c 0-7,128-135` (run 2 checks). 256 × 50 ms on 16 workers:
  0.94 s (ideal 0.8 s).
- **Sessions per endpoint: invalid in run 1.** A harness bug: twin ids came
  from the millisecond clock, so concurrently created twins collided
  (`twin id ... is already used`). The failed twins' sessions still built
  their pools, so the counts are not per S.
  - Valid: S = 1: one pool of 128 workers (130 Dragon native processes),
    64 × 100 ms in 0.15 s, 8.0 GB of the node's memory.
  - Indicative: about 24 sessions' pools, 3,076 Dragon processes and 6,588
    threads, took 121 s to start and used about 172 GB.
  - Twin ids are now uuids; run 2 repeats S = 1, 4, 16, 64.

### R8-0 smoke, run 2 (job 61246494, debug, 2 nodes) and the GPU check (61246506)

`RES=r8/r8-0b STEPS="basic kill pool sessions" KILL_WAIT=1
POOL_CPUS=0-7,128-135`, twin ids now uuids.

- basic: as run 1 (function task 5.1-5.9 ms, endpoint up 12 s).
- **Reattach, rerun as the contract asks:** the broker held the endpoint
  as `suspect` right after the kill (wait_lost, 0.0 s), then the restart.
  It fails the same way: 89 tries in 180 s, all `HTTP 404 — [r8_ep/rhapsody]
  submit 1 task(s) — unknown session id`. The result holds.
  - **Finding:** after the whole Dragon runtime of an endpoint is killed
    and the endpoint restarts under the same name, an existing twin does
    not recover. Its DT session keeps submitting to the remote rhapsody
    session id that died with the runtime, and nothing creates a new one.
  - A restart after the suspect window, once the broker has declared the
    endpoint lost, is E5's case (R8-5).
  - Described, not fixed (no fix branches). For Andre: should the DT
    service re-create its remote rhapsody session on a 404 `unknown
    session id`?
- **Pool size:** `taskset -c 0-7,128-135` gives a pool of **8** workers. 256
  × 50 ms took 1.87 s (ideal 1.6 s). The pool follows the launch's CPU
  restriction, counted in physical cores; R8-D can hold a site to 8
  workers without a `src/` change.
- **Sessions per endpoint** (each DT session builds its own `dragon_native`
  backend, one pool of 128 workers on this node):

| S | sessions ready | ready s (all) | Dragon native processes | threads | node memory used, GB | 64 × 100 ms per session at once, worst makespan s |
|---|---|---|---|---|---|---|
| 1 | 1/1 | 2.0 | 130 | 482 | about 12 | 0.15 |
| 4 | 4/4 | 5.6 | 520 | 1,682 | about 31 | 0.39 |
| 16 | 16/16 | 38.3 | 2,078 | 6,492 | about 104 | 2.41 |
| 64 | **0/64** | 241 (failed) | 4,352 | 9,192 | about 209 | – |

  - S = 64 breaks: every session fails with `twin ... failed to initialize:
    RuntimeError: Session init timed out after 120.0s` while 34 pools
    (4,352 processes) start on 128 cores.
  - At S = 16 the 1,024 tasks take 3× their ideal (0.8 s on 128 cores):
    16 pools of 128 workers oversubscribe the node 16×.
  - **Decision:** R8-2 and R8-C use at most **16** sessions per Dragon
    endpoint for their one-session-per-twin rows.
- **GPU check: passed** (job 61246506, 1 A100 node, debug).
  - TensorFlow 2.21.0 inside a `dragon_native` pool worker sees all four
    A100s (`CUDA_VISIBLE_DEVICES=0,1,2,3`); TF import takes 12.5 s in the
    worker.
  - One PINN field from the September archive (`tk_pinn_eval`): 2.52 s
    cold, then 0.121 s; shapes 3 × 38 × 85.
  - The first submission failed in my harness (asyncflow requires an async
    task function; job 61246055) and was fixed.
- **R8-0 done; the gate passes.** All isolation checks are empty. Jobs:
  61245985, 61246494 (CPU debug, 2 nodes); 61246055, 61246506 (GPU debug).
