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
| 61225635 | r7-z1 | m5290 | 3 | 00:27:06 | 1.355 | 1.45 | 0.00 |
| 61225637 | r7-z2 | m5290 | 3 | 00:07:46 | 0.388 | 1.83 | 0.00 |
| 61225659 | r7-z3 | m5290 | 3 | 00:08:18 | 0.415 | 2.25 | 0.00 |
| 61226377 | r7-z2b | m5290 | 3 | 00:11:15 | 0.562 | 2.81 | 0.00 |

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
- Z3: job 61225659 (regular, 3 nodes, 1 h). N = 256 twins with
  `--twins-per-session T` for T = 256, 64, 16, 4, 1 (S = 1, 4, 16, 64,
  256), telemetry on, default deadline, one repeat. Each T is its own
  `run_broker.sh` call with a fresh broker and endpoint, results in
  `results/r7/mixed/t<T>/`.
- Decision: Z3 was submitted while Z1 and Z2 still queued. The budget holds
  all three (about 1.3 + 0.5 + 0.5 node-h of 4), so the page's order
  only sets reporting priority, and queuing them together saves wall time.

## Z1: telemetry off over the full range (done, job 61225635, 3 nodes, about 28 min)

Round 6's Y1 setup with `RADICAL_ORBIT_RHAPSODY_TELEMETRY=0` on the
endpoint, 2 repeats. Table: `results/r7/notel/broker-table-stack-r7-20261113.md`.
Columns: req/s and p50 are medians, with r1 / r2 in brackets. Broker and
endpoint CPU are % of one core in the load window.

| N | req/s (r1 / r2) | p50 ms | p99 ms | create s (r1 / r2) | broker CPU % | endpoint CPU % | ep threads | broker threads / fds | Y1 telemetry on req/s | Y3 off, 20 s req/s |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 227.1 (228.6 / 225.6) | 4.3 | 5.3 | 2.0 / 2.0 | 71 | 43 | 70 | 71 / 44 | 200.8 | – |
| 4 | 337.9 (327.6 / 348.3) | 11.7 | 16.3 | 0.6 / 0.6 | 120 | 59 | 104 | 117 / 95 | 316.8 | – |
| 16 | 356.3 (316.5 / 396.0) | 45.2 | 88.7 | 0.8 / 0.8 | 123 | 57 | 116 | 177 / 299 | 352.7 | – |
| 64 | 366.9 (329.0 / 404.8) | 177.5 | 269.1 | 3.2 / 3.2 | 123 | 52 | 164 | 417 / 1,115 | 328.8 | 382.3 |
| 128 | 336.6 (313.0 / 360.2) | 367.5 | 558.7 | 8.6 / 7.8 | 122 | 50 | 228 | 737 / 2,203 | 79.0 | – |
| 256 | 291.9 (254.1 / 329.6) | 835.4 | 1,155 | 46.9 / 32.1 | 122 | 45 | 356 | 1,377 / 4,379 | 19.7 | 264.5 |
| 384 | 256.0 (– / 256.0) | 1,379 | 1,881 | 461.8 failed / 150.9 | 122 | 39 | 484 | 2,017 / 6,555 | 11.2 | 210.3 |

- **With telemetry off there is no collapse.** Throughput falls at most 30% below
  its peak (367 req/s at 64) up to 384 sessions, and p50 grows
  linearly with N (closed loop). At 128 / 256 / 384 sessions that is
  4.3x / 15x / 23x round 6's Y1 (79.0 / 19.7 / 11.2).
- The broker is CPU-bound at 120-123% from N = 4 on. The endpoint is not:
  its CPU falls from 59% to 39% as N grows, and it has about one thread per
  session (70 + N). So with telemetry off the broker is the limit.
- Creation is fragile at 384 even with telemetry off. In r1 one twin
  exceeded the 300 s initialization limit after 461.8 s, so r1 has no 384
  point and the 384 row is r2 alone. The broker log has 2 keepalive
  timeouts in r1 (during that creation burst) and 0 in r2. Creation per
  session rises from 0.05 s (16-64) to 0.15 s (256) and 0.8 s (384).
- The repeat spread is up to 23% (16 sessions: 316.5 / 396.0). It is not
  tuned between repeats and is reported as measured.
- Isolation check empty, no failed requests.

## Z2: where the per-session cost sits (done; jobs 61225637 and 61226377)

### Attempt 1 (job 61225637): no recordings

`py-spy record --rate 100 --idle`, blocking (the default), on broker and
endpoint, at N = 256, telemetry on and off.

