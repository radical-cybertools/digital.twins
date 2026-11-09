"""Round 3 T1-C: what crosses the ORBIT wire per request, per E1 row.

Runs `bench_dt_insitu.py` unchanged (same arguments) with the client's
ORBIT runtime instrumented: every frame it sends (`EndpointRuntime._enqueue`) and
receives (`EndpointRuntime._on_frame`) is counted by kind, request path and event
topic, with its size.  Counts are taken around each row's `run_row`, so
the twin's start-up and readiness polling are not in them, and divided by
the calls that row made (warm-up + sequential + burst).

    python diag_wire.py --broker URL --endpoint EP --rows agent --tasks 200 \\
        --concurrent 50 --wire-out wire-agent.json

Prints one `WIRE` line per row and frame class.
"""

import asyncio
import json
import sys

from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bench_dt_insitu as bench  # noqa: E402

from radical.orbit import protocol  # noqa: E402
from radical.orbit.runtime import EndpointRuntime as Runtime  # noqa: E402

N = Counter()       # (direction, class) -> frames
B = Counter()       # (direction, class) -> bytes


def _cls(msg) -> str:
    kind = msg.kind
    if kind == "request":
        return f"request {msg.method} {msg.path}"
    if kind == "event":
        return f"event {msg.plugin}/{msg.topic}"
    return kind


_emit, _enqueue, _on_frame = Runtime._emit, Runtime._enqueue, Runtime._on_frame


def emit(self, msg):
    try:
        size = len(protocol.pack_message(msg, cap=self._frame_cap))
    except Exception:
        size = 0
    N["out", _cls(msg)] += 1
    B["out", _cls(msg)] += size
    self._dt_wire_emitting = True
    try:
        return _emit(self, msg)
    finally:
        self._dt_wire_emitting = False


def enqueue(self, data, kind):
    if not getattr(self, "_dt_wire_emitting", False):  # packed elsewhere
        N["out", kind] += 1
        B["out", kind] += len(data)
    return _enqueue(self, data, kind)


def on_frame(self, data, gen=None):
    try:
        msg = protocol.parse_message(data, cap=self._frame_cap)
        cls = _cls(msg)
    except Exception:
        cls = "unparseable"
    N["in", cls] += 1
    B["in", cls] += len(data)
    return _on_frame(self, data, gen)


Runtime._emit, Runtime._enqueue, Runtime._on_frame = emit, enqueue, on_frame

WIRE: dict = {}
_run_row = bench.run_row


async def run_row(label, call, n_meas, n_conc):
    n0, b0 = N.copy(), B.copy()
    out = await _run_row(label, call, n_meas, n_conc)
    calls = bench.N_WARM + n_meas + n_conc
    row = {"calls": calls, "frames": {}}
    for key in sorted(set(N) | set(n0)):
        n, b = N[key] - n0[key], B[key] - b0[key]
        if n:
            d, cls = key
            row["frames"][f"{d} {cls}"] = {"n": n, "bytes": b,
                                           "per_call": n / calls,
                                           "bytes_per_frame": b / n}
            print(f"WIRE {label:24s} {d:3s} {cls:48s} {n / calls:6.2f}/call "
                  f"{b / n:8.0f} B/frame")
    WIRE[label] = row
    return out


bench.run_row = run_row

if __name__ == "__main__":
    wire_out = None
    if "--wire-out" in sys.argv:
        i = sys.argv.index("--wire-out")
        wire_out = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    asyncio.run(bench.main())
    if wire_out:
        Path(wire_out).write_text(json.dumps(WIRE, indent=2))
