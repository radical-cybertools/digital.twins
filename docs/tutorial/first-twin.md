# Your first twin

This page runs a complete twin on your machine in under a minute, then
walks through its code.  It needs the `learn` extra and nothing else: no
service, no HPC, no configuration.

## Run it

```sh
git clone https://github.com/radical-cybertools/digital.twins
cd digital.twins/examples/surrogate
python run_local.py
```

You see the learner's progress and, every two seconds, the error of the
predictions the twin serves:

```
stop criterion metric: rmse is not met yet (0.1135...)
served surrogate rmse: 0.7790
stop criterion metric: rmse is met with value of: 0.0439... . Breaking the active learning loop
served surrogate rmse: 0.0329
surrogate is accurate: done
```

The twin starts with an empty model, which predicts `0.0` everywhere.
It learns a surrogate for a simulation from its own input stream, and
the served error drops once the first good fit is published.  The
"Breaking the active learning loop" line is ROSE's wording; in a twin the
learner keeps running and keeps refining the model.

## What is in the example

```
examples/surrogate/
├── dtypes.py        the data types: READING, PREDICTION
├── physics.py       the expensive simulation the surrogate replaces
├── sensor.py        a synthetic sensor
├── surrogate.py     the surrogate model and how it is trained
├── sink.py          the end of the graph
├── run_local.py     runs the twin in this process
└── run_service.py   runs the same twin on a DTaaS service
```

The graph is three components connected by two data types:

```
Sensor ──READING──▶ Surrogate ──PREDICTION──▶ Sink
```

## The data types

```python
--8<-- "examples/surrogate/dtypes.py"
```

A `DataType` is a name.  The runtime connects components by the types
they consume and produce.

## The sensor

```python
--8<-- "examples/surrogate/sensor.py"
```

Registered on `TRUTHY`, a component runs once when the twin starts.
This one loops forever and publishes readings into the twin's stream.

## Putting it together

```python
--8<-- "examples/surrogate/run_local.py:main"
```

The five numbered steps are all a local twin needs: a stream broker, an
execution engine, a runtime, the graph, and something that uses it.
`runtime.get_inference` sends one input through the graph and returns
the answer to the caller.

[Concepts](concepts.md) explains each of these parts.
[Your own surrogate](surrogate.md) replaces the model with yours.
