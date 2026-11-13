#!/usr/bin/env python3
"""Round 7 Z2: run the ORBIT broker with a count of the frames it handles.

    FRAME_COUNT_FILE=out.jsonl python r7/frame_counter.py $(which radical-orbit-broker.py) ARGS...

Harness only, no radical.orbit change: wraps ``Broker._route_frame`` (every
inbound frame) and ``Broker._send`` (every outbound frame) in this process,
then runs the broker script unchanged.  Inbound frames are keyed by kind
plus a coarse class: requests by method and path with ids replaced by ``*``,
responses by status, events by plugin/topic.  Once a second one JSON line
goes to $FRAME_COUNT_FILE: epoch, {key: [frames, bytes]} since the last line,
and the outbound frames and bytes.  The wrapper decodes each inbound frame a
second time, so it costs the broker a little CPU; Z2's profiled runs use it,
Z1's curve does not.
"""

import collections
import json
import os
import re
import runpy
import sys
import threading
import time

import msgpack

from radical.orbit import broker as _b

_ID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}|session\.[0-9a-f]+|[0-9a-f]{16,}|\d{3,}")
_lock = threading.Lock()
_in = collections.defaultdict(lambda: [0, 0])
_out = [0, 0]


def _key(data):
    try:
        raw = msgpack.unpackb(data, raw=False)
    except Exception:
        return "undecodable"
    kind = raw.get("kind")
    if kind == "request":
        path = _ID.sub("*", raw.get("path", ""))
        return f"request {raw.get('method')} {'/'.join(path.split('/')[:6])}"
    if kind == "response":
        return f"response {raw.get('status')}"
    if kind == "event":
        return f"event {raw.get('plugin')}/{raw.get('topic')}"
    return str(kind)


_route = _b.Broker._route_frame
_send = _b.Broker._send


async def _route_frame(self, name, data):
    k = _key(data)
    with _lock:
        c = _in[k]
        c[0] += 1
        c[1] += len(data)
    return await _route(self, name, data)


async def _send_counted(self, ws, data):
    with _lock:
        _out[0] += 1
        _out[1] += len(data)
    return await _send(self, ws, data)


_b.Broker._route_frame = _route_frame
_b.Broker._send = _send_counted


def _dump(path):
    with open(path, "a") as f:
        while True:
            time.sleep(1)
            with _lock:
                snap = {k: list(v) for k, v in _in.items()}
                out = list(_out)
                _in.clear()
                _out[0] = _out[1] = 0
            f.write(json.dumps({"t": time.time(), "in": snap, "out": out}) + "\n")
            f.flush()


if os.environ.get("FRAME_COUNT_FILE"):
    threading.Thread(target=_dump, args=(os.environ["FRAME_COUNT_FILE"],),
                     daemon=True).start()

script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
