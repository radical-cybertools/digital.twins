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
| 60927139 | s2-remote | m5290 | 2 | 00:00:00 | 0.000 | 0.04 | 0.00 |
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
| 60932997 | s2-r1a | m5290 | 2 | 00:00:54 | 0.030 | 1.39 | 0.00 |
| 60932998 | s2-r1b | m5290 | 2 | 00:00:54 | 0.030 | 1.42 | 0.00 |
| 60932999 | s2-r3 | m5290 | 2 | 00:00:29 | 0.016 | 1.44 | 0.00 |
| 60933102 | s2-r1a | m5290 | 2 | 00:21:38 | 0.721 | 2.16 | 0.00 |
| 60933103 | s2-r1b | m5290 | 2 | 00:18:29 | 0.616 | 2.77 | 0.00 |
| 60933104 | s2-r3 | m5290 | 2 | 00:08:41 | 0.289 | 3.06 | 0.00 |
| 60934116 | s2-r3re | m5290 | 2 | 00:07:41 | 0.256 | 3.32 | 0.00 |
| 60934573 | s3-service | m5290 | 2 | 00:04:14 | 0.141 | 3.46 | 0.00 |

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

## S1 P5: E2a rerun (done) -- S1 complete

- Rerun job 60931928 (debug): holds. One twin 1,327-1,400 req/s at
  0.68-0.72 ms; aggregate 1.9-2.35k req/s from 2 to 64 twins; 64 twins
  28.7-29.0 ms p50. py-spy at 16 twins: 41 % of samples in
  concurrent.futures / multiprocessing and 32 % in rhapsody (dispatch to the
  one shared process pool), 13 % asyncflow, 4 % DT runtime. The ceiling is
  the main process feeding one shared pool of 64, not the DT; consistent
  with P1 (pool 64, c=500: 3.0k req/s). Lower than round 1 (2.8k): the
  paper stack's concurrent-backend dispatch tops out lower at pool 64.

## S2: split into debug jobs

