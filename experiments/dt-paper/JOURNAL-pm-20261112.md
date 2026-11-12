# Journal: DT paper Perlmutter round 5, E3 rerun (2026-11-12)

Unattended Claude Code session following the round 5 page
(https://claude.ai/artifact/UfTYYsfiBL2AiVaVHnY5yb); rules from the round 1-2c
page (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn), layouts from round 4
(https://claude.ai/artifact/J1xrvuuGSDwthhQ8vbWkRx, `JOURNAL-pm-20261111b.md`).
Branch `exp/pm-round5-20261112` off `307c247` (digital.twins `paper/dtaas`).
Work dir `/pscratch/sd/m/merzky/dt-pm5`, checkout `digital.twins`, venv `ve5`,
env `experiments/dt-paper/r5/env-r5.sh` (`D=stack-r5-20261112`, `RT=r5`).
Times PST unless marked UTC.

## Node-hour ledger (round 5 budget: 6, CPU, m5290)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 5`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 61162899 | r5-e3-local | m5290 | 5 | 00:19:36 | 1.633 | 1.63 | 0.00 |
| 61162900 | r5-smoke | m5290 | 2 | 00:00:47 | 0.026 | 1.66 | 0.00 |
| 61162942 | r5-e3-conc | m5290 | 5 | 00:20:25 | 1.701 | 3.36 | 0.00 |
| 61163497 | r5-smoke2 | m5290 | 3 | 00:00:49 | 0.041 | 3.40 | 0.00 |
| 61163550 | r5-e3-x123 | m5290 | 5 | 00:18:03 | 1.504 | 4.91 | 0.00 |

## X0: setup (done, 2026-11-12 01:20)

- Same Perlmutter session as rounds 3b-4; GitHub over SSH (key in this
  shell's agent now). `memo sync`: up to date.
- Note: a memory note says Andre wants no branch per round (merge rounds
  into `paper/dtaas`, 2026-11-11); this round's kickoff names the branch
  `exp/pm-round5-20261112`, so the kickoff is followed.
- Clone `dt-pm5/digital.twins`, branch at `307c247`. `DT_PYTHON=python3.12
  DT_REF=307c247 ./deploy/install.sh endpoint $W/ve5` (cray-python 3.12.12):
  rc 0, `pip check` clean, `digitaltwin` 0.1.0. Pins: digitaltwin `307c247`,
  asyncflow `24667a5`, rhapsody-py `fd3bad7` (#139: `_drain` in
  `backends/execution/orbit.py`, 5 hits), radical.orbit `7904852`, ROSE
  `9cc47a5`.
- `r5/env-r5.sh`: round 4's `r4/env-r4.sh` with `dt-pm5`, `ve5`,
  `D=stack-r5-20261112` and `RT=r5`.
- Harness changes (defaults unchanged):
  - `--work {wall,cpu}` in `bench_sites.py` and `xgf_sites.py`, passed to
    `e3_components.SiteAgent` / `SiteInvestigator` and to the hand-wired
    tasks: `wall` spins on `time.perf_counter()` as before, `cpu` on
    `time.thread_time()` (the task's own thread CPU). The JSON records
    `work_model` at top level (and `args.work` in the provenance).
    In `xgf_sites.py` the clock choice is folded into the existing line, so
    `wiring_lines` stays 65 (checked against round 4's file).
  - `r4/run_e3_local.sh` and `r4/run_e3_remote.sh`: round tag `RT` in the
    file names (default `r4`); `NS` may use spaces ("1 4"), since a comma
    splits sbatch's `--export` (round 4); the remote script takes `ARGS`.
  - `r4/e3_table.py` takes the round tag as a third argument.
  - `s1/ledger.py 5`: this journal's ledger.
- Decision (budget): round 4's W1 took 4.0 node-h at `--tasks 200`, and the
  CPU model brings back about 20 req/s per site, so X1-X3 at round 4's sizes
  would need about 8 node-h on their own. X1-X3 run with `--tasks 100`
  (requests per burst; 5 bursts, 16 threads, 5 repeats as the page says);
  throughput is the median of bursts 2-5, a rate, so the burst size should
  not move it much. X4 is `--tasks 100` as on the page.
- Decision: X1 uses `NS="1 2 3 4"`, so the N list is in the file names.
- Smoke test of `--work cpu`, job 61162900 (r5-smoke, debug, 2 nodes, one
  site, N=1, `--tasks 20 --bursts 2 --seq 5`), `results/r5/smoke/`: dt
  19.4 req/s, xgf 19.5 req/s (one site at about 1 / 50 ms, as the model
  intends; round 4's wall model gave xgf 49.6 at this size), seq p50 57.2 /
  55.4 ms; placement ok; `work_model: cpu` in both JSONs; isolation check
  empty.
- X1 submitted: job 61162899 (regular, 5 nodes, 1 h), `REPEATS="1 2 3 4 5"
  NS="1 2 3 4" ARGS="--tasks 100" RES=r5/local`.

## Setback: a harness bug hung X1 and X2 (2026-11-12 01:45)

- X2 was submitted early to debug (job 61162942, 5 nodes, 20 min cap) while
  X1 (61162899) waited for regular nodes; both started within minutes.
- X2 hit its time limit after the first repeat's dt run and one xgf point;
  X1 was cancelled after 19:36 for the same reason. Cause, mine: in
  `xgf_sites.py` the site tasks are defined in a loop as `async def
  work(..., work=work)`; from k=1 on, `work` no longer names the work-model
  string but the previous site's task object, which does not pickle
  (`cannot pickle '_queue.SimpleQueue' object`), the submit fails and the
  hand-wired run waits forever. N=1 has one loop pass, so the N=1 smoke test
  passed. The DT side (`e3_components.py`) was correct (one definition per
  investigator); renamed the same way for clarity.
- Fix: the default is `model=work_model`; `wiring_lines` stays 65. Smoke
  test at N=2, job 61163497 (3 nodes, cpu model, both harnesses): rc 0,
  placement ok, dt 37.2 / xgf 38.1 req/s on 2 sites, isolation check empty.
- Guard: `run_e3_local.sh` takes `RUN_TIMEOUT` (each harness run under
  `timeout`), so a hung run cannot eat an allocation again.
- The killed jobs' isolation checks did not run; checked by hand right
  after (nothing newer than either stamp), noted in
  `results/r5/{local,conc}/orbit-isolation-check-<job>-*.txt`. Their partial
  results (dt runs valid, xgf runs from the buggy harness) are kept in
  `results/r5/{local,conc}/aborted/`.
- Cost: 3.40 node-h of 6 spent so far, almost all of it in the two hung jobs.

## Replan (budget, 2026-11-12 01:50)

- X1, X3 and X2 in one 5-node allocation (`r5/run_x123.sh`, job 61163550,
  regular, capped at 23 min = 1.92 node-h): `r4/run_e3_local.sh` three
  times on the same nodes, each with its own broker, endpoints and isolation
  check; `RUN_TIMEOUT=300`.
- Decisions to fit the remaining 2.6 node-h:
  - 3 repeats instead of 5 (X1-X3).
  - Layout `one` at N=4 only (`NS_ONE=4`): one N=1 is the same run as
    spread N=1, and round 4 showed `one` flat over N.
  - X2 runs `--concurrent 32` only; its c=16 points are X1's spread N=1 and
    4 (same nodes, same allocation).
  - Order X1, X3, X2, so the time limit, if it hits, cuts X2.
  - X4 afterwards, 4 nodes, capped at 9 min (0.6 node-h), 3 repeats.

## X1-X3 (done, 2026-11-12 02:10)

Job 61163550 (r5-e3-x123, regular, 5 nodes, 18:03 of the 23-min cap;
`r5/run_x123.sh`): X1 06:00, X3 09:45, X2 02:20 (min:s). 30 runs, every rc
0; placement ok at every point; no errors; all three isolation checks
empty. Provenance `7f9b878` in every JSON, `work_model` as intended. Tables
`results/r5/{local,cpu,conc}/e3-table-stack-r5-20261112.md`
(`r4/e3_table.py <dir> stack-r5-20261112 r5`). 3 repeats, `--tasks 100`,
16 threads unless noted; req/s = median of bursts 2-5.

### X1: wall model, fixed stack (round 4 W1 in brackets)

| harness | layout | N=1 | N=2 | N=3 | N=4 | N=4 x N=1 |
|---|---|---|---|---|---|---|
| dt | spread | 42.7 (20.4) | 69.2 (39.6) | 86.9 (58.5) | 102.8 (77.5) | 2.41 (3.81) |
| dt | one | = spread N=1 | - | - | 42.4 (20.4) | 0.99 |
| xgf | spread | 45.0 (25.5) | 71.8 (42.8) | 93.8 (61.4) | 105.9 (80.3) | 2.35 (3.15) |
| xgf | one | = spread N=1 | - | - | 44.4 (26.7) | 0.99 |

- #139 removes the per-site submit cap: one site through the DT service
  42.7 req/s (round 4 20.4), and the DT path now follows the hand-wired one
  (0.95x at N=1, 0.97x at N=4; round 4 0.80x / 0.97x).
- Round 4's xgf numbers also rise (25.5 -> 45.0 at N=1): `--tasks 100`
  instead of 200 and 3 repeats here; and the wall model lets tasks overlap, so
  a site's rate depends on how many requests are in flight, and scaling over
  sites flattens (2.4x at 4 sites) because 16 threads are spread thinner.
  That is the wall model's artefact X3 removes.
- Seq p50 56.9-57.2 ms (dt), 54.8-56.0 ms (xgf), as in round 4.

### X3: CPU model (`--work cpu`)

| harness | layout | N=1 | N=2 | N=3 | N=4 | N=4 x N=1 |
|---|---|---|---|---|---|---|
| dt | spread | 19.5 | 38.3 | 56.1 | 75.3 | 3.86 |
| dt | one | = spread N=1 | - | - | 19.5 | 1.00 |
| xgf | spread | 19.6 | 38.5 | 56.4 | 75.7 | 3.87 |
| xgf | one | = spread N=1 | - | - | 19.6 | 1.00 |

- The model holds up: one site serves 1 / 50 ms (19.5-19.6), sites add
  capacity almost linearly (3.86x at 4), all investigators on one site stay
  at one site's rate, and the DT path equals the hand-wired one within 1% at
  every N (ranges within 0.4 req/s over the repeats). Seq p50 56.8-57.5 /
  55.0-56.4 ms.
- For the paper: this is the E3 figure. With work that occupies a site's
  CPU, the twin scales over sites exactly as the hand-wired deployment does,
  at 2 lines of code per site instead of 65 lines of wiring.

### X2: 32 client threads, wall model, spread (c=16 from X1)

| N | dt c=16 | dt c=32 | xgf c=16 | xgf c=32 | dt / xgf c=32 | round 4 dt / xgf c=32 |
|---|---|---|---|---|---|---|
| 1 | 42.7 | 50.3 | 45.0 | 54.9 | 0.92 | 0.42 |
| 4 | 102.8 | 129.1 | 105.9 | 138.0 | 0.94 | 0.91 |

- The DT path now follows the hand-wired one as concurrency grows (+18% /
  +26% from 16 to 32 threads, hand-wired +22% / +30%). The remaining 6-8%
  at c=32 is within what the DT service's request path costs (round 4: about
  2 ms of p50 over hand-wired at every point).
