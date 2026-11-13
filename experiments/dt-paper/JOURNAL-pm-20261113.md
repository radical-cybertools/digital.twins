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
| 61219149 | r6-y1 | m5290 | 3 | 00:30:46 | 1.538 | 1.58 | 0.00 |
| 61219150 | r6-y2 | m5290 | 3 | 00:00:00 | 0.000 | 1.58 | 0.00 |
| 61221797 | r6-y2 | m5290 | 3 | 00:28:06 | 1.405 | 2.98 | 0.00 |
| 61222208 | r6-smoke-y1c | m5290 | 3 | 00:00:52 | 0.043 | 3.03 | 0.00 |
| 61222210 | r6-smoke-y1b | m5290 | 4 | 00:02:55 | 0.194 | 3.22 | 0.00 |
| 61222332 | r6-y1b | m5290 | 4 | 01:02:22 | 4.158 | 7.38 | 0.00 |
| 61222333 | r6-y1c | m5290 | 3 | 00:06:43 | 0.336 | 7.71 | 0.00 |

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

## Y1: default keepalive deadline, 3 s (done, 2026-11-13 02:35)

Job 61219149 (r6-y1, regular, 3 nodes, 30:57), `r6/run_broker.sh`, 2
repeats, `--sessions 1,4,16,64,128,256,384 --seconds 20 --keep-going
--create-threads 16`. Both repeats ran every N: 0 failed requests, 0
keepalive ping timeouts in either broker log; isolation check empty.
`results/r6/t3s/`, table `broker-table-stack-r6-20261113.md`
(`r6/broker_table.py`, medians over the 2 repeats).

| N | create s | s per session | req/s | p50 ms | p99 ms | broker CPU % | RSS MB | threads | fds | round 3 T4-C req/s |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2.0 | 2.04 | 200.8 | 5.0 | 5.9 | 60 | 85 | 71 | 44 | 147 |
| 4 | 0.6 | 0.14 | 316.8 | 12.3 | 18.0 | 113 | 107 | 117 | 95 | 243 |
| 16 | 0.8 | 0.05 | 352.7 | 43.3 | 96.0 | 119 | 147 | 177 | 299 | 290 |
| 64 | 3.4 | 0.05 | 328.8 | 186.3 | 374.2 | 116 | 272 | 417 | 1115 | 264 |
| 128 | 9.7 | 0.08 | 79.0 | 1604.6 | 1978.8 | 46 | 466 | 737 | 2203 | – |
| 256 | 63.6 | 0.25 | 19.7 | 12467.8 | 14139.4 | 31 | 911 | 1377 | 4379 | stalled |
| 384 | 181.2 | 0.47 | 11.2 | 27313.1 | 35654.0 | 36 | 1513 | 2017 | 6555 | – |

- #170 works at the default deadline: 384 sessions are created and served
  without a single keepalive timeout (round 3 stalled at 256; the laptop
  stalled at 384 with 3 s).
- Up to 64 sessions the broker is CPU-bound at about one core (113-119%)
  and the aggregate is 317-353 req/s (round 3: 243-290).
- From 128 sessions throughput collapses (79 -> 19.7 -> 11.2 req/s) while
  the broker's CPU falls to 31-46%: it is waiting, not working. Threads
  grow by about 5 per session (2,017 at 384), fds by about 17.
- Creation per session grows with N (0.05 s at 16-64, 0.25 at 256, 0.47 at
  384).
- Y1b (client scaling) and Y1c (one session) look at the collapse.

## Y1b and Y1c: harness, smoke tests, submitted (2026-11-13 02:45)

- `bench_broker.py`: round 3's `--start-at` / `--dump-lat` (from
  `exp/pm-round3-20261110`, applied unchanged; behaviour without them is
  the same); new `--one-session` (all N twins on one DT service session,
  built with the same 16 creation threads; teardown once per session);
  every point records `client_cpu_s` / `client_cpu_pct`, the client
  process's CPU over the load window. Applied after Y1 finished; Y2 started
  after that, so its JSONs record the newer commit, but it uses none of the
  new options and its behaviour is unchanged.
