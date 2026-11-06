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
