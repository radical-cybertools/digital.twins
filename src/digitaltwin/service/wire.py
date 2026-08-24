"""Wire format shared by the DT service and its client.

Everything a DT verb carries -- dtypes, component classes, constructor
arguments, inference payloads -- is arbitrary Python, so it travels as
base64-encoded cloudpickle inside the JSON envelope.

Two guards ride along, both cheap and both mandatory:

- a **size check** against ORBIT's 4 MiB frame cap, applied client-side
  where the offending object is still in scope and the error can name it;
- a **version stamp** (client Python + cloudpickle), rejected server-side
  on skew -- a pickle from a different interpreter fails in confusing
  ways deep inside the plugin otherwise.
"""

import base64
import sys

from dataclasses import dataclass, field
from importlib import metadata
from typing import Any

import cloudpickle

try:
    from radical.orbit.protocol import FRAME_CAP
except ImportError:  # the client may be installed without ORBIT
    FRAME_CAP = 4 * 1024 * 1024

# Room for the JSON envelope (verb, ids, keys) around the payload.  The
# cap applies to the whole packed frame, so the payload must stay below.
ENVELOPE_MARGIN = 64 * 1024
MAX_PAYLOAD = FRAME_CAP - ENVELOPE_MARGIN


@dataclass
class Package:
    """A component class plus its constructor arguments, shipped to the
    service, which instantiates it injecting the session's engine as the
    leading `flow` argument.

    Built by `DTClient.package()`; never instantiated by hand.
    """

    cls: type
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)

    def instantiate(self, flow, **engines: Any) -> Any:
        """Instantiate with the twin's engine, plus any extra engine the
        service injects by class (`learn_backend` for a streaming learner)."""

        return self.cls(flow, *self.args, **{**self.kwargs, **engines})


def register_user_modules(modules: list) -> None:
    """Ship these modules by value rather than by reference.

    User code living in a demo directory does not exist on the service,
    so its modules have to travel with the pickle.
    """

    for module in modules:
        cloudpickle.register_pickle_by_value(module)


def _dt_version() -> str:
    try:
        return metadata.version("digitaltwin")
    except metadata.PackageNotFoundError:  # running from a source tree
        return "unknown"


def version_stamp() -> dict:
    """The identity a pickle was produced with.

    `digitaltwin` is in here because a shipped component class pickles
    its framework base classes, dtypes and `Package` *by reference*: the
    two sides have to be looking at the same code, not merely at
    compatible pickle machinery.
    """

    return {
        "python": "%d.%d" % sys.version_info[:2],
        "cloudpickle": cloudpickle.__version__,
        "digitaltwin": _dt_version(),
    }


def _minor(version: str) -> tuple:
    return tuple(str(version).split(".")[:2])


# How closely each version has to line up.  Python and cloudpickle break
# pickle compatibility at minor-version granularity; `digitaltwin` is
# resolved by reference, so any difference at all is a different service.
_COMPARE = {"python": _minor, "cloudpickle": _minor, "digitaltwin": str}


def check_versions(stamp: dict) -> None:
    """Reject a payload produced by a skewed client.

    Raises:
        ValueError: on a missing or mismatched version, naming both sides.
    """

    theirs = stamp or {}

    for key, mine in version_stamp().items():
        yours = theirs.get(key)
        if yours is None:
            raise ValueError(f"client did not report its {key} version")

        compare = _COMPARE[key]
        if compare(yours) != compare(mine):
            raise ValueError(
                f"{key} version skew: client {yours}, service {mine}"
                f" -- cloudpickled payloads are not portable across those"
            )


def encode(obj: Any) -> str:
    """Cloudpickle `obj` into a JSON-safe string."""

    return base64.b64encode(cloudpickle.dumps(obj)).decode("ascii")


def decode(blob: str) -> Any:
    """Inverse of `encode`."""

    return cloudpickle.loads(base64.b64decode(blob))


def encode_checked(obj: Any, what: str) -> str:
    """`encode`, refusing payloads that cannot survive the frame cap."""

    blob = encode(obj)

    if len(blob) > MAX_PAYLOAD:
        raise ValueError(
            f"{what} is {len(blob) / 1024**2:.1f} MiB encoded, over the"
            f" {MAX_PAYLOAD / 1024**2:.1f} MiB the ORBIT frame cap leaves"
            f" for it -- keep bulk data out of the control plane (stage it"
            f" or stream it)"
        )

    return blob
