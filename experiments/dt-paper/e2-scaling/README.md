# E2 Scaling

How do inputs per second and DT size scale?  (Outline, 2026-10-02.)

- Axes: number of streams (via join) × number of agents, side by side or
  chained.
- Same metrics as E1, plus model-publish throughput.
- Also: DTs and sessions per broker until the broker saturates.
- Have: placeholder plots only (`p_charts.ipynb`).

## Perlmutter batch 2026-11-06 (P5, preliminary)

First real numbers, from `bench_twins.py` and `bench_streams_join.py`
(one CPU node, local process pool, embedded ZMQ broker; journal
`../JOURNAL-pm-20261106.md`, raw data `../results/p5/`, 3 repeats each).
Preliminary: one node, no-op work, one engine.

**E2a, N twins on one engine (pool 64), closed loop, one client per twin:**

| twins | aggregate req/s | p50 per twin | p99 per twin |
|---|---|---|---|
| 1 | 84 | 11.96 ms | 12.11 ms |
| 4 | 367 | 10.58 ms | 12.54 ms |
| 16 | 1,450 | 10.82 ms | 12.48 ms |
| 32 | 2,681 | 11.07 ms | 16.00 ms |
| 64 | 2,812 | 20.91 ms | 25.97 ms |

Linear up to 32 twins at an unchanged per-request latency (the ~11 ms
asyncflow floor, see `../e1-overhead/README.md` P2); at 64 the engine
saturates at about 2.8k req/s and latency doubles.  The worst twin is
within 0.1 ms of the median twin at every N: no twin is starved.

**E2b, K input streams joined (`add_data_join`) into one consumer.**
Lockstep rounds (one message per stream per round); max sustainable =
highest rate whose p50 stays below twice the 10 rounds/s p50, with no
dropped or misaligned tuples (none were dropped at any tested rate):

| K | rounds/s | inputs/s | p50 at that rate | p50 at 10/s |
|---|---|---|---|---|
| 1 | 5,000 | 5,000 | 0.26 ms | 0.89 ms |
| 2 | 2,000 | 4,000 | 0.44 ms | 0.90 ms |
| 4 | 2,000 | 8,000 | 0.86 ms | 1.01 ms |
| 8 | 1,000 | 8,000 | 0.88 ms | 1.24 ms |
| 16 | 500 | 8,000 | 0.88 ms | 1.49 ms |
| 32 | 200 | 6,400 | 1.78 ms | 1.95 ms |

The join sustains about 8k inputs/s in total, independent of K from 4 to
16; past that a backlog forms and p50 jumps from about 1 ms to hundreds of
ms (full grid in `../results/summary-pm-20261106.json`).  Latency falls
with rate up to about 1k/s (a busy event loop answers faster than an idle
one).  K=2 had one repeat sustaining 5,000 rounds/s, hence its range.

## Perlmutter round 3, 2026-11-09 (T4; `JOURNAL-pm-20261110.md`)

Tables: `results/r3/t45-tables-stack-r3-20261110.md` (medians over 5
repeats, min-max in brackets).  Jobs: 61060406 (E2a/E2b reruns),
61061603 (agents, publish), 61061984 / 61062231 (broker capacity).

### A: agents per twin (`bench_agents.py`)

One twin, M agents (selector + investigator, pass-through inference, no
task runs), embedded ZMQ broker, external `ChannelPublisher`s; rate grid
10, 50, 100, 200, 500, 1000, 2000, 5000, 10000 rounds/s, 3 s per point;
the max sustainable rate is the last before p50 doubles against 10/s or an
output is lost (none was lost: every step failed on p50, i.e. backlog).

| M | side by side, inputs/s | p50 ms | chained, inputs/s at the end | p50 ms |
|---|---|---|---|---|
| 1 | 5000 | 0.31 | 5000 | 0.31 |
| 2 | 4000 | 0.54 | 2000 | 0.46 |
| 4 | 4000 | 0.67 | 2000 | 0.61 |
| 8 | 4000 (one run 8000) | 0.88 | 2000 | 0.56 |
| 16 | 8000 | 1.70 | 1000 | 1.37 |

