# E4 Hot-swap

Update components while the DT runs.  (Outline, 2026-10-02.)

- Baseline: TBD; Flink, which stops, checkpoints and restarts.
- Metrics:
  - turnaround per update
  - throughput dip at a given update rate
  - model-update propagation latency (stream → learner → published
    model → inference)

Not started.

## Perlmutter batch 2026-11-06 (P7, preliminary): model-update propagation

`bench_model_update.py`: one twin, one `ModelInvestigator` publishing model
versions v = 1..N every `--interval` (`publish_new_model({"v": v})`); the
inference is an asyncflow function task returning the version it ran
with; one client calls `get_inference` back to back.  Latency = first
answer carrying v (or newer) minus the publish time of v.  Only the
publish -> inference half of the chain; the stream -> learner half is
E1 P3 (`../e1-overhead/README.md`).  Journal `../JOURNAL-pm-20261106.md`,
raw data `../results/p7/`.

Local process pool (8 workers), one CPU node, 3 repeats:

| publish interval | versions seen | answered p50 | answered p90 | one inference p50 |
|---|---|---|---|---|
| 1 s | 100 % | 16.65 ms | 20.26 ms | 11.51 ms |
| 100 ms | 100 % | 16.35 ms | 20.53 ms | 11.63 ms |
| 10 ms | 93.6 % | 16.21 ms | 20.09 ms | 10.57 ms |

A new model is served on the next request: the propagation latency is
about 1.5 inference times (the in-flight request finishes with the old
model, the next one uses the new), independent of the update rate.  At a
10 ms interval, faster than one inference, 6 % of the versions are
replaced before any request sees them; nothing queues up.  The inference
time is again the asyncflow floor (P2).

Through ORBIT (P4 layout: broker + client on node 0; endpoint on node 1
"cross", or on node 0 "loop"; notify window 0), 3 repeats:

| publish interval | cross: seen / answered p50 / inference p50 | loop: seen / answered p50 / inference p50 |
|---|---|---|
| 1 s | 100 % / 22.14 ms / 14.77 ms | 100 % / 21.36 ms / 14.72 ms |
| 100 ms | 100 % / 22.35 ms / 14.84 ms | 100 % / 21.09 ms / 14.52 ms |
| 10 ms | 66 % / 21.89 ms / 15.04 ms | 68 % / 22.18 ms / 14.69 ms |

Same shape: about 1.5 inference times, independent of the update rate.
The network hop between nodes adds less than 1 ms; ORBIT adds about 3 ms
per inference over the local pool (as in E1 run C).

## Perlmutter round 3, 2026-11-09 (T5; `JOURNAL-pm-20261110.md`)

Tables: `results/r3/t45-tables-stack-r3-20261110.md` (medians over 5
repeats, min-max in brackets).  Local pool 8: job 61061603 (swap, dip),
61060406 (P7); ORBIT cross-node (P4 layout, unpatched endpoint): 61061605.

### A: hot-swap turnaround (`bench_swap.py`)

A running twin with an agent and investigator v0; under closed-loop
inference the agent starts investigator v_k (`RuntimeAPI.start_investigator`,
main loop starts at once) and switches its selector to it
(`update_model_selector`); 20 swaps per run.  (The page named the
twin-level `DTRuntime.add_investigator`; an agent's selector picks only
among the agent's own investigators, so the agent-side call is the one
that swaps.)  Turnaround = the start call to the first answer from v_k.

| layout | c | swaps | missed | turnaround p50 ms | p90 | max | stale answers |
|---|---|---|---|---|---|---|---|
| pool 8 | 1 | 100 | 0 | 0.77 | 1.26 | 1.30 | 0 |
| pool 8 | 50 | 100 | 0 | 16.5 | 18.9 | 19.6 | 12 |
| ORBIT cross | 1 | 100 | 0 | 5.1 | 7.2 | 33 (one run 69) | 0 |
| ORBIT cross | 50 | 100 | 0 | 170 | 182 | 207 | 0 |

At c=1 a swap takes about one inference (local 0.6 ms, cross-node 4-5 ms
inference p50): the new investigator publishes its model in its first
main-loop step and the next request is already served by it; no request
fails or waits on a missing model.  At c=50 the turnaround is the queue of
50 in-flight requests ahead of the first new one (local c=50 inference p50
about 16 ms, see B).  "Stale" counts answers from an older investigator
after v_k's first answer (requests issued before the switch and answered
after it): 12 of about 50k answers locally, none through ORBIT.

### B: throughput dip under model publishing (`e2-scaling/bench_publish.py`)

Closed-loop inference at c=50 on pool 8 while the investigator publishes
models at 0, 1, 10, 100 per second:

| models/s | req/s | x rate 0 | p50 ms | x rate 0 |
|---|---|---|---|---|
| 0 | 3063 | 1.00 | 15.5 | 1.00 |
| 1 | 3002 | 0.99 | 15.8 | 1.01 |
| 10 | 2927 | 0.94 | 16.1 | 1.05 |
| 100 | 2927 | 0.96 | 15.7 | 1.01 |

Publishing up to 100 models/s costs inference at most 6% of throughput
and 5% of p50; 92-96% of the published versions serve at least one answer
at 100/s.

### C: round 2's P7 with 5 repeats (`bench_model_update.py`)

| layout | interval s | versions seen | answered p50 ms | inference p50 ms |
|---|---|---|---|---|
| pool 8 | 1 | 100% | 0.63 | 0.59 |
| pool 8 | 0.1 | 98% | 0.68 | 0.60 |
| pool 8 | 0.01 | 100% | 0.66 | 0.61 |
| ORBIT cross | 1 | 100% | 6.99 | 4.26 |
| ORBIT cross | 0.1 | 100% | 6.81 | 4.44 |
| ORBIT cross | 0.01 | 100% | 7.49 | 5.12 |

A published model serves its first answer within about one inference
(plus one in flight): 0.6-0.7 ms locally, 7-7.5 ms cross-node.  Inference
p50 through ORBIT grows from 4.3 to 5.1 ms over the three intervals of one
run: the session-age slowdown of T1 (one client session, about 15k tasks).
