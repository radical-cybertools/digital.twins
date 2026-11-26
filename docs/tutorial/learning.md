# Train it online

`Surrogate` in `examples/surrogate/surrogate.py` is a
`StreamingLearnerInvestigator`: a model investigator with a ROSE
streaming active learner inside.  Every input the twin receives is both
answered by the inference task and fed to the learner.

## One window, one iteration

The learner collects inputs into windows of `batch_size` items, or
whatever arrived within `max_wait` seconds.  Each window runs three
tasks in order:

```
window ──▶ training ──▶ active_learn ──▶ criterion ──▶ met? publish the model
              ▲              │
              └── previous ──┘   (warm start for the next window)
```

```python
--8<-- "examples/surrogate/surrogate.py:learning"
```

- **training** gets the window, labels it with the expensive simulation
  and fits a model.  It returns the model as a dict; ROSE records every
  key of it as learner state.  `previous` is the model the last window's
  `active_learn` returned.
- **active_learn** chooses what to learn next.  A real one picks the
  inputs worth simulating; this one passes the model on as the next
  window's warm start.
- **criterion** scores the model and returns one number.  When it beats
  `threshold` under `operator`, the learner state becomes the published
  model, and the very next prediction uses it.  In a twin the criterion
  is a publish gate: learning continues after it is met.

`bootstrap_model()` is what the twin serves before the first window is
learned.  Inference waits for a published model, so every learner needs
one.

## Rules for learner tasks

- **Register them with `as_executable=False`.**  ROSE's default makes a
  task a shell command, and a command line with local paths does not run
  on an endpoint that shares no filesystem with you.  With
  `as_executable=False` the task is a Python function, shipped by value.
  The investigator warns when it finds executable tasks.
- **The criterion's model travels with it.**  ROSE passes the criterion
  no input from the loop, so the example captures `latest`, a dict that
  mirrors learner state, as a default argument.  It is shipped with every
  criterion call; keep the state small.
- **Return plain values.**  A dict of numbers and lists survives every
  path; see [Status and limits › Sizes](../overview/status-and-limits.md#sizes).

## Tuning

| Knob | Where | Effect |
|---|---|---|
| `batch_size` | `super().__init__(..., batch_size=)` | inputs per window: larger windows give better fits and fewer updates |
| `max_wait` | `super().__init__(..., max_wait=)` | seconds before a partial window is learned anyway |
| `conflate` | `super().__init__(..., conflate=True)` | the default: a stream faster than the learner drops its backlog instead of queuing it |
| threshold, operator | `as_stop_criterion(...)` | when a model is good enough to serve |

The window metrics appear in the twin's `metrics` on the service and as
a convergence bar in the [dashboard](../use/dashboard.md).

## Learning on other hardware

Locally, every task runs on the one engine.  On the service, the learner
tasks carry the `learning` role and the inference task the default
`inference` role, and a session can put the two roles on different
endpoints: inference next to the data, learning on an HPC allocation.
Nothing in `surrogate.py` changes for that; see
[Run the twin on the service](service.md#two-endpoints-inference-and-learning).