- `r6/run_clients.sh` (Y1b) from `r3/run_t4c3.sh`: one broker and endpoint
  for the job, N = 128, 256, 384 over P = 1, 4, 8 processes alternating two
  client nodes, the shared load window starts 60 + N s after launch (all
  creation done first), a 2400 s timeout per point. `r6/clients_table.py`
  pools them (`r3/t4c_merge.py` reads only round 3's 3-column /proc file).
- `r6/run_broker.sh`: `BENCH_ARGS` passes extra arguments (Y1c:
  `--one-session`).
- Smoke tests (debug): 61222208 (Y1c, N = 1, 4, one session: 198 / 334
  req/s) and 61222210 (Y1b, N=8, P = 1 and 4: 342 / 331 req/s, all
  processes in the window, client CPU 23% for one process). Isolation
  checks empty.
- Submitted: Y1b 61222332 (regular, 4 nodes, 2 h), Y1c 61222333 (regular,
  3 nodes, 90 min, `STEP_TIMEOUT=2400`).

## Y2: keepalive deadline 20 s (done, 2026-11-13 03:10)

Job 61221797 (r6-y2, regular, 3 nodes; `PING=20`, `STEP_TIMEOUT=2400`),
2 repeats, all N in both: 0 failed requests, 0 keepalive timeouts,
isolation check empty. `results/r6/t20s/`, table
`broker-table-stack-r6-20261113.md`. The JSONs record
`ping_timeout: 20`.

| N | Y1 req/s (3 s) | Y2 req/s (20 s) | Y1 p50 ms | Y2 p50 ms | Y1 create s | Y2 create s |
|---|---|---|---|---|---|---|
| 1 | 200.8 | 198.2 | 5.0 | 5.0 | 2.0 | 2.0 |
| 4 | 316.8 | 318.5 | 12.3 | 12.2 | 0.6 | 0.6 |
| 16 | 352.7 | 360.7 | 43.3 | 42.5 | 0.8 | 0.8 |
| 64 | 328.8 | 303.6 | 186.3 | 200.0 | 3.4 | 3.1 |
| 128 | 79.0 | 113.5 | 1604.6 | 1160.1 | 9.7 | 8.6 |
| 256 | 19.7 | 23.6 | 12467.8 | 10292.9 | 63.6 | 49.7 |
| 384 | 11.2 | 11.9 | 27313.1 | 27199.6 | 181.2 | 162.1 |

- Same shape as Y1: CPU-bound plateau up to 64 sessions, collapse from 128
  with the broker's CPU at 30-55%. The 20 s deadline is a little better at
  128-256 (113.5 vs 79.0, 23.6 vs 19.7 req/s; creation 11-22% faster), the
  same at 384.
- Decision for the paper's E2 figure: the default 3 s deadline. On
  Perlmutter it never fired (0 timeouts at every N in four repeats), so
  the figure needs no tuning; the 20 s numbers go next to it as the
  sensitivity check. (On the laptop, 3 s stalled at 384; Perlmutter has
  more headroom.)

## Y1c: all N twins in one session (done, 2026-11-13 03:25)

Job 61222333 (r6-y1c, regular, 3 nodes; `BENCH_ARGS=--one-session
STEP_TIMEOUT=2400`), 2 repeats, all N in both: 0 failed requests, 0
keepalive timeouts, isolation check empty. `results/r6/onesess/`, table
`broker-table-stack-r6-20261113.md`.

| twins N | one session: create s | req/s | p50 ms | p99 ms | broker CPU % | threads | fds | Y1 (N sessions) req/s | Y1 p50 ms |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2.0 | 206.2 | 4.8 | 5.9 | 61 | 71 | 44 | 200.8 | 5.0 |
| 4 | 0.6 | 374.0 | 10.3 | 14.9 | 93 | 108 | 71 | 316.8 | 12.3 |
| 16 | 0.6 | 608.9 | 25.1 | 54.1 | 96 | 132 | 179 | 352.7 | 43.3 |
| 64 | 1.9 | 777.0 | 77.1 | 233.7 | 84 | 228 | 611 | 328.8 | 186.3 |
| 128 | 2.2 | 830.1 | 142.3 | 353.4 | 77 | 356 | 1187 | 79.0 | 1604.6 |
| 256 | 3.9 | 842.1 | 278.3 | 712.4 | 72 | 612 | 2339 | 19.7 | 12467.8 |
| 384 | 5.7 | 794.8 | 446.8 | 890.7 | 68 | 868 | 3491 | 11.2 | 27313.1 |

- The collapse is a per-session cost, not a per-twin one: 384 twins in one
  session serve 795 req/s (384 sessions: 11.2), created in 5.7 s (181 s).
  Throughput plateaus at about 800-840 req/s from 64 twins, latency grows
  linearly with N (closed loop), the broker stays at 68-96% CPU.
- Per twin in one session the broker gains about 2 threads and 9 fds; per
  session (Y1) about 5 threads and 17 fds.
- The single client is not the limit here: its CPU over the load window
  is 18-33% at every N while it drives 800 req/s. Y1b tests the client at
  N sessions.
- For the paper: a deployment should put many twins in one session, or
  the dt service should share per-session machinery (broker participant,
  engine, backends) across sessions. That is a radical.orbit / digital.twins
  question, not measured further here.

## Y1b: N sessions over P client processes (job 61222332, 4 nodes, 62 min)

`r6/run_clients.sh`, default 3 s keepalive, one broker and one endpoint for
the whole job, 20 s load window shared by all processes (`--start-at`),
clients alternating over two nodes. Table `results/r6/clients/clients-table-61222332-stack-r6-20261113.md`.

| N | P | processes ok | req/s | p50 ms | p99 ms | client CPU sum / max % | broker CPU % | RSS MB | threads | fds |
|---|---|---|---|---|---|---|---|---|---|---|
| 128 | 1 | 1/1 | 82.2 | 1535 | 1891 | 7 / 7 | 45 | 440 | 737 | 2203 |
| 128 | 4 | 4/4 | 86.8 | 1428 | 2041 | 9 / 2 | 46 | 519 | 737 | 2206 |
| 128 | 8 | 8/8 | 82.6 | 1511 | 1884 | 10 / 1 | 45 | 565 | 737 | 2210 |
| 256 | 1 | 1/1 | 20.2 | 12186 | 13915 | 2 / 2 | 28 | 996 | 1377 | 4379 |
| 256 | 4 | 4/4 | 18.5 | 13219 | 15405 | 2 / 1 | 29 | 1166 | 1377 | 4382 |
| 256 | 8 | 8/8 | 18.8 | 12239 | 13894 | 3 / 0 | 35 | 1260 | 1377 | 4386 |
| 384 | 1 | 0/1 | – | – | – | – | – | – | – | – |
| 384 | 4 | 3/4 | (11.5) | (21759) | (25926) | 2 / 1 | 37 | 1916 | 1900 | 6158 |
| 384 | 8 | 5/8 | (20.4) | (10602) | (20033) | 3 / 1 | 33 | 1889 | 1300 | 4119 |

- The client side is not the limit: at N = 128 and 256 the rate and the
  latency are the same for 1, 4 and 8 processes (82-87 and 18.5-20.2 req/s),
  and the clients use 1-10% of a core in total. Y1's collapse is in the
  service, matching Y1c (one session: 830 / 842 req/s at the same N).
- N = 384 is unstable when the sessions are opened at the same time:
  - P=1: one of 384 twins exceeded the 300 s initialization limit (after
    431.6 s); bench_broker drops a process on any create error.
  - P=4: one process lost a twin the same way.
  - P=8: three processes lost 9, 2 and 4 twins to `HTTP 504 ... call timed
    out` from the endpoint's rhapsody service.
  - Bracketed rows cover only the surviving processes (288 and 240
    sessions), so they do not compare with the other rows.
- 4 keepalive ping timeouts in the broker log, all during the 384-session
  creation bursts (11:42, 11:55, 12:05 and 12:05 UTC); none at 128 or 256.
- No failed requests once the sessions were up. Orbit isolation check empty.
- Reading for the paper: Y1 (one client) is representative up to 256
  sessions; at 384 the limit is session creation (endpoint rhapsody calls
  time out under the burst), not the request path.

## Y3: telemetry off (submitted)

- Job 61224556 (`RES=r6/t20s-notel PING=20 TELEMETRY=0 REPEATS=1 SESSIONS="64 256 384"`,
  regular, 3 nodes, 1:15, STEP_TIMEOUT 2400). Budget: 7.71 node-h used before
  Y3 (ledger), over the page's 5; Andre relaxed the allocation guards
  ("we can relax allocation guards quite a bit"), and Y3 adds at most 3.75.
