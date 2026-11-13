# Perlmutter round 7: E2 per-session cost (2026-11-13)

Unattended session on a Perlmutter login node, from the round 7 page
(https://claude.ai/artifact/4jwpinRQgfNiMEJDn38Dw1). Rules: the round 1-2c
page's autonomy contract, session mechanics, ORBIT isolation and known
traps. Branch `exp/pm-round7-20261113` off `f4b1f16`, merged into
`paper/dtaas` at the end. Work dir `/pscratch/sd/m/merzky/dt-pm7`. Budget 4
node-h, m5290, CPU. Ledger: `python s1/ledger.py 7`.

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
