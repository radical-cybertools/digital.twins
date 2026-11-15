# Perlmutter round 8c: converge on the default stack (2026-11-15)

Unattended session, page https://claude.ai/artifact/MfVYNiFtQ1Ra7CRB6qaPwc.
Rules: the round 1-2c page's autonomy contract, session mechanics, ORBIT
isolation and known traps; round 8's and 8b's terms, setup and harness.
Branch `exp/pm-round8c-20261115` off `a64effc`. Work dir
`/pscratch/sd/m/merzky/dt-pm8`. Budget 6 CPU node-h on m5290. Runs in
parallel with SwarmSlicer phase 9 (also m5290, its own budget and ledger).

## Ledger

| job | phase | account | nodes | elapsed | node-h | total |
|---|---|---|---|---|---|---|
| 61363245 | C0 smoke | m5290 | 3 | 00:02:34 | 0.128 | 0.13 |
| 61363584 | C2 | m5290 | 3 | 00:05:13 | 0.261 | 0.39 |
| 61363794 | C5 + C6 | m5290 | 3 | 00:10:02 | 0.502 | 0.89 |

## C0: setup (2026-11-15)

- `memo sync`; read the contract page sections, round 8's and 8b's pages
  and the round 8c page.
- Branch `exp/pm-round8c-20261115` off `a64effc` (paper/dtaas: 63d8692 +
  #65 `9068a23`, a step's own timeout keeps its message, + #66 `a64effc`,
  one ORBIT stream participant per DT session).
- `ve8c`: `DT_PYTHON=python3.12 DT_REF=a64effcdba1a9e482ee56f5e5386535391ab83d7
  RHAPSODY_EXTRAS=telemetry,dragon deploy/install.sh endpoint dt-pm8/ve8c`
  (cray-python 3.12.12), log `logs/install-ve8c.log`; `pip check` clean;
  installed digitaltwin `a64effc`. py-spy, pytest, pytest-asyncio,
  pytest-timeout added (tools).
- `r8c/env-r8c.sh`: round 8b's env, `VE` default ve8c; compression left
  at orbit's default (`auto`) unless the caller sets
  `RADICAL_ORBIT_WS_COMPRESSION`; provenance records it per run.
- `r8b/bench_windfield_stream.py`:
  - `--shared-stream on|off` sets `"shared_stream"` in the session config
    (unset = the stack's default, on); recorded in the provenance and per
    point, with the `dt_stream.*` participants the broker's topology shows
    after the build;
  - `--run-all-to N` (C1's rule): every N up to N, larger N only if nothing
    broke yet. The default stays round 8b's (one step past the break).
- `r8/prov.py`: the dirty check includes `r8c/`.
- `r8c/run_c3.sh`: C3's runner (below).
- **C0 smoke (job 61363245, debug, 3 nodes, one learning endpoint):**
  `r8b/run_windfield_b.sh` with `r8c/env-r8c.sh`, 16 twins, 20 s per
  point, `--shared-stream on` then `off`. The broker's topology after the
  build: **1** `dt_stream.*` participant with sharing on, **16** with it
  off. Both settings: every streamed answer arrived (320 of 320), bursts
  every 16.0 s, p50 33 ms. Isolation check empty.

## C2: the closed loop on the current stack (job 61363584, debug, 3 nodes)

Round 8b's B1 "both" cell (`r8b/run_b1.sh`, R8-2's `noop-one` row, 15 s
per point, a fresh broker and endpoint per repeat) on ve8c (`a64effc`),
compression orbit's default (`auto`; `ws_check.py`: no extension
negotiated), shared stream the default (on). `run_b1.sh` got two knobs for
this, `CELL_ENV` and `CELL_RES`. Table `results/r8c/c2/c2-table.md`.

| twins | rep | req/s | p50 ms | p99 ms | worst twin p99 ms | broker CPU % | endpoint CPU % | build s |
|---|---|---|---|---|---|---|---|---|
| 256 | 1 | 797.0 | 308 | 428 | 512 | 62 | 167 | 7.2 |
| 256 | 2 | 832.2 | 295 | 426 | 470 | 59 | 167 | 6.4 |
| 1,024 | 1 | 860.3 | 1,156 | 1,317 | 1,621 | 67 | 155 | 24.5 |
| 1,024 | 2 | 828.1 | 1,222 | 1,412 | 1,543 | 62 | 154 | 25.0 |

