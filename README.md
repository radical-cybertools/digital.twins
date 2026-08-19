# Experimental Digital Twin Framework

Main set of features implemented:
- Model Investigator
- Utility Tasks
- Persistent Tasks
- Callbacks
- Two pubsub backends: ZMQ, and ORBIT eventing
- Graph builder
- Convert to a Python Package
- Several Tests / Examples
- Science Agents
- Request inference API on runtime
- Barrier
- Split
- Join
- Shared SIM / subtasks running on agent, accessible by all investigators
- Ex-situ learning (ROSE streaming learner on a second engine)

Not yet implemented:
- Barrier working on remote
- Split working on remote
- Join working on remote

## Running the unit tests:

1. `pip install .[test,service,learn]`
2. `pytest` (or `tox` for all supported interpreters)

The `learn` extra currently needs ROSE from **PR #98** (commit
`64330d9`) -- `StreamingActiveLearner` is not in a release yet, so
`pip install <rose-checkout>` at that commit until it merges.

The unit tests start their own stream broker on a random port; no setup.
The integration tests under `test/integration` bring up a real ORBIT
broker and two rhapsody endpoints and skip themselves when they cannot.

## Running the demos:

1. `pip install .`
2. `cd test/`
3. In one terminal, run `local_broker.py` -- it prints the addresses it
   bound
4. In a second terminal, cd into the demo and run `run_me.py`
5. In a third terminal, in the same demo, run its `sensor.py` if it has
   one (`01-start-inference-stop` and `04-start-agent-stop` do)

**When running a demo: be sure to start the ZMQ PubSub broker!**

The third terminal is the point, not an inconvenience: a sensor is an
external entity.  It is a process of its own with a lifetime of its own,
it publishes JSON on a shared channel, and it knows nothing about twins.
The twin binds that channel with `runtime.add_input(dtype, channel)`, and
a second twin binding the same channel receives the same messages -- which
is how one instrument feeds many twins.  Start and stop the sensor
independently of the twin; neither cares.

Demos without a `sensor.py` produce their input inside the twin, which is
what persistent components are still for: `06-agent-pi` drives itself off
a timer, and `07-barrier` off several.

Every side resolves the broker addresses the same way: `DT_STREAM_PUB_ADDR`
and `DT_STREAM_SUB_ADDR`, defaulting to `tcp://127.0.0.1:5000` and `:5001`
(see `digitaltwin.config`).  Set them in every terminal to move the broker.

**Binding policy**: the broker binds to loopback by default, and it must
stay that way unless you know what you are doing -- twin-internal payloads
are cloudpickled, so anyone who can reach the broker ports can execute code
in every subscriber.  A non-loopback bind needs an explicit configuration
and a private/firewalled network.  External channels are decoded with the
codec their binding names: `json` (the default) and `raw` are safe to
accept from a producer you do not control, `cloudpickle` is not.  The
demos are the reason the ZMQ backend exists; anything beyond a laptop
should be on the ORBIT one below.

## Choosing a data plane

`DT_STREAM_BACKEND` picks which transport carries the twins' streams.  It
is a **deployment-time** choice, resolved once where the framework runs;
no client and no session can ask for a different one.  Nothing above
`PubSubBackend` -- not `DTRuntime`, not a component, not the injected
`RuntimeAPI.stream` client -- knows which is in use.

| `DT_STREAM_BACKEND` | transport | ports it opens | use |
|---------------------|-----------|----------------|-----|
| `zmq` (default)     | the framework's own XSUB/XPUB broker | two, unauthenticated, loopback by default | local, demos, the two-terminal loop |
| `orbit`             | ORBIT eventing (`radical.orbit`)     | **none** | anything shared, and everything in production |

```sh
# a service deployment with the data plane inside the token domain
DT_STREAM_BACKEND=orbit radical-orbit-broker.py --plugins default,dt
```

An external subscriber joins the same way -- as an ORBIT participant, so
it needs the broker URL and the token, and no addresses at all:

