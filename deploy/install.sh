#!/usr/bin/env bash
#
# Deploy the DTaaS stack for the live demo.
#
# Run this on every host that takes part -- the broker host, any host
# running a rhapsody endpoint, and the client.  It installs the same
# pinned commit everywhere, which matters more than it looks: the service
# checks Python and cloudpickle at minor-version granularity and rejects
# skew, and it compares `digitaltwin` by exact version string -- which is
# `0.0.1` on every commit of this branch, so a *commit* mismatch would
# NOT be caught by that gate.  Pinning here is the only thing standing
# between us and a confusing unpickle failure mid-demo.
#
#   ./install.sh <role> [venv-dir]
#
#     role       broker | endpoint | client   (informational; same install)
#     venv-dir   default ./ve.demo
#
set -euo pipefail

ROLE="${1:-}"
VENV="${2:-$PWD/ve.demo}"

REPO="https://github.com/radical-cybertools/digital.twins"
# The paper/dtaas stack: every repo on its `paper/dtaas` branch, the four
# dependencies pinned by commit (see experiments/dt-paper/STACK.md).  The
# digitaltwin package itself comes from DT_REF, the branch by default; pass
# the SHA from STACK.md to reproduce a recorded run exactly.
REF="${DT_REF:-paper/dtaas}"

# The radical dependencies must NOT come from naive PyPI resolution: PyPI's
# rhapsody-py 0.4.0 lacks `rhapsody.backends.execution.orbit` (the
# OrbitExecutionBackend the whole service runs on), and PyPI's `rose` is an
# unrelated project.  All four are git commits of public radical-cybertools
# repos.
GH="https://github.com/radical-cybertools"

# asyncflow paper/dtaas: main + hot path (#100), tickless run loop (#110,
# no 10 ms poll), cancel fixes (#119, #121-#124), submit-failure isolation
# (#126: a refused submit fails its own tasks, not the engine), slow-submit
# warning (#127), finished tasks released (#128)
ASYNCFLOW="radical.asyncflow @ git+$GH/radical.asyncflow@24667a5eae6872f9863e31ca631d8af2bc945f04"
# rhapsody paper/dtaas: main + OrbitDataBackend (#96), idempotent cancels
# (#91), telemetry teardown (#77), concurrent cancel (#123), Dragon 0.15
# sizing and PMI (#113, #114), executable stdout through ORBIT (#125),
# immediate submits sent in the background (#127), finished tasks released
# and opt-in telemetry bound (#134, cherry-picked: its base is a newer main),
# immediate sends coalesced while one is in flight (#139), one telemetry
# node sampler per process (#147, cherry-picked: its base is a newer main),
# the Dragon native backend `dragon_native` (#121, squashed onto this base).
# The [telemetry] extra is required: the ORBIT
# plugin calls `session.start_telemetry()` whenever it exists, and that path
# hard-imports opentelemetry.
RHAPSODY="rhapsody-py[telemetry] @ git+$GH/rhapsody@5abecd6f89dcf3b18e72bb2504fd775883aabeed"
# orbit paper/dtaas: devel (0.8.0) + calls held for a suspect endpoint are
# failed (503) on resume (#166), finished tasks released after 1 h and
# telemetry bounded (#167), configurable keepalive deadline
# (RADICAL_ORBIT_PING_TIMEOUT) and coalesced topology broadcasts (#170)
ORBIT="radical.orbit @ git+$GH/radical.orbit@adf25487c772791f99bf3812ea55b02bec6fc9b1"
# ROSE paper/dtaas: main with the Stream API (#98).  The dist name is
# `rose-surrogate-explorer`; a `rose @ ...` direct URL is rejected by pip
ROSE="rose-surrogate-explorer @ git+$GH/ROSE@9cc47a597063351c6192e3520f1bb0d39dd35230"

# Python minor version is part of the wire contract (cloudpickle is not
# portable across minors, and the service rejects skew at the first verb),
# so it is pinned, not discovered.  EVERY host must use the same value:
# export the same DT_PYTHON everywhere, or take the default everywhere.
# 3.12 is the demo choice -- radical.3 has it, and it matches the dragonhpc
# constraint should that backend ever join.
PYTHON="${DT_PYTHON:-python3.12}"

case "$ROLE" in
    broker|endpoint|client) ;;
    *) echo "usage: $0 <broker|endpoint|client> [venv-dir]" >&2; exit 2 ;;
esac

command -v "$PYTHON" >/dev/null || {
    echo "ERROR: $PYTHON not found.  The service compares Python at minor"    >&2
    echo "       granularity and rejects skew at the first verb, so every"    >&2
    echo "       host must run the same minor.  Set DT_PYTHON (same value"    >&2
    echo "       on every host) if it is installed under another name."       >&2
    exit 1; }

echo "==> $ROLE: creating $VENV with $($PYTHON -V)"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip

# pinned deps first: with these already satisfied, resolving digitaltwin's
# requirements will not reach for the broken PyPI variants
echo "==> $ROLE: installing pinned radical deps (asyncflow, rhapsody, orbit, rose)"
"$VENV/bin/pip" install --quiet "$ASYNCFLOW" "$RHAPSODY" "$ORBIT" "$ROSE"

# Same extras on every host.  The endpoint arguably needs less, but a task
# body that closes over anything from `digitaltwin` would fail to unpickle
# there, and uniformity is cheaper than being clever about it at 2am.
echo "==> $ROLE: installing digitaltwin @ ${REF:0:8} (+ service, learn)"
"$VENV/bin/pip" install --quiet "digitaltwin[service,learn] @ git+$REPO@$REF"

# soft dependency of the demo driver: highlighted api snippets.  The
# driver degrades to plain text without it -- never demo-critical.
"$VENV/bin/pip" install --quiet pygments

# (the SSE bytes fix that used to be patched in here is upstream now --
# radical.orbit#113 -- and rides in via the ORBIT pin above)

# belt and braces: fail HERE, not mid-demo, if pip quietly swapped one out
"$VENV/bin/python" - <<'CHECK'
import rhapsody.backends.execution.orbit  # noqa: F401  (PyPI 0.4.0 lacks this)
from radical.orbit import EndpointRuntime  # noqa: F401
import radical.asyncflow  # noqa: F401

# the SSE tap must survive a bytes payload (radical.orbit#113); without it
# the dashboard shows tiles but no stream pulses
from radical.orbit.gateway import Gateway
Gateway._sse_frame("notification", {"data": b"\x80"})

# the real ROSE, not PyPI's homonym (a version-string helper)
from rose import Stream  # noqa: F401
print("==> dependency sanity: OK")
CHECK

echo
echo "==> $ROLE: version stamp -- must be IDENTICAL on every host"
"$VENV/bin/python" - <<'PY'
from digitaltwin.service.wire import version_stamp
import json, sys, platform
print(json.dumps(version_stamp(), indent=2))
print("host:", platform.node())
PY

cat <<NOTE

==> $ROLE: done.  Still needed by hand:

    ~/.radical/orbit/ must hold the ORBIT credentials.

      broker host    broker_cert.pem, broker_key.pem (mode 0600), broker.token
      endpoint host  broker_cert.pem, broker.token
      client host    broker_cert.pem, broker.token

    The cert is *pinned*, not validated against the hostname, so the one
    we already use works for a broker on any host -- no regeneration.
    The key never leaves the broker host.

NOTE
