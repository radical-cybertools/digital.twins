# API Test. Do all the features the DT framework promises to the user actually
# work?


# DT has:
#  ADD_INPUT - DONE
#  ADD_TASK - DONE
#  - persistent - DONE
#  - non-persistent - DONE
#  ADD_INVESTIGATOR
#  - input callback - DONE
#  - inference task - DONE
#  - inference task update - DONE
#
#  ADD_AGENT
#  - Model selector task - DONE
#  - Model publish callback - DONE
#  - filter input task - DONE
#  - inter-agent inference - DONE
#  - Model selector update - DONE
#  - Multi Investigators - DONE
#
#  ADD_BARRIER
#  - Hard barrier
#  - Soft default barrier
#  - Hard (slow) soft (fast)
#  - Soft (fast) hard (slow)
#
#  ADD_DATA_JOIN
#  - Data Join - DONE
#
#  ADD_DATA_SPLIT
#  - Data split task
#  - a None
#  - one None, one Item
#  - both items
#
# claude --resume 18e73ba2-602f-4436-8e3f-958f132df1b7


import asyncio
import contextlib

from digitaltwin import PubSubBackend, PubSubConfig, connect_stream_client
import pytest

from digitaltwin.streaming import ZMQ_BrokerProcess
from sensors import input_sensor

NAMESPACE = "api_test"


@pytest.fixture
async def broker():
    """An embedded stream broker on a random loopback port."""

    proc = ZMQ_BrokerProcess()
    await proc.start()
    try:
        yield proc
    finally:
        await proc.stop()


@pytest.fixture
async def stream_clients(broker):
    """Factory for namespaced stream clients on the fixture broker.

    All clients it hands out are closed when the test ends -- a client
    left open would be caught by the leak assertions of the next test.
    """

    clients = []

    async def make(namespace: str = NAMESPACE):
        client = await connect_stream_client(namespace, *broker.get_connection_str())
        clients.append(client)
        return client

    try:
        yield make
    finally:
        for client in clients:
            await client.close()


@pytest.fixture
async def no_task_leaks():
    """Assert that the test leaves no asyncio task behind."""

    before = asyncio.all_tasks()
    yield
    leaked = {task for task in asyncio.all_tasks() if task not in before}
    leaked.discard(asyncio.current_task())
    assert not leaked, f"leaked tasks: {leaked}"


@pytest.fixture
async def input_sensor_task(stream_clients, broker, no_task_leaks):
    s = broker.get_connection_str()
    ps_config = PubSubConfig.resolve(NAMESPACE, *s)
    tk = asyncio.create_task(input_sensor(ps_config))
    try:
        yield tk
    finally:
        tk.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tk
