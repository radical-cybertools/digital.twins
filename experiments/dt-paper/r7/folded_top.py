#!/usr/bin/env python3
"""Round 7 Z2: summarize a py-spy raw (folded) profile recorded with --idle.

    python r7/folded_top.py PROFILE.folded [RATE_HZ] [TOP]

A sample is "idle" when its leaf frame waits: the leaf's source line (read
from the venv's site-packages or the stdlib) calls sleep, wait, select,
poll, acquire, a queue get, recv/accept/read, or the leaf is one of the
blocking stdlib functions.  Everything else is "busy".  Prints,
over busy samples:
 - samples and busy thread-seconds (samples / RATE, 100 Hz);
 - the share per component, taken from each stack's file paths (telemetry =
   opentelemetry, psutil or rhapsody telemetry; orbit; rhapsody; asyncflow;
   digitaltwin; websockets; msgpack/json; asyncio; other), each sample
   counted once under the deepest component in its stack;
 - the hottest functions by inclusive busy samples (each counted once per
   stack), and by self (leaf) samples.
Markdown to stdout.
"""

import collections
import re
import sys

import functools
import os

ROOTS = ["/pscratch/sd/m/merzky/dt-pm6/ve6/lib/python3.12/site-packages",
         "/opt/cray/pe/python/3.12.12/lib/python3.12"]
FRAME = re.compile(r"^(?P<fn>.*) \((?P<path>[^():]+):(?P<line>\d+)\)$")
BLOCKING = re.compile(r"\bsleep\(|\.wait\(|\bwait\(|select\(|\bpoll\(|\.acquire\(|"
                      r"\.get\(|\brecv|\baccept\(|\.read\(|readinto\(|_wait_for_tstate_lock|"
                      r"\.join\(|waiter")


@functools.cache
def source(path, line):
    for root in ROOTS:
        for cand in (os.path.join(root, path), os.path.join(root, "radical", path)):
            if os.path.isfile(cand):
                try:
                    with open(cand) as f:
                        for i, text in enumerate(f, 1):
                            if i == line:
                                return text.strip()
                except OSError:
                    pass
    return ""


def idle(leaf):
    m = FRAME.match(leaf)
    if not m:
        return False
    return bool(BLOCKING.search(source(m["path"], int(m["line"]))))
COMP = [("telemetry", re.compile(r"opentelemetry|psutil|rhapsody/telemetry|telemetry")),
        ("dt service", re.compile(r"digitaltwin/")),
        ("asyncflow", re.compile(r"asyncflow/")),
        ("rhapsody", re.compile(r"rhapsody/")),
        ("orbit", re.compile(r"orbit/")),
        ("websockets", re.compile(r"websockets/|uvicorn|starlette|httpx|httpcore|h11")),
        ("serialization", re.compile(r"msgpack|json/|cloudpickle|pickle|pydantic")),
        ("logging", re.compile(r"logging/")),
        ("asyncio", re.compile(r"asyncio/"))]


def parse(path):
    for line in open(path):
        line = line.rstrip("\n")
        if not line:
            continue
        stack, _, n = line.rpartition(" ")
        yield stack.split(";"), int(n)


def main():
    path = sys.argv[1]
    rate = float(sys.argv[2]) if len(sys.argv) > 2 else 100.0
    top = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    total = busy = 0
    comp = collections.Counter()
    incl = collections.Counter()
    leaf = collections.Counter()
    for frames, n in parse(path):
        total += n
        if idle(frames[-1]):
            continue
        busy += n
        c = "other"
        for f in reversed(frames):            # deepest frame that names a component
            hit = next((name for name, rx in COMP if rx.search(f)), None)
            if hit:
                c = hit
                break
        comp[c] += n
        for f in set(frames):
            incl[f] += n
        leaf[frames[-1]] += n
    print(f"**{path.split('/')[-1]}**: {total} samples, {busy} busy "
          f"({busy / rate:.1f} busy thread-s, {100 * busy / max(total, 1):.0f}% of samples)\n")
    print("| component (deepest frame) | busy samples | share |\n|---|---|---|")
    for c, n in comp.most_common():
        print(f"| {c} | {n} | {100 * n / busy:.1f}% |")
    print("\n| inclusive (busy) | samples | share |\n|---|---|---|")
    for f, n in incl.most_common(top):
        print(f"| `{f[:110]}` | {n} | {100 * n / busy:.1f}% |")
    print("\n| self (busy leaf) | samples | share |\n|---|---|---|")
    for f, n in leaf.most_common(top):
        print(f"| `{f[:110]}` | {n} | {100 * n / busy:.1f}% |")


if __name__ == "__main__":
    main()
