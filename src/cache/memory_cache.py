"""In-memory cache implementation."""

import asyncio
import time
from typing import Any

from .base import BaseCache


class MemoryCache(BaseCache[Any]):
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """Initialize memory cache.

        Args:
            max_size: Maximum number of items to store
            default_ttl: Default TTL in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: dict[str, tuple[Any, float | None]] = {}
        self._access_times: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Get value from cache by key."""
        async with self._lock:
            if key not in self._cache:
                return None

            value, expires_at = self._cache[key]

            # Check if expired
            if expires_at and time.time() > expires_at:
                del self._cache[key]
                self._access_times.pop(key, None)
                return None

            # Update access time for LRU
            self._access_times[key] = time.time()
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache with optional TTL."""
        async with self._lock:
            # Calculate expiration time
            expires_at = None
            if ttl is not None:
                expires_at = time.time() + ttl
            elif self.default_ttl > 0:
                expires_at = time.time() + self.default_ttl

            # Add to cache
            self._cache[key] = (value, expires_at)
            self._access_times[key] = time.time()

            # Evict if over max size
            await self._evict_if_needed()

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._access_times.pop(key, None)
                return True
            return False

    async def clear(self, pattern: str | None = None) -> int:
        """Clear cache entries."""
        async with self._lock:
            if pattern is None:
                count = len(self._cache)
                self._cache.clear()
                self._access_times.clear()
                return count

            # Pattern matching (simple glob-style)
            import fnmatch

            keys_to_delete = [
                key for key in self._cache if fnmatch.fnmatch(key, pattern)
            ]

            for key in keys_to_delete:
                del self._cache[key]
                self._access_times.pop(key, None)

            return len(keys_to_delete)

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        async with self._lock:
            if key not in self._cache:
                return False

            value, expires_at = self._cache[key]

            # Check if expired
            if expires_at and time.time() > expires_at:
                del self._cache[key]
                self._access_times.pop(key, None)
                return False

            return True

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment numeric value in cache."""
        async with self._lock:
            current = 0
            expires_at = None

            if key in self._cache:
                value, expires_at = self._cache[key]
                if isinstance(value, int | float):
                    current = int(value)

            new_value = current + amount
            self._cache[key] = (new_value, expires_at)
            self._access_times[key] = time.time()

            return new_value

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL for existing key."""
        async with self._lock:
            if key not in self._cache:
                return False

            value, _ = self._cache[key]
            expires_at = time.time() + ttl
            self._cache[key] = (value, expires_at)
            return True

    async def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache is over max size."""
        while len(self._cache) > self.max_size:
            # Remove least recently used item
            oldest_key = min(
                self._access_times.keys(), key=lambda x: self._access_times[x]
            )
            del self._cache[oldest_key]
            del self._access_times[oldest_key]

    async def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed items."""
        async with self._lock:
            current_time = time.time()
            expired_keys = []

            for key, (_value, expires_at) in self._cache.items():
                if expires_at and current_time > expires_at:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]
                self._access_times.pop(key, None)

            return len(expired_keys)

    async def invalidate(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern. Alias for clear method."""
        return await self.clear(pattern)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_ratio": None,  # Would need to track hits/misses
            "default_ttl": self.default_ttl,
        }