```python
from digitaltwin.streaming import connect_stream_client

stream = await connect_stream_client(twin_id, backend='orbit')
await stream.subscribe_to_dtype(ECHO, queue)
```

**Payload ceiling**: an ORBIT frame is capped at 4 MiB, so a single
stream message must cloudpickle to less than that (64 KiB of the budget
is reserved for the envelope).  Oversized payloads raise a clear
`ValueError` at `publish` -- ORBIT itself would drop the frame with
nothing but a log line, which on a days-long twin is indistinguishable
from a stalled stream.  The ZMQ backend has no such ceiling; a twin meant
to run on either should stay well under it.  Chunk large artifacts, or
stream a reference and move the bytes with the staging plugin.

**Semantics** are the same on both: at-most-once, with bounded
drop-oldest queues (broker-side, and again on the hop into the host
loop).  That *is* the DT conflation contract, so nothing above the
backend adds a second one -- a slow consumer loses samples rather than
memory, and never backpressures a producer.  Loss is visible as a gap in
the broker-assigned sequence numbers.  ORBIT's `replay` plugin would give
late joiners history; it is deliberately not integrated in v1.

`perf/bench_streams.py` measures what the choice costs: about a
millisecond per stream hop on loopback.

## Running it as a service (the `dt` ORBIT plugin)

`digitaltwin.service` exposes the framework as a long-running ORBIT
plugin: one session per client, many independent twins per session, and
twins that keep running while their client is away.  Installing the
package registers the plugin through the `radical.orbit.plugins` entry
point, so a broker or endpoint only has to be told to host it.

```sh
pip install .[service]

# 1 - the broker, hosting the dt plugin
radical-orbit-broker.py --plugins default,dt

# 2 - a rhapsody endpoint: where the twins' tasks execute.  The notify
#     window costs 250 ms on every sequential prediction at its default
radical-orbit-endpoint.py -n dt_task_ep
#     ... started with:
#     RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0
#     RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent
```

The client:

```python
from radical.orbit import EndpointRuntime
from digitaltwin.components import NULL_DTYPE, TRUTHY
from digitaltwin.service import register_user_modules

import my_components                       # not installed on the service
register_user_modules([my_components])

rt = EndpointRuntime()
rt.start(wait=True)

# 'broker' is the participant hosting dt; engine wiring is explicit
dt = rt.get_plugin('broker', 'dt', config={
    'engines': {'task': {'endpoint_name': 'dt_task_ep',
                         'backends': ['concurrent']}}})

twin = dt.create_twin()                    # polls until the twin is ready
dt.add_task(twin, dt.package(MySensor), TRUTHY, SENSOR, is_persistent=True)
dt.add_investigator(twin, dt.package(MyModel), SENSOR, PREDICTION)
dt.start(twin)

print(dt.twin_list())                      # the observation mechanism
answer = dt.get_inference(twin, TypedData(SENSOR, 5), PREDICTION)

dt.twin_close(twin)
```

The session outlives the client: reattach with
`rt.get_plugin('broker', 'dt', sid=<sid>)` and the twins are still
there.  `dt.admin_sessions()` lists every session, twin, state and last
error on the service -- which is how orphans are found and torn down.
`test/09-service/` is a complete worked example.

Three contract notes:

- The client and the service must run **the same `digitaltwin` version**
  (and compatible Python / cloudpickle): shipped component classes
  pickle the framework by reference.  Every call carries those versions
  and the service rejects skew with a clear error rather than failing
  somewhere inside an unpickle.
- A task's *arguments* are cloudpickled, but its **return value must be
  JSON-safe or `bytes`** -- ORBIT's rhapsody plugin JSON-encodes results
  and stringifies anything else.  Return plain values from
  `@flow.function_task` bodies and wrap them in `TypedData` in the
  component.  (Fixed upstream in radical.orbit `devel` after this was
  written: rich results now round-trip by cloudpickle marker.  Keep to
  plain values until the release you deploy against contains it.)
- Persistent components run inline on the service's event loop.  Their
  bodies must be thin async glue publishing through
  `runtime.stream`, never `@flow.function_task`s (the service warns when
  it sees one).

