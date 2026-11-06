# Journal: DT paper Perlmutter round 2, the paper stack (2026-11-06/07)

Unattended Claude Code session following the handover page's "Round 2"
section (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn). Branch
`exp/pm-stack-20261107` off `d885899` (digital.twins `paper/dtaas`). Work dir
`/pscratch/sd/m/merzky/dt-pm3`. Round 1: `JOURNAL-pm-20261106.md`. Times PST.

## Node-hour ledger (round 2 budget: 100, CPU + GPU)

Updated after every job (sacct elapsed x nodes).

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 60926305 | s1-smoke | m5290 | 1 | 00:01:03 | 0.018 | 0.02 | 0.00 |
| 60927053 | s1-p1 | m5290 | 1 | 00:00:00 | 0.000 | 0.02 | 0.00 |
| 60927054 | s1-p2 | m5290 | 1 | 00:00:00 | 0.000 | 0.02 | 0.00 |
| 60927057 | s1-p4 | m5290 | 2 | 00:00:00 | 0.000 | 0.02 | 0.00 |
| 60927061 | s1-p5 | m5290 | 1 | 00:00:00 | 0.000 | 0.02 | 0.00 |
| 60927064 | s1-p6 | m5290 | 1 | 00:00:00 | 0.000 | 0.02 | 0.00 |
| 60927067 | s1-p7 | m5290 | 1 | 00:00:00 | 0.000 | 0.02 | 0.00 |
| 60927070 | s1-p7o | m5290 | 2 | 00:00:00 | 0.000 | 0.02 | 0.00 |
| 60927071 | s1-p3 | m5290 | 1 | 00:01:03 | 0.018 | 0.04 | 0.00 |
| 60927270 | s1-p3re | m5290 | 1 | 00:01:05 | 0.018 | 0.05 | 0.00 |
| 60927438 | s1-p3spy | m5290 | 1 | 00:00:24 | 0.007 | 0.06 | 0.00 |
| 60930958 | s1-p5 | m5290 | 1 | 00:16:54 | 0.282 | 0.34 | 0.00 |
| 60930960 | s1-p7 | m5290 | 1 | 00:02:43 | 0.045 | 0.39 | 0.00 |
| 60930964 | s1-p6 | m5290 | 1 | 00:06:01 | 0.100 | 0.49 | 0.00 |
| 60930968 | s1-p2 | m5290 | 1 | 00:08:02 | 0.134 | 0.62 | 0.00 |
| 60930971 | s1-p1 | m5290 | 1 | 00:07:05 | 0.118 | 0.74 | 0.00 |
| 60931235 | s1-p4 | m5290 | 2 | 00:09:32 | 0.318 | 1.06 | 0.00 |
| 60931654 | s1-p7o | m5290 | 2 | 00:05:56 | 0.198 | 1.25 | 0.00 |
| 60931928 | s1-p5re | m5290 | 1 | 00:04:24 | 0.073 | 1.33 | 0.00 |
| 60932356 | s1-p1re | m5290 | 1 | 00:01:55 | 0.032 | 1.36 | 0.00 |

## S0: build the stack (done)

- `git clone -b paper/dtaas`, branch `exp/pm-stack-20261107` at `d885899`
  ("paper stack: pin install.sh to the paper/dtaas commits, add STACK.md").
- Python: `module load cray-python/3.12.12`, Python **3.12.12** (radical.3 has
  3.12.3; the DT service compares minor versions only).
- `DT_PYTHON=python3.12 DT_REF=d885899 ./deploy/install.sh endpoint $W/ve`:
  rc 0, first try (log `$W/logs/install.log`). Installed, matching STACK.md:

  | package | version | commit |
  |---|---|---|
  | radical.asyncflow | 0.6.0 | 41e49145 |
  | rhapsody-py | 0.6.0 | 36969986 |
  | radical.orbit | 0.8.0 | b10479c3 |
  | rose-surrogate-explorer | 0.3.0 | 9cc47a59 |
  | digitaltwin | 0.0.1 | d8858993 |

  Added: `py-spy 0.4.3`. `PIP_CACHE_DIR=$W/cache/pip` (not home).
