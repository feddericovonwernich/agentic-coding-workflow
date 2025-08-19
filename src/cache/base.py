"""Abstract base cache interface."""

import uuid
from abc import ABC, abstractmethod
from typing import Any


class BaseCache[T](ABC):
    """Abstract base class for cache implementations."""

    @abstractmethod
    async def get(self, key: str) -> T | None:
        """Get value from cache by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: T, ttl: int | None = None) -> None:
        """Set value in cache with optional TTL in seconds."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete value from cache. Returns True if key existed."""
        pass

    @abstractmethod
    async def clear(self, pattern: str | None = None) -> int:
        """Clear cache entries. If pattern provided, only clear matching keys."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass

    @abstractmethod
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment numeric value in cache."""
        pass

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL for existing key."""
        pass

    def make_key(self, prefix: str, *parts: Any) -> str:
        """Create cache key from prefix and parts."""
        key_parts = [str(prefix)]
        for part in parts:
            if isinstance(part, uuid.UUID):
                key_parts.append(str(part))
            elif isinstance(part, list | tuple):
                key_parts.append(",".join(str(p) for p in part))
            elif isinstance(part, dict):
                # Sort dict items for consistent keys
                sorted_items = sorted(part.items())
                key_parts.append(",".join(f"{k}:{v}" for k, v in sorted_items))
            else:
                key_parts.append(str(part))
        return ":".join(key_parts)

    def sanitize_key(self, key: str) -> str:
        """Sanitize cache key to ensure it's valid."""
        # Replace problematic characters with underscores
        sanitized = key.replace(" ", "_").replace("/", "_").replace("\\", "_")
        # Limit key length (Redis has 512MB limit, but keep it reasonable)
        if len(sanitized) > 250:
            # Hash long keys but keep prefix for debugging
            import hashlib

            hash_part = hashlib.sha256(sanitized.encode()).hexdigest()[:16]
            prefix = sanitized[:100]
            sanitized = f"{prefix}...{hash_part}"
        return sanitized
