"""Cache decorators for repository methods."""

import functools
import hashlib
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from .cache_manager import CacheManager

F = TypeVar("F", bound=Callable[..., Any])

# Global cache manager instance
_cache_manager: CacheManager | None = None


def set_cache_manager(manager: CacheManager) -> None:
    """Set the global cache manager instance."""
    global _cache_manager
    _cache_manager = manager


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager.create_default()
    return _cache_manager


def cached_query(
    ttl: int = 300,
    key_prefix: str | None = None,
    invalidate_on: list[str] | None = None,
    serialize_args: bool = True,
    ignore_args: list[str] | None = None,
) -> Callable[[F], F]:
    """Decorator to cache query results.

    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key (defaults to function name)
        invalidate_on: List of method names that should invalidate this cache
        serialize_args: Whether to include function arguments in cache key
        ignore_args: List of argument names to ignore in cache key generation
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = get_cache_manager()

            # Generate cache key
            cache_key = _generate_cache_key(
                func, args, kwargs, key_prefix, serialize_args, ignore_args
            )

            # Try to get from cache
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function and cache result
            result = await func(*args, **kwargs)
            if result is not None:
                await cache.set(cache_key, result, ttl)

            return result

        # Store cache metadata on the function
        wrapper._cache_config = {  # type: ignore
            "ttl": ttl,
            "key_prefix": key_prefix,
            "invalidate_on": invalidate_on or [],
            "serialize_args": serialize_args,
            "ignore_args": ignore_args or [],
        }

        return wrapper  # type: ignore

    return decorator


def invalidate_cache(
    patterns: str | list[str] | None = None,
    key_prefix: str | None = None,
) -> Callable[[F], F]:
    """Decorator to invalidate cache entries after method execution.

    Args:
        patterns: Cache key patterns to invalidate
        key_prefix: Prefix for cache keys to invalidate
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Execute function first
            result = await func(*args, **kwargs)

            # Invalidate cache entries
            cache = get_cache_manager()

            if patterns:
                pattern_list = patterns if isinstance(patterns, list) else [patterns]
                for pattern in pattern_list:
                    await cache.clear(pattern)

            if key_prefix:
                await cache.clear(f"{key_prefix}:*")

            # Auto-invalidate based on method name
            await _auto_invalidate_cache(func, args, kwargs)

            return result

        return wrapper  # type: ignore

    return decorator


def cache_result(
    ttl: int = 300,
    key: str | None = None,
    condition: Callable[..., bool] | None = None,
) -> Callable[[F], F]:
    """Simple cache decorator for individual results.

    Args:
        ttl: Time to live in seconds
        key: Static cache key (if None, generates from function and args)
        condition: Function to determine if result should be cached
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = get_cache_manager()

            # Generate or use provided key
            cache_key = key or _generate_cache_key(func, args, kwargs)

            # Try to get from cache
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result if condition is met
            should_cache = condition is None or condition(result, *args, **kwargs)
            if should_cache and result is not None:
                await cache.set(cache_key, result, ttl)

            return result

        return wrapper  # type: ignore

    return decorator


def _generate_cache_key(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    key_prefix: str | None = None,
    serialize_args: bool = True,
    ignore_args: list[str] | None = None,
) -> str:
    """Generate cache key for function call."""
    # Start with function identifier
    module = getattr(func, "__module__", "unknown")
    name = getattr(func, "__name__", "unknown")
    prefix = key_prefix or f"{module}.{name}"

    if not serialize_args:
        return prefix

    # Get function signature for parameter names
    sig = inspect.signature(func)
    param_names = list(sig.parameters.keys())
    ignore_set = set(ignore_args or [])

    # Build key parts from arguments
    key_parts = [prefix]

    # Process positional arguments
    for i, arg in enumerate(args):
        if i < len(param_names):
            param_name = param_names[i]
            if param_name not in ignore_set:
                key_parts.append(_serialize_arg(param_name, arg))

    # Process keyword arguments
    for param_name, value in kwargs.items():
        if param_name not in ignore_set:
            key_parts.append(_serialize_arg(param_name, value))

    # Create final key
    cache_key = ":".join(key_parts)

    # Hash if too long
    if len(cache_key) > 200:
        hash_obj = hashlib.sha256(cache_key.encode())
        return f"{prefix}:hash:{hash_obj.hexdigest()[:16]}"

    return cache_key


def _serialize_arg(name: str, value: Any) -> str:
    """Serialize argument value for cache key."""
    if value is None:
        return f"{name}:null"
    elif isinstance(value, str | int | float | bool):
        return f"{name}:{value}"
    elif isinstance(value, list | tuple):
        serialized = ",".join(str(v) for v in value)
        return f"{name}:[{serialized}]"
    elif isinstance(value, dict):
        # Sort for consistency
        items = sorted(value.items())
        serialized = ",".join(f"{k}={v}" for k, v in items)
        return f"{name}:{{{serialized}}}"
    else:
        # For complex objects, use string representation
        return f"{name}:{value!s}"


async def _auto_invalidate_cache(
    func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    """Auto-invalidate cache entries based on method name and class."""
    cache = get_cache_manager()

    # Get class name if this is a method
    if args and hasattr(args[0], "__class__"):
        class_name = args[0].__class__.__name__
        method_name = getattr(func, "__name__", "unknown")

        # Common invalidation patterns
        if method_name in ["create", "update", "delete", "save"]:
            # Invalidate all queries for this repository
            await cache.clear(f"*{class_name}*")

        elif (
            method_name.startswith("update_") or method_name.startswith("delete_")
        ) and len(args) > 1:
            # Invalidate specific entity queries
            entity_id = args[1]
            await cache.clear(f"*{class_name}*{entity_id}*")


class CacheWarmer:
    """Utility for warming up cache with frequently accessed data."""

    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager

    async def warm_repository_data(
        self, repository: Any, entity_ids: list[Any], ttl: int = 600
    ) -> None:
        """Pre-load common repository queries into cache."""
        class_name = repository.__class__.__name__

        # Warm up individual entity queries
        for entity_id in entity_ids:
            try:
                entity = await repository.get_by_id(entity_id)
                if entity:
                    key = f"{class_name}:get_by_id:{entity_id}"
                    await self.cache.set(key, entity, ttl)
            except Exception as e:
                # Log cache warmup failure and continue with next entity
                import logging

                logger = logging.getLogger(__name__)
                logger.debug(f"Cache warmup failed for entity {entity_id}: {e}")
                continue

    async def warm_statistics(
        self, repository: Any, repository_ids: list[Any], ttl: int = 300
    ) -> None:
        """Pre-load statistics that are frequently accessed."""
        if not hasattr(repository, "get_statistics"):
            return

        for repo_id in repository_ids:
            try:
                stats = await repository.get_statistics(repo_id)
                if stats:
                    key = f"{repository.__class__.__name__}:statistics:{repo_id}"
                    await self.cache.set(key, stats, ttl)
            except Exception as e:
                # Log statistics warmup failure and continue
                import logging

                logger = logging.getLogger(__name__)
                logger.debug(f"Statistics warmup failed for repo {repo_id}: {e}")
                continue
