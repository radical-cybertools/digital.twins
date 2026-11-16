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
