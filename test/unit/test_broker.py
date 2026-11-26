"""M0.4 -- embedded broker: random ports, loopback default, clean stop."""

import asyncio

from radical.doppelganger import DataType, ZMQ_BrokerProcess, connect_stream_client
from radical.doppelganger.config import DEFAULT_BIND_HOST

PING = DataType("ping")


async def test_start_reports_bound_random_loopback_ports():
    proc = ZMQ_BrokerProcess()
    try:
        pub_addr, sub_addr = await proc.start()

        for addr in (pub_addr, sub_addr):
            assert addr.startswith(f"tcp://{DEFAULT_BIND_HOST}:")
            assert int(addr.rsplit(":", 1)[1]) > 0

        assert pub_addr != sub_addr
        assert proc.get_connection_str() == (pub_addr, sub_addr)
        assert proc.is_alive()

    finally:
        await proc.stop()


async def test_start_stop_cycling():
    proc = ZMQ_BrokerProcess()

    for _ in range(3):
        pub_addr, sub_addr = await proc.start()
        assert proc.is_alive()
        assert int(pub_addr.rsplit(":", 1)[1]) > 0
        assert int(sub_addr.rsplit(":", 1)[1]) > 0

        # start is idempotent while running, and concurrent starts must not
        # spawn a second broker
        assert set(await asyncio.gather(proc.start(), proc.start())) == {
            (pub_addr, sub_addr)
        }

        await proc.stop()
        assert not proc.is_alive()
        assert proc.get_connection_str() == (None, None)

        # stop is idempotent
        await proc.stop()

    # and a broker from a fresh cycle actually proxies
    addrs = await proc.start()
    try:
        client = await connect_stream_client("cycled", *addrs)
        queue: asyncio.Queue = asyncio.Queue()

        await client.subscribe_to_dtype(PING, queue)
        await asyncio.sleep(0.2)
        await client.publish(PING, "alive")

        assert (await asyncio.wait_for(queue.get(), 5.0)).data == "alive"
        await client.close()

    finally:
        await proc.stop()


async def test_configured_addresses_are_honoured():
    # port 0 is the POSIX 'pick one for me' spelling; either way the
    # caller learns the actual port from the reported addresses
    proc = ZMQ_BrokerProcess("tcp://127.0.0.1:0", "tcp://127.0.0.1:0")
    try:
        pub_addr, sub_addr = await proc.start()
        assert not pub_addr.endswith(":0")
        assert not sub_addr.endswith(":0")
    finally:
        await proc.stop()
