# Perlmutter round 8b: broker cost (2026-11-14)

Unattended session, page https://claude.ai/artifact/1qEnoff1tx1AtRP9JCNhLi.
Rules: the round 1-2c page's autonomy contract, session mechanics, ORBIT
isolation and known traps; round 8's terms (project, experiment = one DT
session, twins, clients, phases), setup and harness. Branch
`exp/pm-round8b-20261114` off `a3e64c7`. Work dir `/pscratch/sd/m/merzky/dt-pm8`
(round 8's). Budget 6 CPU node-h on m5290.

## Ledger

| job | phase | account | nodes | elapsed | node-h | total |
|---|---|---|---|---|---|---|
| 61292050 | B1 | m5290 | 3 | 00:11:32 | 0.577 | 0.58 |
| 61292518 | smoke (B2/B4 harness) | m5290 | 3 | 00:02:20 | 0.117 | 0.69 |
| 61292521 | B3 | m5290 | 3 | 00:03:57 | 0.198 | 0.89 |
| 61292738 | diagnostic (smoke latency) | m5290 | 3 | 00:03:45 | 0.188 | 1.08 |
| 61292923 | B3 endpoint profile | m5290 | 3 | 00:02:07 | 0.106 | 1.18 |

## B0: setup (2026-11-14)

- `memo sync`; read the contract page (autonomy contract, session mechanics,
  ORBIT isolation, known traps), round 8's page and the round 8b page.
- Branch `exp/pm-round8b-20261114` off `a3e64c7` (paper/dtaas: round 8's
  `fdf9a5b` plus #63 `a152b04` and the STACK.md note).
- `ve8b`: `DT_PYTHON=python3.12 DT_REF=a3e64c7f14b803c03638301e349a2b7b846594d2
  RHAPSODY_EXTRAS=telemetry,dragon deploy/install.sh endpoint dt-pm8/ve8b`
  (cray-python 3.12.12); log `dt-pm8/logs/install-ve8b.log`. Same versions as
  ve8 (asyncflow 0.6.0, rhapsody 0.6.0, orbit 0.8.0, ROSE 0.3.0, dragonhpc
  0.15.0); `pip check` clean. `digitaltwin.runtime` logs `Online run` at
  debug in ve8b and at info in ve8 (line 1533). py-spy 0.4.3 installed into
  ve8b (recorded tool; ve8 has none, round 8 used ve6's).
- `r8b/env-r8b.sh`: round 8's env with `VE` selectable (default ve8b) and
  `RADICAL_ORBIT_WS_COMPRESSION` (default `off`), exported to every process.
- Provenance (`r8/prov.py`): adds `venv`, `ws_compression` and
  `online_run_log_level` (read from the installed `digitaltwin.runtime`).
- `r8b/ws_check.py`: connects a runtime to a broker and prints the
  negotiated WebSocket extensions (permessage-deflate or none).
- `r8/run_engine.sh`: `ROWS` and `WS_CHECK` knobs (default behaviour
  unchanged). With `WS_CHECK` it runs `ws_check.py` once per repeat and
  counts INFO `Online run` lines in the broker log: that is the B0 check
  "a broker on ve8b logs no Online run at INFO", done in B1's allocation
  (no benchmarks on login nodes).
- **Finding, compression in round 8:** orbit's default is
  `ws_compression=auto`: a runtime offers deflate only if a plain TCP
  connect to the broker takes >= 10 ms. Every round 8 in-cluster log line
  reads `connect 0.4-0.6 ms (threshold 10.0 ms) -> deflate off` (R8-2
  brokers: 33 of 33 lines; the broker profile 61264017: off; endpoints: off).
  So round 8 ran with **no** compression inside the cluster, and the page's
  "compression on" cells are a counterfactual. **Decision:** B1's "on"
  cells force `RADICAL_ORBIT_WS_COMPRESSION=on`; "round 8 as it was" is
  ve8 with auto, which equals ve8 with off (verified by the log line), so
  the 2x2 is venv {ve8, ve8b} x compression {on, off}. The 10.6% deflate
  in the SwarmSlicer phase 6 attempt-2 broker profile was not reproduced
  in that phase's final run either; its cause stays open.

## B1: the ceiling, closed loop (job 61292050, debug, 3 nodes)

R8-2's setup (`r8/run_engine.sh`, row `noop-one`, 15 s closed loop per
point): broker on node 0, one Dragon endpoint (`dragon_native`, whole node)
on node 1, the client `r8/bench_engine.py` on node 2; a fresh broker and
endpoint per repeat; all cells in one allocation on the same three nodes
(`r8b/run_b1.sh`). Table: `r8b/b1_table.py results/r8b/b1`.

- Per repeat, `r8b/ws_check.py` confirmed the negotiated extension:
  `PerMessageDeflate` with `on`, none with `off`.
- B0 check: the broker log has 12,686-13,480 INFO `Online run` lines per
  ve8 repeat and **0** per ve8b repeat.
- Isolation check empty after every cell.

| cell | twins | rep | req/s | p50 ms | p99 ms | worst twin p99 ms | broker CPU % | endpoint CPU % |
|---|---|---|---|---|---|---|---|---|
| round 8 (ve8), compression on | 256 | 1 | 779.9 | 312 | 506 | 606 | 73 | 169 |
| round 8 (ve8), compression on | 256 | 2 | 803.4 | 303 | 487 | 565 | 71 | 170 |
| log fix (ve8b), compression on | 256 | 1 | 795.7 | 304 | 487 | 524 | 64 | 170 |
| log fix (ve8b), compression on | 256 | 2 | 832.6 | 295 | 453 | 507 | 74 | 170 |
| round 8 (ve8), compression off | 256 | 1 | 807.4 | 301 | 499 | 641 | 65 | 168 |
| round 8 (ve8), compression off | 256 | 2 | 836.9 | 293 | 434 | 510 | 66 | 168 |
| both (ve8b, off) | 256 | 1 | 815.8 | 300 | 449 | 487 | 57 | 169 |
| both (ve8b, off) | 256 | 2 | 841.3 | 290 | 445 | 498 | 58 | 171 |
| both (ve8b, off) | 1024 | 1 | 839.1 | 1,182 | 1,369 | 1,458 | 64 | 156 |
| both (ve8b, off) | 1024 | 2 | 847.6 | 1,152 | 1,372 | 1,534 | 64 | 155 |

Round 8: 845 req/s at 256 (824-848), 844 at 1,024 (785-847), broker CPU
65% and 69%.

- **Neither fix moves the ceiling.** At 256 twins the four cells span
  780-841 req/s; the spread between the two repeats of one cell (24-37
  req/s) is as large as the differences between cells. "Both" at 1,024:
  839 and 848, round 8's 844.
- **Both fixes do cut the broker's CPU:** 71-73% (round 8 venv,
  compression on) to 57-58% (both), with the log fix about 5-9 points
  and compression about 6-8 points. Forced compression costs CPU but not
  throughput: the broker has spare CPU at the ceiling.
- **So the broker's CPU is not what holds the ceiling.** The endpoint
  process runs at 155-171% (68 threads; round 8's endpoint numbers came
  from the Dragon launcher, the sampler bug, so this is the first correct
  endpoint CPU at the ceiling). B3 looks at both.

## B3: broker profile after the fixes (job 61292521, debug, 3 nodes)

Round 8's `r8/run_broker_profile.sh` (256 twins, no-op, 60 s, py-spy 20 Hz
`--idle --nonblocking` for 30 s from 5 s into the load, and the frame
counter) on ve8b, compression off. Plain 816.5 req/s, profiled 810.5
(p50 298 ms, p99 602-611 ms). Summary `results/r8b/b3/top-broker-61292521.md`.

