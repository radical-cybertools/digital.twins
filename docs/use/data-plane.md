# Choosing a data plane

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
from radical.doppelganger.streaming import connect_stream_client

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

`experiments/dt-paper/e1-overhead/bench_streams.py` measures what the
choice costs: about a millisecond per stream hop on loopback.
