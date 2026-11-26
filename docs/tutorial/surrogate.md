# Your own surrogate

This page shows where your own model and simulation go in
`examples/surrogate/`.  Copy the directory and change three things.

```sh
cp -r examples/surrogate my-twin && cd my-twin
python run_local.py          # still works before you change anything
```

## 1. The simulation: `physics.py`

```python
--8<-- "examples/surrogate/physics.py"
```

`simulate(x)` is what the surrogate learns to replace.  Call your
solver, simulation code or a lookup into measured data here.  It runs
inside a training task, so it may be slow; it may also run on another
machine (see [Run the twin on the service](service.md)), so it must not
depend on files that exist only on yours.

## 2. The inputs: `dtypes.py` and `sensor.py`

Rename `READING` and `PREDICTION` to what your twin consumes and
produces.  Replace the random positions in `sensor.py` with your inputs,
or bind an external producer with `runtime.add_input` (see
[Concepts › Streams and sensors](concepts.md#streams-and-sensors)).
Payloads from outside the twin are JSON by default, so send numbers,
lists and dicts.

## 3. The model: `surrogate.py`

The model has two halves.  The **inference task** serves it, once per
input:

```python
--8<-- "examples/surrogate/surrogate.py:inference"
```

It is called with the published model as keyword arguments, here
`coeffs`, and returns a `TypedData` of the output type.  Replace
`np.polyval` with your model's prediction.  It runs in situ, for every
reading, so it has to be fast.

The **learning tasks** produce the model; [Train it online](learning.md)
explains them.  To serve a fixed, pre-trained model instead, subclass
`ModelInvestigator`, load the model in `__init__`, and publish it once in
`main_loop`:

```python
from radical.doppelganger import ModelInvestigator, TypedData

class Pretrained(ModelInvestigator):

    def __init__(self, flow):
        super().__init__(flow)
        self.weights = load_weights()          # your code

        @flow.function_task
        async def predict(x, weights=None):
            return my_model(weights, x)        # your code

        async def infer(in_data, weights=None):
            return TypedData(PREDICTION, await predict(in_data.data, weights))

        self.inference_task = infer

    async def main_loop(self, runtime):
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model({"weights": self.weights})
```

## Model size and form

The published model is passed to the inference task by value, and on the
service it crosses the network to the endpoint that runs the task.
Keep it to plain numbers, lists and small arrays: well under the 4 MiB
message limit.  For a large network, publish a path or URL that the
endpoint can read and load the weights inside the task.  See
[Status and limits › Sizes](../overview/status-and-limits.md#sizes).

## Check it

```sh
python run_local.py --timeout 300
```

`run_local.py` compares what the twin serves against `simulate` without
noise.  Adjust `PROBES` and the accuracy check in it to your problem.
