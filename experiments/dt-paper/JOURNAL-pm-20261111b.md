# Journal: DT paper Perlmutter round 4, E3 (2026-11-11)

Unattended Claude Code session following the round 4 page
(https://claude.ai/artifact/J1xrvuuGSDwthhQ8vbWkRx); rules from the round 1-2c
page (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn). Branch
`exp/pm-round4-20261111` off `f68ab66` (digital.twins `paper/dtaas`). Work dir
`/pscratch/sd/m/merzky/dt-pm4`, checkout `digital.twins`, venv `ve4`, env
`experiments/dt-paper/r4/env-r4.sh` (`D=stack-r4-20261111`). Times PST unless
marked UTC.

## Node-hour ledger (round 4 budget: 8, CPU, m5290)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 4`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 61144847 | r4-smoke | m5290 | 2 | 00:00:45 | 0.025 | 0.03 | 0.00 |

## W0: setup (2026-11-11 03:00)

- Same Perlmutter session as rounds 3b and 3c; GitHub over SSH (the key in
  another agent socket). `memo sync`: one inbox note pulled.
- Clone `dt-pm4/digital.twins`, branch `exp/pm-round4-20261111` at
  `f68ab66`. `DT_PYTHON=python3.12 DT_REF=f68ab66 ./deploy/install.sh
  endpoint $W/ve4` (cray-python 3.12.12): rc 0, `pip check` clean;
  `digitaltwin` 0.1.0. Pins: digitaltwin `f68ab66`, asyncflow `24667a5`,
  rhapsody-py `e66ced4`, radical.orbit `7904852`, ROSE `9cc47a5`. py-spy added.
- Page vs repo: the run scripts are in `experiments/dt-paper/r4/`, not
  `e3-portability/r4/`; `env-r4.sh` goes next to them
  (`experiments/dt-paper/r4/env-r4.sh`), and both scripts default to it.
- Harness changes (scripts only, defaults unchanged where they were set):
  - `r4/run_e3_local.sh`: default env and log paths moved from `dt-pm3` to
    `dt-pm4`; knobs `REPEATS`, `LAYOUTS`, `HARNESSES`, `NS`, `CONCS`
    (W2), `NSITES` (smoke test), `ARGS`; per-job stamp and log names.
  - `r4/run_e3_remote.sh`: the same paths; knobs `REPEATS`, `LAYOUTS`,
    `HARNESSES`; it checks `r3_site` in the broker's topology first
    (`r4/check_topology.py`, read-only) and exits 6 if it is missing.
  - `s1/ledger.py 4`: this journal's ledger.
- Decision: the page asks for the smoke test on the login node; the rules
  page's Known traps forbid benchmarks there, smoke tests included. The
  smoke test runs as a short 2-node debug job instead (`NSITES=1 NS=1`,
  tiny sizes, both harnesses).

## W0: smoke test (done, 2026-11-11 04:11)

Job 61144847 (r4-smoke, debug, 2 nodes: broker and client on node 0, site
`e3_s0` on node 1), `NSITES=1 NS=1 REPEATS=1 LAYOUTS=spread`, `--tasks 20
--bursts 2 --seq 5`. Both harnesses rc 0, placement ok, isolation check
empty. `results/r4/smoke/`.

- dt spread n=1: seq p50 57.4 ms, bursts 2-5 31.0 req/s.
- xgf spread n=1: seq p50 55.9 ms, bursts 2-5 49.6 req/s.
- One site serves about 50 req/s at `work_ms` 50 (the README says about
  20). The DT path reaches 31 at 16 client threads, as on the laptop (37 of
  50): this is W2's question.
- Decision: W1 with `REPEATS="1 2 3 4 5"` (regular QOS, the script's 1 h).
  Estimated about 6 min per repeat (both harnesses, both layouts), so about
  35 min on 5 nodes, about 3 node-h. W2 and W3 are submitted once W1's
  first repeat shows `placement_ok` everywhere.
