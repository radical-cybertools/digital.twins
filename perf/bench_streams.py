"""Stream latency: the ZMQ data plane vs the ORBIT one.

One publish, awaited until the subscriber's queue hands it back -- the
shape of every hop in a twin's graph (a persistent component publishes a
dtype, the runtime consumes it).  Both rows go through the *same*
`PubSubClient`, so the difference is the backend and nothing else.

The ZMQ row starts its own embedded broker on a random loopback port,
exactly as the service does.  The ORBIT row needs a live broker::

    # against the integration stack (test/integration/conftest.py has one)
    python perf/bench_streams.py both --broker https://127.0.0.1:8031

Informational, not a gate: the ORBIT row buys the security property of
milestone M3 (no unauthenticated ports) and pays a WebSocket round trip
through the broker for it.
"""

import argparse
import asyncio
import os
import sys
import time

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_insitu import report  # noqa: E402

from digitaltwin import DataType, ZMQ_BrokerProcess  # noqa: E402
from digitaltwin.config import BACKEND_ORBIT, BACKEND_ZMQ  # noqa: E402
from digitaltwin.streaming import connect_stream_client  # noqa: E402

SAMPLE = DataType("sample")

N_WARM = 20
N_MEAS = 200
N_BURST = 200


SETTLE_TIMEOUT = 30.0
DELIVER_TIMEOUT = 10.0


async def settle(client, queue, message) -> None:
    """Publish until something comes back.

    Neither backend acknowledges a subscription -- ZMQ's SUBSCRIBE and
    ORBIT's `subscribe` frame are both fire-and-forget -- so the only
    honest barrier is a message that made the round trip.
    """

    deadline = time.perf_counter() + SETTLE_TIMEOUT

    while perf_left(deadline):
        await client.publish(SAMPLE, message)
        try:
            await asyncio.wait_for(queue.get(), 0.25)
            break
        except TimeoutError:
            continue
    else:
        raise TimeoutError(f"no message came back within {SETTLE_TIMEOUT}s")

    while not queue.empty():  # drop whatever the barrier left behind
        queue.get_nowait()


def perf_left(deadline: float) -> bool:
    return time.perf_counter() < deadline


async def measure(client, label: str, n_meas: int, n_burst: int,
                  payload: int) -> None:
    """Publish -> deliver round trips through one stream client."""

    queue: asyncio.Queue = asyncio.Queue()
    await client.subscribe_to_dtype(SAMPLE, queue)

    message = b"x" * payload if payload else 0

    await settle(client, queue, message)

    for _ in range(N_WARM):
        await client.publish(SAMPLE, message)
        await asyncio.wait_for(queue.get(), DELIVER_TIMEOUT)

    latencies = []
    for _ in range(n_meas):
        start = time.perf_counter()
        await client.publish(SAMPLE, message)
        await asyncio.wait_for(queue.get(), DELIVER_TIMEOUT)
        latencies.append(time.perf_counter() - start)

    report(label, latencies)

    # burst: how fast the data plane drains a producer that does not wait.
    # Both backends drop the oldest when a queue overruns, so the count
    # that arrives is part of the measurement.
    start = time.perf_counter()
    for _ in range(n_burst):
        await client.publish(SAMPLE, message)

    received = 0
    while received < n_burst:
        try:
            await asyncio.wait_for(queue.get(), 5.0)
        except TimeoutError:
            break
        received += 1

    elapsed = time.perf_counter() - start
    print(f"{label:28s} {received}/{n_burst} burst messages in "
          f"{elapsed * 1000:.1f}ms ({received / elapsed:.0f} msg/s)")


async def bench_zmq(args) -> None:
    broker = ZMQ_BrokerProcess()
    await broker.start()

    try:
        client = await connect_stream_client(
            "bench-zmq", *broker.get_connection_str(), backend=BACKEND_ZMQ
        )
        try:
            await measure(client, "zmq (embedded broker)", args.messages,
                          args.burst, args.payload)
        finally:
            await client.close()
    finally:
        await broker.stop()


async def bench_orbit(args) -> None:
    client = await connect_stream_client(
        "bench-orbit", backend=BACKEND_ORBIT, broker_url=args.broker
    )
    try:
        await measure(client, "orbit eventing", args.messages, args.burst,
                      args.payload)
    finally:
        await client.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("which", nargs="?", default="both",
                        choices=["zmq", "orbit", "both"])
    parser.add_argument("--broker", default=os.environ.get(
        "RADICAL_ORBIT_BROKER_URL"),
        help="ORBIT broker URL (default: ORBIT's own resolution)")
    parser.add_argument("--messages", type=int, default=N_MEAS)
    parser.add_argument("--burst", type=int, default=N_BURST)
    parser.add_argument("--payload", type=int, default=0,
                        help="payload size in bytes (0: a bare int)")

    args = parser.parse_args()

    if args.which in ("zmq", "both"):
        await bench_zmq(args)

    if args.which in ("orbit", "both"):
        await bench_orbit(args)


if __name__ == "__main__":
    asyncio.run(main())
