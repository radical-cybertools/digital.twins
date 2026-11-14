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
| 61293158 | B4 | m5290 | 3 | 00:18:13 | 0.911 | 2.09 |
| 61293157 | B2 | m5290 | 6 | 00:29:00 | 2.900 | 4.99 |

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

## B4: the 300 ms tail at one twin (job 61293158, debug, 3 nodes, 63d8692)

Round 8's harness (`r8/bench_windfield_scale.py`, one session, 1 Hz probe,
1 Hz stream; on 63d8692 the probe no longer feeds the investigators), N = 1,
`--records`, 5 min after a 40 s warm-up per row, one learning endpoint
(`NLEARN=1`; one twin uses only `learning_0`). Three rows in one
allocation, each a new session: `b4base`, `b4noburst` (`--every 1000000`),
`b4nostream` (`--no-stream`). Tables `results/r8b/b4/b4-tables.md`
(`r8b/b4_table.py`).

| row | probes | p50 ms | p99 ms (interpolated) | max ms | PINN p50 / max | FNO p50 / max |
|---|---|---|---|---|---|---|
| b4base | 300 | 33.8 | 136.1 | 143.4 | 33.5 / 143.4 | 133.8 / 137.2 |
| b4noburst | 300 | 34.0 | 136.5 | 137.5 | 33.6 / 38.0 | 133.9 / 137.5 |
| b4nostream | 300 | 35.1 | 225.9 | 305.6 | 34.7 / 225.2 | 134.9 / 305.6 |

- b4base saw 40 burst starts (3 investigators, every 16 s: #64 works).
  The slowest probes are FNO probes at 135-137 ms at every distance from a
  burst start (-6 to +8 s). One PINN probe at 143 ms, 2.3 s before a burst.
  **Bursts do not make the tail**: removing them (b4noburst) leaves p99
  and max where they are.
- The split around the worker-side `t_task`: submit + run 30 ms (PINN) and
  130 ms (FNO), return path 3-4 ms in every row and in every slow probe.
- **The ~300 ms answers appear only in b4nostream, and only in the first
  20 s of its load window** (40-60 s after the session was created): FNO
  294-306 ms, PINN 195-225 ms, i.e. **+165 ms per answer**, all of it on
  the submit/run side. After that, the row is like the others.
- **Cause, with evidence:** a new session's `dragon_native` pool (128
  workers) charges about 165 ms the first time each worker runs a task.
  With the stream off, the twin submits about 2 inference tasks per
  second (selector plus surrogate per probe), so the 128 workers are all
  warm after about 64 s: 40 s warm-up plus about 20 s into the load, as
  seen. With the stream on (about 4 tasks/s) they are warm before the
  40 s warm-up ends, so b4base and b4noburst show no slow answer. The
  smoke tests showed the same: 2 twins with the stream (about 5 tasks/s)
  turned normal about 30 s after session creation (61292518).
- **Round 8's "p99" of 301 ms at N = 1** (60 probes, `xs[int(0.99*n)]` =
  the slowest) fits this: round 8 warmed up 25 s, about 100 tasks, short
  of 128, so a probe or two in the window landed on a cold worker; an FNO
  probe (134 ms) on a cold worker is about 300 ms. Its p50 (36 ms) matches
  B4's 34 ms.
- **The endpoint's steady 133-140% CPU** comes with the session's pool,
  not with load: the idle endpoint without a session is at 0% (smoke
  61292518, `top -H` all threads 0.0); in B4 it jumps to 134-137% within
  4 s of the first session and stays at 128-141% through all three rows,
  stream or no stream, bursts or none. In both the Python and the
  `--native` dump (`endpoint-session-dump-*.txt`, 25 s into the first row)
  the only thread py-spy calls active is Dragon's
  `ProcessGroup._exq_monitor` (process_group.py:2209), in `Queue.poll`
  -> `pydragon_fli.c` `poll` -> `pthread_cond_timedwait`; B3's `top -H`
  put that thread at 62% of a core. So most of the steady CPU is the pool's
  exception-queue monitor looping on short timed waits (0.1 s patience
  per poll in Python; the C loop below it is not visible). The remaining
  ~70% is not attributed: no per-thread CPU at idle was captured (the
  `top -H` lines were cut by `tail`). Described, not fixed.