Round 8b B1 "both" (63d8692 predecessor a3e64c7, compression off): 816 /
841 req/s at 256 (build 7.0 s), 839 / 848 at 1,024 (build 23.2-23.3 s),
broker 57-64%, endpoint 155-171%.

- **No change**: the ceiling stays at 800-860 req/s, broker CPU 59-67%,
  endpoint 154-167%, and the 1,024-twin build still takes about 25 s
  (24 ms per twin). One participant instead of 1,024 makes no measurable
  difference in this no-op loop, where the stream carries nothing.
- 0 INFO `Online run` lines; isolation checks empty.

## C5: inputs per twin (job 61363794, debug, node 0 of 3)

`e2-scaling/bench_streams_join.py` and `bench_agents.py` build their twin
as `DTRuntime(None, stream)` with pass-through inferences: **no task runs
on any engine**, so the backend cannot change them. Per the page, one run
each on the current stack (ve8c, `a64effc`), round 3 T4's arguments
(join: K = 1..32, default rates, 5 s per point; agents: M = 1, 2, 4, 8, 16,
side and chain, 3 s per point), embedded ZMQ broker, plain Python on node 0.
Max sustainable inputs/s by round 3's rule (highest rate before p50
doubles, an output is lost, or the producer falls behind), against round
3 T4's median of 5 (`results/r3/t4/`):

| case | 1 | 2 | 4 | 8 | 16 | 32 |
|---|---|---|---|---|---|---|
| join K streams, r8c | 5,000 | 4,000 | 8,000 | 8,000 | 8,002 | 6,404 |
| join, round 3 | 5,000 | 4,000 | 8,001 | 8,001 | 8,001 | 6,404 |
| M agents side by side, r8c | 9,999 | 10,000 | 7,999 | 8,002 | 8,003 | – |
| side, round 3 | 5,000 | 4,000 | 4,001 | 4,002 | 8,003 | – |
| M agents chained, r8c | 10,000 | 9,999 | 5,000 | 2,000 | 2,000 | – |
| chain, round 3 | 5,000 | 2,000 | 2,000 | 2,000 | 1,000 | – |

- Joins: identical to round 3 at every K.
- Agents: 1.5-5x round 3 up to M = 4 (side) and M = 4 (chain), equal or 2x
  beyond. These rows are the stack's routing cost alone (no tasks): the
  stack changes since round 3 (asyncflow's tickless loop and later
  runtime work) show here, not dragon_native. One run, so steps of one
  rate level (the rate grid is coarse: 1k, 2k, 4k, 5k, 8k, 10k) are within
  noise.

## C6: what a twin build costs, step by step (same job, stretch)

`r8c/bench_build_steps.py` (new): one session, 16 WindField-like twins
(round 8b's B2 graph: WindAgent with three surrogate investigators,
TrendLearner, Sink) built one after another, shared stream on (default);
broker node 0, inference endpoint node 1, learning endpoint node 2, both
dragon_native. `results/r8c/c6/build-steps-*.json` (every twin's record).

| step | median ms (16 twins) |
|---|---|
| create_twin (register, no wait) | 1.3 |
| background init (wait_ready) | 1.4 |
| add_input | 1.2 |
| add_agent (WindAgent + 3 investigators) | 2.2 |
| add_investigator (TrendLearner) | 1.3 |
| add_investigator (Sink) | 1.1 |
| start | 0.7 |
| first get_inference | 209.0 (to the worker's task end 205.9, return 3.2) |
| total | 218.1 |

- **The build verbs are cheap: about 9 ms per twin together**, init
  included. A twin build is about 0.2 s because of its **first
  answer**: about 206 ms on the submit/run side for a 20 ms PINN (plus a
  1 ms selector). That is B4's finding: a fresh session pool's worker
  costs about 165 ms on its first task, and with 16 twins x 2 first tasks
  on a 128-worker pool, every first answer lands on cold workers.
- So B2's "about 0.1 s per twin" (16 builders in parallel) is the first
  answer's cold workers, overlapped, not the service's build path.
