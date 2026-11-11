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
| 61144870 | r4-e3-local | m5290 | 5 | 00:47:59 | 3.999 | 4.02 | 0.00 |
| 61145515 | r4-e3-conc | m5290 | 5 | 00:14:04 | 1.172 | 5.20 | 0.00 |
| 61145516 | r4-e3-remote | m5290 | 4 | 00:22:15 | 1.483 | 6.68 | 0.00 |
| 61146168 | r4-e3-conc4 | m5290 | 5 | 00:05:58 | 0.497 | 7.18 | 0.00 |

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

## W1: E3 on Perlmutter nodes (done, 2026-11-11 05:00)

Job 61144870 (r4-e3-local, regular, 5 nodes, 47:59; `r4/run_e3_local.sh`
with `REPEATS="1 2 3 4 5"`, `results/r4/local/`): broker (`dt` plugin) and
client on node 0, sites `e3_s0`-`e3_s3` on nodes 1-4, throwaway TLS,
`work_ms` 50, `--tasks 200 --bursts 5 --concurrent 16`. 20 runs, every rc 0;
`placement_ok` true at every point in every repeat (80 of 80); no errors;
isolation check empty. Table `e3-table-stack-r4-20261111.md`
(`r4/e3_table.py`).

| harness | layout | N=1 | N=2 | N=3 | N=4 | N=4 x N=1 |
|---|---|---|---|---|---|---|
| dt | spread | 20.4 | 39.6 | 58.5 | 77.5 | 3.81 |
| dt | one | 20.3 | 20.2 | 20.4 | 20.4 | 1.01 |
| xgf | spread | 25.5 | 42.8 | 61.4 | 80.3 | 3.15 |
| xgf | one | 25.7 | 25.3 | 25.5 | 26.7 | 1.04 |

(req/s, median of bursts 2-5 over 5 repeats; ranges in the table file.)

- Sequential p50: 56.2-57.1 ms (dt), 54.7-56.1 ms (xgf), at every N and
  layout; `work_ms` is 50.
- The DT twin scales with sites: 3.81x at 4 sites, at 20 req/s per site;
  all investigators on one site stay at one site's rate. The hand-wired
  layout gets 80.3 at 4 sites (DT 0.97x of it), but more at one site
  (25.5 vs 20.4), so its scaling factor is lower (3.15x).
- Code per site (from the JSON): DT 2 lines (one engine config entry
  `site_k: {endpoint_name, backends}`, one element in the agent's `sites`);
  hand-wired 1 `SITES` entry per site plus 65 wiring lines the user owns
  (`wiring_lines`), which the DT service provides.
- Per-site rate: 20 req/s for the DT path is exactly 1 / 50 ms, as if a site
  ran the twin's tasks one at a time; the hand-wired path's per-site rate
  depends on client concurrency (W2). Note the work is a wall-clock busy
  loop (`time.perf_counter()` deadline), so concurrent tasks on one
  endpoint do not queue on the GIL as the README suggests: they share it
  and all end 50 ms after they start.

## W3: E3 across facilities (done, 2026-11-11 04:45)

Job 61145516 (r4-e3-remote, debug, 4 nodes, 22:15; `r4/run_e3_remote.sh`
with `REPEATS="1 2 3 4 5" LAYOUTS=spread HARNESSES=dt`, `results/r4/remote/`).
Submitted together with W2 once W1's first repeat showed placement ok
everywhere (W3 touches only radical.3's broker, W1 only its own).

- Topology check from the compute node: `r3_site` in the broker's topology
  with rhapsody (`topology-check-*.txt`), so W3 ran.
- Client on node 0; sites `pm_e3_s0/1/2_61145516` on nodes 1-3 and `r3_site`
  on radical.3; broker and `dt` service radical.3 :8010; default
  credentials (read only); `--tasks 100`, 16 client threads. 5 runs, every
  rc 0; placement ok at every point (20 of 20); at N=4 every repeat sent
  133 requests to each site including `r3_site`. Isolation check empty.
- WAN connect (curl, 20 from node 0): p50 171 ms (165-180), as in rounds
  2c-3c.

| N | sites | bursts 2-5 req/s | x N=1 | seq p50 ms | W1 dt spread (req/s, p50 ms) |
|---|---|---|---|---|---|
| 1 | pm_e3_s0 | 6.1 (6.0-7.2) | 1.00 | 394.3 | 20.4, 56.4 |
| 2 | + pm_e3_s1 | 10.6 (10.4-11.0) | 1.75 | 393.2 | 39.6, 56.8 |
| 3 | + pm_e3_s2 | 15.5 (15.2-15.7) | 2.55 | 395.0 | 58.5, 56.8 |
| 4 | + r3_site | 19.7 (19.4-19.8) | 3.25 | 396.9 | 77.5, 57.1 |

- Through radical.3 every request pays the WAN round trip twice (client to
  broker, broker to site and back): seq p50 about 394 ms against 57 ms on
  the cluster, i.e. about 340 ms over the 50 ms of work, 2 x 171 ms.
- Throughput still grows with every site, including the one on another
  facility (radical.3); with 16 client threads it is latency-bound (16 /
  0.394 s is about 41 req/s at most), not site-bound, so the absolute
  numbers are lower than W1's and the scaling factor is 3.25x, not 3.8x.
