# src/digitaltwin/lru.py
"""Asynchronous LRU cache.

This module implements a minimal LRU cache that is safe for concurrent
access in an asyncio program. ``LRUCache`` stores key/value pairs in an
:class:`collections.OrderedDict` and evicts the oldest entry when the
configured ``max_size`` is exceeded.

Typical usage pattern:

    cache = LRUCache(size=128)
    await cache.put_item("foo", 42)
    value = await cache.fetch_item("foo")

The API is short and to the point - only ``put_item``, ``fetch_item``,
``exists`` and ``drop`` are public.
"""

import asyncio
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

_MISSING = object()

# Helper freeze functions:


def freeze(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return (
            frozenset((freeze(key), freeze(value)) for key, value in obj.items()),
            type(obj),
        )

    if isinstance(obj, list):
        return tuple(freeze(item) for item in obj)

    if isinstance(obj, tuple):
        return tuple(freeze(item) for item in obj)

    if isinstance(obj, (set, frozenset)):
        return (frozenset(freeze(item) for item in obj), freeze(type(obj)))

    try:
        hash(obj)

    except TypeError:
        raise TypeError(f"Cannot freeze object of type {type(obj).__name__}")

    return obj


class LRUCache:
    """Async LRU cache.

    Args:
        size (int, optional): Maximum number of entries the cache can hold.
            When the limit is reached the least recent entry is removed.
            Defaults to 128.
    """

    def __init__(self, size: int = 128) -> None:
        self.cache: OrderedDict[Any, Any] = OrderedDict()
        self.edit_lock = asyncio.Lock()
        self.max_size = size

    async def put_item(self, key: Any, value: Any) -> None:
        """Insert or update a key/value pair.

        Args:
            key (Any): Key to store.
            value (Any): Value associated with the key.

        Returns:
            None
        """
        async with self.edit_lock:
            if key in self.cache:
                self.cache[key] = value
                self.cache.move_to_end(key)
                return

            # add key to value
            self.cache[key] = value

            # is size over max?
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

    async def fetch_item(self, key: Any) -> Any:
        """Retrieve an entry from the cache.

        Args:
            key (Any): Key of the entry to retrieve.

        Raises:
            KeyError: If *key* is not present in the cache.

        Returns:
            Any: The stored value.
        """

        async with self.edit_lock:
            if key not in self.cache:
                raise KeyError
            self.cache.move_to_end(key)
            return self.cache[key]

    async def exists(self, key: Any) -> bool:
        """Return ``True`` if *key* is in the cache, ``False`` otherwise."""

        async with self.edit_lock:
            return key in self.cache

    def drop(self, key: Any, value: Any = _MISSING) -> None:
        """Remove *key* from the cache if present.

        Synchronous on purpose: it is called from future done-callbacks,
        which run between event-loop callbacks and thus never interleave
        with the dict operations the async methods perform under
        ``edit_lock``.

        Args:
            key (Any): Key of the entry to remove.  Absent keys are ignored.
            value (Any, optional): When given, the entry is removed only
                while it still maps to this exact object -- so a stale
                callback cannot evict a successor entry under the same key.
        """

        if value is not _MISSING and self.cache.get(key) is not value:
            return
        self.cache.pop(key, None)
