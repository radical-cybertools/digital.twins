# Learner Demo: ex-situ retraining, in-situ inference

Digital twin application:
- sensor: a stream of raw readings (persistent component, running inline
  on the service loop and publishing through its injected stream client)
- calibration learner: a `StreamingLearnerInvestigator` -- a ROSE
  `StreamingActiveLearner` embedded in a model investigator
- data sink

One stream drives both halves of the twin.  Every reading feeds the
learner (through `ON_INPUT`) *and* is served by the inference task.
Each window of 8 readings runs one training / active-learning /
criterion iteration; when the resulting calibration beats the criterion
it is published, and the next prediction already uses it.

## The dual-engine wiring

This is the demo's point, so it is spelled out rather than defaulted:

```python
ENGINES = {'engines': {
    'task':   {'endpoint_name': TASK_ENDPOINT,   'backends': ['concurrent']},
    'exsitu': {'endpoint_name': EXSITU_ENDPOINT, 'backends': ['concurrent']},
}}
```

- **`'task'`** runs the twin's components, including the inference task.
  It sits in the per-reading critical path, so it belongs on a
  co-located endpoint.
- **`'exsitu'`** runs the learner's training, active-learning and
  criterion tasks -- the expensive half, typically on remote HPC
  hardware.

There is no `engine=` argument anywhere.  The service picks the engines
by *class*: `StreamingLearnerInvestigator` (and only it) is instantiated
with the ex-situ engine as `learn_flow` on top of the usual `flow`, and
`model.py` hands one to the learner and the other to the inference task.
Both engines are session-shared and built once, in the background phase
of `twin_create`.

`'exsitu'` is optional.  Left out of the config it aliases `'task'`, so
this demo also runs against a single endpoint -- the twin is then simply
sharing one endpoint between learning and inference.

## Why the learner tasks are function tasks

The learner's three tasks are registered with `as_executable=False`, so
ROSE submits them as **cloudpickled function tasks** instead of shell
commands.  A command line with local paths (ROSE's default, and what
`test/rose_streaming` uses) only runs where those paths exist: it does
not survive an `'exsitu'` endpoint that shares no filesystem with the
service.  The backend's Python-version guard and the wire's version
stamp cover the rest.

Two consequences visible in `model.py`:

- the criterion task gets its model by *value*, cloudpickled with the
  task, rather than by reading a `model.json` the training task left
  behind -- there is no shared filesystem to leave it on;
- the training task returns its model as a dict.  Rich return values
  round-trip (ORBIT cloudpickles non-JSON results back), and ROSE
  registers a returned dict as learner state, which is what
  `published_model()` turns into the inference task's kwargs.

## Running it

Four terminals.  All of them need `pip install .[service,learn]` and the
ORBIT broker cert/token in `~/.radical/orbit/`.

```sh
# 1 - the ORBIT broker, hosting the dt plugin
radical-orbit-broker.py --plugins default,dt

# 2 - the co-located endpoint: the twin's components and inference
RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
radical-orbit-endpoint.py -n dt_task_ep

# 3 - the ex-situ endpoint: the learner's tasks.  It keeps the default
#     notify window -- 250 ms is noise under a training task
RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
radical-orbit-endpoint.py -n dt_exsitu_ep

# 4 - the client
cd test/10-learner
DT_TASK_ENDPOINT=dt_task_ep DT_EXSITU_ENDPOINT=dt_exsitu_ep python run_me.py
```

## What to watch

`run_me.py` asks the twin for the same reading (`4.0`) every few
seconds.  The uncalibrated bootstrap model answers `0.000`; as windows
are learned the answer climbs to the true calibration
(`2.5 * 4.0 + 1.0 = 11.0`).  Nothing about the *request* changes -- only
the model behind it.
