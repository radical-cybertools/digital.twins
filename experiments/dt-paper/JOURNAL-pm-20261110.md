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
