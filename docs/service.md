# Digital twins as a service: user guide

This guide covers the client side of the `dt` ORBIT plugin: how a twin is
built, fed, observed and closed through `DTClient`.  Deployment (broker,
endpoints), the dashboard, endpoint loss (R8) and the data-plane trust
boundary (R7) are in the [README](../README.md#running-it-as-a-service-the-dt-orbit-plugin).
`test/09-service/` is a complete worked example.

## Concepts

| Role | What it is |
|------|------------|
| Client | Your process.  It holds a `DTClient`, ships component classes and steers twins.  It can leave and reattach. |
| Broker | The ORBIT broker hosting the `dt` plugin.  Twins live here, and it is the only publicly reachable component. |
| Endpoint | An ORBIT endpoint with the rhapsody plugin.  The twins' tasks execute here, on HPC or locally. |
| Instrument | An external producer (sensor, archive replay, simulation) publishing to a named channel. |

A **session** belongs to one client and outlives it.  It owns the execution
engines, which all its twins share.  A **twin** is one `DTRuntime`: a graph of
components connected by dtypes, plus its own stream namespace.

## Twin lifecycle

```
initializing -> ready -> running -> stopped
      |           |         |
      +-----------+---------+-----> failed
```

- `create_twin` registers the twin and returns at once.  The engines and the
  stream connection come up in the background (`initializing`).  With the
  default `wait=True` the client polls until the twin is `ready`.
- Graph verbs (`add_*`) are accepted in `ready` and `running`, and refused
  once the twin is `stopped` or `failed`.
- `start` runs the graph; `stop` is terminal in v1.
- `failed` is terminal and carries the reason in `last_error`, for example a
  component that raised or an engine endpoint that was lost.
- `twin_close` stops the twin and removes it.  The state then reads `closed`.

`create_twin` takes a client-generated id.  Re-issuing it with the same id
after a lost response is a no-op, so the one asynchronous verb is safe to
retry.  `start`, `stop` and `twin_close` are idempotent too.

## Client API

Get a client from a running `EndpointRuntime`:

```python
dt = rt.get_plugin('broker', 'dt', config=SESSION_CONFIG)   # new session
dt = rt.get_plugin('broker', 'dt', sid=old_sid)             # reattach
```

| Call | Purpose |
|------|---------|
| `package(cls, *args, **kwargs)` | Ship a component class and its constructor arguments.  The service instantiates it with the session engine as the leading `flow` argument. |
| `register_user_modules([mod, ...])` | Ship modules that are not installed on the service (call once, before `package`). |
| `create_twin(twin_id=None, wait=True)` | Create a twin and return its id. |
| `add_task(twin, pkg, in_dtype, out_dtype, is_persistent=False)` | Add a utility task.  Persistent tasks run inline on the service loop (see the README contract notes). |
| `add_investigator(twin, pkg, in_dtype, out_dtype)` | Add a model investigator. |
| `add_agent(twin, pkg, in_dtype, out_dtype)` | Add a science agent. |
| `add_input(twin, dtype, channel, codec='json')` | Bind an external channel to an input dtype (see below). |
| `add_data_join(twin, join_dtype)` | Emit one joined event per complete set of the member dtypes. |
| `start(twin)` / `stop(twin)` | Run the graph / stop it (terminal). |
| `get_inference(twin, typed_data, out_dtype, timeout=600)` | Run one inference through the graph and return the `TypedData` result. |
| `describe(twin)` | The graph as a serializable summary. |
| `twin_list()` / `twin(twin_id)` | State of all twins in the session / of one twin. |
| `twin_close(twin)` | Stop and remove a twin. |
| `admin_sessions()` | Every session and twin on the service, with errors. |

Barriers and split tasks are not exposed through the service yet (#30).

## Session configuration

The `config` passed when the session is created selects the engines.  It
applies at creation only.

```python
SESSION_CONFIG = {
    'engines': {
        'inference': {'endpoint_name': 'dt_inference_ep', 'backends': ['concurrent']},
        'learning':  {'endpoint_name': 'dt_learning_ep',  'backends': ['concurrent']},
    },
}
```

- `inference` runs the twins' components.
- `learning` is optional.  It receives the learner tasks of a
  `StreamingLearnerInvestigator`.  Left out, it aliases `inference`.
- A role can name a dispatcher-managed pool instead of an endpoint
  (`{'pool': 'exsitu'}`), with the pool configs listed once under
  `'pools'`.  Pool-backed roles survive the loss of single endpoints.

Both engines are built once per session and shared by its twins.

## Feeding a twin: external channels

Instruments are not twin components.  They publish to a named channel, and
any number of twins bind that channel with `add_input`:

```python
from digitaltwin.streaming import ChannelPublisher, PubSubConfig

dt.add_input(twin, SENSOR, 'lab/probe-3')          # returns once the binding is live

pub = await ChannelPublisher.open('lab/probe-3', config=PubSubConfig(
    kind='zmq', pub_addr=pub_addr, sub_addr=sub_addr))
await pub.publish({'t': 12.5, 'value': 0.83})
await pub.close()
```

- `codec` is `json` for plain scripts and instruments, `raw` for bytes, and
  `cloudpickle` only inside one trust domain.
- Delivery is at most once, and the newest message is kept under pressure.
- On an ORBIT data plane use `PubSubConfig(kind='orbit', broker_url=...)`.
  With `DT_STREAM_BACKEND` set in the producer's environment,
  `PubSubConfig.resolve()` picks the configured backend.
- **ZMQ caveat:** messages published right after `open()` can be dropped
  until the broker's subscription reaches the publisher (#40).  A producer
  that publishes a short burst at start-up should pause briefly after
  `open()`.  The ORBIT backend is not affected.

The ZMQ addresses of the service's stream broker are in the admin listing:
`dt.admin_sessions()['stream_broker']['addresses']`.

## Getting results out

The runtime passes a component's result to the next component on that dtype
and publishes nothing by itself.  There are two ways to see results:

1. **`get_inference`** answers the caller directly.  It raises an error when
   no component serves the requested mapping (#41).
2. **The twin's stream.**  A component publishes with
   `await runtime.stream.publish(dtype, value)`, and the client subscribes
   to that twin's namespace:

```python
import asyncio
from digitaltwin.streaming import connect_stream_client

pub_addr, sub_addr = dt.admin_sessions()['stream_broker']['addresses']
client = await connect_stream_client(twin, pub_addr, sub_addr)
queue = asyncio.Queue()
await client.subscribe_to_dtype(RESULT, queue)
item = await queue.get()        # item.data is the published value
```

On an ORBIT data plane, connect with
`connect_stream_client(twin, backend='orbit', broker_url=...)`.

## Observing

`twin_list` polling is the observation mechanism in v1; the service pushes
nothing to the client.  Each entry carries:

| Field | Meaning |
|-------|---------|
| `state`, `last_error` | Lifecycle state and the reason for `failed`. |
| `metrics` | A learner's convergence criterion: value, threshold, window count, recent history.  Empty without a learner. |
| `calls` | Verbs answered for this twin, per verb. |
| `tasks`, `task_components` | The newest task uids the twin submitted and the component that submitted each. |
| `components` | The graph: class names, kinds and dtypes. |
| `outputs` | The latest image a component rendered, if any. |

`admin_sessions()` adds, per session, the built engines and the endpoint
behind each role, plus the stream broker's backend and addresses.  It is
also how orphaned sessions are found.

## Sessions and cleanup

Sessions are persistent: closing the client does not close them.  Reattach
with the `sid` to continue, and close twins with `twin_close` when done.
After an endpoint loss, recreate the session (see the README section on
R8).
