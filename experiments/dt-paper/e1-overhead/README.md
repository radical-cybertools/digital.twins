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

Perlmutter (2026-11-05, one CPU node `nid200018`, Python 3.13.18,
Slurm job 60879182, local pool, n=1000; median of 3 repeats per row,
raw data in `results/insitu-pm-pool*-c*-r[123]-20261105.json`):

| row                 | pool 8, c=50         | pool 8, c=500        | pool 64, c=50        | pool 64, c=500       |
|---------------------|----------------------|----------------------|----------------------|----------------------|
| bare asyncflow task | 11.44 ms, 2434 req/s | 11.65 ms, 4449 req/s | 11.89 ms, 2181 req/s | 11.91 ms, 3528 req/s |
| DT investigator     | 11.53 ms, 2408 req/s | 11.67 ms, 4345 req/s | 11.91 ms, 2084 req/s | 11.87 ms, 3261 req/s |
| DT agent + selector | 11.53 ms, 2435 req/s | 11.66 ms, 3928 req/s | 11.94 ms, 2069 req/s | 11.96 ms, 3253 req/s |

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
