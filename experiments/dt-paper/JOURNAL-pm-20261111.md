# Journal: DT paper Perlmutter round 3c (2026-11-11)

Unattended Claude Code session following the "Round 3c" section of the round
3b page (https://claude.ai/artifact/DyFqSmEjc4Xr9pLbgz6zKx); rules from the
round 1-2c page (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn). Branch
`exp/pm-round3c-20261111` off `e660bb9` (round 3b's branch, on
`paper/dtaas` `fca2d54`). Work dir `/pscratch/sd/m/merzky/dt-pm3`, checkout
`digital.twins-r3b` (new branch in it), env `$W/env6.sh` (venv `ve3b`,
`D=stack-r3c-20261111`). Round 3b: `JOURNAL-pm-20261110b.md`. Times PST
unless marked UTC.

## Node-hour ledger (round 3c budget: 1.5, CPU, m5290)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 3c`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|

## Setup (2026-11-11 00:20)

- Same Perlmutter session as round 3b. GitHub over SSH again (the key Andre
  added sits in another agent socket; this shell points `SSH_AUTH_SOCK` at
  it). `memo sync`: up to date.
- `ve3b` reused (still at `fca2d54`, unchanged since round 3b).
- Harness changes, all opt-in, defaults unchanged:
  - `r3b/nogc.py --gc-threshold G0[,G1[,G2]]` (V2); `--freeze` now calls
    `gc.freeze()` (round 3b's only printed it; never used in a run).
  - `bench_dt_insitu.py` provenance records `gc_enabled` and
    `gc_threshold` of the client process.
  - `s1/ledger.py 3c`: this journal's ledger.
- Scripts: `r3c/run_v12.sh` (V1 and V2 in one 1-node job, so V2 compares
  with V1 on the same node), `r3c/run_v3.sh` (2 nodes), V4 is
  `s2/run_s2.sh PARTS=r1 CS=1`.
- Decisions: V2 threshold `100000,50,50` (the section's example). V3 runs
  rows bare, investigator and agent (not xgf: the slow first bursts hit
  every row, and 4 rows x 10 x 4 settings would not fit the 0.5 node-h
  guide); rows rotated per repeat; a fresh endpoint per setting.
