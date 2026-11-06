# E1 Overhead

Do the abstractions cost performance?  (Outline, 2026-10-02.)

- Baseline: xGFabric-style hand-wired workflow on one endpoint.
- Metrics:
  - in-situ inference throughput and latency
  - ex-situ learner throughput
- Have (single host only):
  - service inference 20 ms vs 11 ms in-process (`bench_insitu.py`)
  - stream hop 0.98 ms on ZMQ vs 2.09 ms on ORBIT (`bench_streams.py`)
- Missing: the baseline comparison; runs on Perlmutter.

## `bench_dt_insitu.py` — in-situ: hand-wired vs DT

The E1 in-situ comparison.  One no-op prediction (an asyncflow function
task), measured three ways on the same backend: called directly (the
hand-wired, xGFabric-style baseline), through `DTRuntime.get_inference`
into a `ModelInvestigator`, and through a `SciAgent` with a model
selector in front of it (the xGFabric twin shape).  The difference
between the rows is the DT layer.

```sh
# local process pool
python experiments/dt-paper/e1-overhead/bench_dt_insitu.py \
    --out results/insitu-<host>-<date>.json

# tasks on an ORBIT endpoint (notify window 0, see below)
python experiments/dt-paper/e1-overhead/bench_dt_insitu.py \
    --broker https://127.0.0.1:8031 --endpoint dt_test_task_ep \
    --out results/insitu-orbit-<host>-<date>.json
```

The JSON records host, python, backend, notify window, Slurm job id and
the `digital_twins` commit next to the raw latencies.

Laptop smoke run (2026-11-02, local pool of 8, n=100, 50 concurrent):

| row                 | p50      | concurrent |
|---------------------|----------|------------|
| bare asyncflow task | 11.09 ms | 1352 req/s |
| DT investigator     | 11.21 ms | 1265 req/s |
| DT agent + selector | 11.14 ms | 1248 req/s |

## `bench_insitu.py` — in-situ inference latency

The harness behind the compute-placement decision: one no-op asyncflow
function task per call, awaited sequentially (the shape of an in-situ
prediction), plus a 50-way concurrency probe.

```sh
# against the integration stack (test/integration/conftest.py starts one)
python experiments/dt-paper/e1-overhead/bench_insitu.py both \
    --broker https://127.0.0.1:8031 --endpoint dt_test_task_ep
```

Three configurations matter, and only one of them is a client-side knob:

| path                                            | measured (loopback) |
|-------------------------------------------------|---------------------|
| in-process `ProcessPoolExecutor`                 | ~11 ms p50, ~35 tasks/s concurrent |
| orbit, `batch_window=0`, notify window 0.25 s    | ~260 ms p50 |
| orbit, `batch_window=0`, notify window 0         | ~19 ms p50, ~334 tasks/s concurrent |

`batch_window=0` is hardcoded in the harness (and in the service's
engines).  The **notify window is an endpoint setting** — start the
endpoint with `RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0` for the fast row
and leave it at its 0.25 s default to reproduce the slow one.

Routing all user compute through the Rhapsody abstraction therefore
costs single-digit milliseconds per sequential prediction and wins by an
order of magnitude under concurrency.

## `bench_streams.py` — stream latency, ZMQ vs ORBIT data plane

One publish awaited until the subscriber's queue hands it back: the shape
of every hop in a twin's graph.  Both rows go through the same
`PubSubClient`, so the only difference is the backend (M3).

```sh
# the zmq row starts its own embedded broker; the orbit row needs a live one
python experiments/dt-paper/e1-overhead/bench_streams.py both --broker https://127.0.0.1:8031
```

Loopback, one host, bare-int payloads (2026-08-15):

| data plane                  | p50     | p99     | burst          |
|-----------------------------|---------|---------|----------------|
| zmq, embedded broker        | 0.98 ms | 1.32 ms | 20 200 msg/s   |
| orbit eventing              | 2.09 ms | 2.60 ms |  4 300 msg/s   |

With 64 KiB payloads (`--payload 65536`): 1.18 ms / 3.56 ms p50, and
6 500 vs 1 150 msg/s in burst.

So the ORBIT data plane costs roughly **1 ms per stream hop** and about a
quarter of the burst throughput, in exchange for the security property of
M3: the payloads ride the token-authenticated WebSocket star and the
deployment opens no unauthenticated ports (risk R7).  Against the ~20 ms
of a single in-situ prediction (the row above), that is noise.
Informational, not a gate.

The extra hop is structural: ZMQ's XSUB/XPUB proxy forwards a frame
between two sockets, while an ORBIT event is packed, sent to the broker,
stamped with a `seq`, fanned out, and handed across a thread boundary
into the host loop.  Payload size hurts the ORBIT row more because the
frame is msgpacked around the pickle.

