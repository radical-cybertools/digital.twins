"""Shared-subtask memoisation: the lock survives cancellation, and a run
that failed or was cancelled is not replayed from the cache.

The wrapper under test lives in :meth:`RuntimeAPI.register_shared_subtask`
and needs no engine or stream -- an ``_AnnotatedComponent`` around a bare
``SciAgent`` is enough to exercise it (issue #12).
"""

import asyncio

import pytest

from digitaltwin.components import SciAgent, SharedSubtaskLabel
from digitaltwin.runtime import RuntimeAPI, _AnnotatedComponent


def make_api():
    ant = _AnnotatedComponent(SciAgent(flow=None))
    return RuntimeAPI(None, ant)


async def test_concurrent_calls_share_one_execution():
    """Two callers with the same arguments, one run of the task."""

    api = make_api()
    calls = []

    async def slow(x):
        calls.append(x)
        await asyncio.sleep(0.05)
        return x * 2

    shared = api.register_shared_subtask(SharedSubtaskLabel("slow"), slow)

    assert await asyncio.gather(shared(21), shared(21)) == [42, 42]
    assert calls == [21]

    # and a different key is a different run
    assert await shared(1) == 2
    assert calls == [21, 1]


async def test_a_failed_run_is_not_cached():
    """A transient failure must not poison the key for later callers."""

    api = make_api()
    attempts = []

    async def flaky(x):
        attempts.append(x)
        if len(attempts) == 1:
            raise RuntimeError("transient")
        return x

    shared = api.register_shared_subtask(SharedSubtaskLabel("flaky"), flaky)

    with pytest.raises(RuntimeError):
        await shared(7)

    assert await shared(7) == 7
    assert attempts == [7, 7]


async def test_a_cancelled_caller_leaves_the_label_usable():
    """Cancellation mid-call must release the lock and not poison the key."""

    api = make_api()
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(x):
        started.set()
        await release.wait()
        return x

    shared = api.register_shared_subtask(SharedSubtaskLabel("slow"), slow)

    caller = asyncio.ensure_future(shared(1))
    await started.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    # the lock is free and the label still answers
    release.set()
    assert await asyncio.wait_for(shared(2), timeout=5) == 2


async def test_cancelling_one_waiter_does_not_fail_the_other():
    """The shared future is shielded from any single caller's cancellation."""

    api = make_api()
    started = asyncio.Event()
    release = asyncio.Event()
    runs = []

    async def slow(x):
        runs.append(x)
        started.set()
        await release.wait()
        return x

    shared = api.register_shared_subtask(SharedSubtaskLabel("slow"), slow)

    first = asyncio.ensure_future(shared(5))
    await started.wait()
    second = asyncio.ensure_future(shared(5))
    await asyncio.sleep(0)

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    release.set()
    assert await asyncio.wait_for(second, timeout=5) == 5
    assert runs == [5]