- With about 1,400 broker threads and 300-600 endpoint threads, py-spy fell
  about 50 s behind ("results may be inaccurate"). The `timeout 60` around
  each recording killed it before it wrote the folded file.
- Pausing the process for every sample also slowed both runs: 49.1 req/s
  with telemetry on, 79.1 with it off, against 254-330 in Z1.
- The dumps (`pyspy-*-dump.txt`) and the frame counts came through and are
  used below.

### Attempt 2 (job 61226377)

- Change: `PYSPY_RATE=20 PYSPY_NB=1`, i.e. `--rate 20 --idle --nonblocking`,
  and a timeout of the duration + 180 s. This deviates from the page's
  `--rate 100`, which py-spy could not hold with this many threads.
- Same job, first run: telemetry on without profiling (`tel-on-plain`), for
  undisturbed CPU numbers.
- The nonblocking recordings barely disturb the runs: telemetry off gives
  231.5 req/s (Z1: 254-330), telemetry on 28.8 (unprofiled: 21.8).

| run (N = 256) | req/s | p50 ms | broker CPU % | endpoint CPU % | endpoint threads | broker threads |
|---|---|---|---|---|---|---|
| telemetry on, no profiler | 21.8 | 11,365 | 31 | 192 | 613 | 1,377 |
| telemetry on, py-spy 20 Hz nonblocking | 28.8 | 8,715 | 32 | 195 | 613 | 1,378 |
| telemetry off, py-spy 20 Hz nonblocking | 231.5 | 1,027 | 98 | 38 | 356 | 1,378 |
| Z1 telemetry off (median of 2) | 291.9 | 835 | 122 | 45 | 356 | 1,377 |

### What crosses the broker (r7/frame_counter.py, load window, per second)

| | twin_call requests | rhapsody/submit requests | 200 responses | rhapsody/task_status events | other inbound | outbound frames |
|---|---|---|---|---|---|---|
| telemetry on (attempt 1) | 50.7 | 50.0 | 49.3 | 98.6 | 0 | 149 |
| telemetry off (attempt 1) | 85.1 | 83.5 | 83.3 | 166.1 | ~0 | 250 |

The frames per request are the same with telemetry on and off: one
twin_call, one submit, one response and two task_status events. No telemetry
or sysinfo frames cross the broker during the load. The broker relays
nothing extra per session.

### Profiles (`r7/folded_top.py`, `results/r7/profile/*/top-*.md`)

**Endpoint, telemetry on.**
- 98.4% of its busy samples are in rhapsody's
  `ConcurrentTelemetryAdapter._collect_loop` (`rhapsody/telemetry/adapters/concurrent.py:225`, its `_poll()`).
- Hot frames, share of busy samples:
  - `psutil.disk_io_counters` (`concurrent.py:161`): 59.0%, of which
    `psutil/_pslinux.py:248 is_storage_device` is 47.7% self;
  - `psutil.virtual_memory` (`concurrent.py:136`): 14.0%;
  - `psutil.net_io_counters` (`concurrent.py:170`): 13.7%;
  - `cpu_times`: about 4.5%;
  - `open_binary` / `open_text` (psutil reading /proc and /sys): 26% self.
- The dump shows 549 threads against 293 with telemetry off: the 256 extra
  threads are one `_collect_loop` per session.
- **Endpoint, telemetry off:** almost idle. 0.2% of samples are busy, all
  in its event loop and socket writes.

**Broker, both cases.**
- Busy time is the event loop's socket and SSL writes
  (`_SelectorSocketTransport.write`, `SSLObject.write`) and pydantic in
  `protocol.parse_message` / `public_plugins`.
- The dt service (digitaltwin) and asyncflow are at or below 0.1%.
- With telemetry on the broker is mostly idle (31% CPU), waiting on the
  endpoint.
- Note: `_dump (frame_counter.py:79)` is the counter thread's `time.sleep`.
  folded_top.py finds no source for that file, so it counts the sleep as busy.

### Answer

- **The time goes to the endpoint, into rhapsody's per-session telemetry
  collector.** Every service session starts its own `ConcurrentTelemetryAdapter`
  thread, which polls node-level psutil counters (CPU, memory, disk I/O,
  network) every 0.1 s (`resource_poll_interval=0.1` in radical.orbit's
  `plugin_rhapsody.py`).
- At 256 sessions that is 2,560 polls a second. Each poll reads several
  /proc and /sys files; `disk_io_counters` checks every block device with
  `is_storage_device`.
