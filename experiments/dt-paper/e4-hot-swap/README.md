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
