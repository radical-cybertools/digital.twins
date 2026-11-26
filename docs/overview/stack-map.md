# The stack

Doppelganger is the top layer of a stack of RADICAL components.  Each
layer has its own documentation; this page says what each one does for
a twin and where to read more.

| Layer | Package | What it does for a twin | Docs |
|---|---|---|---|
| L5 twin framework | `radical.doppelganger` | the component model (tasks, investigators, agents), the twin runtime, streams, the `dt` service plugin and its client | this site |
| L4 active learning | `rose` (ROSE) | the streaming active learner behind `StreamingLearnerInvestigator` | [ROSE](https://github.com/radical-cybertools/ROSE) |
| L3 workflow engine | `radical.asyncflow` | `WorkflowEngine`: async function tasks a component submits | [AsyncFlow](https://github.com/radical-cybertools/radical.asyncflow) |
| L2 execution | `rhapsody-py` (Rhapsody) | execution backends that run those tasks: local threads or processes, Dragon on HPC, or a remote endpoint | [Rhapsody](https://radical-cybertools.github.io/rhapsody) |
| L1 connectivity | `radical.orbit` (ORBIT) | the broker, endpoints, token authentication and eventing that connect client, service and HPC | [ORBIT](https://radicalorbit.readthedocs.io/en/latest/) |

## How a twin uses the layers

**Locally**, a twin is a `DTRuntime` in your process.  Its components
submit tasks to an AsyncFlow `WorkflowEngine` on a local Rhapsody backend
(a thread pool), and its streams run through a small ZMQ broker.  ORBIT
is not involved.

**On the service**, the same components are shipped to an ORBIT broker
that hosts the `dt` plugin.  The plugin runs one `DTRuntime` per twin.
Its engines are AsyncFlow engines whose Rhapsody backend forwards every
task to an ORBIT endpoint, which executes it locally, on a cluster with
Dragon, or anywhere else an endpoint runs.  Streams can ride ORBIT's
eventing, inside the same token-authenticated connection.

```
client ── ships components, calls verbs ──▶ broker + dt plugin (twins live here)
                                                 │ tasks
                                                 ▼
                                     endpoint(s): laptop, cluster, HPC
```

## What you need to know about the layers below

To build a twin you need only two concepts from below this layer:

- an AsyncFlow `WorkflowEngine` (`flow`), passed to every component.
  `@flow.function_task` turns an `async def` into a task that runs on
  the engine's backend.
- for the service, an ORBIT broker URL and token.  The
  [ORBIT getting-started guide](https://radicalorbit.readthedocs.io/en/latest/getting_started/)
  covers both.
