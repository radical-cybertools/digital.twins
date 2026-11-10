# Journal: DT paper Perlmutter round 3 (2026-11-09/10)

Unattended Claude Code session following the round 3 page
(https://claude.ai/artifact/UKBRzfypy6hxU4TWoph9h7); rules from the round 1-2c
page (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn). Branch
`exp/pm-round3-20261110` off `b24b9ab` (digital.twins `paper/dtaas`). Work dir
`/pscratch/sd/m/merzky/dt-pm3`, checkout `digital.twins-r3`. Rounds 2-2c:
`JOURNAL-pm-20261107.md`. Times PST unless marked UTC.

## Node-hour ledger (round 3 budget: 25, CPU, m5290)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 3`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 61056507 | r3-t1 | m5290 | 2 | 00:12:42 | 0.423 | 0.42 | 0.00 |
| 61057674 | r3-t2 | m5290 | 1 | 00:02:55 | 0.049 | 0.47 | 0.00 |
| 61058980 | r3-t1b | m5290 | 2 | 00:05:02 | 0.168 | 0.64 | 0.00 |
| 61059078 | r3-t2b | m5290 | 1 | 00:02:54 | 0.048 | 0.69 | 0.00 |
| 61059793 | r3-t1c | m5290 | 2 | 00:03:44 | 0.124 | 0.81 | 0.00 |
| 61060193 | r3-t3 | m5290 | 2 | 00:09:37 | 0.321 | 1.13 | 0.00 |
| 61060406 | r3-t45r | m5290 | 1 | 00:32:14 | 0.537 | 1.67 | 0.00 |
| 61061603 | r3-t45l | m5290 | 1 | 00:34:31 | 0.575 | 2.25 | 0.00 |
| 61061605 | r3-t45o | m5290 | 3 | 00:07:13 | 0.361 | 2.61 | 0.00 |
| 61061984 | r3-t4c | m5290 | 3 | 00:01:27 | 0.072 | 2.68 | 0.00 |
| 61062231 | r3-t4c2 | m5290 | 3 | 00:21:18 | 1.065 | 3.74 | 0.00 |

## T0: setup (done, 2026-11-09 13:22)

- Started in the existing Perlmutter session (not a fresh tmux one): Andre
  pointed it at the round 3 page after the T1 corrections were made there.
- Clone `digital.twins-r3`, branch `exp/pm-round3-20261110` at `b24b9ab`;
  `git diff --stat 259fa2d b24b9ab -- src deploy` is empty, so 2c's venv
  `ve2c` is reused (no `ve3`). `env3.sh` = `env2c.sh` with the new checkout
  and `D=stack-r3-20261110`.
- `digitaltwin` imports from
  `/pscratch/sd/m/merzky/dt-pm3/ve2c/lib/python3.12/site-packages/digitaltwin/__init__.py`
  (installed, not the checkout); asyncflow 0.6.0, rhapsody-py 0.6.0,
  radical.orbit 0.8.0, py-spy 0.4.3, as in 2c.
- Harness changes, all opt-in, defaults unchanged:
  - `bench_dt_insitu.py --bursts K`: K back-to-back bursts per row;
    `concurrent_s` stays the first, all are in `bursts_s`. For the bimodal
    bare question: is the mode set per process or per burst?
  - `e1-overhead/diag_wire.py`: runs `bench_dt_insitu.py` with the client's
    `EndpointRuntime` instrumented and counts frames and bytes per call,
    by kind, request path and event topic, around each `run_row` (T1-C).
  - `s1/ledger.py 3`: this journal's ledger.

## T1: submitted (2026-11-09 13:50)

`r3/run_t1.sh` (2 nodes, regular, 1:30), job 61056507: A (solo per row and
in-process, c = 50 / 500, 5 repeats with rotated row order, 5 bursts per
run), C (`diag_wire.py`, each row solo, c = 50 / 500), B (py-spy `--idle`
on client and endpoint, `--subprocesses` on the endpoint, one solo run per
row at c = 500, folded and speedscope).

## T1: done (2026-11-09 15:40)

Jobs 61056507 (r3-t1, A/B/C), 61058980 (r3-t1b, decay / per-burst wire /
broker and endpoint py-spy), 61059793 (r3-t1c, endpoint with finished
tasks pruned).  All isolation checks empty.  Write-up: E1 README, "T1".

- A: solo at c=500 the rows are equal (819 / 818 / 764 req/s first burst);
  in one process the throughput decays with every burst, so later rows
  lose (investigator 0.63x, agent 0.44x).  Not a DT cost.
- C: the wire carries the same per call in every row.
- Decay: follows the session's task count (20 bursts: 717 -> 243; the same
  curve with `--tasks 1`, shifted), resets with a new client session.
