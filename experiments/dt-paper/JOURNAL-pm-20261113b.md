# Perlmutter round 7: E2 per-session cost (2026-11-13)

Unattended session on a Perlmutter login node, from the round 7 page
(https://claude.ai/artifact/4jwpinRQgfNiMEJDn38Dw1). Rules: the round 1-2c
page's autonomy contract, session mechanics, ORBIT isolation and known
traps. Branch `exp/pm-round7-20261113` off `f4b1f16`, merged into
`paper/dtaas` at the end. Work dir `/pscratch/sd/m/merzky/dt-pm7`. Budget 4
node-h, m5290, CPU. Ledger: `python s1/ledger.py 7`.

## Node-hour ledger (round 7 budget: 4, CPU, m5290)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 7`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 61225576 | r7-smoke | m5290 | 3 | 00:01:50 | 0.092 | 0.09 | 0.00 |

## Z0: setup (2026-11-13 05:05 PST)

- `/pscratch` healthy (`lfs df` answers, 70% full): work dir there.
- `git diff --stat c2cbc5c f4b1f16 -- src deploy` is empty, so round 6's
  venv `/pscratch/sd/m/merzky/dt-pm6/ve6` is reused. Added `py-spy` 0.4.3 to
  it (`pip install py-spy`, no other change).
- New checkout `dt-pm7/digital.twins` (cloned with `--reference` to the
  round 6 checkout, then repacked and the alternates file removed, so it
  stands alone).
- Harness, all under `experiments/dt-paper/`:
  - `r7/env-r7.sh`: round 7 paths, ve6, `D=stack-r7-20261113`.
  - `r7/run_broker.sh`: round 6's script, plus:
    - the endpoint process sampled from `/proc` on node 1, the same 5
      columns as the broker (`r7/proc_sampler.sh`);
    - `PROFILE=1` for Z2. The broker runs under `r7/frame_counter.py`, and
      py-spy dump and record (`--rate 100 --idle`) run on the broker and the
      endpoint once the client's load phase starts.
    - Port 8161.
    - `TELEMETRY` sets `RADICAL_ORBIT_RHAPSODY_TELEMETRY` on the endpoint,
      as in round 6.
  - `r7/frame_counter.py`: a wrapper that runs the unchanged broker script
    after patching `Broker._route_frame` and `Broker._send` in-process to
    count frames. It logs inbound frames per second by kind (request
    method and path, response status, event plugin/topic) plus outbound
    frames and bytes. Harness only, no `src/` or radical.orbit change. It
    decodes each inbound frame a second time, so it is used only in Z2's
    profiled runs.
  - `e2-scaling/bench_broker.py`:
    - `--twins-per-session T` for Z3: N/T sessions, T twins each; the
      sessions are opened first, then the twins are built on 16 threads.
      `--one-session` is the same as T = N.
    - `--load-marker` writes the load-start epoch to a file, which starts
      the profiler.
    - Each point records `twins_per_session` and `service_sessions`.
  - `r7/broker_table.py`: r6's table plus endpoint CPU, RSS and threads,
    keyed by (N, T).
- Decision: py-spy records `--format raw` (folded stacks). Speedscope
  imports folded stacks directly, so one recording serves both views. A
  second, simultaneous speedscope recording would double the sampling load
  on the profiled process.
- Lead found while reading the code, before any run. radical.orbit's
  rhapsody plugin starts rhapsody telemetry for every session with
  `resource_poll_interval=0.1` and `checkpoint_path="telemetry-output"`, a
  path relative to the endpoint's cwd: the checkout, on Lustre. Round 6
  left 5,741 `session.*.telemetry.jsonl` files (4.2 GB) in
  `dt-pm6/digital.twins/telemetry-output/`. The checkout root also holds
  about 12.9k `asyncflow.session.*` dirs, one per service session (ignored
  by git). Z2 checks whether the time goes there.
- Decision: broker and endpoint run with the checkout root as cwd, as in
  round 6, so Z1 is the same setup. The new checkout starts without those
  files.

### Z0 smoke test (job 61225576, debug, 3 nodes, 2 min)

- Run 1: `PROFILE=1 SESSIONS=4 SECONDS_=25 PROFILE_S=10`, telemetry on.
  232.6 req/s. Working: both /proc samplers, py-spy dump and record on
  broker and endpoint (attach allowed on the compute nodes, no extra
  privileges), and the frame counter. Per second in the load window:
  - 228 twin_call requests, 228 `rhapsody/submit` requests and 228 200
    responses;
  - 455 `rhapsody/task_status` events (2 per request);
  - 685 outbound frames;
  - no telemetry frames through the broker at N=4.
- Run 2: `--twins-per-session 2 SESSIONS=8`: 4 sessions with 2 twins each,
  8 created, 316 req/s.
- Isolation checks empty. Results under `results/r7/smoke*` (kept as the
  harness check).

## Z1, Z2 submitted (05:20 PST)

- Z1: job 61225635 (`RES=r7/notel TELEMETRY=0 REPEATS="1 2"`, regular, 3
  nodes, 1 h, STEP_TIMEOUT 2400). Otherwise round 6's Y1: default 3 s
  deadline, N = 1 to 384, `--keep-going --seconds 20 --create-threads 16`.
- Z2: job 61225637, two runs back to back at N = 256, `PROFILE=1
  SECONDS_=40 PROFILE_S=30`, one repeat each: telemetry on
  (`r7/profile/tel-on`, port 8171), then off (`r7/profile/tel-off`, port
  8172).
- Decision: Z1 and Z2 run at the same time. They are independent and use
  different nodes, so this saves wall time at no node-h cost.
