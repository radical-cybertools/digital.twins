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
