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
| 61246711 | r8-e | m5290_g | 1 | 01:02:44 | 1.046 | 0.67 | 1.06 |
| 61246713 | r8-e-warm | m5290_g | 1 | 01:02:41 | 1.045 | 0.67 | 2.11 |
| 61246837 | r8-b-smoke | m5290 | 5 | 00:07:30 | 0.625 | 1.29 | 2.11 |
| 61247053 | r8-b-smoke | m5290 | 5 | 00:01:32 | 0.128 | 1.42 | 2.11 |
| 61247087 | r8-a | m5290 | 2 | 00:06:24 | 0.213 | 1.63 | 2.11 |
| 61247141 | r8-1 | m5290 | 2 | 00:14:01 | 0.467 | 2.10 | 2.11 |
| 61247176 | r8-2 | m5290 | 3 | 00:25:34 | 1.278 | 3.38 | 2.11 |
| 61247211 | r8-b | m5290 | 5 | 00:28:55 | 2.410 | 5.79 | 2.11 |
| 61249075 | r8-1-local | m5290 | 2 | 00:11:36 | 0.387 | 6.17 | 2.11 |
| 61249379 | r8-d | m5290 | 17 | 00:24:43 | 7.003 | 13.18 | 2.11 |
| 61249380 | r8-c | m5290 | 6 | 00:20:34 | 2.057 | 15.23 | 2.11 |
| 61258267 | r8-c-smoke | m5290 | 6 | 00:12:29 | 1.248 | 16.48 | 2.11 |

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

## R8-A: payload size (done, job 61247087, debug, 2 nodes, about 6 min)

Node 0: broker and clients; node 1: one Dragon endpoint (dragon_native,
whole node). Wide area: radical.3:8010 with `r3_site` (read-only default
credentials). Results in `results/r8/r8-a/`.

**Stream messages** (`e1-overhead/bench_streams.py --payload`). Rows:
zmq embedded broker as the local floor; ORBIT eventing through the
cluster broker; ORBIT through radical.3. Cells: p50 ms / burst msg/s.

| size | zmq (local floor) | ORBIT cluster | ORBIT radical.3 |
|---|---|---|---|
| 100 B | 0.19 / 19,878 | 0.51 / 8,364 | 173.4 / 530 |
| 1 KB | 0.19 / 18,934 | 0.42 / 8,278 | 178.7 / 399 |
| 100 KB | 0.27 / 7,538 | 0.81 / 2,651 | 173.5 / 266 |
| 1 MB | 0.97 / 1,311 | 4.97 / 345 | 198.0 / 59 |
| 16 MB | 20.4 / 108 | **error** | **error** |
| 64 MB | 126.1 / 16 | **error** | **error** |