- These threads hold the endpoint at about 190% CPU and contend for its GIL
  with the event loop that answers the broker. Each request then waits on
  the endpoint and the broker idles.
- Neither the broker's relaying nor the dt service in the broker is the cost.
- This is also why one session with 384 twins (Y1c) is fast: one session
  has one poller.

**Bug, described and not fixed (no fix branches this round):**
- The telemetry collects node-level figures that are identical for every
  session on the node, yet radical.orbit's rhapsody plugin starts one
  collector per session at 10 Hz.
- Its cost grows with the session count and starves the endpoint. Each
  session also writes its own `telemetry-output/session.*.telemetry.jsonl`
  into the endpoint's cwd: 4.2 GB in round 6.
- Candidates:
  - one shared collector per endpoint process, fanned out to the sessions;
  - a much longer default poll interval;
  - telemetry off by default for service sessions.
- To decide in radical.orbit #? / rhapsody, not here.

## Z3: S sessions x T twins, 256 twins (done, job 61225659, 3 nodes, about 14 min)

Telemetry on, default 3 s deadline, one repeat per split, a fresh broker and
endpoint each. Tables: `results/r7/mixed/t<T>/broker-table-stack-r7-20261113.md`.

| S sessions | T twins each | create s | req/s | p50 ms | p99 ms | broker CPU % | endpoint CPU % | endpoint threads | broker threads / fds |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 256 | 5.8 | 875.4 | 274 | 473 | 75 | 84 | 103 | 612 / 2,339 |
| 4 | 64 | 5.5 | 893.6 | 275 | 551 | 88 | 103 | 233 | 621 / 2,363 |
| 16 | 16 | 6.3 | 712.4 | 336 | 699 | 103 | 119 | 629 | 657 / 2,459 |
| 64 | 4 | 9.5 | 395.8 | 631 | 952 | 107 | 153 | 956 | 801 / 2,843 |
| 256 | 1 | 76.7 | 20.0 | 12,400 | 13,854 | 38 | 196 | 613 | 1,377 / 4,379 |

- At a fixed 256 twins, throughput depends on the number of sessions: flat
  from 1 to 4 sessions (about 880 req/s), down 20% at 16, 55% at 64 and 98%
  at 256 (20.0, matching Y1's 19.7). The endpoint's CPU rises with S (84 to
  196%), as one telemetry poller per session predicts.
- The broker's CPU peaks at 64 sessions (107%) and drops to 38% at 256: up
  to 64 the broker still carries the load, at 256 the endpoint is the limit.
- 0 failures, 0 keepalive timeouts, isolation checks empty.
- Endpoint threads do not grow monotonically with S (956 at S=64, 613 at
  S=256); not investigated.

## Close-out (2026-11-13 06:45 PST)

- Phases: Z0, Z1, Z2 (in two attempts; the first produced no recordings,
  see above) and Z3 (stretch). All done.
- Ledger (`python s1/ledger.py 7`): 5 jobs, 2.81 node-h on m5290 of the 4
  budgeted.
- Every result JSON (14) has provenance with the digital.twins commit;
  every isolation check is empty; no allocation left (`squeue` empty).
- Findings for E2:
  1. **Telemetry off:** no collapse over N = 1-384 (Z1, 2 repeats). 256
     req/s at 384 sessions, broker-bound at about 122%.
  2. **The per-session cost** is rhapsody's per-session psutil telemetry
     poller in the endpoint (Z2). It is not the broker's relaying and not
     the dt service.
  3. **At a fixed number of twins** the cost grows with the session count
     (Z3: 875 to 20 req/s from 1 to 256 sessions).
- Open questions for Andre:
  - The per-session collector: the radical.orbit / rhapsody fix (one
    collector per endpoint, a longer interval, or off for service sessions),
    and whether the paper reports telemetry-on as the default or as a known
    issue with the fix pending.
  - Per-session telemetry files: they land in the endpoint's cwd (4.2 GB of
    `telemetry-output/` from round 6 is still in `dt-pm6/digital.twins/`,
    not deleted). Should they go elsewhere?
  - Creation at 384 sessions stays fragile with telemetry off: one twin hit
    the 300 s init limit in Z1 r1, and creation per session rises to 0.8 s.
    It is a separate cost that this round did not locate.
  - Z1's repeat spread reaches 23%. A third repeat would tighten the curve
    if it goes into the paper.
  - Endpoint threads in Z3 do not grow monotonically with S (956 at S=64,
    613 at S=256).
- Branch `exp/pm-round7-20261113` merged into `paper/dtaas` after this entry.