- Cause: rhapsody's `ConcurrentExecutionBackend` (thread pool) keeps every
  finished asyncio Task alive (`self.tasks[uid]` and `task["future"]`, the
  task dict also kept by the ORBIT rhapsody plugin's session), and every
  task's `asyncio.run()` scans all live Tasks.  Reproduced locally
  (`r3/diag_thread_decay.py`), removed with a harness-side prune; through
  ORBIT with the prune the decay, the in-process row gap and the bimodal
  c=50 bare are gone.
- Decision: no `src/` change (the bug is in rhapsody, outside the page's
  fix scope); no rhapsody branch either -- reported as an open question.
  `fix/pm-orbit-burst` not created.  A is not rerun "with the fix": T1c is
  that rerun with the harness-side prune.
- B (py-spy) mistakes: `run_t1.sh` passed the file extension (`folded`) as
  py-spy's format for the endpoint, so the folded-format half of B had no
  endpoint and its client profiles are import-only; the speedscope half is
  good.  Fixed in `run_t1b.sh`.

## T2: done (2026-11-09 15:30)

Jobs 61057674 (r3-t2, 5 repeats, rows bare / zmq / dt / dt-batched) and
61059078 (r3-t2b, py-spy at window 100 with 100k samples; T2's own
profiles covered 2000 samples, about 0.16 s of the dt row, and show only
imports).  Write-up: E1 README, "T2".

- zmq (the same ZMQ hop, no twin) is 0.86x bare at window 100, dt 0.34x,
  dt-batched (a window per message) 0.84x: round 2's "it is the ZMQ hop" is
  refuted.  The hop is about 4 us per message, the DT adds about 47 us.
- py-spy: no single hot spot; the per-message event path (consumer, gather,
  `_run_component`, `ON_INPUT` task, per-sample in-situ inference).  Design
  cost, measured, no `src/` change.
- The stream API can publish a list as one message; the learner unpacking
  it is harness-side.
- Not committed (kept in `results/r3/` on pscratch): T1's folded client
  profiles (import-only, see above) and T2's py-spy profiles (0.16 s of the
  run); T2b's replace the latter.

## T3: done (2026-11-09 15:55)

Job 61060193 (r3-t3, 2 nodes): local pool 8 (c = 50, 500) and ORBIT
cross-node (c = 1, 50, 500), rows bare / investigator / agent / xgf, each
solo, 5 repeats, 5 bursts.  Isolation check empty.  Write-up: E1 README,
"T3".

- xgf follows xGFabric `devel` `service/src/xgfabric/service/service.py`
  and `service/bin/xgfabric-client.py` (ZMQ request per reading, workload
  per request, result as reply); the CSPOT / input-directory feed is not
  reproducible without the testbed, so the row starts at the service's
  request (decision: page's "measure its message-bus hop alone" applies to
  that feed only).
- xgf is slower than the DT rows: 0.72x / 0.67x bare locally (bursts),
  0.85x / 0.92x through ORBIT, seq p50 +0.3 ms locally, +0.8 ms at c=1
  through ORBIT.  xGFabric cloned into `$W/scratch-xgf` (not committed to).

## T4: done (2026-11-09 16:55)

Jobs 61060406 (E2a / E2b 5 repeats), 61061603 (agents, publish c=1),
61061605 (C failed: broker env), 61061984 (C), 61062231 (C past the
doubled p50, cancelled at N=256).  Isolation checks empty (t4c2's run by
hand after the cancel).  Write-up: E2 README, "Perlmutter round 3".

- A agents: side by side 4000-8000 inputs/s whatever M; chained 2000/s up
  to M=8, 1000/s at M=16; no output lost.  Coarse rate grid: lower bounds.
- B publish: free up to 1000 models/s; "max" (163k/s) starves inference
  to 0.28x.
- C broker: CPU-bound on about one core, 250-290 req/s aggregate from N=4,
  p50 6.6 ms at N=1, 233 ms at N=64; at N=256 creation stalls (keepalive
  timeouts), no error.  Decision: N=256 counted as "fails to create",
  cancelled after 21 min rather than waiting for the 30-min limit.
- D: E2a / E2b numbers in line with round 2 (see table file).

## T5: done (2026-11-09 16:55)

Jobs 61061603 (swap and dip, local), 61061605 (swap and P7 cross-node),
61060406 (P7 local).  Write-up: E4 README, "Perlmutter round 3".

- A swap: 200 swaps per layout and c, none missed; turnaround p50 0.77 ms
  local / 5.1 ms cross-node at c=1, 16.5 / 170 ms at c=50 (the in-flight
  queue).  Decision: agent-side `start_investigator` instead of the page's
  twin-level `add_investigator` (the selector only sees the agent's own).
- B dip: publishing up to 100 models/s costs at most 6% req/s, 5% p50.
- C P7: 0.6-0.7 ms local, 7-7.5 ms cross-node from publish to first answer.

## Close-out (round 3)

All phases done; nothing skipped.  Node-hours: 3.74 of 25 (m5290; table
above).  No allocation left running.  Every ORBIT job's isolation check
is empty (t1, t1b, t1c, t3, t45o, t4c, t4c2).  No `src/` change, so no
fix branch (`fix/pm-orbit-burst` not created).  Branch
`exp/pm-round3-20261110` pushed.

Open questions for Andre:

1. rhapsody `ConcurrentExecutionBackend` (thread pool) keeps every
   finished asyncio Task alive (`self.tasks[uid]`, `task["future"]`, and
   the task dict in the ORBIT rhapsody plugin's session `_tasks`), so
   every task's `asyncio.run()` gets slower with the session's age (T1).
   That is what the paper's 0.74x / 0.60x and the bimodal c=50 bare were.
   Fix in rhapsody (drop the future when a task ends, prune `self.tasks`)?
   Not done here: outside this repo and the page's fix scope.  After a fix
   the E1 ORBIT figure should be rerun (T1c shows the expected numbers).
2. With the prune, one burst in about ten still drops to about 450 req/s
   in every row (T1c): not investigated.
3. T2: the DT's per-message path costs about 47 us per message; batching a
   window per message recovers it.  Should the paper recommend batching,
   or is a lighter per-message path (no `gather`, no task per `ON_INPUT`)
   worth a change in `src/`?
4. T4-C: the broker's dt service saturates one core at about 250-290
   req/s.  Is that the number for the paper, or should the client be
   spread over several processes / nodes first to rule out the client?
5. T3: xgf starts at xGFabric's service request; the CSPOT / input-dir
   feed (1 s polling) is not in it.  Enough for the baseline?
6. The ORBIT rows in T3 / T4 / T5 ran on the unpatched stack, so long
   sessions (P7 cross-node, about 15k tasks) carry the T1 slowdown.