### Ex-situ learning: the second engine

A `StreamingLearnerInvestigator` (`digitaltwin.learn`, needs the `learn`
extra) embeds a ROSE `StreamingActiveLearner` in a model investigator:
the twin's input stream both feeds the learner and is served by the
inference task, and each window of samples retrains the model the
inference task runs with.

That class is the *only* thing that selects an engine in v1 -- there is
no `engine=` argument.  The service recognises it by subclass check and
hands it two engines: its learner tasks run on `'exsitu'`, its inference
stays on `'task'`.

```python
dt = rt.get_plugin('broker', 'dt', config={'engines': {
    'task':   {'endpoint_name': 'dt_task_ep',   'backends': ['concurrent']},
    'exsitu': {'endpoint_name': 'dt_exsitu_ep', 'backends': ['concurrent']},
}})
```

`'exsitu'` is optional: left out, it aliases `'task'` and one endpoint
serves both.  Both engines are session-shared and built once, in the
background phase of `twin_create`.

Register the learner's training / active-learning / criterion tasks with
`as_executable=False`.  ROSE's default makes them shell commands, and a
command line with local paths does not survive an endpoint that shares
no filesystem with the service; `as_executable=False` sends them as
cloudpickled function tasks instead (the component warns if it finds
executable ones).  `test/10-learner/` is a complete worked example.

### When an endpoint disappears (R8)

`OrbitExecutionBackend` does not reconnect and components bind their
engine at construction, so a twin whose endpoint went away is stranded
and v1 cannot heal it.  It is at least not silent: the plugin watches
the ORBIT topology and marks every twin that bound an engine on a lost
endpoint `failed`, with `engine endpoint lost: <endpoint>` in
`twin_list`.  Twins on surviving engines keep running.

Recovery means **closing the session**, not just the twins: engines are
session-shared, so a twin created afterwards would inherit the dead one.
The session remembers the loss and refuses to hand that engine out
again, so a `twin_create` after it fails immediately with `engine
'<name>' endpoint was lost; recreate the session` rather than coming up
`ready` and stalling.  `unregister_session`, then build the session and
its twins again.

### The data plane and its trust boundary (R7)

The DT streams carry cloudpickled payloads.  That is accepted -- the
service already executes client-shipped component classes, and both sit
inside ORBIT's single-token trust domain (risk R4).  What was *not*
acceptable is where those payloads used to travel: a pair of ZMQ ports
that authenticate nobody, so anyone who could reach them got code
execution in every subscriber, no token required.  The data plane was
weaker than the control plane wrapped around it.

**`DT_STREAM_BACKEND=orbit` closes that gap**, and a production
deployment must use it:

```sh
DT_STREAM_BACKEND=orbit radical-orbit-broker.py --plugins default,dt
```

The twins' streams become ORBIT events on the same token-authenticated
WebSocket star as every other call, under one `dt_stream` plugin
namespace.  The embedded ZMQ broker is then **never started** -- the
service opens no data-plane port at all, and there is nothing left to
firewall.  The payloads are still cloudpickle; what changed is that
reaching them now requires the same token as calling `twin_create`.
Reviewers can check the guarantee directly: the plugin host has no child
processes, and `admin/sessions` reports `{"stream_broker": {"backend":
"orbit"}}`.

Two things this does *not* do.  It does not make the payloads safe to
receive from an untrusted party -- per-tenant auth is post-v1, so
everything inside the token domain is still mutually trusting.  And it
does not remove the 4 MiB frame cap, which the ZMQ backend did not have
(see "Choosing a data plane").

**With the `zmq` backend the old mitigations still apply, in full.** The
plugin runs its own DT stream broker, embedded, one per plugin and shared
by every twin.  It binds to loopback on a random port by default, and
that default is the safe one.  A non-loopback bind is possible
(`DT_STREAM_PUB_ADDR` / `DT_STREAM_SUB_ADDR` on the service host) but
requires a deliberate decision *and* a firewalled or private network.  Do
not expose those ports -- including in demos.
