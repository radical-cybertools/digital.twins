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
      |           |  |      |          ^
      |           |  +------|----------+
      +-----------+---------+-----> failed
```

- `create_twin` registers the twin and returns at once.  The engines and the
  stream connection come up in the background (`initializing`).  With the
  default `wait=True` the client polls until the twin is `ready`.  With
  `wait=False`, call `wait_ready` before the first graph verb.
- Graph verbs (`add_*`) are accepted in `ready` and `running`.  They are
  refused with a 409 while the twin is `initializing`, and once it is
  `stopped` or `failed`.
- `start` runs the graph; `stop` is terminal in v1.
- `failed` is terminal and carries the reason in `last_error`, for example a
  component that raised or an engine endpoint that was lost.
- `twin_close` stops the twin, removes it and returns `closed`.  The twin is
  then gone: `twin_list` omits it and `twin` raises.

`create_twin` takes a client-generated id.  Re-issuing it with the same id
after a lost response is a no-op, so the one asynchronous verb is safe to
retry.  `start`, `stop` and `twin_close` are idempotent too.

## Client API

Get a client from a running `EndpointRuntime`:

```python
dt = rt.get_plugin('broker', 'dt', config=SESSION_CONFIG)   # new session
dt = rt.get_plugin('broker', 'dt', sid=old_sid)             # reattach
```

`dt.sid` is the session id to keep for reattaching.

| Call | Purpose |
|------|---------|
| `package(cls, *args, **kwargs)` | Ship a component class and its constructor arguments.  The service instantiates it with the session engine as the leading `flow` argument. |
| `register_user_modules([mod, ...])` | Ship modules that are not installed on the service (call once, before `package`). |
| `create_twin(twin_id=None, config=None, wait=True, timeout=300)` | Create a twin and return its id. |
| `wait_ready(twin, timeout=300)` | Wait until a twin created with `wait=False` is `ready`. |
| `add_task(twin, pkg, input_dtype, output_dtype, is_persistent=False)` | Add a utility task.  Persistent tasks run inline on the service loop (see the README contract notes). |
| `add_investigator(twin, pkg, input_dtype, output_dtype, ...)` | Add a model investigator.  Further arguments go to its `main_loop`. |
| `add_agent(twin, pkg, input_dtype, output_dtype, ...)` | Add a science agent.  Further arguments go to its `main_loop`. |
| `add_input(twin, dtype, channel, codec='json')` | Bind an external channel to an input dtype (see below). |
| `add_data_join(twin, join_dtype)` | Emit one joined event per complete set of the member dtypes. |
| `add_barrier(twin, barrier)` | Register a `Barrier` built locally.  Only a plain `Barrier` can be sent. |
| `add_data_split_task(twin, pkg, input_dtype, output_dtypes)` | Add a split task: one input event, one output per dtype. |
| `start(twin)` / `stop(twin)` | Run the graph / stop it (terminal). |
| `get_inference(twin, in_data, output_dtype, timeout=600)` | Run the one non-persistent component that maps this input dtype to `output_dtype` and return its `TypedData`.  This is a single step: it does not traverse the graph or forward the result.  The twin must be running. |
| `describe(twin)` | The graph as a serializable summary. |
| `twin_list()` / `twin(twin_id)` | State of all twins in the session / of one twin. |
| `twin_close(twin)` | Stop and remove a twin. |
| `admin_sessions()` | Every session and twin on the service, with errors. |
| `unregister_session()` | End the session: stop its twins and shut down its engines. |

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
  `'pools'`.  Pool-backed roles survive the loss of single endpoints: the
  dispatcher reruns the affected tasks, so those tasks must be idempotent.
- `default_engine` moves tasks without a role label to `'learning'`.  The
  broker's `DT_DEFAULT_ENGINE` sets this for a whole deployment, and the
  session config wins.

Every configured engine is built once per session, when a twin is
created, and shared by the session's twins.

### Components on several sites

A session can configure further, named engines, one per site, and place a
twin's components on them:

```python
SESSION_CONFIG = {
    'engines': {
        'inference': {'endpoint_name': 'pm_node_a'},
        'site_b':    {'endpoint_name': 'pm_node_b'},
        'site_c':    {'endpoint_name': 'remote_c'},
    },
}