- Note: the stack's rhapsody (3696998) does not contain round 1's
  rhapsody#125 (executable stdout over ORBIT). None of the S1 harnesses use
  executable tasks.
- The round-1 harnesses are in this checkout (merge of exp/pm-batch-20261106,
  learner harnesses ported to ROSE's Stream API in b416ea8).
- Decision: S1 runs round 1's batch scripts unchanged except for paths and
  names, generated into `experiments/dt-paper/s1/run_s1_<phase>.sh`
  (dt-pm2 -> dt-pm3, `results/pN` -> `results/s1/pN`, job names `s1-*`, logs
  `$W/logs/s1-*`); `env.sh` sets `D=stack-20261107`, so files are named
  `...-stack-20261107.json` as the page asks. Same harnesses, sizes and
  repeats as round 1. Jobs run via sbatch, as in round 1 (salloc + srun steps
  from the login node hung there).
- orbit 0.8 keeps the CLI flags the scripts use (`--plugins`, `--host`,
  `--port`; endpoint `-n -u -p --tunnel none`).

## S1: submitted

- Smoke job 60926305 (debug, 1:03): every local harness runs on the stack
  (in-situ, learner, ex-situ, twins, join, model update); the floor is gone
  (model-update inference p50 0.58 ms, twins p50 1.4 ms).
- Submitted together (separate ports, stamps and per-job TLS dirs): P1
  60927053, P2 60927054, P3 60927071 (debug), P4 60927057 (2 nodes), P5
  60927061, P6 60927064, P7 60927067, P7o 60927070 (2 nodes).

## S2: prepared

- Login node: `curl -sk https://95.217.193.116:8010/` -> 200, TCP connect
  0.165 s. Default `broker_cert.pem` and `broker.token` present in
  `~/.radical/orbit` (checked with `ls` only; not read by me, the processes
  read them).
- `experiments/dt-paper/s2/run_s2.sh` (2 nodes): WAN RTT from both nodes
  (20 x curl `time_connect`), R1 (endpoint `pm_e1_ep_<job>` on node A,
  `bench_dt_insitu.py` on node B), R2 (`bench_streams.py both` from B), R4
  (`bench_model_update.py` 1 s / 100 ms from B, 3 repeats), R3
  (`bench_endpoint_loss.py` on A owning `pm_p6_learn_<job>`, inference
  endpoint `pm_p6_inf_<job>` on B, 10 kills / 10 reattaches; the harness
  already takes `--broker`), isolation check around everything.
- Decision: R1 `--tasks 100` instead of 1000 (5 repeats, c = 1 / 50 / 500
  as asked). A remote request crosses the WAN twice (client -> radical.3 ->
  endpoint and back) at about 165 ms per round trip, so 1000 sequential
  requests per row would take hours; 100 still gives 100 latency samples
  per row and run.
- Submitted as job 60927139 with `--dependency=afterany` on all S1 jobs
  ("after S1").

## S1 P3: ex-situ learner on the stack (done)

- Job 60927071 (debug, 1:03; round 1 took 6 min), 5 repeats, pool 8, same
  harness, sizes, rows as round 1 (now on ROSE's Stream API; ROSE prints
  a line per window in both rows alike).
- Result: bare 489 -> 37,588 msg/s (batch 1 -> 100), paced publish flat at
  about 2.0 ms; dt 480 -> 13,011 msg/s, publish 2.66 -> 11.79 ms. dt/bare
  0.98 at batch 1, 0.35 at batch 100.
- **Contradicts round 1** ("no measurable ex-situ cost"): there both rows sat
  on asyncflow 0.5.1's ~11.7 ms per-task floor (3 tasks per window), which
  hid a per-sample cost of the DT input path of about 70-80 us. Per the
  contract, rerun once unchanged: job 60927270 (`results/s1/p3-rerun/`,
  debug) gives dt/bare 0.955 / 0.342 at batch 1 / 100, dt publish 2.72 /
  11.84 ms: it holds. Both runs reported.
- Where it sits (job 60927438, py-spy at 500 Hz on one batch-100 run per
  row, 4000 samples): in the dt row 26 % of samples are in
  `digitaltwin.streaming` and 21 % in zmq (the channel publish, receive and
  decode per sample), 8 % in `digitaltwin.runtime`; in the bare row both are
  about 1 %. So the cost is the per-sample hop through the stream broker into
  the twin, not the twin's logic. Folded profiles in `results/s1/p3/`.

## S1: moved to debug (Andre, 14:15)

- The seven regular jobs (P1 60927053, P2 60927054, P4 60927057, P5
  60927061, P6 60927064, P7 60927067, P7o 60927070) waited 75 min without
  starting; debug jobs started within minutes. Andre: "yes, move them to
  debug". S2 (60927139) held first, so cancelling did not satisfy its
  afterany dependency; the seven cancelled (never ran, 0 node-h).
- Resubmitted with `-q debug -t 00:30:00`: P5 60930958, P7 60930960, P6
  60930964, P2 60930968, P1 60930971. debug's submit limit is 5 jobs per
  user, so P4 and P7o go in as slots free (`$W/logs/s1-feeder.sh`), which
  then repoints S2's dependency at all seven debug jobs and releases it.

## S1 P7: model-update propagation, local (done)

- Job 60930960 (debug, 2:43), pool 8, 3 repeats, same harness as round 1.
- Answered p50 0.73 / 0.67 / 0.63 ms at 1 s / 100 ms / 10 ms intervals
  (round 1: 16.65 / 16.35 / 16.21 ms), inference p50 0.59-0.60 ms (round 1
  11.5 ms); versions seen 100 / 98.5 / 100 % (round 1 100 / 100 / 93.6 %).
  Still about one inference time: the in-flight request finishes, the next
  one uses the new model.

## S1 P6: endpoint loss and client reattach (done)

- Job 60930964 (debug, 6:01), loopback, broker `--plugins dt` (orbit 0.8),
  10 kills / 10 reattaches. Isolation check empty.
- Detect 10.4 s (round 1 10.1 s: the broker's suspect -> lost grace),
  in-situ answers 210/210 per twin during the windows, endpoint up 1.5 s,
  learning resumed 3.0 s (round 1 2.8 s), reattach 0.02 s, first answer
  0.02-0.03 s. Unchanged by the stack, as expected: it is set by the
  broker's grace, not by task overhead.

## S1 P2: learner pool sweep on the stack (done)

- Job 60930968 (debug, 8:02), same sweep as round 1 (engine mode, both
  feeds, pool 4/8/32/128/256/default, 3 repeats, py-spy at default and 8).
- **The floor is gone:** pool 8, engine/inproc: 692 msg/s at batch 1 (one
  window = 2 tasks in 1.4 ms, about 0.7 ms per task; round 1 43 msg/s,
  11.6 ms per task), 50,757 msg/s at batch 100 (round 1 4,337; laptop on
  0.5.1 30,417). No profile needed for a residual floor.
- **Pool size now matters** (round 1 could not see it under the floor):
  pools 4-8 are fastest; the default `ProcessPoolExecutor()` (256 workers on
  a CPU node) is 3.3x slower at batch 1 (207 vs 692) and 1.6x at batch 100
  (31,377 vs 50,757). The round-1 "256-worker theory" was right in direction
  after all, only masked.
- **engine/zmq caps at about 13-14k msg/s** (pool 8, batch 100: 13,700),
  the same as P3's dt row (13,011): the ex-situ DT cost of P3 is the ZMQ
  stream transport, which a hand-wired learner fed through ZMQ pays as well.

## S1 P4: E1 through ORBIT, cross-node and loopback (done)

- Job 60931235 (debug, 2 nodes nid005665/005858, 9:32; round 1 33 min),
  orbit 0.8, broker `--plugins dt`, per-job TLS; all 48 runs rc=0;
  isolation check empty.
- p50 through ORBIT: cross 3.36-3.54 ms, loop 3.88-4.01 ms (round 1 15.0 /
  14.7 ms). The ORBIT hop is now about 3 ms over the local pool (0.55 ms,
  P1). Cross-node is not slower than loopback (within the repeat spread).
- DT p50 equal to bare within 0.5 ms.
- Burst throughput through ORBIT did not change (bare c=50 794 cross / 785
  loop; round 1 699 / 727): the ORBIT burst ceiling is in the ORBIT /
  rhapsody client path, not asyncflow.
- Agent burst gap: in-process 0.64-0.71 x bare at c=50/500 (as round 1);
  in its own process 0.98 x (807 vs 824 cross, 730 vs 790 loop). The gap is
  row order. Investigator solo 0.82-0.83 x.
- One ORBIT task per request in every row (diag), as in round 1.
- bench_streams: orbit p50 0.52 / 0.53 ms (round 1 0.45 / 0.43), burst 8.4k /
  9.0k msg/s; zmq 0.19 ms, 19k msg/s (round 1 0.15 ms, 32k): orbit 0.8's
  stream path is not faster, zmq a little slower (different nodes).

## S1 P5: E2 scaling (E2b done; E2a rerun pending)

- Job 60930958 (debug, 16:54). E2b (join) unchanged: about 8k joined
  inputs/s for K = 4-16 (round 1 the same; the join does not use asyncflow).
- E2a: one twin 1,367 req/s at p50 0.70 ms (round 1 84 / 11.96 ms), but the
  aggregate stops at about 2.2k req/s from 2 twins on and per-twin p50 grows
  linearly (64 twins: 2,161 req/s, 28 ms; round 1 2,812 req/s, 21 ms). A
  lower ceiling than round 1 on a faster stack: rerun once unchanged plus a
  py-spy at 16 twins, job 60931928 (`results/s1/p5-rerun/`).

## S1 P1: E1 pool-size sweep (done)

- Job 60930971 (debug, 7:05; round 1 57 min), 90 runs, all rc=0.
- p50 0.53-0.57 ms at pools 1-16 (round 1 11.2-11.7 ms), rising with pool
  size to 1.31 ms at 256. DT p50 within 0.12 ms of bare in every cell.
- Burst throughput peaks at pool 2-4 (c=500: about 4.0k req/s) and falls
  with pool size (pool 256: 1.8k), as in round 1.
- DT/bare throughput: median 0.94 (investigator) / 0.94 (agent) over all
  cells; c=50 0.90-1.01 in every cell. Anomaly: at c=500 the investigator
  row is 0.67-0.74 x bare at pools 1-128 while the agent row is 0.90-1.02 x.
  Rerun once unchanged (job 60932356, pools 1/8/64, c=500, 5 repeats,
  `results/s1/p1-rerun/`): holds (investigator 0.66-0.70 x). Plus each row
  in its own process (pool 8, c=500, 5 repeats): bare 3,782, investigator
  3,518 (0.93 x), agent 3,601 (0.95 x). So the in-process dip is row order:
  the first DT row after the bare row pays something under a 500-request
  burst; on its own the DT costs 5-7 %. Both reported.

## S1 P7o: model-update propagation through ORBIT (done)

- Job 60931654 (debug, 2 nodes, 5:56), isolation check empty.
- Answered p50 cross 5.95 / 6.63 / 7.75 ms, loop 6.76 / 7.17 / 7.92 ms at
  1 s / 100 ms / 10 ms (round 1 cross 22.1 / 22.4 / 21.9 ms); inference p50
  3.7-5.3 ms (round 1 14.5-15.0); versions seen 100 % even at 10 ms (round
  1 66-68 %).
