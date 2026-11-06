# E5 Persistence

Outline, 2026-10-02.

- Repeated client loss: time to reattach; DT state intact.
- Endpoint loss: detection, then recovery.
- Long run: 30 days of uptime (STELLAR-AI milestone T3).
- Out of scope: broker loss.

Not started.

## Perlmutter batch 2026-11-06 (P6, preliminary): endpoint and client loss

`bench_endpoint_loss.py` on one CPU node over loopback: ORBIT broker
hosting `dt` only, an inference endpoint for the whole run, and a learning
endpoint the script SIGKILLs and restarts.  Twins as in the R8 integration
test: a learner twin (CountingSensor -> LinearLearner, training on the
learning endpoint) and an inference-only sibling in the same session.
Journal `../JOURNAL-pm-20261106.md`, raw data `../results/p6/`.

| metric (10 kills / 10 reattaches) | median | min-max |
|---|---|---|
| kill -> twin reports `failed` ("engine endpoint lost: ...") | 10.09 s | 10.05-10.16 s |
| in-situ answers during that window, learner twin / sibling | 200/200 / 200/200 | |
| endpoint restart -> advertises rhapsody | 1.25 s | 1.25-1.50 s |
| endpoint restart -> new session + twin serves a learned model | 2.82 s | 2.81-3.07 s |
| client stopped; fresh client reattaches by sid | 0.018 s | 0.018-0.019 s |
| ... to its first correct inference | 0.026 s | 0.025-0.027 s |

The loss is reported after the broker's 10 s suspect -> lost grace in
every case, and in-situ inference never stopped meanwhile: the learner
twin's own inference runs on the surviving inference endpoint and kept
answering until the twin was marked failed; the sibling never noticed.
A lost engine is terminal for the session (as the R8 test asserts), so
"recovery" is a new session and twin; with the endpoint back, learning
resumes in under 3 s.  Reattach by sid is immediate, twin state intact.