ORBIT's error is a clear client-side `ValueError: stream payload ... is
16777225 bytes, over the 4128768 byte ceiling (ORBIT's 4194304 byte frame
cap, less envelope overhead)`. **Break: between 1 MB and 16 MB (the 4 MiB
frame cap), on both brokers.**

**Task argument and return** (`r8/bench_echo.py`: the investigator sends S
random bytes as the argument and the task returns S bytes; 5 calls each).

| size | cluster | radical.3 |
|---|---|---|
| 1 KB | 5/5, p50 5.7 ms | 5/5, p50 426 ms |
| 100 KB | 5/5, 10.6 ms | 5/5, 433 ms |
| 1 MB | 5/5, 40.1 ms | 5/5, 493 ms |
| 2 MiB - 1 KB | **returns `None`**, no error | **returns `None`**, no error |
| 2 MiB + 1 KB | **returns `None`**, no error | **returns `None`**, no error |
| 16 MB | `HTTP 413 — [r8a_ep/rhapsody] submit 1 task(s) — frame size 21335241 bytes exceeds cap 4194304 bytes` | the same (r3_site) |

- **Break and bug (described, not fixed):** above about 1.5 MiB the
  return value is silently replaced by `None`. The task completes, the
  investigator gets `None`, and nothing reports an error, already at
  2 MiB - 1 KB. With base64 encoding (×1.33), a 1.5 MiB return already
  exceeds the 2 MiB return limit.
- Arguments fail loudly with HTTP 413 once the encoded frame passes 4 MiB
  (raw arguments of about 3 MiB).
- For Andre: the silent `None` should become an error, in the radical.orbit
  rhapsody plugin's return-value limit or in rhapsody's orbit backend.

**Model publish** (`e4-hot-swap/bench_model_update.py`, new `--payload-mb`
/ `--path-mb`, interval 1 s, 20 versions, client-side runtime with
`OrbitExecutionBackend` on dragon_native).

| model | cluster: publish → first answer p50 / p90 ms | inference p50 ms | requests/s | radical.3 |
|---|---|---|---|---|
| by value 0.2 MB | 13.6 / 17.2 | 8.3 | about 118 | 791 / 958 ms, inference 490 ms, 2 req/s |
| by value 10 MB | **error**: `HTTP 413 ... frame size 13983026 bytes exceeds cap 4194304 bytes` | – | – | same error |
| by value 100 MB | **error**: frame size 139812146 bytes | – | – | same error |
| by path 10 MB | 5.4 / 7.0 | 3.4 | about 290 | not possible (the file would have to be on radical.3) |
| by path 1 GB | 310 / 433 | 4.0 | **about 5** (each of 128 workers reads the 1 GB once) | – |

- **By value, the model travels with every inference task**, so the 4 MiB
  frame cap is a hard limit on model size by value (about 3 MiB raw):
  WindField's FNO (about 9.5 MB) and PCR (about 10 MB) cannot be published
  by value. **By path has no size limit**, but each pool worker loads
  the file on first use: at 1 GB the 128 workers' first reads hold the
  rate at 5 req/s for the 20 s run (236 answers in the final window, once
  warm).
- Isolation check empty.

## R8-1: overhead on Dragon (done; jobs 61247141 and 61249075)

`e1-overhead/bench_dt_insitu.py`, rows bare / investigator / agent, 200
sequential requests (p50) and 50 at once (req/s), 5 repeats, each cell its
own process. Harness additions:
- `--work-ms`: the task holds its process's CPU for that long
  (`thread_time`);
- `--local-backend dragon_native`: the harness runs under `dragon -s`;
- `--stream-broker`, needed because under Dragon the embedded ZMQ broker
  cannot start: Dragon's multiprocessing bridge returns no `Pipe`
  (`TypeError: 'NoneType' object is not callable` in `ctx.Pipe`). Every
  local-dragon cell of job 61247141 failed that way; the twin's stream
  client now goes to the job's ORBIT broker, which get_inference does not
  use. The local-dragon cells were rerun in job 61249075 (debug).

Table: `results/r8/r8-1/insitu-table-stack-r8-20261114.md`. Medians of 5
repeats; the DT's cost per request is the row's p50 minus bare's.

| setup | task | bare p50 ms | investigator: cost ms (ratio) | agent: cost ms (ratio) | bare / inv / agent req/s, 50 at once |
|---|---|---|---|---|---|
| local dragon_native | 0.58 ms | 1.92 | -0.36 (0.81x) | -0.38 (0.80x) | 2839 / 2867 / 2522 |
| local dragon_native | 20 ms | 21.38 | -0.28 (0.99x) | +0.04 (1.00x) | 1356 / 1252 / 1156 |
| local dragon_native | 120 ms | 121.88 | -0.10 (1.00x) | -0.31 (1.00x) | 356 / 356 / 359 |
| ORBIT → Dragon endpoint | 0.58 ms | 3.87 | -0.12 (0.97x) | -0.21 (0.95x) | 907 / 967 / 880 |
| ORBIT → Dragon endpoint | 20 ms | 24.86 | -0.36 (0.99x) | +0.62 (1.03x) | 976 / 837 / 972 |
| ORBIT → Dragon endpoint | 120 ms | 125.68 | -0.23 (1.00x) | -0.46 (1.00x) | 324 / 328 / 327 |
| local concurrent (process pool) | 0.58 ms | 3.02 | -0.98 (0.68x) | -1.21 (0.60x) | 1647 / 1620 / 1706 |
| ORBIT → endpoint, concurrent | 0.58 ms | 3.44 | +0.22 (1.06x) | +0.27 (1.08x) | 608 / 623 / 623 |

- **The DT layer costs nothing measurable on dragon_native**: at 20 and 120
  ms it is within ±0.6 ms of bare locally and through ORBIT, inside the
  repeats' spread.
- At 0.58 ms the DT rows' p50 is *below* bare's in both local setups (0.6-0.8x).
  Bare runs first in each process, so this is likely warm-up order
  (the first row pays the pool's first contacts), not a DT gain; reported
  as measured, not corrected.
- **dragon_native is cheaper per task than concurrent** through ORBIT at
  0.58 ms: 907 against 608 req/s, p50 3.87 against 3.44 ms (concurrent's
  thread pool has a lower floor, but less throughput).
- At 120 ms all rows serve about 325-356 req/s: 50 requests at once on 128
  workers, so one 120 ms round each, plus overhead.
- Isolation checks empty.

## R8-2: one engine (done, job 61247176, 3 nodes, about 27 min)

`r8/bench_engine.py` through the DT service: broker on node 0, one Dragon
endpoint (dragon_native, 128 workers) on node 1, the client on node 2; a
fresh broker and endpoint per repeat, 3 repeats, 15 s closed loop per N.
Each request is one function task of `--work-ms` CPU. Table:
`results/r8/r8-2/engine-table-stack-r8-20261114.md`, made with `r8/engine_table.py`.

| row | twins | req/s (min-max) | p50 ms | p99 ms | worst twin p99 ms | broker CPU % | client CPU % |
|---|---|---|---|---|---|---|---|
| no-op, one session | 1 | 191 (190-200) | 5.1 | 6.5 | 7 | 58 | 18 |
| | 16 | 588 (586-596) | 26.0 | 64.2 | 70 | 84 | 30 |
| | 64 | 774 (751-781) | 78.1 | 213.7 | 273 | 72 | 30 |
| | 256 | 845 (824-848) | 287.3 | 552.2 | 604 | 65 | 28 |
| | **1024** | 844 (785-847) | 1197 | 1420 | **1674** | 69 | 28 |
| 20 ms, one session | 1 | 38 (37-38) | 26.4 | 27.5 | 28 | 17 | 5 |
| | 16 | 447 (436-447) | 35.0 | 44.6 | 48 | 88 | 29 |
| | 64 | 750 (745-757) | 80.6 | 231.0 | 292 | 78 | 31 |
| | 256 | 953 (901-962) | 256.2 | 528.3 | 620 | 74 | 33 |
| | **1024** | 879 (842-887) | 1123 | 1483 | **1837** | 71 | 29 |
| no-op, one session per twin | 1 | 185 | 5.3 | 6.6 | 7 | 61 | 17 |
| | 4 | 273 | 14.4 | 20.7 | 21 | 97 | 20 |
| | 16 | 248 (2 of 3 repeats) | 58.8 | 202 | 220 | 89 | 18 |

- **Break: N = 1024 twins on one engine** (worst twin p99 1.57-1.84 s in all
  repeats, both task costs). N = 256 is the last point under 1 s. No failed
  requests and no keepalive timeouts at any N.
- **The plateau is about 850-950 req/s** from 256 twins, the same as round 6's
  one-session ceiling (about 800-840, Y1c). It is below round 2's 2.2k
  req/s on the thread pool (`bench_twins.py`), which ran the twins in a local
  client-side runtime with no broker or DT service in the request path; here
  every request crosses the broker twice. With 20 ms tasks the endpoint's 128 workers are never the
  limit: 950 req/s × 20 ms is about 19 busy workers.
- What saturates: no process reaches 100% of a core by these counters. The
  broker is at 65-92%, the client at 28-33% (one Python process, 1,024
  threads). Latency grows linearly with N past 256 (closed loop), so the
  service path is throughput-bound at about 850-950 req/s, as in rounds 6/7
  (Y1c: broker 68-96%).
  - **Harness error:** the endpoint sampler measured the wrong process.
    Under `dragon -s radical-orbit-endpoint.py` the oldest process whose
    command line matches is the Dragon launcher, not the endpoint, so the
    "endpoint CPU" column of this job is the launcher's and is left out.
    `r8/proc_sampler.sh -f` now skips Dragon launcher command lines; R8-D
    and R8-C use the fixed sampler.
- **One session per twin** tops out at about 270 req/s from 4 sessions:
  each session is a pool of 128 workers, so 16 sessions oversubscribe the
  node 16×.
  - In repeat 2, the 16 sessions failed to start (`twin ... failed to
    initialize: RuntimeError: Session init timed out after 120.0s`); in
    repeats 1 and 3 creation took 29 s and 57 s.
  - So R8-0's "16 safe" is the edge, not a margin. R8-C's one-session-per-twin
    row still goes to 16 as the page and R8-0 set; a failure there is that
    row's break point.
- Isolation check empty.

## R8-E: WindField decomposed (done; GPU jobs 61246711 cold, 61246713 warm; 3 runs each)

P8b on the round 8 stack, one A100 node each (regular, about 63 min,
m5290_g):
- broker, sensor (1 Hz) and client (probe every 3 s, 1,200 s per run) on
  loopback;
- the endpoint inside a single-node Dragon runtime, with both DT engines
  (inference, learning) on `dragon_native` (`DT_*_BACKEND`). One pool per
  engine: 64 workers each on the 64-core GPU node;
- venv `ve8-xgf`; xGFabric `dt-pm8/xGFabric` on the local branch
  `r8/timings` (3adefa8 plus two commits, never pushed; patches in
  `results/r8/r8-e/xgfabric-patch/`). Commit 1 is task-side timings: phase
  times inside `tk_*_eval`, returned with each answer, and jsonl logs of
  the selector, simulations and trainings. Commit 2 is the warm-model
  variant: a per-worker cache keyed by the archive path, on with
  `R8_WARM_MODEL=1`;
- harness: `p8b_client.py` now records send / receive epochs and the
  task's times; `r8/run_r8e.sbatch`; table `r8/r8e_table.py`
  (`results/r8/r8-e/r8e-table-stack-r8-20261114.md`).

xGFabric's own precheck passed in both jobs (September archives: FNO 6.0
s, PINN 0.15 s, 3 × 38 × 85). Medians over all answers of the 3 runs, ms:

| model | variant | answers | total | to task start | in task | setup | tar extract | model reload | field | cleanup | return |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PINN | reload per call (xGFabric) | 535 | 155.4 | 16.1 | 134.5 | 1.8 | 31.3 | 81.8 | 16.6 | 2.0 | 4.4 |
| PINN | warm model | 417 | **42.9** | 16.9 | 20.9 | 1.7 | 0.0 | 0.0 | 17.5 | 0.9 | 4.1 |
| FNO | reload per call | 109 | 817.8 | 14.8 | 795.3 | 1.7 | 116.0 | 563.2 | 115.0 | 4.4 | 6.1 |
| FNO | warm model | 217 | **178.8** | 15.6 | 151.9 | 1.7 | 0.0 | 0.0 | 115.2 | 1.2 | 5.7 |
| none yet ("na") | either | 674 | 11.9-12.5 | 9.1-9.7 | 0 | – | – | – | – | – | 2.5-2.6 |

- **The reload is the cost, not the framework.** As xGFabric is written, each
  answer pays tar extraction and a model rebuild: 113 ms for PINN, 679 ms
  for FNO. Keeping the model per worker cuts the answer **3.6× (PINN) and
  4.6× (FNO)**. The field itself is 17 ms (PINN) and 115 ms (FNO), close to
  P8a's GPU warm numbers (13 / 97 ms).
- **The framework's share** is "to task start" plus "return": client →
  service, the selector task, and the inference dispatch through ORBIT to
  the Dragon pool, about 15-17 ms in, 4-6 ms out. An answer before any
  model exists ("na") costs 12 ms end to end. The selector's own body takes
  under 0.01 ms; its cost is its task round trip, inside "to task start".
- **Cold workers dominate the tail:** the worst answers take 15-24 s,
  when an inference lands on a pool worker that has not imported TensorFlow
  yet (12.5 s import in a worker, R8-0) plus CUDA initialization. Only 77%
  (PINN) and 51% (FNO) of the warm variant's answers hit the cache; the
  rest are first calls per worker. With 64 workers per pool and about 1
  answer/s, the cache fills slowly. This is why per-run medians vary (cold
  run 3: 9 FNO answers, p50 9.7 s).
- **Sizes** (`archives-*.txt`):
  - FNO archives 8.85-8.87 MB (8.46 MiB, used as the model file in R8-C);
  - PINN 0.25 MB;
  - PCR packed models 0.8-1.7 MB;
  - PCR partitions are directories (`WindField/pcr/partition/<n>/`), not
    one file.
- **Training wall time per model** (task body, not the waits for readings
  and simulations): FNO 249-260 s (p50; 210-331), PINN 316-354 s
  (302-417), PCR partition 262-290 s, plus 7.3 s for the PCR fit.
- **Selector choices over time** (quarters of the run): no model in the
  first quarter, then FNO and PINN mixed (PINN 0.43-0.49, FNO 0.23-0.34),
  then increasingly PINN as the profiler learns that it is cheaper (last
  quarter: PINN 0.77-1.00).
- 1,952 answers, no failed probe, isolation checks empty (all 6 runs).
- `e6-use-cases/README.md` updated: P8b ran (B3, round 2b) and R8-E
  decomposed it.

## R8-B: fan-out (job 61247211, regular, 5 nodes, 29 min; concurrent spread rerun pending)

`r8/bench_fanout.py`, `r8/run_fanout.sh`: one twin, one investigator,
bursts of K function tasks in one gather, 3 repeats. Probes every 0.5 s
during a burst: `twin_list()` and an executable task. Columns per cell:
makespan s (ideal), probe p99 s.

**dragon_native, 64 workers per site** (`taskset -c 0-63,128-191`):

| K | 0.1 s, 1 site | 0.1 s, 4 sites | 10 s, 1 site | 10 s, 4 sites |
|---|---|---|---|---|
| 16 | 0.11 (0.10) | 0.11 (0.10) | 10.01 (10), 0.04 | 10.01 (10), 0.04 |
| 64 | 0.13-0.15 (0.10) | 0.12 (0.10) | 10.03 (10), 0.05 | 10.02 (10), 0.04 |
| 256 | 0.47-0.56 (0.40), 0.05 | 0.16-0.19 (0.10) | 40.08-40.09 (40), 0.04-0.12 | 10.05-10.06 (10), 0.04 |
| 1024 | 1.92-1.99 (1.60), 0.37-0.49 | 0.55-0.67 (0.40), 0.04-0.16 | 160.2-160.4 (160), 0.05 | 40.15-40.19 (40), 0.05-0.21 |

- **No break anywhere on dragon_native**: no failed task, probe p99 at most
  0.49 s, and the first task starts within 0.01-0.27 s of the submit even at
  K = 1024. 10 s CPU-bound tasks (the GIL case) run at the ideal makespan
  within 0.3%.
- Empty tasks, K = 1024 through ORBIT: **1,398-1,510 tasks/s on one site,
  2,308-2,506 on four**.

**concurrent, thread pool (32 threads), one site: breaks at K = 16.**
- 0.1 s tasks: K = 16 makespan 1.61 s (ideal 0.10), probe p99 1.43 s; K = 64
  6.36 s, probe p99 6.18 s. The thread pool serializes on the endpoint's GIL
  and starves its event loop.
- 10 s tasks, K = 16: **all 16 tasks failed**, `HTTP 504 — [r8b_s0/rhapsody]
  submit 16 task(s)`, probe p99 43.6 s. K = 64 (one step past): all 64
  failed, `HTTP 502 ... endpoint lost`: the broker declared the starved
  endpoint lost.
- The spread layout could not start after that (`twin ... failed to
  initialize: engine endpoint lost: r8b_s0`): its failure is inherited
  from the previous row, so it is rerun on fresh endpoints (job 61258304).

**concurrent with a process pool** (`e6-use-cases/p8b_endpoint.py`,
`ProcessPoolExecutor(64)`, one site), as a harness wrapper. The engine
config cannot select a process pool, so the page's condition ("if the
engine config can select it without a src change") is not met in the
strict sense; the wrapper changes nothing installed. Logged as a decision.
- 0.1 s: K = 16 0.41-0.47 s (ideal 0.10), K = 1024 2.09-2.23 s (1.60), probe
  p99 at most 0.65 s.
- 10 s: K = 1024 160.5-160.6 s (160).
- No break, but each burst pays about 0.3 s extra at small K (process pool
  hand-off), and the first task at K = 1024 starts 0.4-0.5 s late.

**The batched-submit row** (`batch_window` > 0, `batch_limit` = 64) is
skipped. The DT service builds every engine with `batch_window=0`
(`session.py:839`) and takes no engine-config key for it, so the row
would need a `src/` change.

## R8-D: sites (job 61249379, regular, 17 nodes; NODE_FAIL in the teardown)

`e3-portability/bench_sites.py` (`E3_BACKENDS=dragon_native`, spread, work
model cpu, 120 ms per request), each site an endpoint in a Dragon runtime
held to 8 workers (`taskset -c 0-7,128-135`). Client concurrency 16 × N,
120 × N requests per burst, 5 bursts (median of 2-5), 3 repeats. All
measurements finished; the node failure came 12 min after the last one,
in the cleanup. The isolation check, run by hand afterwards, is empty.

| sites | DT req/s (3 repeats) | speedup | seq p50 ms | broker CPU % | site 0 endpoint CPU % | hand-wired req/s |
|---|---|---|---|---|---|---|
| 1 | 65.2 / 65.5 / 65.4 | 1.0 | 128 | 18-20 | 162-172 | 65.6 / 65.7 / 65.7 |
| 2 | 130.0 / 130.5 / 130.2 | 2.0 | 128 | 35-39 | 169-174 | 131.1 (×3) |
| 4 | 257.7 / 257.7 / 257.4 | 3.9 | 128 | 69-73 | 177-183 | 260.8 / 260.8 / 260.9 |
| 8 | 495.8 / 497.3 / 496.0 | 7.6 | 128 | 111-116 | 186-193 | – |
| 16 | 663.7 / 688.4 / 680.8 | **10.4** | 128 | **118** | 163 | – |

- **Scaling is linear to 8 sites (7.6×) and stops between 8 and 16
  (10.4×)**, where the broker is CPU-bound at 118%, its ceiling in rounds 6,
  7 and R8-2. 16 sites at 120 ms would serve 1,056 req/s; the broker carries
  about 680.
- Placement was correct in every run. 0 errors. The DT row is within 1% of
  the hand-wired baseline at N = 1-4.
- The endpoint process uses 1.6-1.9 cores at every load, even at 65 req/s.
  The dragon_native backend's threads seem to poll; this is not a
  saturation (site 0 at N = 16 serves 42 req/s).
- **N = 4 with r3_site on radical.3** (three Perlmutter sites registered on
  radical.3:8010 as `pm_r8d_s0..2`, 8 workers each, plus r3_site, 32
  workers; 64 client threads from Perlmutter): 106.6 / 105.5 / 105.1 req/s,
  seq p50 476-482 ms. The WAN round trip bounds it: 64 in flight / 0.48 s is
  about 133 req/s. Placement was right; the harness reports it as "WRONG"
  only because r3_site answers with its host name `three` (it has no
  DT_TEST_ENDPOINT_TAG).

## R8-C: WindField at scale (attempt 1 invalid, smoke passed, real run queued)

- **Attempt 1, job 61249380** (regular, 6 nodes, 21 min): invalid, a
  harness bug. `TrendLearner`'s inference returned the `r8c_field` dtype,
  but it was added with output `r8c_trend`, so every twin failed on its
  first input (`ValueError: Model Investigator ... returned r8c_field dtype.
  Expected: r8c_trend`, broker log). Probes still answered, through the
  agent, but no burst or model update ever ran. Each row stopped after
  N = 4 on the "twin states failed" break.
- I saw it about 3.5 h late, because the job-state Monitor had expired
  unnoticed. The waiting method is now a no-timeout background waiter
  that is re-armed after every event (memory note
  `slurm-wait-no-expiring-monitors`).
- Fix: `TREND` moved into `r8c_components.py`, `TrendLearner` returns it;
  the harness records twins' `last_error`.
- The model file is now 8.46 MiB, R8-E's measured FNO archive (`MODEL_MB=8.46`).
- **Smoke, job 61258267** (debug, 6 nodes, N = 1, 4, 1 repeat;
  `results/r8/r8-c-smoke/`). All rows ran, with 0 failed probes:
  - groups of 16 and one session: p50 36-43 ms, p99 about 300 ms;
    simulation burst makespan 0.28-0.30 s (16 × 0.25 s CPU); model update
    seen 0.8-1.8 s after publish;
  - one session per twin: N = 16 breaks with p99 1,180 ms (worst twin
    1,700 ms), creation 24 s.
- Real run: job 61258719 (`RES=r8/r8-c2`, 2 repeats, N = 1 .. 256).

## R8-5: persistence on Dragon (attempt 1 failed at start; rerun queued)

- Harness: `e5-persistence/bench_endpoint_loss.py` gained `E5_BACKEND`
  (dragon_native for both endpoints), `E5_LAUNCH="dragon -s"` (the learning
  endpoint inside its own Dragon runtime) and `E5_CLEANUP=dragon-cleanup`
  (after every kill). The kill is SIGKILL to the runtime's whole process
  group. `r8/run_persistence.sh`: broker and inference endpoint (own Dragon
  runtime) on node 0; harness and learning endpoint on node 1, so the
  cleanup touches only the learning runtime.
- **Attempt 1 (job 61258409, 3 min):** the learning endpoint never came up
  (`learning endpoint never advertised rhapsody`, no endpoint log at all).
  I had started it with `start_new_session=True`. A by-hand check on a
  1-node interactive allocation (`r8-diag`, about 3 min,
  `attempt1/dragon-launch-diag.py`):
  - `dragon -s prog` from Python without a new session: up and done in 11.9 s;
  - with `start_new_session=True`: hangs 90 s with no output at all;
  - with `process_group=0` (own group, same session): 12.0 s; `killpg(SIGKILL)`
    leaves 0 Dragon processes.
  **Finding:** a Dragon single-node launcher must stay in its caller's
  session. The harness now uses `process_group=0`.
- Rerun: job 61261542.