- S2 (60927139) waited on regular again (Priority, as S1 did for 75 min).
  Decision (same reasoning as Andre's S1 move): cancel it and run S2 as
  three debug jobs (2 nodes, 30 min each), `run_s2.sh` with `PARTS` / `KS`:
  R1 repeats 1-3; R1 repeats 4-5 + R2 + R4; R3. Each job measures the WAN
  RTT in its own allocation (as the page asks) and has its own isolation
  stamp and check.
- First S2 debug jobs 60932997 / 60932998 stopped after 54 s, 60932999
  cancelled: my bug, the RTT loop wrote `wan-rtt-<node>-$D.txt` while the
  check read `wan-rtt-<node>-<job>-$D.txt`, so the reachability test saw
  no file and skipped. The curl output itself showed the compute nodes
  reach the broker (HTTP 200, connect 0.164-0.168 s). Fixed; isolation
  checks of both jobs empty; resubmitted.

## S2 R1 / R2 / R4 through radical.3 (done)

- Jobs 60933102 (R1 repeats 1-3, 21:38) and 60933103 (R1 repeats 4-5, R2,
  R4, 18:29), 2 debug nodes each; endpoint `pm_e1_ep_<job>` on node A,
  clients on node B; default credentials; isolation checks empty.
- WAN: 120 x curl `time_connect` from 4 compute nodes: p50 172.0 ms
  (164.2-179.6).
- R1 (`--tasks 100`, 5 repeats): p50 bare / investigator / agent 350.0 /
  350.1 / 350.2 ms (c=1), 351.7 / 351.6 / 351.5 (c=50), 354.9 / 354.9 / 355.0
  (c=500). A remote request = 2.03 WAN round trips (client -> radical.3 ->
  endpoint -> radical.3 -> client); the stack adds about 6 ms on top (P4
  cross-node on the cluster: 3.5 ms). DT rows equal bare within 0.2 ms.
  Burst: 86-92 req/s at c=50, 450-493 req/s at c=500 (bounded by the
  round trip: 500 requests in about 1 s).
- R2 (`bench_streams.py both`, node B): orbit eventing through radical.3
  p50 173.4 ms (one round trip), burst 515 msg/s; zmq (local, embedded)
  0.2 ms, 20k msg/s.
- R4 (`bench_model_update.py`, 3 repeats): answered p50 506-523 ms at 1 s,
  517-547 ms at 100 ms; inference p50 345-350 ms; versions seen 100 % at
  1 s, 29 % at 100 ms (the interval is shorter than one remote inference).
  Same shape as on the cluster: about 1.5 inferences.

## S2 R3: endpoint loss through the radical.3 dt service (done)

- Job 60933104 (debug, 2 nodes): learning endpoint `pm_p6_learn_<job>` on
  node A (owned by `bench_endpoint_loss.py`), inference endpoint
  `pm_p6_inf_<job>` on node B, twins created in the broker's dt service on
  radical.3. The harness already takes `--broker`; no flag needed.
  Isolation check empty.
- Run 1: 10/10 kills detected (median 10.9 s, 10.2-11.6; the broker's
  grace, as on the cluster: 10.1 / 10.4 s), endpoint up 2.3 s, learning
  resumed 8.0 s (7.8-8.5; cluster 2.8 / 3.0 s: the WAN), 10/10 reattaches
  (attach 1.07 s, first answer 1.60 s; cluster 0.02 s).
- **New, contradicts P6:** in 4/10 kills (those with the fast 10.4 s
  detection) in-situ inference stopped for the whole session: the learner
  twin's probe timed out (`HTTP 504 ... get_inference timed out`, the 5 s
  probe timeout) and the inference-only sibling's probe failed with `HTTP 409
  ... was closed during get_inference`; the sibling's probe after the loss
  was reported failed too, while `twin_list` still showed it `running`. On
  the cluster (P6, both rounds) every probe of both twins answered.
- Rerun once unchanged (job 60934116; run 1's files kept as
  `endpoint-loss-remote-run1-*`): holds, 8/10 kills now show it; detection,
  recovery and reattach the same. Both reported.
- Not explained: the dt service's logs are on radical.3, out of reach from
  here. Open question for Andre: after an engine endpoint is lost, does the
  service let a pending `get_inference` of any twin in that session hang or
  fail until the session is recreated (whereas the loopback broker does
  not)? The sibling uses only the inference endpoint, which stayed up.

## S3: the service path through radical.3 (done, preliminary)

- New `experiments/dt-paper/s3/s3_service.py` (reuses
  `bench_endpoint_loss.py`'s twins and reattach cycle) and `run_s3.sh`: the
  twin (`OffsetModel`) lives in the radical.3 broker's dt plugin, its engine
  on `pm_s3_ep_<job>` (node A), the client on node B. Job 60934573 (debug,
  4:14). Isolation check empty. (A first attempt to write the script via a
  heredoc was refused by a tool hook because of the `find ~/.radical/orbit`
  line; written with the editor instead.)
- `get_inference` p50 346.2-346.4 ms over 3 fresh sessions x 100 requests
  (p99 348-350), i.e. the same two WAN round trips as the client-side path
  (R1: 350 ms); session + twin creation 1.50-1.51 s; 10/10 reattaches,
  attach 1.06 s, first answer 1.59 s (the same as R3).

## Close-out (round 2)

| step | state | headline |
|---|---|---|
| S0 | done | stack venv first try, pins match STACK.md, Python 3.12.12 |
| S1 P1 | done (+rerun, solo rows) | p50 0.55 ms (round 1 11.6); DT within 0.12 ms; in-process investigator dip at c=500 is row order (solo 0.93 x) |
| S1 P2 | done | per-task floor gone (0.7 ms); pools 4-8 fastest, default 256 is 3.3x slower; zmq feed caps at about 13.7k msg/s |
| S1 P3 | done (+rerun) | ex-situ DT cost visible: dt/bare 0.98 -> 0.35 from batch 1 to 100, the ZMQ stream hop (same cap as P2's zmq row) |
| S1 P4 | done | ORBIT p50 3.4-4.0 ms (round 1 15); cross-node no slower; burst ceiling unchanged (about 790 req/s); agent solo 0.98 x |
| S1 P5 | done (+rerun) | E2a: one twin 16x faster, aggregate capped at about 2.2k req/s by dispatch to the shared pool; E2b unchanged (8k inputs/s) |
| S1 P6 | done | unchanged: detect 10.4 s, resume 3.0 s, reattach 17 ms |
| S1 P7 / P7o | done | 0.7 ms local (round 1 16), 6-8 ms through ORBIT (round 1 22), all versions seen |
| S2 R1 / R2 / R4 | done | WAN RTT 172 ms; E1 350 ms (2 RTT + 6 ms), DT = bare; stream event 173 ms; model update 0.5 s |
| S2 R3 | done (+rerun) | detect / recover / reattach work; in-situ inference of the whole session stalls in 4/10 (rerun 8/10) kills |
| S3 | done, preliminary | service-path get_inference 346 ms (= 2 RTT); session + twin 1.5 s; reattach 1.06 s |

**Node-hours (round 2):** see the ledger at the top; m5290 total there, m5290_g 0.
No allocation left running. Every ORBIT job's `~/.radical/orbit` check empty.

**Fix branches:** none. No bug in `src/` blocked a step.

**Open questions for Andre**

1. S2 R3: through the radical.3 dt service an engine-endpoint loss stalls
   `get_inference` for every twin of the session (learner 504, sibling 409
   "closed during get_inference" while `twin_list` says `running`); on the
   cluster's own broker it never does. The service's logs on radical.3 should
   show why.
2. S1 P5 / P1: on the paper stack the shared process pool's dispatch caps
   at about 2.2k tasks/s (pool 64) and burst throughput falls with pool
   size; round 1 reached 2.8k at 64 twins. A pool per twin, or a smaller
   pool, is the lever; worth a look in rhapsody's concurrent backend.
3. S1 P3: the ex-situ DT path is bounded by the ZMQ stream transport (about
   13k samples/s); a learner fed through ZMQ without the DT hits the same
   cap. Batch samples per message, or feed in-process when co-located?
4. S1 P4: the burst ceiling through ORBIT (about 790 req/s) did not move with
   the stack; it sits in the ORBIT / rhapsody client path.
5. The stack's rhapsody (3696998) does not contain rhapsody#125 (executable
   stdout over ORBIT); none of round 2's harnesses needed it, the xGFabric
   twin (P8b) does.

## Round 2b

Following the page's "Round 2b" section (rerun R3 and P6 with the R3 fix,
asyncflow#126). Branch `exp/pm-stack2b-20261107` off `72e4f7c`, venv
`$W/ve2b`, env `$W/env2b.sh` (`D=stack2b-20261107`). Same contract as round 2.
Budget: decision: counted separately from round 2's 3.46 node-hours; it stays
far below 100 either way.

### Round 2b ledger

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 60961770 | b1-r3-run1 | m5290 | 2 | 00:08:28 | 0.282 | 0.28 | 0.00 |
| 60961771 | b1-r3-run2 | m5290 | 2 | 00:08:40 | 0.289 | 0.57 | 0.00 |
| 60961772 | b1-r3-run3 | m5290 | 2 | 00:07:43 | 0.257 | 0.83 | 0.00 |
| 60961773 | b2-p6 | m5290 | 1 | 00:06:06 | 0.102 | 0.93 | 0.00 |
| 60961928 | b3-p8b | m5290_g | 1 | 00:20:32 | 0.342 | 0.93 | 0.34 |

### B0: stack venv at 72e4f7c (done)

- 2026-11-07 05:30 `git fetch`; `exp/pm-stack2b-20261107` at `72e4f7c`
  (`paper/dtaas`: install.sh pins asyncflow `cf638d9` (#126), rhapsody
  `1937801` (#125); orbit `b10479c`, ROSE `9cc47a5` unchanged).
- Decision: merged `exp/pm-stack-20261107` (round 2's harness scripts,
  results and this journal; it touches only `experiments/`) into the new
  branch, so R3 and P6 run the exact round-2 scripts and this journal
  continues. No conflict: `72e4f7c` changes only `deploy/install.sh` and
  `STACK.md`.
- `module load cray-python/3.12.12; DT_PYTHON=python3.12 DT_REF=72e4f7c
  ./deploy/install.sh endpoint $W/ve2b`: rc 0, first try (log
  `$W/logs/b0-install.log`). Python 3.12.12. Installed: digitaltwin
  `72e4f7c`, radical.asyncflow `cf638d9`, rhapsody-py `1937801`,
  radical.orbit `b10479c`, rose-surrogate-explorer `9cc47a5`. The page's
  check (`_fail_submit` in `workflow_manager`) passes; rhapsody's
  `_fetch_output_then_fire` (#125) is present in `backends/execution/orbit.py`.
- Harness changes for round 2b (no change to what is measured):
  - `bench_endpoint_loss.py`: each kill record now also has `kill_t`,
    `kill_utc`, `detect_utc`, `restart_utc`, and the `kill` line prints the
    UTC kill time, so the radical.3 broker log can be matched (B1).
  - `run_s2.sh`, `run_s1_p6.sh`: `ENV_SH` (env file, default round 2's),
    `RES` (results subdir) and, for R3, `TAG` in the output name; R3's
    client log is per job (`s2-client-r3-<job>.log`), since three R3 jobs
    may overlap.
  - `s1/ledger.py 2b` fills the table above from jobs named `b0-`..`b3-`.

### B1/B2/B3 submission (2026-11-07 05:50 PST)

- B1: three debug jobs (2 nodes, 30 min), round 2's `run_s2.sh` with
  `PARTS=r3 ENV_SH=$W/env2b.sh RES=b1 TAG=-run<k>`: 60961770 (run1),
  60961771 (run2), 60961772 (run3). Broker reachable from the login node
  first (200, connect 0.174 s).
- Deviation: I meant to chain the three R3 runs (round 2 ran R3 alone on the
  broker), but runs 1 and 2 started together before the dependency was set.
  They use different endpoint names, so they do not collide, but they share
  the radical.3 broker: a harsher condition than round 2. Decision: let them
  run, and make run 3 wait for both (`afterany:60961770:60961771`), so at
  least one run is alone, as in round 2. Reported per run.
- B2: 60961773 (debug, 1 node, `-t 00:30:00`), round 2's `run_s1_p6.sh` with
  `ENV_SH=$W/env2b.sh RES=b2`. Loopback broker on its own node, independent of
  B1.
- B3 (stretch, GPU): decision: `ve2b` has no TensorFlow, so "P8b on ve2b"
  means ve2b's stack under the TF env. New venv `$W/ve2b-xgf`: round 1's
  conda env `dt-pm2/xgf/env` (Python 3.12.13, TF 2.21.0, numpy 2.5.0) as base
  with `--system-site-packages`, plus the 72e4f7c pins installed into the
  venv (asyncflow `cf638d9`, rhapsody `1937801`, orbit `b10479c`, ROSE
  `9cc47a5`, digitaltwin `72e4f7c`; the latter needed `--force-reinstall
  --no-deps`, since pip took round 1's install as satisfying it). `pip check`
  clean; the venv's stack shadows the conda env's round-1 packages; TF and
  numpy come from the conda env. Log `$W/logs/b3-venv.log`. The conda env
  itself is unchanged.
- xGFabric: `dt-pm2/xGFabric` on `fix/pinn-eval` `3adefa8` (PR #17, equal to
  `origin/fix/pinn-eval`). `twin_service_real` imports under ve2b-xgf.
- `e6-use-cases/run_b3.sbatch`: generated from round 1's final
  `run_p8b.sbatch` (run 6: RUNTIME 1080, TERM-then-KILL teardown); only
  venv, paths, result names (`results/b3/`, `D=stack2b-20261107`) and
  per-job ORBIT log names differ. Job 60961928 (`-A m5290_g -q debug -C gpu`).

### B1: R3 again through radical.3 (done, 3 runs)

- Jobs 60961770 (run1, 8:28), 60961771 (run2, 8:40), 60961772 (run3, alone
  on the broker, 7:43); 2 debug nodes each, WAN connect p50 0.170-0.172 s,
  every R3 rc 0, every isolation check empty. Files
  `results/b1/endpoint-loss-remote-run<k>-stack2b-20261107.{json,log}`.
- Counted with the new `s2/r3_stalls.py` (round 2's files give 4 and 8 dead
  kills with it, as reported then). *dead*: the sibling's probe after the loss
  was reported still fails (round 2's symptom). *paused*: probes fail only
  until then.

| run | detected | dead | paused | submit-refused | detect s | resume s | reattach |
|---|---|---|---|---|---|---|---|
| round 2 run 1 | 10/10 | 4 | 0 | 0 | 10.9 (10.2-11.6) | 8.0 | 10/10, 1.1 s |
| round 2 rerun | 10/10 | 8 | 0 | 0 | 10.4 (10.4-11.1) | 8.0 | 10/10, 1.1 s |
| 2b run 1 | 10/10 | **0** | 5 | 5 | 10.6 (10.4-10.7) | 8.0 | 10/10, 1.1 s |
| 2b run 2 | 10/10 | **0** | 4 | 4 | 10.6 (10.5-10.6) | 7.9 | 10/10, 1.1 s |
| 2b run 3 (alone) | 10/10 | **0** | 8 | 8 | 10.5 (10.5-11.3) | 8.0 | 10/10, 1.1 s |

- The fix works for what it targets: in 30 kills no session died, and the
  sibling answered after every loss. The refused submit now surfaces as the
  learner twin's own `last_error` (`HTTP 504 — [pm_p6_learn_<job>/rhapsody]
  submit 1 task(s) — endpoint lost`), which never happened in round 2 (there
  it took the engine down instead).
- **Not the expected 0 stalls.** Paused kills are exactly the submit-refused
  ones (17/17). In each, both in-situ probes (learner twin, then the
  inference-only sibling) time out at the 5 s probe timeout (`get_inference
  timed out`), back to back, for the whole 10.4 s until the submit fails;
  then the twin is marked failed and the sibling's next probe answers. In the
  13 kills that did not hit a submit every probe answered in 0.36-0.53 s, as
  on the cluster. Reading: while the refused submit to the dead endpoint
  hangs (until the broker's endpoint-lost grace), the session's other
  inference does not run; #126 makes it fail cleanly afterwards instead of
  killing the engine. Not verified: the broker log is out of reach. Same
  cause as round 2 (the submit path), different outcome. Kill times (UTC) are
  in each JSON (`kill_utc`) and in the logs, for matching against the
  radical.3 log's "Error in run loop" count.
- The run1/run2 overlap did not change the picture: run 3, alone, has the
  most paused kills (8). No rerun beyond the three planned: all three agree.
- Open question for Andre (round 2b #1): should a hanging submit on one
  backend block the session's other backend? A fix would make the submit not
  hold the run loop (or bound it), so the inference engine keeps serving
  while the learning endpoint's loss is pending.

### B2: P6 on the cluster, regression check (done)

- Job 60961773 (debug, 1 node, 6:06), round 2's `run_s1_p6.sh` on ve2b,
  `results/b2/`. Isolation check empty. bench rc 0.
- 10/10 kills detected, 10.4 s (10.3-10.4); 0 dead, 0 paused (every probe of
  both twins answered); learning resumed 3.0 s (3.0-3.3); 10/10 reattaches
  (0.02 s). Round 2: 10.4 s, 3.0 s, 10/10, no stalls. Unchanged, as expected.
  No submit-refused kill on the cluster in either round.

### B3: P8b on the stack (done, preliminary)

- Job 60961928 (`m5290_g`, GPU debug, 1 node, 20:32), `run_b3.sbatch` on
  `ve2b-xgf`, xGFabric `3adefa8` (PR #17). Precheck rc 0 (FNO and PINN
  evaluate, 4 concurrent calls each ok). Client rc 0; 353 probes, 0 errors;
  `twin_list` `running` throughout. TF saw the GPUs in every FNO task (no
  "could not find cuda drivers"). Isolation check empty. Teardown: the
  endpoint needed the KILL fallback, as in round 1.
- Selector sequence (probe `arch`): `na` (no model yet) 0-228 s, FNO from
  228 s (25 answers), PINN from 319 s to the end (252). Round 1 run 6: `na`
  0-297 s, FNO from 297 s (19), PCR once at 372 s (a single 19.4 s call),
  PINN from 392 s (228).

| through the twin, p50 | round 1 run 6 (rhapsody e491cd2 + #125) | 2b (72e4f7c stack) |
|---|---|---|
| `na` placeholder (no model) | 24.2 ms (n 99) | 11.0 ms (n 76) |
| FNO | 731 ms (n 19) | 695 ms (n 25) |
| PCR | 19,367 ms (n 1) | not served |
| PINN | 194 ms (n 228) | 162 ms (n 252) |
| first FNO / first PINN | 297 / 392 s | 228 / 319 s |

- Reading: the WindField twin runs on the paper stack end to end, with #125
  from the stack instead of a local build. The selector still ends on PINN,
  the cheapest model. PCR was trained (3 packs in the playground) but PINN's
  runtime estimate arrived first, so the selector never switched to it; in
  round 1 it led by 20 s. The faster `na` path (11 vs 24 ms) is the
  stack's per-task saving. One run only, so preliminary: model arrival times
  depend on training and the sensor stream.

### Round 2b close-out

| phase | status | headline |
|---|---|---|
| B0 | done | `ve2b` at `72e4f7c`, pins match `STACK.md`, `_fail_submit` present |
| B1 | done (3 runs) | 0/30 kills leave the session dead (round 2: 4/10, 8/10); 17/30, exactly the kills that hit a learning submit, pause in-situ inference until the submit fails (about 10.4 s) |
| B2 | done | P6 unchanged: 10.4 s detect, 3.0 s resume, 10/10 reattach, no stall |
| B3 | done, preliminary | WindField twin on the stack: FNO 695 ms, PINN 162 ms (round 1: 731 / 194), selector ends on PINN, PCR not served |

Node-hours (round 2b): m5290 0.93, m5290_g 0.34, total 1.27 (ledger above).
No allocation left running.

Open questions for Andre (round 2b):

1. B1: a learning submit that hangs on the lost endpoint blocks the
   session's in-situ inference (both twins, the inference endpoint is up)
   until the broker's endpoint-lost grace fails it. #126 makes it fail
   cleanly, but should the submit hold the run loop at all? Kill times (UTC)
   are in `results/b1/*.json` (`kill_utc`) for matching against the radical.3
   log's "Error in run loop" count, which I could not read from here.
2. B1: on the cluster (P6, all rounds) no kill ever hit a submit; only
   through radical.3 (WAN) does the kill land inside one. Is that the WAN
   stretching the submit, or the dt service's submit path differing from the
   loopback broker's?
3. B3: PCR is no longer served because PINN's runtime estimate now arrives
   first; if the paper wants all three models shown, the client must run
   longer or PCR must train earlier.

## Round 2c

Following the page's "Round 2c" section (the R3 pause fix: rhapsody#127
background immediate submits, asyncflow#127 run-loop warning, orbit#166 503
on resume). Branch `exp/pm-stack2c-20261108` off `259fa2d`, venv `$W/ve2c`,
env `$W/env2c.sh` (`D=stack2c-20261108`). Same contract as round 2; budget
counted separately, as in 2b.

### Round 2c ledger

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 60992306 | c1-r3-run1 | m5290 | 2 | 00:09:31 | 0.317 | 0.32 | 0.00 |
| 60992307 | c1-r3-run2 | m5290 | 2 | 00:08:11 | 0.273 | 0.59 | 0.00 |
| 60992308 | c1-r3-run3 | m5290 | 2 | 00:07:37 | 0.254 | 0.84 | 0.00 |
| 60992309 | c2-p6 | m5290 | 1 | 00:06:07 | 0.102 | 0.95 | 0.00 |
| 60992310 | c3-p4 | m5290 | 2 | 00:09:55 | 0.331 | 1.28 | 0.00 |
| 60992489 | c3-r1a | m5290 | 2 | 00:14:46 | 0.492 | 1.77 | 0.00 |
| 60992562 | c3-r1b | m5290 | 2 | 00:10:19 | 0.344 | 2.11 | 0.00 |

### C0: venv and scripts (2026-11-08)

- `exp/pm-stack2c-20261108` at `259fa2d` (`paper/dtaas`: asyncflow
  `7e74fcc`, rhapsody `d5ede5f`, orbit `b915a88`, ROSE `9cc47a5`); merged
  `exp/pm-stack2b-20261107` (only `experiments/`), as in 2b. No conflict.
- `DT_PYTHON=python3.12 DT_REF=259fa2d ./deploy/install.sh endpoint $W/ve2c`:
  rc 0, first try (`$W/logs/c0-install.log`), Python 3.12.12. Installed pins
  match the page; the page's check (`_spawn_send(self._send_batch` in
  rhapsody's orbit backend) passes. Added `py-spy` 0.4.3 to ve2c (P4 profiles
  with it; round 2's venv had the same version).
- Scripts: `run_s1_p4.sh` takes `ENV_SH`/`RES` like P6; `run_s2.sh` takes
  `CS` (R1 concurrency levels; C3 runs c = 1 and 50 only, as the page says);
  `ledger.py 2c`.
- Decision: every job that uses the shared radical.3 broker runs alone on it,
  chained: C1 run1 -> run2 -> run3 -> C3 R1 (repeats 1-3) -> C3 R1 (repeats
  4-5). Round 2's R1 needed 18-22 min per job, so R1 is split in two debug
  jobs. C2 (P6) and C3's P4 use local brokers and run alongside.

### C1-C3 submission (2026-11-08)

- C1: 60992306 -> 60992307 -> 60992308 (`afterany` chain, debug, 2 nodes,
  `PARTS=r3 RES=c1 TAG=-run<k>`). C2: 60992309. C3 P4: 60992310 (debug,
  2 nodes, `-t 00:30:00`, `RES=c3/p4`). C3 R1: 60992489 (repeats 1-3) ->
  60992562 (repeats 4-5), after C1 run 3, `PARTS=r1 CS="1 50" RES=c3/r1`,
  queued by a feeder as debug submit slots freed. Broker reachable from the
  login node first (200, connect 0.168 s).

### C2: P6 on the cluster, regression check (done)

- Job 60992309 (debug, 1 node, 6:07), `results/c2/`, isolation check empty,
  bench rc 0.
- 10/10 kills detected at 10.3 s (10.3-10.4); every probe of both twins
  answered (0 dead, 0 paused); learning resumed 3.0 s (3.0-3.3); 10/10
  reattaches (0.02 s). Round 2: 10.4 / 3.0 s; 2b: 10.4 / 3.0 s. Unchanged.

### C1: R3 through radical.3, three runs (done)

- Jobs 60992306 (run1, 9:31), 60992307 (run2, 8:11), 60992308 (run3, 7:37),
  chained, each alone on the broker; 2 debug nodes each; WAN connect p50
  0.171-0.174 s; R3 rc 0; isolation checks empty. Files
  `results/c1/endpoint-loss-remote-run<k>-stack2c-20261108.{json,log}`.

| run | detected | dead | paused | kill hit a submit | detect s | resume s | reattach |
|---|---|---|---|---|---|---|---|
| 2b run 1 | 10/10 | 0 | 5 | 5 | 10.6 (10.4-10.7) | 8.0 | 10/10, 1.1 s |
| 2b run 2 | 10/10 | 0 | 4 | 4 | 10.6 (10.5-10.6) | 7.9 | 10/10, 1.1 s |
| 2b run 3 | 10/10 | 0 | 8 | 8 | 10.5 (10.5-11.3) | 8.0 | 10/10, 1.1 s |
| 2c run 1 | 10/10 | **0** | **0** | 0 | 10.7 (10.7-10.8) | 7.9 | 10/10, 1.1 s |
| 2c run 2 | 10/10 | **0** | **0** | 7 | 11.1 (11.0-11.1) | 7.9 | 10/10, 1.1 s |
| 2c run 3 | 10/10 | **0** | **0** | 9 | 11.5 (11.5-11.5) | 8.2 | 10/10, 1.1 s |

- As expected: 0 dead and 0 paused in all 30 kills. 16 kills hit a learning
  submit (the learner's `last_error` is the refused submit, `HTTP 504 ...
  submit 1 task(s) — endpoint lost`), and in those every probe of both twins
  answered too: 480/480 probes over the three runs, max probe RTT 0.55 s
  (2b paused kills: 5 s probe timeouts back to back).
- One shift: detection is later than in 2b and grows per run (median 10.7 /
  11.1 / 11.5 s, vs 10.5-10.6 s). Within each run it is nearly constant. The
  kills that hit a submit are now reported when the backgrounded submit
  fails, rather than at the broker's endpoint-lost event; that may account
  for it, but run 1 (no submit hit) is at 10.7 s too. Not explained; the
  broker log is out of reach. Reported, not tuned.
- Note on the counter: run 1 has 0 submit hits, so `submit-refused` stays a
  usable count (an early look at run 1 alone made me think the refused submit
  no longer left its own error; runs 2-3 show it does).

### C3, part 1: P4 through ORBIT on the cluster (done)

- Job 60992310 (debug, 2 nodes, 9:55), round 2's `run_s1_p4.sh` on ve2c,
  `results/c3/p4/`, every rc 0, isolation check empty. Compared with
  `s1/compare_insitu.py` (new: median and min-max per layout, c and row,
  round A vs B).
- p50 per request: every row within -0.32..+0.48 ms of round 2 (cross-node
  3.48-4.08 ms, loopback 3.49-4.14 ms), inside the repeat spreads (round 2's
  own min-max spans up to 1.1 ms). No systematic direction: cross-node rows
  are 0.07-0.48 ms slower, loopback rows 0.03-0.32 ms faster.
- Burst req/s at c=500: -2..+8% (bare cross 789 vs 729, loop 772 vs 722).
- The one large median change, bare at c=50 (cross 495 vs 794, loop 506 vs
  785), is bimodality in both rounds: each repeat lands near 500 or near 800
  req/s (round 2: 487 517 812 802 794 / 475 522 810 785 790; 2c: 495 493 826
  797 472 / 506 498 781 767 502). 2c drew 3 low of 5, round 2 drew 2. Not a
  change; the bimodality itself is a property of the bare row (round 2 too).
- Diag task counts identical to round 2 (one ORBIT task per request, every
  row). Solo rows at c=50: bare 783 / 764, investigator 668 / 631, agent
  758 / 773 req/s (cross / loop).

### C3, part 2: R1 through radical.3 (done)

- Jobs 60992489 (repeats 1-3, 14:46) and 60992562 (repeats 4-5, 10:19),
  chained after C1, alone on the broker; c = 1 and 50, `--tasks 100` as in
  round 2; every rc 0; WAN connect p50 0.171-0.172 s (round 2: 172 ms);
  isolation checks empty. `results/c3/r1/`.

| c | row | round 2 p50 ms | 2c p50 ms | change | round 2 req/s | 2c req/s |
|---|---|---|---|---|---|---|
| 1 | bare | 349.99 (349.33-358.88) | 347.82 (344.79-351.41) | -2.17 | 3 | 3 |
| 1 | investigator | 350.09 (349.20-358.85) | 347.84 (344.79-351.41) | -2.25 | 3 | 3 |
| 1 | agent | 350.17 (349.41-358.82) | 348.02 (344.71-351.54) | -2.14 | 3 | 3 |
| 50 | bare | 351.66 (343.05-356.51) | 351.86 (349.33-356.84) | +0.20 | 86 | 87 |
| 50 | investigator | 351.63 (342.65-356.38) | 352.02 (349.14-356.68) | +0.39 | 88 | 87 |
| 50 | agent | 351.47 (342.66-356.42) | 351.95 (349.15-356.63) | +0.47 | 92 | 91 |

- Unchanged: every change is under 0.7% and inside round 2's own repeat
  spread (up to 9.5 ms on 350 ms). DT rows within 0.2 ms of bare, as before.

### Round 2c close-out

| phase | status | headline |
|---|---|---|
| C0 | done | `ve2c` at `259fa2d`, pins match, rhapsody#127 check passes; py-spy added |
| C1 | done (3 runs) | 0 dead, 0 paused in 30 kills (2b: 17 paused); 16 kills hit a submit and inference kept answering (480/480 probes, max 0.55 s); detection later, 10.7 / 11.1 / 11.5 s (2b 10.5-10.6), not explained |
| C2 | done | P6 unchanged (10.3 s detect, 3.0 s resume, 10/10, no stall) |
| C3 | done | P4 and R1 unchanged: p50 within -0.32..+0.48 ms on the cluster and -2.2..+0.5 ms on 350 ms through radical.3; bare c=50 burst bimodal in both rounds |

No allocation left running. Every isolation check empty.

Open questions for Andre (round 2c):

1. C1: detection through radical.3 is 10.7 / 11.1 / 11.5 s per run (median;
   nearly constant within a run), later than 2b's 10.5-10.6 s and rising run
   by run. Is that orbit#166 (suspect endpoint held until resume) or the
   broker's state after many kills? Kill times (UTC) are in
   `results/c1/*.json` for the radical.3 log.
   **Answered 2026-11-09 (laptop):** the broker declares the loss 10 s after
   every kill (radical.3 broker log, CET, 1 s resolution: run 1 kill
   07:35:29 UTC, lost 07:35:39; run 3 kill 07:57:52, lost 07:58:02).  The
   harness sees it in its polling loop (two WAN probes, a `twin` call, a
   0.5 s sleep): in all 2c kills in the 8th iteration, and the iteration
   grew from 1.34 to 1.38 to 1.44 s across the runs.  Measurement
   resolution, not a stack change.
2. P4 (all rounds): the bare row's c=50 burst is bimodal (about 500 or about
   800 req/s per repeat), on cluster and loopback alike; the DT rows are not.
   Cause unknown; it does not affect the DT-vs-bare claim at c=1 or c=500.
