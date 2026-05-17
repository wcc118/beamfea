"""Bounded in-memory cache with TTL and max-size eviction.

Designed for API model and result stores.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Generic, TypeVar

T = TypeVar("T")


class TimeLRUCache(Generic[T]):
    """Dict-like cache with max-size limit and inactivity-based TTL.

    Parameters
    ----------
    maxsize :
        Maximum number of entries. When reached, ``__setitem__`` evicts
        the oldest entry. ``maxsize <= 0`` disables size limits.
    ttl_seconds :
        Seconds of inactivity after which an entry is considered expired.
        ``ttl_seconds <= 0`` disables TTL.
    """

    def __init__(self, maxsize: int = 0, ttl_seconds: float = 0) -> None:
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._data: OrderedDict[str, tuple[T, float]] = OrderedDict()

    # -- dict-like API ---------------------------------------------------- #

    def __contains__(self, key: str) -> bool:
        """Return True if key is present (no side effects)."""
        return key in self._data

    def __getitem__(self, key: str) -> T:
        if key not in self._data:
            raise KeyError(key)
        value, _ = self._data[key]
        if self._ttl_seconds > 0:
            if time.time() - self._data[key][1] > self._ttl_seconds:
                del self._data[key]
                raise KeyError(key)
        self._touch(key)
        return value

    def __setitem__(self, key: str, value: T) -> None:
        if key in self._data:
            self._data[key] = (value, time.time())
            self._touch(key)
        else:
            self._data[key] = (value, time.time())
            if self._maxsize > 0 and len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def get(self, key: str) -> T | None:
        """Return value or None if missing / expired."""
        try:
            return self[key]
        except KeyError:
            return None

    # -- Utility methods -------------------------------------------------- #

    def clear(self) -> None:
        """Remove all entries."""
        self._data.clear()

    def cleanup(self) -> None:
        """Remove entries whose inactivity exceeds the TTL."""
        if self._ttl_seconds <= 0:
            return
        now = time.time()
        expired = {k for k, (_, ts) in self._data.items()
                   if now - ts > self._ttl_seconds}
        for k in expired:
            del self._data[k]

    @property
    def keys(self):
        """View of currently stored keys."""
        return self._data.keys()

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return (f"{type(self).__name__}(maxsize={self._maxsize}, "
                f"ttl={self._ttl_seconds}s, items={len(self._data)})")

    def _touch(self, key: str) -> None:
        """Update access timestamp and reorder."""
        if key in self._data:
            value, _ = self._data.pop(key)
            self._data[key] = (value, time.time())
            self._data.move_to_end(key)
