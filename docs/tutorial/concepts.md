# Concepts

A digital twin in Doppelganger is a **graph of components** connected by
**data types**.  Data enters the graph from sensors, flows from component
to component, and leaves as predictions.  A **runtime** executes one such
graph; the runtime and its graph are one twin.

## Data types and typed data

A `DataType` is a name, such as `DataType("reading")`.  A `TypedData`
pairs a data type with a payload:

```python
READING = DataType("reading")
sample = TypedData(READING, 1.5)
```

Every component is registered with an input type and an output type.
The runtime routes each `TypedData` to every component registered for
its type, and routes that component's result on as its output type.
There is no other wiring.

Two data types are special:

- `TRUTHY` as an input type means "run once, when the twin starts".
  Sources use it.
- `NULL_DTYPE` as an output type means "produces nothing".  Sinks use it.

## Components

There are three kinds.  Each receives the twin's execution engine,
`flow`, in its constructor and implements `async def main_loop`.

| Kind | Registered with | Role |
|---|---|---|
| `UtilityTask` | `runtime.add_task(task, in, out, is_persistent=False)` | transforms one input into one output: a filter, a unit conversion, a sink.  `main_loop(runtime, in_data)` runs once per input and returns a `TypedData` or `None`. |
| `ModelInvestigator` | `runtime.add_investigator(inv, in, out)` | owns a model.  Its `main_loop` runs once, when it is registered, and sets an **inference task**, which then answers every input with the current model.  It can publish a new model at any time. |
| `SciAgent` | `runtime.add_agent(agent, in, out)` | owns several investigators for one input/output pair and picks, per input, which one answers. |

At most one investigator or agent serves a given input → output pair.

### Persistent components

`add_task(..., is_persistent=True)` makes a utility task persistent: its
`main_loop` runs detached for the twin's lifetime instead of once per
input.  A persistent component publishes its output through
`runtime.stream.publish(dtype, value)` rather than returning it.  A
persistent task on `TRUTHY` is the usual way to write a sensor that lives
inside the twin.

### The inference task and model publishing

An investigator separates *serving* a model from *producing* it:

```python
class MyModel(ModelInvestigator):

    def __init__(self, flow):
        super().__init__(flow)

        @flow.function_task
        async def predict(x, weight=0.0):
            return weight * x

        async def infer(in_data, weight=0.0):
            return TypedData(PREDICTION, await predict(in_data.data, weight))

        self.inference_task = infer

    async def main_loop(self, runtime):
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model({"weight": 2.0})
```

`publish_new_model(model_kwargs)` stores the model; the runtime calls the
inference task with those keyword arguments for every input that
follows.  Publishing again swaps the model without stopping the twin.
Until the first publish, inference waits.

## Tasks and engines

`flow` is an AsyncFlow `WorkflowEngine`.  Decorating an `async def` with
`@flow.function_task` makes calling it submit a task to the engine's
backend and await its result.  Locally the backend is a thread pool.  On
the service it is an ORBIT endpoint, so the same decorated function runs
on a laptop, a cluster node or an HPC machine without changes.

Put expensive work (simulation, training, large inference) in function
tasks.  Keep `main_loop` bodies to coordination.

## Streams and sensors

Each twin has a stream client with its own namespace.  Components
publish into it with `runtime.stream`, and the runtime routes what
arrives by data type.  Sensors come in two forms:

- **Inside the twin**: a persistent `UtilityTask` on `TRUTHY` that
  publishes readings.  `examples/surrogate/sensor.py` is one.
- **Outside the twin**: a separate process, such as an instrument, a
  replay of archived data or a simulation, publishing to a shared
  channel with `ChannelPublisher`.  The twin binds the channel to a data
  type with `runtime.add_input(dtype, channel)`.  Any number of twins can
  bind the same channel, and each receives every message.
  `test/01-start-inference-stop/` shows this form.

External payloads are JSON by default (`codec="json"`); `"raw"` passes
bytes.  `"cloudpickle"` executes code on decode, so use it only for
producers you trust as much as the service itself.

## Asking the twin

`await runtime.get_inference(TypedData(READING, x), PREDICTION)` sends
one input to the component that serves `READING → PREDICTION` and
returns its answer to the caller.  It is how a client queries a twin.
The answer goes only to the caller; components downstream do not see
it.  The input is an input like any other for the serving component:
its `ON_INPUT` subscribers see it, so a streaming learner adds it to its
next window.  Keep held-out evaluation data out of `get_inference`.

## In-situ and ex-situ

**In situ** means inside the twin's per-input path: the inference task
runs for every reading and has to keep up with the stream.  **Ex situ**
means alongside it: training on windows of data, on other hardware, at
its own pace.  `StreamingLearnerInvestigator` combines both: one stream
feeds its learner ex situ and is served by its inference task in situ.
See [Train it online](learning.md).

## More graph patterns

The `test/` directory holds one runnable demo per pattern:

| Pattern | Demo |
|---|---|
| a sensor in its own process, bound by channel | `test/01-start-inference-stop/` |
| replace the model while the twin runs | `test/02-start-redeploy-stop/`, `test/03-conditional-redeploy/` |
| an agent choosing between investigators | `test/04-start-agent-stop/`, `test/05-agent-w-multi-investigators/` |
| a barrier: wait for several inputs, or window one | `test/07-barrier/` |
| join two streams into one input | `test/08-data-join/` |
| split one input into several outputs | `test/10-data-split/` |
| a simulation shared by several investigators | `test/11-shared-sim/` |

Each demo runs in three terminals: `python test/local_broker.py` (the
stream broker), `python run_me.py` in the demo's directory, and its
`sensor.py` if it has one.  `DT_STREAM_PUB_ADDR` and `DT_STREAM_SUB_ADDR`
move the broker from its default `tcp://127.0.0.1:5000` and `:5001`; set
them the same in every terminal.

## On the service

The service adds two concepts:

- A **session** belongs to one client and outlives it.  It owns the
  execution engines, one per configured role (`inference`, `learning`,
  or a named site), and all its twins share them.
- A **twin** on the service is a `DTRuntime` the service runs for you.
  You build its graph with the same calls, through the client:
  `dt.add_task(twin, dt.package(MySensor), TRUTHY, READING, ...)`.

See [Run the twin on the service](service.md).
