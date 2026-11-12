# E4 on the laptop, 2026-11-12: the DT and an Apache Flink baseline

Same machine (i7-12800H, 20 threads, 62 GB, shared, load average 4-9).

## DT (`dt/`, paper stack, pool 8, 5 repeats)

`bench_swap.py --workers 8 --concurrency {1,50} --swaps 20 --interval 0.5`,
`bench_model_update.py --workers 8 --intervals 1,0.1,0.01 --seconds 20`,
`bench_publish.py --workers 8 --concurrency 50 --rates 0,1,10,100`.

- inference p50 2.56 ms (Perlmutter: about 0.6 ms)
- swap to first answer from the new investigator: c=1 4.2 ms (3.5-5.1),
  0 missed; c=50 53 ms (36-61), 0 missed, 34 stale of about 50k
- publish to first answer with the new model: 3.9 / 4.3 / 4.4 ms at
  1 s / 100 ms / 10 ms; every version seen
- throughput while publishing 1 / 10 / 100 models/s: 1.06 / 0.99 / 0.97x
  (repeat range 0.87-1.32)

## Flink (`flink/`, Apache Flink 2.2.1, JDK 17, standalone, p=1)

Java DataStream jobs (`job-src/`), driver and analysis scripts next to them;
`tables.md` has every number.  Two update paths:

- code swap, stop-with-savepoint then resubmit: 127 ms (108-151) via the
  REST API, about 8 s via the `flink` CLI, about 1 s with 1 MB of operator
  state; about 120 ms without answers (requests wait, none lost or
  duplicated)
- model parameters via broadcast state: publish to first answer
  0.23-0.27 ms (0.8-1.0 ms with 0.5 ms of work per inference); no
  throughput dip at 1 / 10 / 100 updates/s

A code swap in Flink restarts the job graph (new classloader, redeploy,
state restore, with exactly-once state migration); the DT adds an
investigator to the running twin and switches the agent's selector.
