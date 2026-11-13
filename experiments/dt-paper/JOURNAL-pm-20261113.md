# Journal: DT paper Perlmutter round 6, E2 broker capacity (2026-11-13)

Unattended Claude Code session following the round 6 page
(https://claude.ai/artifact/8hk9CnUNzxiUvKf3vecmYm); rules from the round 1-2c
page (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn). Branch
`exp/pm-round6-20261113` off `c2cbc5c` (digital.twins `paper/dtaas`), to be
merged into `paper/dtaas` at the end. Work dir `/pscratch/sd/m/merzky/dt-pm6`,
checkout `digital.twins`, venv `ve6`, env `experiments/dt-paper/r6/env-r6.sh`
(`D=stack-r6-20261113`). Times PST unless marked UTC.

## Node-hour ledger (round 6 budget: 5, CPU, m5290)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 6`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 61219092 | r6-smoke | m5290 | 3 | 00:00:48 | 0.040 | 0.04 | 0.00 |

## Y0: setup (2026-11-13 01:30)

- Same Perlmutter session as rounds 3b-5 (it also runs the Dragon phase 3
  work, whose 16-node allocation is queued alongside).
- File system: `/pscratch` healthy (`lfs df /pscratch` 0.06 s, no inactive
  or unavailable targets; venv and package directories list in under
  0.4 s), so the work dir is `/pscratch/sd/m/merzky/dt-pm6` with pip's cache
  there.
- Branching: a memory note says no per-round branches (2026-11-11); this
  kickoff names `exp/pm-round6-20261113` and asks for the merge at the end,
  so the kickoff is followed.
- Clone at `c2cbc5c`; `DT_PYTHON=python3.12 DT_REF=c2cbc5c ./deploy/install.sh
  endpoint $W/ve6`.
- Harness changes:
  - `e2-scaling/bench_broker.py`: provenance now also records the
    digital.twins commit and `RADICAL_ORBIT_PING_TIMEOUT` (round 3's had
    neither).
  - `r6/run_broker.sh` from `r3/run_t4c.sh` part C: a fresh broker and
    endpoint per repeat, `--keep-going --create-threads 16`, a timeout per
    repeat (`STEP_TIMEOUT`, 1500 s), the soft fd limit raised to the hard
    one (both logged per node), `/proc` sampler with RSS, CPU ticks,
    threads and fds, keepalive-timeout count from the broker log per
    repeat; knobs `PING`, `TELEMETRY`, `REPEATS`, `SESSIONS`, `SECONDS_`.
  - `s1/ledger.py 6`: this journal's ledger.
- Venv: `install.sh` rc 0, `pip check` clean, `digitaltwin` 0.1.0; pins
  digitaltwin `c2cbc5c`, asyncflow `24667a5`, radical.orbit `adf2548`
  (#170: `RADICAL_ORBIT_PING_TIMEOUT` in `broker.py` and `runtime.py`),
  rhapsody-py `fd3bad7`, ROSE `9cc47a5`.
- Smoke test, job 61219092 (r6-smoke, debug, 3 nodes): fd limits soft
  400000 / hard 600000 on every node (raised to 600000); N=1 created in
  2.5 s, 195.9 req/s, p50 5.1 ms, 0 keepalive timeouts; sampler works;
  isolation check empty. It ran N=1 only: I passed `SESSIONS=1,4` through
  `--export`, whose comma splits the list (round 4's trap). The script
  now takes spaces (`SESSIONS="1 4"`); Y1/Y2 use its default
  1,4,16,64,128,256,384.
- Decision: Y1 and Y2 run concurrently (regular, 3 nodes each, 40 min,
  `STEP_TIMEOUT=1080` per repeat): separate nodes and brokers, no shared
  state, and it halves the wall time. Phases are still written up in order.
  Submitted Y1 61219149 (`RES=r6/t3s`), Y2 61219150 (`RES=r6/t20s PING=20`).
- Andre (2026-11-13 02:25): avoid tight timeouts, the allocation is fine.
  Y2 (still pending) cancelled (61219150) and resubmitted as 61221797 with
  `-t 01:15:00 STEP_TIMEOUT=2400`. Y1 (61219149) was already running with
  40 min / 1080 s per repeat; its repeat 1 took 17 min, so repeat 2 may be
  cut at N=384 by the step timeout (recorded if so).
- Andre also added two phases after Y1 and Y2:
  - Y1b: client scaling at the top end, N = 128, 256, 384 spread over 1, 4
    and 8 client processes on two client nodes (round 3 T4-C3 measured
    only up to N=64, where the broker was CPU-bound; here the broker's CPU
    falls to 34-51% while latency explodes, so the single client is a
    suspect). Uses round 3's `--start-at` / `--dump-lat` in
    `bench_broker.py` (from `exp/pm-round3-20261110`, never merged) and
    `r3/t4c_merge.py`; client CPU sampled too.
  - Y1c: all N twins in one DT service session (a `--one-session` mode in
    `bench_broker.py`), to separate per-session from per-twin cost. Mixed
    modes (N sessions x K twins) later if needed.
  Both harness changes are applied only after Y1 and Y2 finish, so neither
  run sees a changed harness.
