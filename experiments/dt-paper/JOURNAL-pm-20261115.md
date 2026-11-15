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
| 61363581 | C1 | m5290 | 6 | 00:21:19 | 2.132 | 3.02 |
| 61363587 | C3 | m5290 | 2 | 00:26:30 | 0.883 | 3.90 |
| 61363679 | C4 | m5290 | 2 | 00:26:23 | 0.879 | 4.78 |

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

## C1: WindField twins per experiment, shared stream on and off (job 61363581, regular, 6 nodes)

Round 8b's B2 (`r8b/run_windfield_b.sh`, `r8b/bench_windfield_stream.py`:
broker and client on node 0, inference endpoint node 1, four learning
endpoints, all dragon_native; one session; 1 Hz stream per twin, the 1 Hz
read-only probe and the stream-path Sink) on ve8c (`a64effc`), compression
orbit's default (`auto`). Per repeat (a fresh broker and endpoints), first
`--shared-stream on` (the default), then `off`, each at N = 64, 96, 128,
and 160 only if 128 held (`--run-all-to 128`; 128 broke everywhere, so no
160). 2 repeats.

**Decision (budget):** 60 s per point after a 20 s warm-up, not B2's 120 s
after 40 s. At N >= 64 the pool is warm within seconds (2 x N tasks/s
against 128 workers; B4); 60 s still gives >= 3,840 stream samples per
point. B2's length would have needed about 5 node-h, twice C1's cap.

| shared | twins | rep | probe p50 / p99 ms | stream p50 / p99 / max ms | worst twin p99 | stream answers | burst period / makespan s | update p50 s | broker / endpoint CPU % | build s | participants | create errors | break |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| on | 64 | r1 | 48 / 648 | 51 / 652 / 840 | 754 | 3835 of 3840 | 16.0 / 0.49 | 1.05 | 80 / 224 | 3.4 | 1 | 0 | – |
| on | 64 | r2 | 47 / 604 | 49 / 612 / 883 | 744 | 3838 of 3840 | 16.0 / 0.50 | 1.07 | 82 / 225 | 3.4 | 1 | 0 | – |
| on | 96 | r1 | 261 / 1,284 | 186 / 1,547 / 1,895 | 1,741 | 5734 of 5760 | 16.0 / 0.80 | 1.05 | 72 / 197 | 3.7 | 1 | 0 | p99 1547 ms |
| on | 96 | r2 | 151 / 1,185 | 114 / 1,137 / 1,374 | 1,227 | 5757 of 5760 | 16.0 / 0.69 | 1.07 | 78 / 209 | 3.8 | 1 | 0 | p99 1137 ms |
| on | 128 | r1 | 369 / 1,922 | 344 / 2,221 / 2,422 | 2,362 | 7676 of 7680 | 16.0 / 0.88 | 1.20 | 83 / 189 | 4.1 | 1 | 0 | p99 2221 ms |
| on | 128 | r2 | 318 / 1,878 | 297 / 2,327 / 2,587 | 2,502 | 7664 of 7680 | 16.0 / 0.96 | 1.27 | 88 / 189 | 4.4 | 1 | 0 | p99 2327 ms |
| off | 64 | r1 | 149 / 1,349 | 63 / 1,365 / 1,929 | 1,572 | 3839 of 3840 | 16.0 / 0.45 | 1.35 | 72 / 212 | 5.4 | 64 | 0 | p99 1365 ms |
| off | 64 | r2 | 84 / 665 | 69 / 688 / 894 | 776 | 3839 of 3840 | 16.0 / 0.48 | 1.07 | 80 / 216 | 5.6 | 64 | 0 | – |
| off | 96 | r1 | 229 / 1,146 | 184 / 1,125 / 1,297 | 1,228 | 5758 of 5760 | 16.0 / 0.57 | 1.15 | 88 / 201 | 7.3 | 96 | 0 | p99 1125 ms |
| off | 96 | r2 | 170 / 1,251 | 167 / 1,263 / 1,491 | 1,380 | 5743 of 5760 | 16.0 / 0.72 | 1.16 | 91 / 200 | 8.0 | 96 | 0 | p99 1263 ms |
| off | 128 | r1 | 934 / 1,663 | 1,752 / 2,864 / 3,056 | 2,981 | 7680 of 7680 | 16.0 / 0.67 | 1.62 | 105 / 169 | 10.8 | 128 | 0 | p99 2864 ms |
| off | 128 | r2 | 934 / 1,691 | 1,550 / 2,590 / 2,880 | 2,853 | 7672 of 7680 | 16.0 / 0.68 | 1.60 | 108 / 172 | 11.3 | 128 | 0 | p99 2590 ms |