## B2: WindField twins per experiment (job 61293157, regular, 6 nodes, 63d8692)

R8-C's setup, both fixes (ve8b 63d8692, compression off): broker and
client on node 0, inference endpoint on node 1, four learning endpoints;
all twins in one DT session; 1 Hz stream per twin; corrected harness
`r8b/bench_windfield_stream.py` (`r8b/run_windfield_b.sh`, row `b2`):
- the 1 Hz probe as the answer-time measurement (marked, and since #64
  read-only, so it feeds no investigator);
- the **stream path** (reading published -> the agent's answer at the
  twin's Sink investigator, `r8b/r8b_components.py`) on every answer;
- 120 s per point after a 40 s warm-up (budget, see "Decisions");
- p99 interpolated, max separate, every record in the JSON.
2 repeats, a fresh broker and endpoints per repeat. Table
`results/r8b/b2/b2-table.md` (`r8b/b2_table.py`).

| twins | rep | probe p50 / p99 / max ms | stream p50 / p99 / max ms | worst twin p99 (stream) | stream answers | burst period s | burst makespan s | update delay p50 / max s | broker CPU % | endpoint CPU % | break |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | 1 | 32 / 140 / 216 | 34 / 141 / 235 | 193 | 1,917 of 1,920 | 16.0 | 0.29 | 0.85 / 14.9 | 30 | 216 | – |
| 16 | 2 | 34 / 145 / 262 | 34 / 144 / 274 | 164 | 1,919 of 1,920 | 16.0 | 0.30 | 0.84 / 15.8 | 34 | 212 | – |
| 32 | 1 | 35 / 214 / 376 | 37 / 234 / 442 | 319 | 3,840 of 3,840 | 16.0 | 0.31 | 0.83 / 15.8 | 54 | 226 | – |
| 32 | 2 | 39 / 272 / 423 | 39 / 275 / 427 | 326 | 3,839 of 3,840 | 16.0 | 0.32 | 0.80 / 14.9 | 58 | 223 | – |
| 64 | 1 | 50 / 769 / 1,066 | 52 / 750 / 1,100 | 920 | 7,676 of 7,680 | 16.0 | 0.48 | 1.02 / 15.5 | 86 | 221 | – |
| 64 | 2 | 58 / 951 / 1,195 | 56 / 947 / 1,171 | 1,002 | 7,673 of 7,680 | 16.0 | 0.54 | 1.03 / 15.9 | 92 | 219 | – |
| 96 | 1 | 229 / 1,405 / 1,595 | 202 / 1,361 / 1,867 | 1,545 | 11,469 of 11,520 | 16.0 | 0.76 | 1.09 / 16.2 | 85 | 196 | p99 1,361 ms |
| 96 | 2 | 201 / 1,450 / 1,679 | 202 / 1,561 / 1,812 | 1,734 | 11,518 of 11,520 | 16.0 | 0.69 | 1.22 / 16.5 | 96 | 195 | p99 1,561 ms |
| 128 | 1 | 719 / 1,798 / 2,106 | 1,269 / 2,746 / 3,324 | 3,150 | 15,358 of 15,360 | 16.0 | 0.72 | 1.57 / 17.1 | 102 | 175 | p99 2,746 ms |
| 128 | 2 | – | – | – | – | – | – | – | – | – | creation: 1 twin "failed to initialize: twin initialization exceeded 300.0s" |

Round 8 R8-C (probe feeding the investigators, 8 s bursts, `xs[int(.99n)]`
p99): 16 twins p50 65 / p99 263 ms, 64 twins p50 148 / p99 1,249 (1,034
and 1,464), 128 twins p50 1,288 / p99 2,768; broker 28 / 83 / 113%,
endpoint 193 / 205 / 161%.

- **The break moves from 64 to 96 twins in one experiment.** At 64 twins
  p99 is 750-951 ms (probe and stream agree within 20 ms), the worst
  twin's 920-1,002 ms; at 96 both repeats break (p99 1,361 and 1,561 ms).
- **The investigators burst every 16.0 s** at every N (#64 works);
  bursts take 0.29 s at 16 twins and 0.7-0.8 s from 96 on.
- **The stream path and the probe agree** (p50 within 2-4 ms, p99 within
  about 20 ms up to 96 twins), so in this graph the probe's answer time
  stands for the field's. At 128 the stream path is slower (p50 1,269
  against 719 ms): queued streamed readings wait behind each other.
- **Streamed answers lost:** 0-7 per point up to 64 twins (out of up to
  7,680), 51 at 96 (repeat 1), 2 at 128: readings published near the end of
  the window whose answers had not reached the Sink 3 s after the window.
- **Update delay:** p50 0.8-1.6 s; max 15-17 s, because a model is "seen"
  only when the selector picks its surrogate (80% PINN, 20% FNO, PCR never),
  so an FNO version can wait several readings for its first answer.
- **Broker CPU** rises to 86-92% at 64 twins and 102% at 128: in this
  workload (stream frames, events and tasks) the broker is close to a full
  core at the break, unlike B1's no-op closed loop. The inference endpoint
  stays at 175-226%.
- **Creation failure at 128 (repeat 2):** one twin of 128 failed with
  "twin initialization exceeded 300.0s", though the whole build took
  34.9 s by the client's clock. Described, not investigated (open question).
- With half of round 8's investigator load (16 s bursts) and both fixes,
  the experiment carries 1.5x the twins at the same break criterion.

## Close-out (2026-11-14)

- B0-B4 done. B2 at 120 s per point (not 5 min) and B4 on 3 nodes, both for
  the budget (see "Decisions"). Total **4.99 of 6 node-h** on m5290 (ledger
  above). No allocation left (`squeue` empty), no Dragon runtime: every run
  ends with `dragon-cleanup` on its nodes. Every ORBIT job's isolation check
  (`results/r8b/*/orbit-isolation-check-*.txt`) is empty.
- Provenance in every new JSON: commits (`packages`), backend, venv,
  `ws_compression`, `online_run_log_level`.
- Results measured on `a3e64c7` (before #64): B1, B3 and both smokes;
  B2 and B4 on `63d8692`.

### For the paper

- The two cheap fixes cut the broker's CPU at the ceiling (about 72% ->
  57% of a core) but leave the no-op closed-loop ceiling at 800-850 req/s.
  Neither the broker loop (45% busy) nor the endpoint work loop (52%) is
  saturated there, so round 8's "the broker's event loop is the limit" is
  corrected: the limit is not one saturated CPU.
- In-cluster compression was already off in round 8 (orbit's auto mode).
- WindField: with the query fix (#64) and both fixes, one experiment
  carries 64 twins under 1 s p99 (750-951 ms) and breaks at 96 (round 8:
  broke at 64). At the break the broker is near a full core (86-102%).
- The one-twin tail of round 8 (301 ms) is pool warm-up: about +165 ms on
  each of the 128 workers' first task in a new session.

### Open questions for Andre

1. **The ~830 req/s no-op ceiling**, with no thread saturated in broker or
   endpoint: per-hop latency at 256 in flight (four ORBIT hops, two Dragon
   queue hops per request), or a serial wait somewhere? The same pattern
   showed in SwarmSlicer phase 7 today (ORBIT DDict at about 32k keys/s
   from 16 nodes on with idle work loops). A per-hop timestamp trace would
   tell.
2. **dragon_native first-task cost:** each worker of a new pool costs
   about 165 ms on its first task (128 per session). Pre-warm the pool at
   session start (a no-op per worker) in rhapsody? With one pool per DT
   session, every new experiment pays it.
3. **The endpoint's steady ~135% CPU per session pool**, most of it
   Dragon's `ProcessGroup._exq_monitor` polling the exception queue
   (0.1 s patience, C-level timed waits). With R8-0's ~16 sessions per
   endpoint that is many cores. Report to HPE, or create the pool's group
   with `ignore_error_on_exit` as rhapsody does for executables?
4. **Twin initialization timeout at 128 twins** (B2 repeat 2): "exceeded
   300.0s" while the whole build took 34.9 s by the client's clock. Which
   clock does the 300 s count from?
5. **The broker near a full core at WindField's break** (86-102%) but not
   in the no-op loop: stream frames and events per twin are the extra
   broker work. More than one broker process (round 8's lever) is the next
   step for this workload.
6. The SwarmSlicer phase 6 attempt-2 broker profile with 10.6%
   permessage-deflate is still unexplained (all in-cluster connections
   chose `deflate off` here and in round 8).
