# The data plane and its trust boundary (R7)

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
(see [Choosing a data plane](../../use/data-plane.md)).

**With the `zmq` backend the old mitigations still apply, in full.** The
plugin runs its own DT stream broker, embedded, one per plugin and shared
by every twin.  It binds to loopback on a random port by default, and
that default is the safe one.  A non-loopback bind is possible
(`DT_STREAM_PUB_ADDR` / `DT_STREAM_SUB_ADDR` on the service host) but
requires a deliberate decision *and* a firewalled or private network.  Do
not expose those ports -- including in demos.
