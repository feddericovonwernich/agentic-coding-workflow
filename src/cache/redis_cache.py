"""Redis cache implementation."""

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as redis
    from redis.exceptions import RedisError
else:
    redis = None
    RedisError = Exception

try:
    import redis.asyncio as _redis_module
    from redis.exceptions import RedisError as _RedisError

    REDIS_AVAILABLE = True
    redis = _redis_module
    RedisError = _RedisError  # type: ignore[misc]
except ImportError:
    REDIS_AVAILABLE = False
    if not TYPE_CHECKING:
        redis = None  # type: ignore[assignment]
        RedisError = Exception  # type: ignore[assignment,misc]

from .base import BaseCache


class RedisCache(BaseCache[Any]):
    """Redis-based cache implementation with JSON serialization."""

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        default_ttl: int = 300,
        # Note: Only JSON serialization supported for security
        key_prefix: str = "app_cache",
    ):
        """Initialize Redis cache.

        Args:
            url: Redis connection URL
            default_ttl: Default TTL in seconds
            # Note: Only JSON serialization supported for security reasons
            key_prefix: Prefix for all cache keys
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for RedisCache")

        self.url = url
        self.default_ttl = default_ttl
        # Always use JSON for security
        self.serialization = "json"
        self.key_prefix = key_prefix
        self._client: Any | None = None

    async def _get_client(self) -> Any:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(self.url, decode_responses=False)
        return self._client

    def _serialize(self, value: Any) -> bytes:
        """Serialize value for storage using JSON."""
        return json.dumps(value, default=str).encode("utf-8")

    def _deserialize(self, data: bytes) -> Any:
        """Deserialize value from storage using JSON."""
        return json.loads(data.decode("utf-8"))

    def _make_redis_key(self, key: str) -> str:
        """Create Redis key with prefix."""
        sanitized = self.sanitize_key(key)
        return f"{self.key_prefix}:{sanitized}"

    async def get(self, key: str) -> Any | None:
        """Get value from cache by key."""
        try:
            client = await self._get_client()
            redis_key = self._make_redis_key(key)
            data = await client.get(redis_key)

            if data is None:
                return None

            return self._deserialize(data)
        except (RedisError, json.JSONDecodeError):
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache with optional TTL."""
        try:
            client = await self._get_client()
            redis_key = self._make_redis_key(key)
            data = self._serialize(value)

            ttl_to_use = ttl if ttl is not None else self.default_ttl

            if ttl_to_use > 0:
                await client.setex(redis_key, ttl_to_use, data)
            else:
                await client.set(redis_key, data)
        except (RedisError, json.JSONDecodeError):
            # Fail silently - cache is not critical
            pass

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        try:
            client = await self._get_client()
            redis_key = self._make_redis_key(key)
            result = await client.delete(redis_key)
            return bool(result > 0)
        except RedisError:
            return False

    async def clear(self, pattern: str | None = None) -> int:
        """Clear cache entries."""
        try:
            client = await self._get_client()

            if pattern is None:
                # Clear all keys with our prefix
                pattern = f"{self.key_prefix}:*"
            else:
                # Apply prefix to pattern
                pattern = f"{self.key_prefix}:{pattern}"

            keys = await client.keys(pattern)
            if keys:
                deleted_count = await client.delete(*keys)
                return int(deleted_count)
            return 0
        except RedisError:
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            client = await self._get_client()
            redis_key = self._make_redis_key(key)
            result = await client.exists(redis_key)
            return bool(result > 0)
        except RedisError:
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment numeric value in cache."""
        try:
            client = await self._get_client()
            redis_key = self._make_redis_key(key)
            result = await client.incrby(redis_key, amount)
            return int(result)
        except RedisError:
            return 0

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL for existing key."""
        try:
            client = await self._get_client()
            redis_key = self._make_redis_key(key)
            result = await client.expire(redis_key, ttl)
            return bool(result)
        except RedisError:
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None

    async def ping(self) -> bool:
        """Test Redis connection."""
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except RedisError:
            return False

    async def stats(self) -> dict[str, Any]:
        """Get cache statistics from Redis INFO."""
        try:
            client = await self._get_client()
            info = await client.info()
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_ratio": self._calculate_hit_ratio(
                    info.get("keyspace_hits", 0), info.get("keyspace_misses", 0)
                ),
            }
        except RedisError:
            return {}

    def _calculate_hit_ratio(self, hits: int, misses: int) -> float:
        """Calculate cache hit ratio."""
        total = hits + misses
        return hits / total if total > 0 else 0.0