- 16,544 samples, 755 busy; 484 of them are the frame counter's own
  `_dump` thread (as in round 8, not counted). **271 busy samples of the
  event loop's 600 in 30 s: about 45% busy** (round 8: 312, about 52%).
- Breakdown of those 271 (round 8 in brackets): asyncio event loop
  (socket writes, self-pipe wake-ups, callbacks) 153, **56%** (47%);
  radical.orbit 47, 17% (17%); serialization 16, 6%; DT service 16, 6%
  (8%); websockets and TLS 14, 5% (4%); asyncflow 12, 4% (3%); rhapsody 7,
  3%; **logging: gone** (13%). Top self frames: `_SelectorSocketTransport.write`
  (selector_events.py:1075) 52, `_write_to_self` (:152) 31, `wire.decode`
  (digitaltwin/service/wire.py:135) 11, `Handle._run` 11.
- **Next largest cost in the broker:** asyncio's socket writes and the
  self-pipe wake-ups (`_write_to_self`, from `run_coroutine_threadsafe`:
  work handed to the loop from other threads), about 30% of its busy time
  between them.
- **But the broker idles more than half the time at the ceiling**, which
  together with B1 means the ~830 req/s limit sits elsewhere. Follow-up in
  the same B3 setup: a py-spy of the endpoint per thread (job below).

### B3 follow-up: the endpoint per thread (job 61292923, debug, 3 nodes)

Same setup, `RUNS_LIST=profiled PROFILE_EP=1` (new knob in
`r8/run_broker_profile.sh`): in the same 30 s window, `top -H`, a py-spy
dump and `py-spy record --rate 20 --idle --nonblocking --threads` on the
endpoint process (found with `r8b/pid_of.sh`, which skips the Dragon
launcher). 824.5 req/s, so profiling both does not lower the rate.
Summary `results/r8b/b3/top-endpoint-threads-61292923.md`.

