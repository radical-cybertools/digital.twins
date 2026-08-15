# Performance harnesses

## `bench_insitu.py` — in-situ inference latency

The harness behind the compute-placement decision: one no-op asyncflow
function task per call, awaited sequentially (the shape of an in-situ
prediction), plus a 50-way concurrency probe.

```sh
# against the integration stack (test/integration/conftest.py starts one)
python perf/bench_insitu.py both \
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
python perf/bench_streams.py both --broker https://127.0.0.1:8031
```

Loopback, one host, bare-int payloads (2026-08-15):

| data plane                  | p50     | p99     | burst          |
|-----------------------------|---------|---------|----------------|
| zmq, embedded broker        | 0.84 ms | 1.14 ms | 20 400 msg/s   |
| orbit eventing              | 1.94 ms | 2.47 ms |  5 300 msg/s   |

With 64 KiB payloads (`--payload 65536`): 1.04 ms / 3.04 ms p50, and
6 800 vs 1 100 msg/s in burst.

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
