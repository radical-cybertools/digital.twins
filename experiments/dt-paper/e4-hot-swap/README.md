# E4 Hot-swap

Update components while the DT runs.  (Outline, 2026-10-02.)

- Baseline: TBD; Flink, which stops, checkpoints and restarts.
- Metrics:
  - turnaround per update
  - throughput dip at a given update rate
  - model-update propagation latency (stream → learner → published
    model → inference)

Not started.
