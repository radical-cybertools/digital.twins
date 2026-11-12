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
| 61162900 | r5-smoke | m5290 | 2 | 00:00:47 | 0.026 | 0.03 | 0.00 |

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