dt.add_investigator(twin, dt.package(FieldModel), SENSOR, FIELD, engine='site_b')
```

- An engine name is an identifier.  Every engine other than `inference`
  and `learning` names an `endpoint_name` or a `pool`.
- `engine=` on `add_task`, `add_investigator`, `add_agent` and
  `add_data_split_task` places every task the component registers while
  it is built on that engine.  A component's `main_loop` cannot take a
  keyword argument named `engine`: the service consumes it.
- A task decorated with its own `backend='site_c'` label keeps it.  That
  is how a component that builds other components, an agent with its
  investigators for example, places them on different sites; the site
  names reach it as `package()` keyword arguments.
- A `StreamingLearnerInvestigator` placed with `engine=` runs its learner
  tasks on `learning` if configured, else on the placed engine.
- `default_engine` may also name a configured engine.
  `DT_DEFAULT_ENGINE` stays limited to `inference` and `learning`.
- An unknown or unconfigured engine name is refused, and so is an engine
  whose endpoint was lost.

Limits:

- Tasks registered after the component was built (in `main_loop`) run on
  the default engine unless they carry a `backend=` label.  Such a late
  label is neither checked nor bound to the twin, so losing that site does
  not fail the twin: label tasks in `__init__`.  A `backend` passed
  positionally to a task decorator is not checked.  Placement relabels the session's
  task decorators while a component is built; a task registered from
  another thread at that moment would be labelled too, so register tasks
  on the event loop.
- Losing an engine's endpoint fails the twins whose components use it.
  Every twin uses the default engine, so losing that one fails them all.
  After losing the default or `inference`, no new twin can start and the
  session has to be recreated.  Losing another engine fails only the
  twins placed there; new twins that do not use it still start.
- Every configured engine is built when a twin is created, so a site that
  is unreachable fails every new twin: until its loss is detected if it
  was connected once, and for good if it never connected (as an
  unreachable `learning` endpoint does).
- The dashboard draws lanes for `inference` and `learning` only; tasks on
  other engines do not appear there.
- Client and service must run the same `digitaltwin` version (0.1.0
  introduced `engine=`).  The check needs installed packages: run from a
  source tree, both sides report `unknown` and the check passes.

## Feeding a twin: external channels

Instruments are not twin components.  They publish to a named channel, and
any number of twins bind that channel with `add_input`:

```python
from digitaltwin.streaming import ChannelPublisher, PubSubConfig

dt.add_input(twin, SENSOR, 'lab/probe-3')

pub = await ChannelPublisher.open('lab/probe-3', config=PubSubConfig(
    kind='zmq', pub_addr=pub_addr, sub_addr=sub_addr))
await pub.publish({'t': 12.5, 'value': 0.83})
await pub.close()
```

- `codec` is `json` for plain scripts and instruments, `raw` for bytes, and
  `cloudpickle` only inside one trust domain.
- Delivery is at most once.  A twin that falls behind queues messages in
  memory and works through them oldest first.  Transport limits can drop
  messages, and those drops hit the newest ones.
- On an ORBIT data plane use `PubSubConfig(kind='orbit', broker_url=...)`.
  With `DT_STREAM_BACKEND` set in the producer's environment,
  `PubSubConfig.resolve()` picks the configured backend.
- **ZMQ:** a message published before a twin's subscription reaches the
  publisher is dropped.  `open()` therefore waits up to `ready_timeout`
  (2 s) for a subscriber on the channel, and warns if none appears.  It
  does not wait for a second twin on the same channel, or for a twin that
  binds after `open()` returned.  So let `add_input` finish first, and do
  not rely on a single message sent right after it.

The ZMQ addresses of the service's stream broker are in the admin listing:
`dt.admin_sessions()['stream_broker']['addresses']`.  They are loopback
addresses, valid on the service host only, and stay empty until the first
twin connects.  Clients on other hosts need the ORBIT data plane, which is
also what production deployments use (see the README).

## Getting results out

The runtime passes a component's result to the next component on that dtype
and publishes nothing by itself.  There are two ways to see results:

1. **`get_inference`** answers the caller directly.  It raises an error when
   no component serves the requested mapping (#41).
2. **The twin's stream.**  A component's `main_loop` on the service publishes
   with `await runtime.stream.publish(dtype, value)`, and the client
   subscribes to that twin's namespace.  A `function_task` runs on the
   endpoint, where the live stream is out of reach: pass it
   `runtime.stream_config` and open a client there with `connect()`.
   Delivery is at most once, so a value published before the subscription
   lands is lost, and a read needs a timeout:

```python
import asyncio
from digitaltwin.streaming import connect_stream_client

pub_addr, sub_addr = dt.admin_sessions()['stream_broker']['addresses']
client = await connect_stream_client(twin, pub_addr, sub_addr)
queue = asyncio.Queue()
await client.subscribe_to_dtype(RESULT, queue)
item = await asyncio.wait_for(queue.get(), 30)   # item.data is the value
await client.close()
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

Sessions are persistent: they survive the client's process and any network
loss, and nothing ends them on a timer.  Reattach with the `sid` to continue.

Ending a session is explicit.  `dt.unregister_session()` stops its twins and
shuts down its engines, and `dt.close()` does the same, so do not call
`close()` on a client you mean to reattach to.  A session you never end
keeps its engines on the service.  Close single twins with `twin_close`.

After an endpoint loss, call `dt.unregister_session()` and create a new
session (see the README section on R8).