| endpoint thread | busy share of 463 samples | top busy frames |
|---|---|---|
| `orbit-work` | 52% | `dragon.native.Queue.put` (queue.py:626) 20% of its busy samples, rhapsody `submit_tasks` (dragon_native.py:1630) 6%, JSON encode 6%, cloudpickle 4% |
| `dragon_native_results` | 17% | rhapsody `_handle_messages` (dragon_native.py:691: unpickling results) 80% |
| `orbit-transport` | 11% | socket and SSL writes |
| `Thread-4 (_exq_monitor)` | 4% in Python, but **62% CPU in `top -H`** | Dragon `ProcessGroup._exq_monitor` (process_group.py:2209) in `Queue.poll` -> `_fli.poll` with a 0.1 s timeout: the CPU is spent in C inside the poll |

- **No single thread is saturated at the ceiling**: broker loop about 45%,
  endpoint work loop 52%. So the ~830 req/s closed-loop limit is not a
  saturated CPU in either process; it looks like latency per hop (four
  ORBIT hops and two Dragon queue hops per request) at 256 requests in
  flight. Not proven; open question.
- **Correction to round 8's write-up:** round 8 called the broker's one
  event loop "the limit"; its own profile had the loop busy 312 of 600
  samples (52%), and B1/B3 show the broker at 57-74% CPU with throughput
  unchanged when its CPU drops. The limit is not the broker's CPU.
- `_exq_monitor`: Dragon starts it for a ProcessGroup without
  `ignore_error_on_exit`; rhapsody's executable groups pass
  `ignore_error_on_exit=True` (dragon_native.py:1207), the worker pool
  apparently does not. Lead for B4's "steady 133-140%" question.

## Stack switch to 63d8692 (#64) (2026-11-14, during B3)

The laptop updated the round 8b page while B1/B3 ran: stack `63d8692`
(#63 plus **#64, queries are read-only**: `get_inference` fires no
ON_INPUT); rebuild `ve8b`; merge `origin/paper/dtaas` into the branch; B2
keeps the 1 Hz probe as the answer-time measurement, records the stream
path too, and drops the old-harness N = 64 rerun.

- Merged `origin/paper/dtaas` (`63d8692`) into the branch: `8a5084f`.
- Old venv kept as `dt-pm8/ve8b-a3e64c7` (B1, B3 and the smokes ran on it;
  their provenance records digitaltwin `a3e64c7` and venv `/ve8b`). New
  `ve8b` at `63d86929`, same recipe, log `logs/install-ve8b-63d8692.log`,
  `pip check` clean, py-spy 0.4.3 added.
- B1 is labelled "measured on a3e64c7": R8-2's investigator subscribes to
  no ON_INPUT, so #64 does not change that path.
- My B2 harness already kept probes away from the investigators (a probe
  marker); with #64 that is redundant and harmless. Per the page, B2's
  probe now runs at 1 Hz.

## Smoke tests of the B2/B4 harness (jobs 61292518, 61292738)

- 61292518 (3 nodes, one learning endpoint, ve8b a3e64c7): the stream
  bench works: 40 of 40 streamed answers reached the sink, the burst
  period read 16.0 s, every record lands in the JSON. **But every answer
  took about 177 ms more than its task** (PINN 197 ms, FNO 296 ms), in
  both harnesses, until about 30 s after the session (and its new
  128-worker `dragon_native` pool) was created; then 32 ms (PINN) and
  134 ms (FNO). The second row, with a fresh session and 5 s warm-up,
  stayed at 197 ms throughout.
- 61292738 (diagnostic): round 8's harness at N = 1, 25 s warm-up, 30 s,
  once without and once with py-spy attached to the inference endpoint
  first: p50 35.5 and 36.3 ms, p99 304 and 299 ms (round 8: 36 / 301).
  So py-spy is not the cause; **a new session's pool adds about 177 ms per
  task for its first ~30 s.** Decision: B2 and B4 warm up 40 s per point
  (each point is a new session). Described, not investigated further.

## Decisions for B2 and B4 (budget)

1.18 node-h used. B2 per the page (2 repeats x 5 points x >= 5 min on 6
nodes) would need about 6.4 node-h alone. **B2:** 2 repeats, 120 s per
point after 40 s warm-up (>= 1,920 probe and stream samples per point at
N >= 16, >= 7 burst periods per investigator), about 3.5 node-h. **B4:**
5 min per row as the page asks, on 3 nodes (`NLEARN=1`): a single twin
uses only `learning_0`, so one learning endpoint is round 8's N = 1
setup. The endpoint dump moves into the first row (25 s in, the session
and its pool exist, only the 1 Hz stream runs), with `top -H`, a Python
and a `--native` dump and a 20 s thread record.
