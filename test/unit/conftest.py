import asyncio

import pytest

from radical.doppelganger import ZMQ_BrokerProcess, connect_stream_client


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

    async def make(namespace: str):
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
