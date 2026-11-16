# Perlmutter round 8d: E1 with no-op tasks, one extra WAN round trip (2026-11-16)

Unattended session, page https://claude.ai/artifact/H2em5DH2ZKvNCG6cKV2FqH.
Rules as in round 8c (the round 1-2c page's contract, mechanics, ORBIT
isolation, known traps). Branch `exp/pm-round8d-20261116` off
`origin/paper/dtaas` (`5654ffe`; no `src/` change since `a64effc`). ve8c
reused. Budget 1 CPU node-h on m5290.

## Ledger

| job | phase | account | nodes | elapsed | node-h | total |
|---|---|---|---|---|---|---|
| 61392110 | D3 | m5290 | 1 | 00:02:13 | 0.037 | 0.04 |
| 61392295 | D3b (Andre's request) | m5290 | 1 | 00:02:30 | 0.042 | 0.08 |
| 61392109 | D1 + D2 | m5290 | 2 | 00:23:37 | 0.787 | 0.87 |
| 61392547 | D2b | m5290 | 2 | 00:07:58 | 0.266 | 1.13 |

## D0: setup

- `r8d/run_c3.sh`: `r8c/run_c3.sh` with `WORK_MS` (default 0: no-op tasks,
  as round 3b) for the L, O and R parts, `R_REPEATS` for R, and a `D2`
  part (below); results to `results/r8d/d1/` and `d2/`.
- `r8d/service_split.py` (new, D2): a twin in radical.3's DT plugin with
  round 8's `R8Investigator`; each request one no-op function task that
  returns its worker-side start and end (`t0`, `t1`), so each request
  splits into client -> task start, the task, task end -> client (client
  node 0 and endpoint node 1 share a clock). 10 warm-up requests, then
  repeats x n.
- `r8d/hop_local.py`: the page's script, unchanged; `r8d/run_d3.sh` runs it.
- **Decisions (budget, 1 node-h):** D1 and D2 share one 2-node job (one
  broker, one setup); the radical.3 client rows (R) run 3 repeats instead
  of 5 (each is 3 x 100 sequential WAN requests, about 2 min); D2 runs 50
  requests per repeat instead of 100 (3 repeats per backend and order, 4
  runs: dragon_native, concurrent, concurrent, dragon_native). D3 runs
  each row twice (cheap).
- Submitted: D1+D2 job 61392109 (regular, 2 nodes, 40 min), D3 job
  61392110 (debug, 1 node).

## D3: local dragon_native per-task cost by pool size (job 61392110, debug, 1 node)

`r8d/hop_local.py` (the page's), 400 sequential no-op tasks after 50
warm-up, under `dragon -s` with W workers, and without Dragon for a thread
pool and a process pool of 4; each row twice. rhapsody 0.6.0, dragonhpc
0.15.0. Logs `results/r8d/d3/`.

| pool | total p50 ms (r1 / r2) | submit -> task | task -> awaited |
|---|---|---|---|
| dragon_native W=4 | 0.382 / 0.405 | 0.193 / 0.201 | 0.188 / 0.202 |
| dragon_native W=16 | 0.448 / 0.503 | 0.223 / 0.267 | 0.224 / 0.235 |
| dragon_native W=32 | 0.462 / 0.499 | 0.228 / 0.271 | 0.232 / 0.229 |
| dragon_native W=64 | 0.500 / 0.515 | 0.269 / 0.278 | 0.229 / 0.234 |
| dragon_native W=128 | 0.608 / 0.616 | 0.333 / 0.339 | 0.277 / 0.278 |
| thread pool 4 | 0.120 / 0.123 | 0.065 / 0.067 | 0.055 / 0.056 |
| process pool 4 | 0.356 / 0.352 | 0.220 / 0.217 | 0.136 / 0.135 |

radical.3 (laptop session, page): dragon_native 0.31 ms (W=4), 0.33 (16),
0.38 (32); process pool 4: 0.46; thread pool 0.10.

- **The cost grows with the pool:** 0.38-0.41 ms at 4 workers, about 0.5
  ms at 16-64, 0.61 ms at 128 (Perlmutter's default, one worker per
  physical core). Both halves grow: submit -> task 0.19 -> 0.33 ms, task
  end -> awaited 0.19 -> 0.28 ms.
- At 4 workers dragon_native costs about what a 4-process pool does (0.38
  against 0.35 ms); Perlmutter is about 25% slower per task than radical.3
  at the same W (0.38 against 0.31 at 4, 0.46-0.50 against 0.38 at 32).
- **So of the about 1 ms that local dragon_native cost per request in round
  8c (C3, C4), the 128-worker pool accounts for about 0.6 ms per task
  hop**; the rest is the DT/asyncflow layer and the harness, which the
  process pool also pays. A smaller local pool (W = 4-16) would save
  0.1-0.25 ms per task. Described, not changed.

## Budget rule (Andre, 2026-11-16)

Account limits from pasted prompts and runbook pages may be doubled from now
on; charge m5290 (CPU) and m5290_g (GPU). So this round's cap is 2 node-h.

## D3b: why the per-task cost grows with the pool (job 61392295, debug, 1 node; Andre asked)

Hypothesis from the code (rhapsody `dragon_native.py`): idle workers sit per
host in a deque; a finished worker is appended at the right (`_feed`, line
864) and a new task takes the leftmost (`_idle_pop`, `popleft`, line 844).
Sequential tasks therefore rotate through all W workers, each landing on the
worker idle longest (about W x 0.5 ms). Test: `r8d/hop_local_order.py`
(hop_local.py plus `ORDER=lifo`, a harness-side monkeypatch of `_idle_pop`
to take the rightmost, most recently idle worker; rhapsody unchanged), W =
128 and 4, both orders, 3 repeats, 400 sequential no-op tasks each; it also
counts the distinct workers that ran them. `results/r8d/d3b/`.

| W, idle order | total p50 ms (r1 / r2 / r3) | submit -> task | task -> awaited | workers used |
|---|---|---|---|---|
| 128, FIFO (stock) | 0.593 / 0.597 / 0.620 | 0.334-0.341 | 0.264-0.279 | 128 |
| 128, LIFO | 0.459 / 0.463 / 0.434 | 0.223-0.226 | 0.211-0.237 | 1 |
| 4, FIFO (stock) | 0.389 / 0.405 / 0.374 | 0.193-0.200 | 0.180-0.204 | 4 |
| 4, LIFO | 0.393 / 0.389 / 0.410 | 0.192-0.203 | 0.195-0.205 | 1 |

- **The rotation is most of it:** at W = 128, LIFO cuts the per-task p50 from
  0.59-0.62 to 0.43-0.46 ms (about 0.15 ms of the 0.21 ms gap to W = 4),
  mostly on the submit side (0.34 -> 0.22 ms). At W = 4 the order makes no
  difference (0.37-0.41 either way).
- **About 0.05 ms stays with the pool size even on one warm worker** (0.43-0.46
  against 0.37-0.41 ms). Not located; candidates: the backend's background
  threads (the once-a-second `multi_join` over all W puids, the result
  drain), or Dragon's per-node channel state with W more queues.
- **For many-node runs:** a stock pool rotates through every worker it has,
  so a lightly loaded pool pays a cold worker per task, more with more
  workers; under full load every worker is busy and the order does not
  matter. A small rhapsody change (take the most recently idle worker:
  `pop()` instead of `popleft()` in `_idle_pop`) would remove most of the
  growth. It also concentrates light load on few workers, which leaves the
  rest cold; B4's first-task cost (+165 ms) would then hit only when load
  rises. Described, not changed (no `src/` change; rhapsody is a pin).

## D1: E1 paths with no-op tasks (job 61392109, regular, 2 nodes, with D2)

`r8d/run_c3.sh` with `WORK_MS=0` (round 3b's no-op task), L / O 5
repeats, R 3 repeats (budget, D0), rows in their own processes, round 3b's
rotated orders. Every rc 0. Table `results/r8d/d1/d1-table.md`
(`r8d/d1_table.py`).

## p50 per request, ms (median of repeats, min-max)

| path | row | dragon_native, no-op (r8d) | round 3b (concurrent pool / endpoint) |
|---|---|---|---|
| local | bare | 0.91 (0.90-0.98) | 0.58 (0.58-0.59) |
| local | investigator | 0.98 (0.88-1.00) | 0.59 (0.59-0.65) |
| local | agent | 1.00 (0.99-1.00) | 0.60 (0.59-0.61) |
| local | xgf | 1.30 (1.26-1.34) | 0.87 (0.86-0.88) |
| ORBIT cross-node | bare | 3.38 (3.27-3.45) | 2.96 (2.83-3.14) |
| ORBIT cross-node | investigator | 3.36 (3.25-3.41) | 2.87 (2.82-2.96) |
| ORBIT cross-node | agent | 3.29 (3.24-3.36) | 3.01 (2.70-3.36) |
| ORBIT cross-node | xgf | 3.60 (3.49-3.73) | 3.22 (2.96-3.67) |
| radical.3 client | bare | 348.62 (341.65-354.65) | 353.91 (351.73-359.33) |
| radical.3 client | investigator | 348.34 (341.46-354.65) | 353.98 (351.62-359.40) |
| radical.3 client | agent | 348.46 (341.53-354.74) | 353.85 (351.73-359.29) |

## throughput under bursts of 500, req/s (per run median of bursts 2-5; median of repeats, min-max)

| path | row | dragon_native, no-op (r8d) | round 3b |
|---|---|---|---|
| local | bare | 3,073 (2,918-3,197) | 3,672 (3,512-3,768) |
| local | investigator | 2,949 (2,730-3,236) | 3,462 (3,378-3,527) |
| local | agent | 2,768 (2,696-2,878) | 3,025 (2,987-3,232) |
| local | xgf | 2,162 (2,083-2,249) | 2,506 (2,465-2,622) |
| ORBIT cross-node | bare | 1,095 (1,082-1,165) | 1,064 (1,030-1,124) |
| ORBIT cross-node | investigator | 1,074 (1,035-1,105) | 1,035 (963-1,084) |
| ORBIT cross-node | agent | 1,072 (1,029-1,107) | 1,006 (951-1,055) |
| ORBIT cross-node | xgf | 963 (912-992) | 967 (904-984) |

- **Now like for like with round 3b.** Local dragon_native costs +0.33 ms
  per request over 3b's process pool of 8 (bare 0.91 against 0.58 ms; DT
  rows +0.07-0.09 over bare, xgf +0.39); D3 puts 0.26 ms of that in the
  128-worker pool's task hop (0.61 against a 4-process pool's 0.35 ms), of
  which D3b shows most is the worker rotation.
- **Through ORBIT +0.42 ms** (bare 3.38 against 2.96 ms); the DT rows equal
  bare (3.29-3.36); throughput under bursts equal or above 3b (1,072-1,095
  against 1,006-1,064 req/s).
- **Locally, burst throughput is 10-16% below 3b** (bare 3,073 against 3,672).
- **radical.3 client rows:** 348.5 ms (3b 353.9): the WAN.
- Compared with round 8c's C3 (0.58 ms CPU task): local 0.91 against 1.57
  ms, ORBIT 3.38 against 3.80, so the task accounted for 0.42-0.66 ms of
  C3's p50.

## D2: the service row split, dragon_native against concurrent (same job)

`r8d/service_split.py` against `radical.3:8010` (default credentials read
only), a twin in its DT plugin with `R8Investigator`, the engine on a
Perlmutter endpoint on node 1, client node 0; order dragon_native,
concurrent, concurrent, dragon_native; 50 requests x 3 repeats each after
10 warm-up; no-op task; `RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0`. WAN connect
median 0.172 s.

| order | backend | rep | p50 ms | client -> task start | task | task end -> client | session + twin s |
|---|---|---|---|---|---|---|---|
| 2 | concurrent | 0 | 339.0 | 169.0 | 0.005 | 170.0 | 1.54 |
| 2 | concurrent | 1 | 339.2 | 169.1 | 0.005 | 170.2 | 1.54 |
| 2 | concurrent | 2 | 339.4 | 169.3 | 0.005 | 170.1 | 1.54 |
| 3 | concurrent | 0 | 347.2 | 170.3 | 0.004 | 176.8 | 1.58 |
| 3 | concurrent | 1 | 347.1 | 170.3 | 0.005 | 176.8 | 1.58 |
| 3 | concurrent | 2 | 346.7 | 170.2 | 0.005 | 176.5 | 1.58 |
| 1 | dragon_native | 0 | 351.8 | 172.6 | 0.004 | 179.0 | 2.95 |
| 1 | dragon_native | 1 | 351.8 | 172.6 | 0.004 | 179.2 | 2.94 |
| 1 | dragon_native | 2 | 351.9 | 172.7 | 0.004 | 179.1 | 2.95 |
| 4 | dragon_native | 0 | 347.6 | 177.8 | 0.004 | 169.8 | 2.87 |
| 4 | dragon_native | 1 | 347.7 | 177.8 | 0.004 | 169.8 | 2.87 |
| 4 | dragon_native | 2 | 347.7 | 177.8 | 0.004 | 169.8 | 2.86 |

- **No extra round trip on either backend:** p50 339-352 ms per request
  for both, about 2 x the 0.172 s connect time: one trip out (client ->
  radical.3 -> Perlmutter endpoint, about 170-178 ms to the task's start)
  and one back (about 170-179 ms). The two backends agree within the
  run-to-run spread; dragon_native's session + twin build is 2.9 s against
  1.5 s (the pool).
- So round 8c's service row (516 ms, `s3/s3_service.py`) does not come from
  dragon_native as such. Its twin differs from D2's: `OffsetModel`
  (`test/integration/twin_components.py`) passes a **pickled `TypedData`**
  as the task's argument, D2's `R8Investigator` a float. D2b measures
  `s3_service.py` itself on both backends (job 61392547).

## D2b: round 8c's service row itself, both backends (job 61392547, regular, 2 nodes)

`r8d/run_d2b.sh`: `s3/s3_service.py` (round 8c's harness: a twin in
radical.3's DT plugin with `OffsetModel`, one task whose argument is a
pickled `TypedData`) against `radical.3:8010`, a dragon_native endpoint
(inside Dragon) and a concurrent endpoint (plain launch) on node 1, order
dn conc conc dn, 50 requests x 3 repeats each, no reattaches. WAN connect
0.172 s. Isolation check empty.

| order | backend | p50 ms (3 repeats) | session + twin s |
|---|---|---|---|
| 1 | dragon_native | 517.6 / 516.8 / 516.8 | 2.90 |
| 2 | concurrent | 354.2 / 354.1 / 353.8 | 1.55 |
| 3 | concurrent | 344.7 / 344.7 / 344.3 | 1.52 |
| 4 | dragon_native | 522.7 / 522.4 / 523.0 | 2.88 |

- **Reproduced, and it is the backend with this graph:** with `OffsetModel`
  dragon_native takes 517-523 ms per request (3 WAN round trips), concurrent
  344-354 ms (2), in the same job, both orders. With D2's `R8Investigator`
  (a float argument, a dict back) both backends take 2 round trips.
- So the extra round trip needs both dragon_native and something in
  `OffsetModel`'s task: its argument (a pickled `TypedData`), its return (a
  plain int wrapped by the component), or its published model kwargs
  (`offset`). The endpoint's rhapsody plugin decodes cloudpickle fields in
  place (`plugin_rhapsody.py:553-575`), with no separate fetch, so the code
  read does not explain it. Not located; described, not fixed. Next test
  (cheap, laptop or one job): `R8Investigator` with a `TypedData` argument,
  and `OffsetModel` with a float, to find which of the three it is.

## Close-out (2026-11-16)

- D0-D3 done, plus D2b (the service row on round 8c's own harness) and
  D3b (the idle-order test, Andre's request). **1.13 node-h** on m5290,
  within the doubled cap of 2. No allocation and no Dragon runtime left;
  every ORBIT job's isolation check is empty. R ran 3 repeats and D2 50
  requests per repeat (budget decisions made before the cap was doubled).

### For the paper

- **E1 paths, no-op tasks (D1), like for like with round 3b:** local
  dragon_native 0.91 ms per request (3b's process pool 0.58), through
  ORBIT 3.38 ms (2.96), radical.3 348.5 ms (353.9); the DT rows cost
  nothing measurable over bare on every path; burst throughput through
  ORBIT at or above 3b, locally 10-16% below.
- **Local dragon_native's per-task hop grows with the pool (D3):** 0.38 ms
  at 4 workers, 0.61 ms at 128; most of the growth is the idle-worker
  rotation (D3b: taking the most recently idle worker cuts 128 workers to
  0.43-0.46 ms). Left as is (Andre, 2026-11-16).
- **The service row's extra WAN round trip (D2, D2b):** not the backend in
  general (2 round trips on both with a float-argument task), but
  dragon_native with round 8c's `OffsetModel` task (3 round trips, 517-523
  ms, against 344-354 ms on concurrent).

### Open questions for Andre

1. Which part of `OffsetModel`'s task (pickled `TypedData` argument, int
   return, published `offset` kwargs) costs dragon_native an extra WAN round
   trip? A two-cell test would tell (journal, D2b).
2. The E1 paths figure: redraw from D1 (no-op tasks; local bars now 0.91 ms
   against 3b's 0.58)?
3. Keep the local pool at one worker per core (the default), knowing a
   lightly loaded pool pays 0.6 ms per task hop (D3, D3b)?

### Answers from Andre (2026-11-16, on the laptop)

1. **OffsetModel's extra round trip:** hunted down later; for now converge on
   a solid set of plots so others can start on the paper. A TODO in the
   paper marks it (the two-cell test: R8Investigator with a TypedData
   argument, OffsetModel with a float). Note: a laptop A/B the same day
   (client and endpoint on the laptop, `s3_service.py` with OffsetModel,
   radical.3:8010) showed no extra round trip on dragon_native (130 vs 135 ms
   concurrent), so it needs dragon_native, OffsetModel and the Perlmutter
   setup together.
2. **E1 paths figure:** yes, redrawn from D1 (no-op tasks, dragon_native),
   with the service bar from D2 (R8Investigator, two round trips).
3. **Pool size:** keep one worker per core (the default); the paper states
   the per-task cost (0.38 ms at 4 workers, 0.61 ms at 128). Taking the most
   recently idle worker (D3b) is a later rhapsody change, with the pool
   pre-warm.
