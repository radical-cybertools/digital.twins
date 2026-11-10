# Journal: DT paper Perlmutter round 3b (2026-11-10)

Unattended Claude Code session following the round 3b page
(https://claude.ai/artifact/DyFqSmEjc4Xr9pLbgz6zKx); rules from the round 1-2c
page (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn), layouts from round 3
(https://claude.ai/artifact/UKBRzfypy6hxU4TWoph9h7, `JOURNAL-pm-20261110.md`).
Branch `exp/pm-round3b-20261110` off `fca2d54` (digital.twins `paper/dtaas`).
Work dir `/pscratch/sd/m/merzky/dt-pm3`, checkout `digital.twins-r3b`, env
`$W/env5.sh` (venv `ve3b`, `D=stack-r3b-20261110`). Times PST unless marked
UTC.

## Node-hour ledger (round 3b budget: 8, CPU, m5290)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 3b`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 61111505 | r3b-u1 | m5290 | 2 | 00:01:07 | 0.037 | 0.04 | 0.00 |
| 61111623 | r3b-u2 | m5290 | 2 | 00:13:07 | 0.437 | 0.47 | 0.00 |
| 61111624 | r3b-u3a | m5290 | 2 | 00:14:51 | 0.495 | 0.97 | 0.00 |
| 61111625 | r3b-u3b | m5290 | 2 | 00:10:18 | 0.343 | 1.31 | 0.00 |
| 61111713 | r3b-u4 | m5290 | 1 | 00:10:49 | 0.180 | 1.49 | 0.00 |
| 61111714 | r3b-u5 | m5290 | 1 | 00:02:14 | 0.037 | 1.53 | 0.00 |
| 61112677 | r3b-u4b | m5290 | 1 | 00:00:00 | 0.000 | 1.53 | 0.00 |
| 61114029 | r3b-u4b | m5290 | 1 | 00:01:54 | 0.032 | 1.56 | 0.00 |
| 61114268 | r3b-u4c | m5290 | 1 | 00:00:52 | 0.014 | 1.58 | 0.00 |

## U0: setup (done, 2026-11-10 15:20)

- Started in the existing Perlmutter session (the one that ran round 3 and
  the DTaaS video work), not a fresh tmux: Andre pasted the kickoff there.
- `git clone` over SSH failed (`Permission denied (publickey)`: the ssh
  agent has no identities in this session). Decision: clone and push over
  HTTPS with `gh auth git-credential` as the credential helper (gh is
  logged in as andre-merzky); remote URL
  `https://github.com/radical-cybertools/digital.twins.git`.
- `digital.twins-r3b` at `fca2d54`, branch `exp/pm-round3b-20261110`.
  `fca2d54` has round 3's `r3/` scripts but not the follow-up ones;
  `run_t1d.sh`, `run_t2c.sh`, `run_t4c3.sh` and `t4c_merge.py` copied from
  `exp/pm-round3-20261110` (`fa440a0`) unchanged, for reference.
- `DT_PYTHON=python3.12 DT_REF=fca2d54 ./deploy/install.sh endpoint $W/ve3b`
  (cray-python 3.12.12): rc 0, "dependency sanity: OK", `pip check` clean.
  Pins: digitaltwin `fca2d54`, asyncflow `24667a5`, rhapsody-py `e66ced4`,
  radical.orbit `7904852`, ROSE `9cc47a5` (`pip freeze`); versions asyncflow
  0.6.0, rhapsody-py 0.6.0, radical.orbit 0.8.0, rose 0.3.0.
- `radical.orbit.plugin_rhapsody`: `FINISHED_RETAIN_S, TELEMETRY_RETAINED`
  = `3600.0 20000`, as the page requires. `digitaltwin` imports from the
  venv (installed, not the checkout).
- Added to the venv: py-spy 0.4.3, psutil 7.0.0.
- `s1/ledger.py 3b`: this journal's ledger (job names `r3b-*`, budget 8).
- Results under `results/r3b/<phase>/`, names as round 3 with
  `stack-r3b-20261110`.

## U1: the decay is gone (done, 2026-11-10 15:10)

Job 61111505 (r3b-u1, debug, 2 nodes, 1:07; `r3b/run_u1.sh`,
`results/r3b/u1/`). Isolation check empty.

- A, `r3/diag_thread_decay.py --bursts 20 --concurrent 500`, no prune, on
  compute node 0 (round 3 ran it on the login node; here on a compute node
  per "Known traps"): 2172-2518 req/s over 20 bursts, no trend (first
  2481, last 2462); `_scheduled_tasks` stays at 2 and `backend.tasks` at 0
  after every burst. Round 3, unpatched, login node: 1813 -> 437 req/s
  while the set grew to 6000.
- B, one bare process, `bench_dt_insitu.py --tasks 1000 --concurrent 500
  --bursts 20 --rows bare`, ORBIT cross-node (broker node 0, endpoint node 1,
  client node 0): first burst 983 req/s, last 1125, range 843-1157, median
  1112, no trend. Round 3 T1b (unpatched 2c stack): 717 -> 243; T1d
  (`52926e6`): 800-1100.
- Decision (page's gate): the decay is gone, so U2-U5 run. No py-spy /
  endpoint Task count taken: the page asks for it only if the decay
  remains.
- Decision: to save wall time, U2 (regular, 2 nodes) and U3 (two chained
  debug jobs, the radical.3 broker) are queued together after U1; they run
  on different nodes and only U3 uses radical.3. U4 and U5 follow when the
  debug slots free up. Phases are still written up and committed in order.
- Submitted: U2 61111623 (regular, 1:00), U3 61111624 (repeats 1-3) ->
  61111625 (repeats 4-5), `s2/run_s2.sh PARTS=r1 CS="1 50"`, `--tasks 100`,
  `ENV_SH=$W/env5.sh RES=r3b/u3`.

## U4: pool sweep (runs done 2026-11-10 15:18; diagnostic pending)

Job 61111713 (r3b-u4, debug, 1 node, 10:35; `r3b/run_u4.sh`,
`results/r3b/u4/`), 135 runs, every rc 0. No ORBIT. Tables:
`p1-compare-s1-vs-r3b.md` (`s1/compare_insitu.py`, round 2 S1 P1 vs this),
`solo-table-stack-r3b-20261110.md` (`r3b/u4_solo_table.py`).

- P1 (all rows in one process, one burst): seq p50 unchanged at every pool
  (within +-0.04 ms of round 2). c=50 throughput within -13..+2% of round 2.
- c=500: in round 2 the investigator (second row) was the slow one (0.67-0.71x
  bare at pools 1-32), now it is close to bare (0.93-0.98x at pools 1-32,
  0.85x at 64, 0.92x at 128) and the agent (third row) is the slow one
  (0.67-0.73x at pools 1-32, 0.74x at 64, 0.75x at 128); pool 256 equal in
  both rounds. Bare itself unchanged (-4..+2%).
- Solo (each row its own process, 5 bursts), c=500, first burst x bare:
  pool 1 0.97 / 0.96, pool 8 0.92 / 0.91, pool 64 0.94 / 0.90
  (investigator / agent); bursts 2-5: 0.84-0.95.
- So the in-process c=500 loss is a position effect on the local process
  pool, not a DT row cost (and not the thread-pool leak: the local rows run
  on a process pool). Which position loses changed between stacks.
- Harness: `bench_dt_insitu.py` runs the rows in a fixed order whatever
  `--rows` says. A rotated-order diagnostic (job 61112677) was submitted and
  cancelled before it started (0 s) for that reason. Decision: make `--rows`
  order significant (defaults and all earlier calls unchanged), after U2
  finishes (U2 runs from this checkout), then rerun the diagnostic as U4b.

## U5: ex-situ on the lighter message path (done, 2026-11-10 15:21)

Job 61111714 (r3b-u5, debug, 1 node, 2:13; `r3b/run_u5.sh`,
`results/r3b/u5/`, table `t2-table-stack-r3b-20261110.md`). Every rc 0, 28
rows per repeat. `digitaltwin` from the venv (fca2d54, DT #60).

| window | dt x bare, T2 (old stack) | follow-up (b08c8a6) | U5 (fca2d54) | zmq x bare U5 | dt-batched x bare U5 |
|---|---|---|---|---|---|
| 1 | 0.93 | - | 0.97 | 1.01 | 0.97 |
| 10 | 0.76 | 0.90 | 0.90 | 0.93 | 0.90 |
| 50 | 0.45 | 0.82 | 0.80 | 0.89 | 0.87 |
| 100 | 0.34 | 0.77 | 0.73 | 0.88 | 0.84 |

- Per message at window 100: bare 26.9 us, zmq 30.5, dt 37.0 -- the DT adds
  about 6.5 us over the ZMQ hop (T2: 47 us; follow-up: about 4 us). Paced
  publish p50 at window 100: dt 7.24 ms (T2 12.0, follow-up 7.0), zmq 6.58,
  bare 2.11.
- The reviewed DT #60 is slightly slower than `b08c8a6` at large windows
  (0.73 vs 0.77 at 100, 0.80 vs 0.82 at 50); within the repeat spread at 10
  and below. Plausibly the review's change that makes the learner skip
  opt-in, but not investigated.

## U2: E1 in-situ, solo and in-process (done, 2026-11-10 15:30)

Job 61111623 (r3b-u2, regular, 2 nodes, 13:07; `r3b/run_u2.sh` = round 3's
`r3/run_t3.sh` with env5 and the in-process part I added; `results/r3b/u2/`).
110 runs, every rc 0; isolation check empty. Tables:
`t3-table-stack-r3b-20261110.md` (`r3/t3_table.py`, solo) and
`t1-table-stack-r3b-20261110.md` (`r3/t1_table.py`, now with xgf; solo and
in-process per repeat).

- Decision: the in-process runs use all four rows (`--rows
  bare,investigator,agent,xgf`, in that order), 5 bursts per row.
- Provenance: the JSONs record commits db1889a / ef3bfb6 / 6ec7a87 because
  I committed U1/U4/U5 while U2 ran; none of those commits touches `src/`
  or `e1-overhead/` (`git diff --stat 492c66b 6ec7a87 -- e1-overhead src`
  is empty), so every run used the same code.

Solo, medians over 5 repeats, x bare (T3 = round 3, old stack):

| layout | c | metric | bare | investigator | agent | xgf | T3 inv / agent / xgf |
|---|---|---|---|---|---|---|---|
| pool 8 | 50 | bursts 2-5 req/s | 3630 | 0.91 | 0.94 | 0.68 | 0.94 / 0.91 / 0.72 |
| pool 8 | 500 | bursts 2-5 req/s | 3672 | 0.94 | 0.82 | 0.68 | 0.82 / 0.83 / 0.67 |
| pool 8 | seq | p50 ms | 0.58 | 1.02 | 1.02 | 1.49 | 1.03 / 1.03 / 1.50 |
| ORBIT cross | 1 | p50 ms | 2.96 | 0.97 | 1.02 | 1.09 | 1.03 / 1.09 / 1.26 |
| ORBIT cross | 50 | bursts 2-5 req/s | 1010 | 1.00 | 1.00 | 0.93 | 0.99 / 0.98 / 0.85 |
| ORBIT cross | 500 | bursts 2-5 req/s | 1064 | 0.97 | 0.95 | 0.91 | 0.97 / 0.96 / 0.92 |

- ORBIT absolute throughput is up: bare bursts 2-5 at c=50 1010 req/s (T3
  791), at c=500 1064 (T3 650). Local pool 8 unchanged (bare 3630 / 3672 vs
  3525 / 3842).
- In-process, ORBIT cross-node, first burst x bare (round 2: 0.74 / 0.60 at
  c=500; round 3 T1 in-process: 0.63 / 0.44):
  c=500 investigator 1.16, agent 1.16, xgf 1.10 (bursts 2-5: 0.93 / 0.88 /
  0.87); c=50 0.98 / 1.03 / 0.89 (bursts 2-5: 0.99 / 1.00 / 0.89). Bare's
  first burst at c=500 is itself bimodal (874 median, repeats 858-1129), which
  is why the first-burst ratios exceed 1; bursts 2-5 are the steadier number.
  Solo and in-process now agree within the repeat spread.
- Outliers (reported, not dropped): single slow first bursts -- solo c=50 bare
  r1 305 req/s, investigator 421; in-process c=50 xgf 361. This is round 3's
  open question 2 ("one burst in about ten drops to about 450"), still there,
  rarer here (3 of the 40 ORBIT first bursts at c=50); not investigated.

## U3: E1 through radical.3 (done, 2026-11-10 15:35)

Jobs 61111624 (repeats 1-3, debug, 2 nodes) and 61111625 (repeats 4-5),
`s2/run_s2.sh PARTS=r1 CS="1 50"`, `--tasks 100`, endpoint `pm_e1_ep_<job>`
on node A, client on node B, broker `https://95.217.193.116:8010`;
credentials the `~/.radical/orbit` defaults (read only). Every rc 0;
isolation checks empty (both jobs). `results/r3b/u3/`, table
`r1-compare-c3-vs-r3b.md` (`s1/compare_insitu.py`, round 2c C3 R1 vs this).

- WAN connect (curl, 20 per node per job): p50 0.172 s (0.164-0.199); 2c:
  0.171-0.172.
- c=1 p50: bare 353.91, investigator 353.98, agent 353.85 ms (2c: 347.82 /
  347.84 / 348.02), +6 ms for every row alike, just outside 2c's repeat range
  (344.8-351.4).
- c=50 p50: 350.60 / 350.52 / 350.66 ms (2c 351.86 / 352.02 / 351.95);
  throughput 88 / 90 / 92 req/s (2c 87 / 87 / 91).
- The DT rows stay within 0.1 ms of bare in every cell. The c=1 shift is
  common to all rows, with the WAN connect time unchanged: the path to
  radical.3 or its load (the E5 30-day run shares that host), not the stack.
  Decision: no rerun (the contract's rerun rule is for results that
  contradict; the DT-vs-bare comparison does not change).

## U4: diagnostics done (2026-11-10 15:40)

- Harness change (own commit 4389c67): `bench_dt_insitu.py` runs the rows
  in the order `--rows` gives (duplicates dropped); the default and every
  earlier call give the old order.
- U4b, job 61114029 (debug, 1 node, 1:41; `r3b/run_u4b.sh`,
  `results/r3b/u4/order/`): pool 8, c=500, --tasks 1000, 5 bursts per row,
  three row orders, 5 repeats, every rc 0. The slow bursts (about 2700-3000
  against 3400-3800 req/s) sit at fixed positions in the process's burst
  sequence, the same in every repeat of an order (order bare,investigator,
  agent: global bursts 2, 5, 8, 11, 14), whatever row they fall in.
- U4c, job 61114268 (debug, 1 node, 0:43; `r3b/run_u4c.sh`, `r3b/nogc.py`,
  `results/r3b/u4/gc/`): the default order with the client's cyclic GC on
  and off (`gc.disable()` before the harness), 3 repeats each. GC on: every
  third burst slow (all bursts 2676-3883, median 3453); GC off: none (3399-
  3929, median 3575), and the first bursts are bare 3731, investigator 3456
  (0.93x), agent 3478 (0.93x) -- the solo ratios (0.92 / 0.91).
- Finding: the in-process c=500 loss in P1 (round 2: investigator 0.67-0.71x,
  now agent 0.67-0.73x) is the client process's cyclic garbage collector:
  its collections come at fixed allocation counts, and with one burst per
  row the row whose burst meets one loses about 25%. Which row that is
  depends on how many objects the earlier rows allocated, so it moved when
  the stack changed. Not a DT cost and not the thread-pool leak (the local
  rows run on a process pool).
- For the paper: report several bursts per row (median of bursts 2-5, or the
  solo runs) rather than one burst; the P1 single-burst numbers at c=500 are
  GC-phase-dependent. c=50 bursts are short and less affected (U4 P1 c=50
  DT rows 0.86-1.00x bare).
