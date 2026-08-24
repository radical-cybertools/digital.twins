"""Deployment configuration for the digital twin framework.

The single place where the stream transport is decided: which backend
carries the data plane, and -- for the ZMQ one -- at which addresses.  No
other module (and no demo) may contain a hardcoded transport address.

Backend choice (`DT_STREAM_BACKEND`) is a deployment-time decision at the
same altitude as the compute backend; nothing above `PubSubBackend`
depends on which one is in use.

- `zmq` (default): the framework's own XSUB/XPUB broker.  Local and
  two-terminal use.  Its payloads are cloudpickled and its ports carry no
  authentication, so anyone who can reach them can execute code in every
  subscriber (risk R7).  Hence the binding policy: loopback unless the
  deployment explicitly configures something else, and a non-loopback
  bind requires a firewalled/private network.
- `orbit`: ORBIT eventing.  The same cloudpickled payloads, but inside
  the token-authenticated WS star -- no DT-owned ports at all.  This is
  what closes R7 for a deployment, and it is required before production.
"""

import os

# loopback-only by default -- see the binding policy above
DEFAULT_BIND_HOST = "127.0.0.1"

# fixed default ports, used by the standalone broker (two-terminal demos)
DEFAULT_PUB_ADDR = f"tcp://{DEFAULT_BIND_HOST}:5000"
DEFAULT_SUB_ADDR = f"tcp://{DEFAULT_BIND_HOST}:5001"

# wildcard port: let the OS pick.  Used by embedded (subprocess) brokers,
# which report their bound addresses back to the parent.
RANDOM_PUB_ADDR = f"tcp://{DEFAULT_BIND_HOST}:*"
RANDOM_SUB_ADDR = f"tcp://{DEFAULT_BIND_HOST}:*"

ENV_PUB_ADDR = "DT_STREAM_PUB_ADDR"
ENV_SUB_ADDR = "DT_STREAM_SUB_ADDR"

# which transport carries the data plane -- see the module docstring
BACKEND_ZMQ = "zmq"
BACKEND_ORBIT = "orbit"
STREAM_BACKENDS = (BACKEND_ZMQ, BACKEND_ORBIT)

# zmq: the local/two-terminal default.  A deployment that wants R7 closed
# selects 'orbit' -- deliberately, not by accident of the environment.
DEFAULT_STREAM_BACKEND = BACKEND_ZMQ

ENV_STREAM_BACKEND = "DT_STREAM_BACKEND"


def stream_backend(name: str | None = None) -> str:
    """Resolve which pubsub backend carries the data plane.

    Precedence: explicit argument, then `DT_STREAM_BACKEND`, then `zmq`.
    An unknown name is an error rather than a silent fallback -- a typo
    must not quietly reopen the ZMQ ports of a deployment that asked for
    the token-authenticated one.
    """

    chosen = (name or os.environ.get(ENV_STREAM_BACKEND)
              or DEFAULT_STREAM_BACKEND).strip().lower()

    if chosen not in STREAM_BACKENDS:
        raise ValueError(
            f"unknown stream backend {chosen!r};"
            f" expected one of {', '.join(STREAM_BACKENDS)}"
        )

    return chosen


def stream_addresses(
    pub_addr: str | None = None, sub_addr: str | None = None
) -> tuple[str, str]:
    """Resolve the (publish, subscribe) addresses of the stream broker.

    Precedence: explicit argument, then the `DT_STREAM_PUB_ADDR` /
    `DT_STREAM_SUB_ADDR` environment variables, then the loopback defaults.
    """

    return (
        pub_addr or os.environ.get(ENV_PUB_ADDR) or DEFAULT_PUB_ADDR,
        sub_addr or os.environ.get(ENV_SUB_ADDR) or DEFAULT_SUB_ADDR,
    )


def embedded_stream_addresses() -> tuple[str, str]:
    """Resolve the bind addresses of a service-embedded stream broker.

    Same environment variables as `stream_addresses`, but an unconfigured
    embedded broker takes a random loopback port instead of the fixed
    demo ports -- it reports what it bound, so nothing has to agree on a
    number up front.
    """

    return (
        os.environ.get(ENV_PUB_ADDR) or RANDOM_PUB_ADDR,
        os.environ.get(ENV_SUB_ADDR) or RANDOM_SUB_ADDR,
    )
