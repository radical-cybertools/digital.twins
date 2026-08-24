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
REF="4b3defd30c9c9d2376fee2e728e4d106eae54447"   # feature/dtaas-viz, post devel merge

# The radical dependencies must NOT come from naive PyPI resolution: PyPI's
# rhapsody-py 0.4.0 lacks `rhapsody.backends.execution.orbit` (the
# OrbitExecutionBackend the whole service runs on).  These pins are the
# exact commits the verified laptop stack was built from -- all pushed to
# public radical-cybertools repos.

# asyncflow: the 0.5.1 RELEASE carries the non-main-thread engine fix the
# broker-hosted plugin needs (it contains d9f7ca0) -- PyPI is fine
ASYNCFLOW="radical.asyncflow==0.5.1"
# rhapsody's [telemetry] extra is required, not optional, at this commit:
# the ORBIT plugin calls `session.start_telemetry()` whenever it exists, and
# that path hard-imports opentelemetry -- an endpoint without it fails every
# session init with "No module named 'opentelemetry'".  (Known upstream gap;
# the proper fix is an ImportError guard in orbit's plugin_rhapsody.)
RHAPSODY="rhapsody-py[telemetry] @ git+https://github.com/radical-cybertools/rhapsody@e491cd2"   # f479c75 + participant_name + engine role

# orbit: the 0.5.0 RELEASE carries the SSE bytes fix (#113) -- PyPI is fine
ORBIT="radical.orbit==0.5.0"

# ROSE: PyPI's `rose` is an UNRELATED project (a version-string helper) which
# pip will happily install for the `learn` extra -- and the learner then dies
# on `import rose.al`.  Pin the real one, same commit the verified stack uses.
ROSE="rose @ git+https://github.com/radical-cybertools/ROSE@64330d9cb43c3e13ca67daf0d8ae84a2ae6c3f17"

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
from rose.al.streaming_learner import StreamingActiveLearner  # noqa: F401
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