Round 8b B2 (shared participants did not exist: one per twin): 64 twins p99
750 / 947 ms, 96 twins 1,361 / 1,561 ms (break), 128 twins p50 1,269 ms /
p99 2,746 ms; broker 86-92% / 85-96% / 102%; build 5.2-5.4 / 7.6-8.3 /
10.9 s; one twin failed to initialize at 128 (repeat 2).

- **Sharing does not move the break: 96 twins with either setting**, as in
  B2 (p99 1,137-1,547 ms on, 1,125-1,263 ms off).
- **Sharing makes 64 twins hold:** on, p99 612 and 652 ms (worst twin 744 /
  754); off, one repeat breaks at 64 (p99 1,365 ms, worst twin 1,572) and
  the other holds at 688 ms. B2 (one participant per twin) was 750 / 947.
- **Past the break, sharing cuts the median 5x:** 128 twins, stream p50 297 /
  344 ms on against 1,550 / 1,752 off (probe 318 / 369 against 934).
- **The broker's CPU at 128 twins: 83-88% on, 105-108% off** (B2: 102%), so
  one participant per twin cost the broker about 20 points of a core there.
- **Build time: on 3.4 s (64) to 4.1-4.4 s (128), off 5.4 to 10.8-11.3 s**
  (B2 5.2-10.9): the per-twin participant registration was most of it.
- **No twin failed to initialize** in either setting (B2 lost one at 128);
  0 create errors everywhere, so #65's message was not needed.
- The topology shows 1 `dt_stream.*` participant with sharing on and N with
  it off at every point; bursts every 16.0 s; 0-26 streamed answers missing
  per point (end of window).
- Isolation check empty.

## C3: E1 overhead paths on dragon_native (job 61363587, regular, 2 nodes)

`r8c/run_c3.sh`: `e1-overhead/bench_dt_insitu.py`, `--work-ms 0.58`,
rows bare / investigator / agent / xgf each in its own process in round
3b's rotated orders, 5 repeats; per process 1,000 sequential requests (p50)
and 5 bursts of 500 (median of bursts 2-5). L: harness under `dragon -s`,
local dragon_native pool (one worker per physical core), stream through
the job's broker (R8-1's way). O: ORBIT cross-node, a Dragon endpoint on
node 1. R: through `radical.3:8010` (default credentials read only; WAN
connect median 0.172 s), a Dragon endpoint on node 1 registered there,
client on node 0, c = 1, 100 requests, three rows in one process (U3's
way). S: `s3/s3_service.py` (`E5_BACKEND=dragon_native`), a twin in
radical.3's DT plugin with its engine on that endpoint. Every rc 0;
isolation check empty. Table `results/r8c/c3/c3-table.md` (`r8c/c3_table.py`).

**Decision:** U2 ran c = 50 (local) / c = 1 (ORBIT) runs for p50 and
separate c = 500 runs for bursts; every run measures its sequential p50
first anyway, so C3 runs c = 500 only and takes both from it (half the
runs).

## p50 per request, ms (median of repeats, min-max)

