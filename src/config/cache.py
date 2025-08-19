"""Configuration caching system for high-performance configuration access.

This module provides an in-memory caching layer for configuration data that
optimizes access patterns commonly used throughout the application. It includes
cache invalidation, lazy loading, and memory optimization features.

The caching system is designed to:
- Minimize configuration access overhead for hot paths
- Support cache warming for critical configuration sections
- Provide thread-safe operations for concurrent access
- Enable cache invalidation on configuration changes
- Optimize memory usage for large configuration trees
"""

import threading
import time
from collections import defaultdict
from typing import Any
from weakref import WeakValueDictionary

from .exceptions import ConfigurationError
from .models import Config


class ConfigurationCache:
    """High-performance configuration cache with invalidation and lazy loading.

    This cache provides optimized access to configuration data with automatic
    invalidation, memory optimization, and thread safety for concurrent access.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize configuration cache.

        Args:
            config: Optional initial configuration to cache
        """
        self._config: Config | None = config
        self._cache: dict[str, Any] = {}
        self._access_counts: dict[str, int] = defaultdict(int)
        self._access_times: dict[str, float] = {}
        self._dirty_keys: set[str] = set()
        self._lock = threading.RLock()
        self._cache_version = 0
        self._warm_keys: set[str] = set()

        # Weak references for memory optimization
        self._weak_cache: WeakValueDictionary = WeakValueDictionary()

        # Cache statistics
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0

        # Configuration for cache behavior
        self._max_cache_size = 1000
        self._cache_ttl = 3600  # 1 hour default TTL
        self._enable_weak_refs = True

        if config:
            # Don't count cache warming in statistics
            initial_hits = self._cache_hits
            initial_misses = self._cache_misses
            self._warm_critical_paths()
            # Reset statistics after warming
            self._cache_hits = initial_hits
            self._cache_misses = initial_misses

    def get(self, key: str, default: Any = None) -> Any:
        """Get cached configuration value with performance tracking.

        Args:
            key: Configuration key (dot-notation supported)
            default: Default value if key not found

        Returns:
            Cached configuration value or default
        """
        with self._lock:
            # Track access patterns
            self._access_counts[key] += 1
            self._access_times[key] = time.time()

            # Check cache first
            if key in self._cache and key not in self._dirty_keys:
                self._cache_hits += 1
                return self._cache[key]

            # Cache miss - load from configuration
            self._cache_misses += 1
            value = self._load_config_value(key, default)

            # Store in cache if within size limits
            if len(self._cache) < self._max_cache_size:
                self._cache[key] = value
                self._dirty_keys.discard(key)
            else:
                # Evict least recently used items
                self._evict_lru_items()
                self._cache[key] = value
                self._dirty_keys.discard(key)

            return value

    def get_section(self, section: str) -> dict[str, Any]:
        """Get entire configuration section with optimized access.

        Args:
            section: Configuration section name (e.g., 'database', 'llm')

        Returns:
            Dictionary containing section configuration

        Raises:
            ConfigurationError: If section not found
        """
        if not self._config:
            raise ConfigurationError("No configuration loaded")

        with self._lock:
            cache_key = f"section:{section}"

            if cache_key in self._cache and cache_key not in self._dirty_keys:
                self._cache_hits += 1
                cached_section: dict[str, Any] = self._cache[cache_key]
                return cached_section

            # Load section data
            self._cache_misses += 1
            section_data: dict[str, Any] = self._extract_section(section)

            # Cache the section
            self._cache[cache_key] = section_data
            self._dirty_keys.discard(cache_key)

            return section_data

    def batch_get(self, keys: list[str]) -> dict[str, Any]:
        """Retrieve multiple configuration values in a single operation.

        Args:
            keys: List of configuration keys to retrieve

        Returns:
            Dictionary mapping keys to their values
        """
        result = {}

        with self._lock:
            for key in keys:
                result[key] = self.get(key)

        return result

    def set_config(self, config: Config) -> None:
        """Update cached configuration and invalidate as needed.

        Args:
            config: New configuration to cache
        """
        with self._lock:
            old_version = self._cache_version
            self._config = config
            self._cache_version += 1

            # Mark all cached items as potentially dirty
            if self._cache:
                self._dirty_keys.update(self._cache.keys())

            # Re-warm critical paths with new configuration
            if old_version != self._cache_version:
                # Save statistics before warming
                saved_hits = self._cache_hits
                saved_misses = self._cache_misses
                self._warm_critical_paths()
                # Restore statistics after warming
                self._cache_hits = saved_hits
                self._cache_misses = saved_misses

    def invalidate(self, pattern: str | None = None) -> None:
        """Invalidate cached configuration entries.

        Args:
            pattern: Optional pattern to match keys for invalidation.
                    If None, invalidates all entries.
        """
        with self._lock:
            if pattern is None:
                # Invalidate everything
                self._cache.clear()
                self._dirty_keys.clear()
                self._weak_cache.clear()
            else:
                # Invalidate matching keys
                keys_to_remove = [
                    key
                    for key in self._cache
                    if self._key_matches_pattern(key, pattern)
                ]

                for key in keys_to_remove:
                    self._cache.pop(key, None)
                    self._dirty_keys.discard(key)

    def warm_cache(self, keys: list[str] | None = None) -> None:
        """Pre-load configuration values into cache.

        Args:
            keys: Optional list of specific keys to warm.
                 If None, warms critical paths.
        """
        if keys is None:
            keys = list(self._warm_keys)

        with self._lock:
            for key in keys:
                # Force load into cache
                self.get(key)

    def get_statistics(self) -> dict[str, Any]:
        """Get cache performance statistics.

        Returns:
            Dictionary containing cache statistics
        """
        with self._lock:
            total_requests = self._cache_hits + self._cache_misses
            hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0

            return {
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_evictions": self._cache_evictions,
                "hit_rate": hit_rate,
                "cache_size": len(self._cache),
                "max_cache_size": self._max_cache_size,
                "cache_version": self._cache_version,
                "access_patterns": dict(self._access_counts),
                "warm_keys": list(self._warm_keys),
            }

    def clear_statistics(self) -> None:
        """Reset cache statistics counters."""
        with self._lock:
            self._cache_hits = 0
            self._cache_misses = 0
            self._cache_evictions = 0
            self._access_counts.clear()
            self._access_times.clear()
            # Don't clear the cache itself, just statistics

    def configure_cache(
        self,
        max_size: int | None = None,
        ttl: int | None = None,
        enable_weak_refs: bool | None = None,
    ) -> None:
        """Configure cache behavior parameters.

        Args:
            max_size: Maximum number of items to cache
            ttl: Time-to-live for cached items in seconds
            enable_weak_refs: Whether to use weak references for memory optimization
        """
        with self._lock:
            if max_size is not None:
                self._max_cache_size = max_size

            if ttl is not None:
                self._cache_ttl = ttl

            if enable_weak_refs is not None:
                self._enable_weak_refs = enable_weak_refs

    def _load_config_value(self, key: str, default: Any = None) -> Any:
        """Load configuration value from the underlying config object.

        Args:
            key: Configuration key in dot notation
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if not self._config:
            return default

        try:
            # Support dot notation for nested access
            value: Any = self._config
            for part in key.split("."):
                if hasattr(value, part):
                    value = getattr(value, part)
                elif isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default

            return value

        except (AttributeError, KeyError, TypeError):
            return default

    def _extract_section(self, section: str) -> dict[str, Any]:
        """Extract entire configuration section as dictionary.

        Args:
            section: Configuration section name

        Returns:
            Section data as dictionary

        Raises:
            ConfigurationError: If section not found
        """
        if not self._config:
            raise ConfigurationError("No configuration loaded")

        try:
            section_obj: Any = getattr(self._config, section)

            # Convert Pydantic model to dict if needed
            if hasattr(section_obj, "model_dump"):
                model_result: dict[str, Any] = section_obj.model_dump()
                return model_result
            elif hasattr(section_obj, "dict"):
                dict_result: dict[str, Any] = section_obj.dict()
                return dict_result
            elif isinstance(section_obj, dict):
                return dict(section_obj)
            else:
                # Try to convert to dict
                return dict(section_obj) if section_obj else {}

        except AttributeError as e:
            raise ConfigurationError(
                f"Configuration section '{section}' not found"
            ) from e

    def _warm_critical_paths(self) -> None:
        """Pre-load configuration values for critical application paths."""
        if not self._config:
            return

        # Define critical configuration paths that should be cached
        critical_keys = [
            "database.url",
            "database.pool_size",
            "queue.url",
            "queue.provider",
            "default_llm_provider",
            "system.environment",
            "system.debug_mode",
            "notification.enabled",
        ]

        # Add LLM provider configurations
        for provider_name in getattr(self._config.llm, "keys", lambda: [])():
            critical_keys.extend(
                [
                    f"llm.{provider_name}.api_key",
                    f"llm.{provider_name}.model",
                    f"llm.{provider_name}.max_tokens",
                ]
            )

        # Store warm keys for future warming
        self._warm_keys.update(critical_keys)

        # Warm the cache
        for key in critical_keys:
            self.get(key)

    def _evict_lru_items(self, count: int = 10) -> None:
        """Evict least recently used cache items.

        Args:
            count: Number of items to evict
        """
        if not self._access_times:
            return

        # Sort by access time (oldest first)
        sorted_items = sorted(self._access_times.items(), key=lambda x: x[1])

        # Remove oldest items
        for key, _ in sorted_items[:count]:
            self._cache.pop(key, None)
            self._access_times.pop(key, None)
            self._access_counts.pop(key, None)
            self._dirty_keys.discard(key)
            self._cache_evictions += 1

    def _key_matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if cache key matches invalidation pattern.

        Args:
            key: Cache key to check
            pattern: Pattern to match against

        Returns:
            True if key matches pattern
        """
        # Simple wildcard matching for now
        if pattern.endswith("*"):
            return key.startswith(pattern[:-1])
        elif pattern.startswith("*"):
            return key.endswith(pattern[1:])
        else:
            return key == pattern


# Global cache instance
_global_cache: ConfigurationCache | None = None
_cache_lock = threading.Lock()


def get_config_cache() -> ConfigurationCache:
    """Get the global configuration cache instance.

    Returns:
        Global configuration cache instance
    """
    global _global_cache

    if _global_cache is None:
        with _cache_lock:
            if _global_cache is None:
                _global_cache = ConfigurationCache()

    return _global_cache


def set_config_cache(config: Config) -> None:
    """Update the global configuration cache with new config.

    Args:
        config: Configuration to cache globally
    """
    cache = get_config_cache()
    cache.set_config(config)


def invalidate_config_cache(pattern: str | None = None) -> None:
    """Invalidate global configuration cache.

    Args:
        pattern: Optional pattern for selective invalidation
    """
    cache = get_config_cache()
    cache.invalidate(pattern)


def warm_config_cache(keys: list[str] | None = None) -> None:
    """Warm the global configuration cache.

    Args:
        keys: Optional specific keys to warm
    """
    cache = get_config_cache()
    cache.warm_cache(keys)


def get_cache_statistics() -> dict[str, Any]:
    """Get global cache performance statistics.

    Returns:
        Cache statistics dictionary
    """
    cache = get_config_cache()
    return cache.get_statistics()
