"""Discovery cache implementation with Redis and memory backends.

This module provides intelligent caching for API responses with ETag support,
TTL strategies, and fallback mechanisms for improved performance.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import time
from typing import Any

import redis.asyncio as aioredis

from src.cache.memory_cache import MemoryCache

from .interfaces import CacheStrategy

logger = logging.getLogger(__name__)


class DiscoveryCache(CacheStrategy):
    """Multi-tier cache implementation for discovery operations.

    Provides L1 (memory) and L2 (Redis) caching with ETag support
    and intelligent cache invalidation strategies.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        memory_cache_size: int = 1000,
        default_ttl: int = 300,
        compression_threshold: int = 1024,
    ):
        """Initialize cache with Redis and memory backends.

        Args:
            redis_url: Redis connection URL (optional)
            memory_cache_size: Maximum entries in memory cache
            default_ttl: Default TTL in seconds
            compression_threshold: Compress values larger than this size
        """
        self.default_ttl = default_ttl
        self.compression_threshold = compression_threshold

        # Initialize memory cache (L1)
        self.memory_cache = MemoryCache(max_size=memory_cache_size)

        # Initialize Redis cache (L2) if URL provided
        self.redis_client: aioredis.Redis | None = None
        if redis_url:
            try:
                self.redis_client = aioredis.from_url(
                    redis_url,
                    decode_responses=False,  # We handle encoding ourselves
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                )
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self.redis_client = None

        # Metrics tracking
        self.stats = {"l1_hits": 0, "l2_hits": 0, "misses": 0, "sets": 0, "errors": 0}

    async def close(self) -> None:
        """Close cache connections."""
        if self.redis_client:
            await self.redis_client.close()

    def _generate_key(self, key: str) -> str:
        """Generate normalized cache key with prefix."""
        # Use hash for long keys to ensure Redis compatibility
        if len(key) > 200:
            key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
            return f"disc:{key_hash}"
        return f"disc:{key}"

    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value for caching."""
        try:
            serialized = json.dumps(value, default=str).encode("utf-8")

            # TODO: Add compression for large values if needed
            # if len(serialized) > self.compression_threshold:
            #     serialized = gzip.compress(serialized)
            #     return b'compressed:' + serialized

            return serialized
        except Exception as e:
            logger.warning(f"Failed to serialize cache value: {e}")
            return b""

    def _deserialize_value(self, data: bytes) -> Any:
        """Deserialize cached value."""
        if not data:
            return None

        try:
            # TODO: Handle decompression if implemented
            # if data.startswith(b'compressed:'):
            #     data = gzip.decompress(data[11:])

            return json.loads(data.decode("utf-8"))
        except Exception as e:
            logger.warning(f"Failed to deserialize cache value: {e}")
            return None

    async def get(self, key: str) -> Any | None:
        """Get cached value with L1/L2 cascade.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        cache_key = self._generate_key(key)

        # Try L1 cache first (memory)
        try:
            value = await self.memory_cache.get(cache_key)
            if value is not None:
                self.stats["l1_hits"] += 1
                logger.debug(f"Cache L1 hit for key: {cache_key}")
                return value
        except Exception as e:
            logger.debug(f"L1 cache error for key {cache_key}: {e}")

        # Try L2 cache (Redis)
        if self.redis_client:
            try:
                data = await self.redis_client.get(cache_key)
                if data:
                    value = self._deserialize_value(data)
                    if value is not None:
                        self.stats["l2_hits"] += 1
                        logger.debug(f"Cache L2 hit for key: {cache_key}")

                        # Populate L1 cache
                        with contextlib.suppress(Exception):
                            await self.memory_cache.set(cache_key, value, ttl=60)

                        return value
            except Exception as e:
                logger.warning(f"Redis cache error for key {cache_key}: {e}")
                self.stats["errors"] += 1

        self.stats["misses"] += 1
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set cached value in both L1 and L2.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
        """
        if ttl is None:
            ttl = self.default_ttl

        cache_key = self._generate_key(key)
        self.stats["sets"] += 1

        # Set in L1 cache (memory) with shorter TTL
        try:
            memory_ttl = min(ttl, 60)  # Max 1 minute in memory
            await self.memory_cache.set(cache_key, value, ttl=memory_ttl)
            logger.debug(f"Set L1 cache for key: {cache_key}")
        except Exception as e:
            logger.debug(f"L1 cache set error for key {cache_key}: {e}")

        # Set in L2 cache (Redis)
        if self.redis_client:
            try:
                serialized = self._serialize_value(value)
                if serialized:
                    await self.redis_client.setex(cache_key, ttl, serialized)
                    logger.debug(f"Set L2 cache for key: {cache_key} (TTL: {ttl}s)")
            except Exception as e:
                logger.warning(f"Redis cache set error for key {cache_key}: {e}")
                self.stats["errors"] += 1

    async def invalidate(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern.

        Args:
            pattern: Pattern to match cache keys

        Returns:
            Number of entries invalidated
        """
        total_invalidated = 0
        normalized_pattern = f"disc:*{pattern}*"

        # Invalidate from L1 cache (memory)
        try:
            memory_invalidated = await self.memory_cache.invalidate(normalized_pattern)
            total_invalidated += memory_invalidated
            logger.debug(f"Invalidated {memory_invalidated} L1 cache entries")
        except Exception as e:
            logger.debug(f"L1 cache invalidation error: {e}")

        # Invalidate from L2 cache (Redis)
        if self.redis_client:
            try:
                # Find keys matching pattern
                keys = await self.redis_client.keys(normalized_pattern)
                if keys:
                    redis_invalidated = await self.redis_client.delete(*keys)
                    total_invalidated += redis_invalidated
                    logger.debug(f"Invalidated {redis_invalidated} L2 cache entries")
            except Exception as e:
                logger.warning(f"Redis cache invalidation error: {e}")
                self.stats["errors"] += 1

        return total_invalidated

    async def get_with_etag(self, key: str) -> tuple[Any | None, str | None]:
        """Get cached value with ETag for conditional requests.

        Args:
            key: Cache key

        Returns:
            Tuple of (cached value, etag)
        """
        etag_key = f"{key}:etag"

        # Get both value and etag
        value_task = self.get(key)
        etag_task = self.get(etag_key)

        results = await asyncio.gather(value_task, etag_task, return_exceptions=True)
        value_result, etag_result = results

        # Handle exceptions from gather
        value: Any = None
        etag: str | None = None

        if isinstance(value_result, Exception):
            logger.debug(f"Error getting cached value: {value_result}")
            value = None
        else:
            value = value_result

        if isinstance(etag_result, Exception):
            logger.debug(f"Error getting cached etag: {etag_result}")
            etag = None
        else:
            # Ensure etag_result is properly typed as str or None
            etag = etag_result if isinstance(etag_result, str | type(None)) else None

        return value, etag

    async def set_with_etag(
        self, key: str, value: Any, etag: str, ttl: int | None = None
    ) -> None:
        """Set cached value with ETag for conditional requests.

        Args:
            key: Cache key
            value: Value to cache
            etag: ETag for conditional requests
            ttl: Time-to-live in seconds
        """
        etag_key = f"{key}:etag"

        # Set both value and etag with same TTL
        await asyncio.gather(
            self.set(key, value, ttl),
            self.set(etag_key, etag, ttl),
            return_exceptions=True,
        )

    async def get_entry_count(self) -> int:
        """Get total number of cached entries."""
        total = 0

        # Count L1 entries
        with contextlib.suppress(Exception):
            total += len(self.memory_cache._cache)

        # Count L2 entries (approximate)
        if self.redis_client:
            try:
                keys = await self.redis_client.keys("disc:*")
                total += len(keys)
            except Exception as e:
                logger.debug(f"Failed to count Redis cache entries: {e}")
                self.stats["errors"] += 1

        return total

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = (
            self.stats["l1_hits"] + self.stats["l2_hits"] + self.stats["misses"]
        )

        return {
            "total_requests": total_requests,
            "l1_hits": self.stats["l1_hits"],
            "l2_hits": self.stats["l2_hits"],
            "misses": self.stats["misses"],
            "sets": self.stats["sets"],
            "errors": self.stats["errors"],
            "hit_rate": (
                (self.stats["l1_hits"] + self.stats["l2_hits"]) / total_requests
                if total_requests > 0
                else 0.0
            ),
            "l1_hit_rate": (
                self.stats["l1_hits"] / total_requests if total_requests > 0 else 0.0
            ),
        }

    async def warm_cache(
        self, entries: dict[str, tuple[Any, str | None]], ttl: int | None = None
    ) -> None:
        """Warm cache with multiple entries efficiently.

        Args:
            entries: Dictionary of key -> (value, etag) pairs
            ttl: Time-to-live for all entries
        """
        if not entries:
            return

        logger.info(f"Warming cache with {len(entries)} entries")

        # Prepare all cache operations
        operations = []
        for key, (value, etag) in entries.items():
            if etag:
                operations.append(self.set_with_etag(key, value, etag, ttl))
            else:
                operations.append(self.set(key, value, ttl))

        # Execute all operations concurrently
        try:
            results = await asyncio.gather(*operations, return_exceptions=True)

            # Log any errors
            error_count = sum(1 for result in results if isinstance(result, Exception))
            if error_count > 0:
                logger.warning(f"Cache warming completed with {error_count} errors")
            else:
                logger.info("Cache warming completed successfully")

        except Exception as e:
            logger.error(f"Cache warming failed: {e}")

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on cache backends."""
        health = {
            "healthy": True,
            "l1_cache": {"healthy": True, "error": None},
            "l2_cache": {"healthy": True, "error": None},
        }

        # Test L1 cache (memory)
        try:
            test_key = f"health_check_{int(time.time())}"
            await self.memory_cache.set(test_key, "test", ttl=1)
            await self.memory_cache.get(test_key)
        except Exception as e:
            health["l1_cache"] = {"healthy": False, "error": str(e)}
            health["healthy"] = False

        # Test L2 cache (Redis)
        if self.redis_client:
            try:
                test_key = f"disc:health_check_{int(time.time())}"
                await self.redis_client.set(test_key, "test", ex=1)
                await self.redis_client.get(test_key)
                await self.redis_client.delete(test_key)
            except Exception as e:
                health["l2_cache"] = {"healthy": False, "error": str(e)}
                health["healthy"] = False
        else:
            health["l2_cache"] = {"healthy": False, "error": "Redis not configured"}

        return health