Side by side, one twin serves 4000-8000 agent inputs/s in total whatever
M: the agents share one event loop, so the twin's routing capacity is the
limit, not the agent count.  A chain passes each input through every
stage, so its end rate falls with M: about 2000/s up to M=8, 1000/s at
M=16 (2000 x 8 = 16k and 1000 x 16 = 16k stage passes/s).  The grid is
coarse (2000 -> 5000), so the numbers are lower bounds at the grid points.

### B: model publishing as fast as possible (`bench_publish.py`, c=1)

| models/s target | published/s | seen by inference/s | req/s | x no publishing | p50 ms |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 1675 | 1.00 | 0.58 |
| 1 | 1 | 1 | 1628 | 0.97 | 0.59 |
| 100 | 100 | 98 | 1642 | 0.98 | 0.59 |
| 1000 | 1000 | 975 | 1617 | 0.97 | 0.60 |
| max | 163k | 469 | 469 | 0.28 | 1.43 |

Up to 1000 models/s publishing is free for inference (within 3%) and
inference sees 97-98% of the versions.  A learner that publishes as fast
as it can (163k models/s, one per event-loop turn) starves inference to
0.28x; every answer then carries a different model.

### C: broker capacity (`bench_broker.py`)

N sessions on one broker's `dt` plugin (node 0, throwaway TLS), one twin
each (`OffsetModel`, inference = one function task on the endpoint, node
1), closed-loop `get_inference` at c=1 per twin from one client process
(node 2, one thread per twin).  Broker CPU and RSS from `/proc` every
second (`results/r3/t4/broker-proc-*.txt`).

| N | create s | aggregate req/s | p50 ms | p99 ms | broker CPU | broker RSS |
|---|---|---|---|---|---|---|
| 1 | 2.0 | 147-153 | 6.4-6.6 | 7.7-8.2 | 56% of a core | 90 MB |
| 4 | 0.6 | 243 | 15.6 | 25.3 | 96% | 110 MB |
| 16 | 0.8 | 290 | 53 | 137 | about 110% | - |
| 64 | 3.8 | 264 | 233 | 401 | about 110% | 545 MB |
| 256 | - | - | - | - | 110-114% | 760-845 MB |

Job 61061984 stopped at N=4 (p50 doubled: 6.6 -> 15.6 ms).  Job 61062231
went on (`--keep-going`, 10 s per point): at N=256 the sessions were still
being created after 20 minutes, the broker held 110-114% CPU and 0.8 GB
RSS, and the client's websocket timed out on keepalive pings 100 times
(`connection lost: ... keepalive ping timeout; reconnecting`); cancelled
after 21 minutes, no session creation error was ever returned.  (Job
61061605's first try failed at N=1 for a setup reason: the broker lacked
`RADICAL_ORBIT_BROKER_URL`, which a twin in its `dt` plugin needs for its
engine.)

The broker's dt service is CPU-bound on about one core: aggregate
throughput saturates at about 250-290 req/s from N=4 on, and past that
more sessions only add queueing (p50 grows with N).  At 256 sessions the
saturated broker no longer answers its own keepalives in time and session
creation stalls rather than fails.  The client side is one Python process
with one thread per twin, so part of the latency at large N may be the
client's; the broker's CPU says the broker is the limit.

### D: round 2's E2a / E2b with 5 repeats

E2a, N twins on one engine (pool 64), aggregate req/s: 1 twin 1346, 2:
2095, 4-64: 2112-2214 (flat); per-twin p50 0.72 ms at 1, 28.5 ms at 64.
E2b, max sustainable inputs/s by joined streams: 1: 5000, 2: 4000, 4-16:
8000, 32: 6400.