| path | row | dragon_native (r8c) | round 3b (concurrent pool / endpoint) |
|---|---|---|---|
| local | bare | 1.57 (1.48-1.58) | 0.58 (0.58-0.59) |
| local | investigator | 1.59 (1.57-1.59) | 0.59 (0.59-0.65) |
| local | agent | 1.56 (1.54-1.60) | 0.60 (0.59-0.61) |
| local | xgf | 1.84 (1.82-1.87) | 0.87 (0.86-0.88) |
| ORBIT cross-node | bare | 3.80 (3.73-3.91) | 2.96 (2.83-3.14) |
| ORBIT cross-node | investigator | 3.77 (3.67-3.83) | 2.87 (2.82-2.96) |
| ORBIT cross-node | agent | 3.81 (3.69-3.93) | 3.01 (2.70-3.36) |
| ORBIT cross-node | xgf | 4.09 (4.00-4.17) | 3.22 (2.96-3.67) |
| radical.3 client | bare | 350.11 (345.73-357.72) | 353.91 (351.73-359.33) |
| radical.3 client | investigator | 350.13 (345.67-357.64) | 353.98 (351.62-359.40) |
| radical.3 client | agent | 350.25 (345.66-357.71) | 353.85 (351.73-359.29) |
| radical.3 service | bare (twin in the broker's dt plugin) | 516.47 (516.20-516.48) | 346.37 (346.18-346.43) |

## throughput under bursts of 500, req/s (per run median of bursts 2-5; median of repeats, min-max)

| path | row | dragon_native (r8c) | round 3b |
|---|---|---|---|
| local | bare | 3,082 (2,863-3,346) | 3,672 (3,512-3,768) |
| local | investigator | 2,801 (2,739-2,958) | 3,462 (3,378-3,527) |
| local | agent | 2,748 (2,689-2,920) | 3,025 (2,987-3,232) |
| local | xgf | 2,062 (1,992-2,245) | 2,506 (2,465-2,622) |
| ORBIT cross-node | bare | 1,145 (1,055-1,179) | 1,064 (1,030-1,124) |
| ORBIT cross-node | investigator | 1,068 (1,042-1,085) | 1,035 (963-1,084) |
| ORBIT cross-node | agent | 1,024 (1,001-1,094) | 1,006 (951-1,055) |
| ORBIT cross-node | xgf | 953 (897-990) | 967 (904-984) |

Service: session + twin 2.90 s (S3 1.51), reattach 10/10 in 1.07 s (S3 10/10 in 1.06 s), first answer after reattach 1.75 s (S3 1.59).

- **Caveat on p50, local and ORBIT:** the page asks for a "0.58 ms task",
  so C3 adds 0.58 ms of CPU per task (`--work-ms 0.58`, R8-1's reading of
  E1's cost). Round 3b's runs had no `--work-ms` (added in round 8): their
  tasks were no-ops, and 0.58 ms was the whole local request. So the r8c
  local p50 (1.57 ms) carries the 0.58 ms task plus about 1.0 ms, against
  0.58 ms total in 3b; through ORBIT 3.80 against 2.96 ms (about 0.25 ms
  more after the task). The DT rows stay within 0.05 ms of bare in every
  path, as before; xgf costs 0.27-0.30 ms more than bare. **Open question:
  does the figure want the no-op task (round 3b's) or 0.58 ms of CPU?**
- **Throughput under bursts:** through ORBIT dragon_native matches or beats
  3b (bare 1,145 against 1,064, the DT rows 1,024-1,068 against
  1,006-1,035); locally it is 10-20% lower (bare 3,082 against 3,672),
  partly the 0.58 ms of CPU per task (500 x 0.58 ms on the pool).
- **radical.3 client:** 350.1 ms p50 for every row (3b 353.9), the WAN.
- **Service row: 516 ms p50 against S3's 346 ms**, steady in all three
  repeats (516.2-516.5 ms; min 504 ms): +170 ms, about one more WAN round
  trip (connect time 0.172 s) per request than S3 (concurrent backend,
  2026-11-07). Session plus twin 2.9 s (S3 1.5 s); reattach 10/10 in 1.07
  s (1.06), first answer after reattach 1.75 s (1.59). Not investigated:
  whether the dragon_native path from the broker's DT plugin to a remote
  endpoint adds a round trip (a task-state event or result fetch) that the
  concurrent path batches. Open question.

## C4: E4 updates on dragon_native (job 61363679, regular, 2 nodes)

`r8c/run_c4.sh`: (a) `bench_swap.py` c = 1 / 50, 20 swaps 0.5 s apart,
5 repeats, local (under `dragon -s`, new `--local-backend dragon_native
--stream-broker`, pool of one worker per physical core: **decision**, the
stack's default instead of the original pool of 8) and through ORBIT to a
Dragon endpoint; (b) `bench_model_update.py` intervals 1 / 0.1 / 0.01 s,
**10 s per interval** (decision: the original 20 s, halved for the budget;
10-500 versions per interval), local and ORBIT 5 repeats, radical.3 3
repeats (S2 had 3); (c) `bench_publish.py` rates 0 / 1 / 10 / 100, 10 s
each, c = 1 and c = 50, 5 repeats, local. Every rc 0; isolation check
empty. Table `results/r8c/c4/c4-table.md` (`r8c/c4_table.py`).

## (a) swap a running investigator: to the first answer from the new one, p50 ms

| config | dragon_native (r8c) | round 3 T5 |
|---|---|---|
| local c=1 | 1.84 (1.79-1.96) | 0.77 (0.74-1.12) |
| local c=50 | 27.10 (23.74-30.71) | 16.51 (16.17-17.21) |
| ORBIT c=1 | 5.11 (4.90-5.35) | 5.12 (4.16-6.05) |
| ORBIT c=50 | 74.84 (62.49-76.48) | 169.61 (163.89-179.83) |

## (b) a new model, publish to first answer that uses it, p50 ms (intervals pooled)

| path | dragon_native (r8c) | original | versions seen (r8c) |
|---|---|---|---|
| local | 1.83 (1.58-1.94) | 0.66 (0.63-1.01) | 1.0s: 10/10; 0.1s: 100/100; 0.01s: 500/500 |
| ORBIT | 4.95 (4.61-6.09) | 7.07 (5.25-8.21) | 1.0s: 10/10; 0.1s: 100/100; 0.01s: 487/500 |
| radical.3 (WAN) | 521.80 (476.22-547.43) | 517.28 (506.33-546.62) | 1.0s: 10/10; 0.1s: 29/100; 0.01s: 15/500 |

## (c) inference throughput while publishing models, ratio to none (median of repeats, min-max)

| concurrency | rate /s | dragon_native (r8c) | round 3 (T4 c=1, T5 dip c=50) |
|---|---|---|---|
| c=1 | 1 | 1.02 (1.00-1.02) | 0.97 (0.95-1.01) |
| c=1 | 10 | 1.02 (1.01-1.03) | 0.98 (0.96-1.01) |
| c=1 | 100 | 1.04 (1.02-1.06) | 0.98 (0.96-0.98) |
| c=1 | 0 (req/s) | 1,063 (1,013-1,088) | 1,675 (1,669-1,794) |
| c=50 | 1 | 1.00 (0.95-1.08) | 0.99 (0.94-0.99) |
| c=50 | 10 | 1.05 (0.93-1.16) | 0.94 (0.94-1.00) |
| c=50 | 100 | 1.07 (0.93-1.15) | 0.96 (0.92-0.97) |
| c=50 | 0 (req/s) | 2,776 (2,724-3,068) | 3,063 (2,927-3,099) |

- **Swap through ORBIT at c = 50 is 2.3x faster on dragon_native** (75
  against 170 ms); at c = 1 it is unchanged (5.1 ms). Locally the swap
  takes 1.8 ms (c = 1) and 27 ms (c = 50) against 0.8 and 16.5 ms: the
  same ~1 ms local per-task cost as C3's local rows.
- **Publish to first use:** locally 1.8 ms (0.7), through ORBIT 5.0 ms
  (7.1), through radical.3 522 ms (517). Every version is seen locally
  and through ORBIT (ORBIT at 10 ms intervals 487 of 500); through
  radical.3 a 350 ms inference sees 29 of 100 versions at 100 ms intervals
  and 15 of 500 at 10 ms, as expected (newer versions overtake older ones).
- **Publishing models costs inference nothing**: at 1, 10 and 100 models
  per second the throughput ratio to none is 1.00-1.07 (round 3:
  0.94-0.99). The no-publish baseline is lower locally on dragon_native
  (c = 1: 1,063 against 1,675 req/s; c = 50: 2,776 against 3,063), the
  per-task cost again.

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

## Close-out (2026-11-15)

- C0-C6 done; C1 at 60 s per point after 20 s warm-up and C4's updates at 10
  s per interval (budget, see the phases); C5 once (pure stream path, per
  the page). **4.78 of 6 node-h** on m5290 (ledger above). No allocation
  and no Dragon runtime left (every run ends with `dragon-cleanup` on its
  nodes; `squeue` shows only SwarmSlicer's own job). Every ORBIT job's
  isolation check (`results/r8c/*/orbit-isolation-check-*.txt`) is empty.
- Provenance in every new JSON: commits (`packages`), backend, venv,
  `ws_compression` (orbit's default, `auto`), shared stream (`--shared-stream`
  or `stack default`), online-run log level.

### For the paper

- **#66 (one stream participant per session)** does not move WindField's
  break (96 twins per experiment), but it makes 64 twins hold reliably
  (p99 612-652 ms), cuts the median past the break 5x (128 twins: 0.3
  against 1.6-1.8 s), takes about 20 points of a core off the broker at
  128 twins and cuts the 128-twin build from 11 s to 4 s; no twin failed to
  initialize.
- The no-op closed loop is unchanged (800-860 req/s, 1,024 twins built in
  25 s).
- E1 on dragon_native: through ORBIT the DT rows cost nothing measurable
  and burst throughput matches round 3b; the redrawn figure's p50 includes
  a 0.58 ms CPU task that round 3b's did not (see C3).
- E4 on dragon_native: swap through ORBIT at c = 50 is 2.3x faster (75
  against 170 ms); publish to first use 1.8 ms local, 5 ms ORBIT, 522 ms
  WAN; publishing up to 100 models/s costs inference nothing.
- Inputs per twin: pure stream path, no engine involved; joins as round 3,
  agents 1.5-5x faster than round 3 at small M.
- A twin build's verbs cost about 9 ms per twin; its first answer (about
  0.2 s) is cold pool workers.

### Open questions for Andre

1. **The E1 paths figure's task:** C3 used `--work-ms 0.58` (the page's
   "0.58 ms task", R8-1's reading). Round 3b's runs had no-op tasks, where
   0.58 ms was the whole local request. Should the redrawn figure use a
   no-op task (like for like with 3b's bars) or keep 0.58 ms of CPU?
2. **The service row is 170 ms slower on dragon_native** (516 against S3's
   346 ms per request, about one WAN round trip more), while the client
   rows through radical.3 are unchanged (350 ms). Does the broker-side DT
   plugin's path to a remote dragon_native endpoint add a round trip (a
   state event, a result fetch) that the concurrent backend did not?
3. **Local dragon_native costs about 1 ms more per request than the local
   process pool** (C3 local p50 1.57 against 0.58 ms with the task, swap
   1.8 against 0.8 ms, no-publish throughput 1,063 against 1,675 req/s at
   c = 1). The figures' local bars will move; is that the paper's story
   (dragon_native is the default) or should local stay on the pool?
4. With #66, 64 WindField twins hold and 96 break: is the paper's number
   "64 twins per experiment under 1 s p99" (shared stream), with the 128
   point as the overload case?

- Merged into `paper/dtaas` as `f090278` (pushed); unit tests on the merged
  tree: 262 passed (`PYTHONPATH=src`, ve8c). No PRs.
