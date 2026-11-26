# Status and limits

Doppelganger v1 is a research prototype.  It runs real twins on real HPC
resources, and it is not a hardened multi-user service.  This page is
the one place that lists what v1 does not do; other pages link here.

## Trust

- **One trust domain per deployment.**  The service runs component
  classes that clients ship to it, and its streams carry cloudpickled
  payloads.  Anyone who holds the broker token can run code on the
  service host and on every endpoint.  Give a token only to people you
  would give a shell account.  Per-tenant authentication is planned
  after v1.
- **The ZMQ data plane is unauthenticated.**  With
  `DT_STREAM_BACKEND=zmq`, the default, the stream broker binds to
  loopback; do not expose its ports.  A shared deployment uses
  `DT_STREAM_BACKEND=orbit`, which puts the streams inside the token
  domain.  Binding the ZMQ broker to anything but loopback
  (`DT_STREAM_PUB_ADDR`, `DT_STREAM_SUB_ADDR`) needs a deliberate decision
  and a private or firewalled network.  See
  [Choosing a data plane](../use/data-plane.md) and
  [Data-plane trust](../develop/design/data-plane-trust.md).
- **External channels decode with the codec their binding names.**
  `json`, the default, and `raw` are safe to accept from a producer you
  do not control.  `cloudpickle` executes code on decode: use it only for
  producers inside the trust domain.

## Versions

- **Client and service run the same `radical.doppelganger` version, the
  same Python minor and the same cloudpickle minor.**  Shipped classes
  pickle the framework by reference.  Every call carries these versions
  and the service refuses a mismatch with an error naming both sides.
  Install every host from the same pins (see [Install](../tutorial/install.md)).
- **Not on PyPI yet.**  The first releases of this package and of
  radical.orbit follow this documentation; rhapsody, radical.asyncflow and
  ROSE follow after.  Until then the install uses pinned git commits.

## Sizes

- **4 MiB per message.**  ORBIT caps a frame at 4 MiB, and 64 KiB of that
  is reserved for the envelope.  This applies to a stream message, to a
  shipped component and its arguments, and to a task's return value.
  Oversized payloads fail with a `ValueError` at the sender.  Stream a
  reference and stage the bytes for anything larger.
- **Task return values may be any picklable object.**  ORBIT returns a
  function task's result by cloudpickle when it is not JSON, so numbers,
  arrays and dicts all come back intact.  The 4 MiB limit applies.
- **Learner state crosses the wire every window.**  A learner's model is
  passed to its criterion and inference tasks by value.  Keep models to
  lists of numbers or small arrays; stage large artifacts.

## Components

<a id="persistent-components"></a>

- **Persistent components run inline on the service's event loop.**
  Keep their bodies to thin async code that publishes through
  `runtime.stream`, and never make them
  `@flow.function_task`s; the service warns when it sees one.  Heavy work
  belongs in tasks.
- **Barriers on the service are plain `Barrier`s.**  The service builds
  its own barrier from the spec the client sends, so a `Barrier` subclass
  cannot travel and is refused.
- **The runtime never publishes a component's result.**  A result goes
  to the next component on that dtype.  To see results from outside, a
  component publishes them, or the client calls `get_inference`.

## Streams

- **At most once, newest wins.**  Queues are bounded and drop the oldest
  entry when full, so a slow consumer loses samples and never slows the
  producer.  Loss shows as gaps in the sequence numbers.
- **No history.**  A subscriber that joins late sees only new messages.

## Lifecycle

- **`stop` is terminal.**  A stopped twin cannot be restarted; create a
  new one.
- **Sessions are immortal until unregistered.**  A session and its twins
  survive the client.  Reattach with the session id, find orphans with
  `admin_sessions()`, and end a session with `unregister_session()`.
- **A lost endpoint is not healed.**  Twins whose engine was on a lost
  endpoint go `failed`, and the session refuses that engine afterwards.
  Recovery means a new session.  See
  [When an endpoint disappears](../develop/design/endpoint-loss.md).