## `streaming_learner_perf.py`, `plot_streaming_perf.py`

Throughput of the streaming active learner (ROSE); unrelated to the
service path.

Both scripts read and write `streaming_perf.json` in the current
directory; run them from `results/`:

```sh
cd experiments/dt-paper/e1-overhead/results
python ../streaming_learner_perf.py
python ../plot_streaming_perf.py      # -> streaming_perf.png (not in git)
```

Flags (2026-11-06): `--workers N` (default: unchanged, `ProcessPoolExecutor()`
= `os.cpu_count()` workers), `--modes stub,engine`, `--feeds inproc,zmq`,
`--out PATH` (default `streaming_perf.json`).  The JSON now carries
`provenance`.

## Perlmutter batch 2026-11-06 (P1–P4)

Branch `exp/pm-batch-20261106`, journal `../JOURNAL-pm-20261106.md`, raw
results in `../results/p<N>/`, tables from `../summarize_pm_20261106.py`.
CPU nodes, account m5290, Python 3.13.18, the four `deploy/install.sh` pins.

### P2: the per-task floor is asyncflow's 10 ms run-loop sleep

The learner's engine rows on Perlmutter (about 4.3k msg/s at batch 100,
7x below the laptop) do **not** depend on the pool size: pool 4, 8, 32,
128, 256 and the default all give 42-45 msg/s at batch 1 and 4.1-4.7k
msg/s at batch 100 (`../results/p2/`, 3 repeats each).  The 256-worker
theory is wrong.

A window costs about 23 ms = 2 tasks x 11.6 ms, the same 11-12 ms that
every single task costs in `bench_dt_insitu.py` (its p50).  py-spy finds
the main process idle most of the time (553 active samples in about 20 s
at 200 Hz).  The cause is radical.asyncflow 0.5.1's `WorkflowEngine` run
loop (`workflow_manager.py`, the `else: await asyncio.sleep(0.01)`
branch): after an iteration that submitted or completed something it
sleeps 10 ms before it looks at the ready queue again, so a task that
becomes ready meanwhile waits for that sleep; the measured 11.6 ms per
task is about one sleep plus the pool round trip.  `diag_asyncflow_poll.py` patches only that sleep,
at run time, and reruns the harnesses unchanged (pool 8, 2 repeats):

| run-loop sleep | learner engine/inproc b=100 | engine/zmq b=100 | in-situ p50 bare / investigator / agent | c=50 req/s bare / agent |
|---|---|---|---|---|
| 0.01 (as installed) | 4,346 msg/s | 4,247 | 11.32 / 11.59 / 11.62 ms | 2,445 / 2,269 |
| 0.001 | 30,422 | 14,973 | 1.61 / 1.67 / 1.66 ms | 4,015 / 3,835 |
| 0 | 68,099 | 18,833 | 0.62 / 0.65 / 0.63 ms | 3,975 / 3,883 |

At 0.001 the learner hits the laptop's number (30,417 msg/s).  The DT
rows stay within 0.03-0.3 ms of bare at every setting, so the E1 claim
holds and gets stronger: the 11 ms that all rows share is the engine's
poll interval, not the DT layer.  Nothing installed was changed (the pins
are fixed for the paper runs); the sleep belongs to radical.asyncflow.

### P3: ex-situ learner, bare vs through DT (`bench_dt_exsitu.py`)

Same pool (8 workers), same no-op training / active-learning / criterion
tasks, criterion met every window.  bare = ROSE `StreamingActiveLearner`
fed in-process; dt = `StreamingLearnerInvestigator` in a `DTRuntime`, fed
by an external `ChannelPublisher` through `add_input`.  400 samples per
throughput run, 20 paced windows per latency run, 5 repeats:

| batch | bare msg/s | dt msg/s | dt/bare | paced publish p50 bare | dt |
|---|---|---|---|---|---|
| 1 | 29 | 29 | 1.00 | 35.1 ms | 33.8 ms |
| 10 | 286 | 287 | 1.00 | 35.2 ms | 33.9 ms |
| 100 | 2,880 | 3,028 | 1.05 | 35.3 ms | 32.4 ms |

The DT path costs nothing measurable ex-situ: same throughput (dt up to
5% faster at large windows) and the same publish latency (dt 1-3 ms
lower, which includes the extra hop through the stream broker).  Both
rows sit on the asyncflow floor: 3 tasks per window x about 11.7 ms.  The
dt row being slightly faster is not a DT gain I can explain; it most
likely reflects where its windows fall relative to the 10 ms run-loop
poll.  Full table: `../results/summary-pm-20261106.json`.
