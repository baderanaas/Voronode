"""Simple in-process TTL cache for endpoint responses."""

import time
from typing import Any, Optional


class TTLCache:
    """Thread-safe-enough dict-backed cache with per-entry TTL.

    Usage:
        _cache = TTLCache(ttl=60)

        value = _cache.get(key)
        if value is None:
            value = expensive_call()
            _cache.set(key, value)
    """

    def __init__(self, ttl: float):
        self._ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._prune()
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        """Remove all keys that start with prefix."""
        stale = [k for k in self._store if k.startswith(prefix)]
        for k in stale:
            del self._store[k]

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if exp <= now]
        for k in expired:
            del self._store[k]
