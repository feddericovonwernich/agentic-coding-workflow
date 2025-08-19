"""Cache manager for coordinating multiple cache backends."""

import asyncio
import logging
from typing import Any

from .base import BaseCache
from .memory_cache import MemoryCache
from .redis_cache import RedisCache

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages multiple cache backends with fallback support."""

    def __init__(
        self,
        backends: list[BaseCache[Any]] | None = None,
        default_ttl: int = 300,
    ):
        """Initialize cache manager.

        Args:
            backends: List of cache backends (ordered by priority)
            default_ttl: Default TTL for cache entries
        """
        self.backends = backends or [MemoryCache(default_ttl=default_ttl)]
        self.default_ttl = default_ttl
        self._stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
        }

    @classmethod
    def create_default(
        cls,
        redis_url: str | None = None,
        memory_cache_size: int = 1000,
        default_ttl: int = 300,
    ) -> "CacheManager":
        """Create cache manager with default backends."""
        backends: list[BaseCache[Any]] = []

        # Add Redis cache if URL provided and available
        if redis_url:
            try:
                redis_cache = RedisCache(
                    url=redis_url,
                    default_ttl=default_ttl,
                )
                backends.append(redis_cache)
            except ImportError:
                logger.warning("Redis not available, using memory cache only")

        # Always add memory cache as fallback
        memory_cache = MemoryCache(
            max_size=memory_cache_size,
            default_ttl=default_ttl,
        )
        backends.append(memory_cache)

        return cls(backends=backends, default_ttl=default_ttl)

    async def get(self, key: str) -> Any | None:
        """Get value from cache, trying backends in order."""
        for i, backend in enumerate(self.backends):
            try:
                value = await backend.get(key)
                if value is not None:
                    self._stats["hits"] = int(self._stats["hits"]) + 1

                    # Write to higher-priority caches that missed
                    await self._populate_higher_caches(key, value, i)
                    return value
            except Exception as e:
                logger.warning(f"Cache backend error: {e}")
                self._stats["errors"] = int(self._stats["errors"]) + 1
                continue

        self._stats["misses"] = int(self._stats["misses"]) + 1
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in all cache backends."""
        ttl_to_use = ttl if ttl is not None else self.default_ttl

        tasks = []
        for backend in self.backends:
            task = self._safe_set(backend, key, value, ttl_to_use)
            tasks.append(task)

        # Set in all backends concurrently
        await asyncio.gather(*tasks, return_exceptions=True)

    async def delete(self, key: str) -> bool:
        """Delete value from all cache backends."""
        results = []
        for backend in self.backends:
            try:
                result = await backend.delete(key)
                results.append(result)
            except Exception as e:
                logger.warning(f"Cache delete error: {e}")
                self._stats["errors"] = int(self._stats["errors"]) + 1
                results.append(False)

        return any(results)

    async def clear(self, pattern: str | None = None) -> int:
        """Clear cache entries from all backends."""
        total_cleared = 0
        for backend in self.backends:
            try:
                cleared = await backend.clear(pattern)
                total_cleared += cleared
            except Exception as e:
                logger.warning(f"Cache clear error: {e}")
                self._stats["errors"] = int(self._stats["errors"]) + 1

        return total_cleared

    async def exists(self, key: str) -> bool:
        """Check if key exists in any cache backend."""
        for backend in self.backends:
            try:
                if await backend.exists(key):
                    return True
            except Exception as e:
                logger.warning(f"Cache exists error: {e}")
                self._stats["errors"] = int(self._stats["errors"]) + 1

        return False

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment value in primary cache backend."""
        if not self.backends:
            return 0

        try:
            return await self.backends[0].increment(key, amount)
        except Exception as e:
            logger.warning(f"Cache increment error: {e}")
            self._stats["errors"] += 1
            return 0

    async def _populate_higher_caches(
        self, key: str, value: Any, found_at_index: int
    ) -> None:
        """Populate higher-priority caches with found value."""
        if found_at_index == 0:
            return  # Already in highest priority cache

        tasks = []
        for i in range(found_at_index):
            backend = self.backends[i]
            task = self._safe_set(backend, key, value, self.default_ttl)
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_set(
        self, backend: BaseCache[Any], key: str, value: Any, ttl: int
    ) -> None:
        """Safely set value in backend, catching exceptions."""
        try:
            await backend.set(key, value, ttl)
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            self._stats["errors"] += 1

    async def health_check(self) -> dict[str, Any]:
        """Check health of all cache backends."""
        backend_health = []

        for i, backend in enumerate(self.backends):
            try:
                # Test basic operations
                test_key = f"health_check_{i}"
                await backend.set(test_key, "test", 10)
                value = await backend.get(test_key)
                await backend.delete(test_key)

                healthy = value == "test"
                backend_health.append(
                    {
                        "type": type(backend).__name__,
                        "healthy": healthy,
                        "error": None,
                    }
                )
            except Exception as e:
                backend_health.append(
                    {
                        "type": type(backend).__name__,
                        "healthy": False,
                        "error": str(e),
                    }
                )

        return {
            "backends": backend_health,
            "stats": self._stats.copy(),
            "hit_ratio": self._calculate_hit_ratio(),
        }

    def _calculate_hit_ratio(self) -> float:
        """Calculate overall cache hit ratio."""
        total = self._stats["hits"] + self._stats["misses"]
        return self._stats["hits"] / total if total > 0 else 0.0

    async def close(self) -> None:
        """Close all cache backends."""
        for backend in self.backends:
            if hasattr(backend, "close"):
                try:
                    await backend.close()
                except Exception as e:
                    logger.warning(f"Error closing cache backend: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "backends_count": len(self.backends),
            "stats": self._stats.copy(),
            "hit_ratio": self._calculate_hit_ratio(),
        }
