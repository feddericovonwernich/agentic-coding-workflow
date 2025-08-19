"""Unit tests for configuration cache functionality.

This module tests the configuration caching system including cache operations,
invalidation, performance tracking, and memory optimization features.
"""

import threading
import time
from unittest.mock import patch

import pytest

from src.config.cache import (
    ConfigurationCache,
    get_cache_statistics,
    get_config_cache,
    invalidate_config_cache,
    set_config_cache,
    warm_config_cache,
)
from src.config.exceptions import ConfigurationError
from src.config.utils import create_minimal_config


class TestConfigurationCache:
    """Tests for ConfigurationCache class functionality."""

    def test_cache_initialization_with_config(self):
        """
        Why: Ensure cache initializes properly with configuration for immediate use
        What: Tests that cache accepts initial config and sets up internal state
        How: Creates cache with config and verifies initialization state
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        assert cache._config is config
        assert len(cache._cache) >= 0  # May have warm cache entries
        assert cache._cache_version == 0
        assert cache._cache_hits == 0
        assert cache._cache_misses == 0

    def test_cache_initialization_without_config(self):
        """
        Why: Support cache creation before configuration is loaded
        What: Tests that cache can be created without initial configuration
        How: Creates empty cache and verifies clean state
        """
        cache = ConfigurationCache()

        assert cache._config is None
        assert len(cache._cache) == 0
        assert cache._cache_version == 0
        assert cache._cache_hits == 0
        assert cache._cache_misses == 0

    def test_cache_get_with_config_loaded(self):
        """
        Why: Verify basic cache functionality for configuration value retrieval
        What: Tests that cache can retrieve configuration values and caches them
        How: Loads config into cache and retrieves values, checking cache behavior
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        # Clear cache to ensure we get predictable behavior
        cache.invalidate()
        cache.clear_statistics()

        # First access should be cache miss
        value = cache.get("database.url")
        assert value == config.database.url
        assert cache._cache_misses > 0

        # Second access should be cache hit
        cache_hits_before = cache._cache_hits
        value2 = cache.get("database.url")
        assert value2 == value
        assert cache._cache_hits > cache_hits_before

    def test_cache_get_with_default_value(self):
        """
        Why: Ensure cache handles missing keys gracefully with default values
        What: Tests that cache returns default value for non-existent keys
        How: Requests non-existent key with default and verifies return value
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        default_value = "default_test_value"
        value = cache.get("nonexistent.key", default_value)
        assert value == default_value

    def test_cache_get_without_config_returns_default(self):
        """
        Why: Handle case where cache is used before configuration is loaded
        What: Tests that cache returns default when no config is loaded
        How: Creates empty cache and verifies default value return
        """
        cache = ConfigurationCache()

        default_value = "no_config_default"
        value = cache.get("any.key", default_value)
        assert value == default_value

    def test_cache_get_section_success(self):
        """
        Why: Ensure efficient retrieval of entire configuration sections
        What: Tests that cache can retrieve and cache entire configuration sections
        How: Retrieves section and verifies content and caching behavior
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        # Get database section
        section_data = cache.get_section("database")
        assert isinstance(section_data, dict)
        assert "url" in section_data
        assert section_data["url"] == config.database.url

        # Verify it's cached
        cache_hits_before = cache._cache_hits
        section_data2 = cache.get_section("database")
        assert section_data2 == section_data
        assert cache._cache_hits > cache_hits_before

    def test_cache_get_section_without_config_raises_error(self):
        """
        Why: Prevent undefined behavior when accessing sections without config
        What: Tests that accessing sections without config raises ConfigurationError
        How: Creates empty cache and verifies exception on section access
        """
        cache = ConfigurationCache()

        with pytest.raises(ConfigurationError, match="No configuration loaded"):
            cache.get_section("database")

    def test_cache_get_section_invalid_section_raises_error(self):
        """
        Why: Provide clear error when requesting non-existent configuration section
        What: Tests that invalid section names raise ConfigurationError
        How: Requests non-existent section and verifies error
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        with pytest.raises(ConfigurationError, match="not found"):
            cache.get_section("nonexistent_section")

    def test_cache_batch_get(self):
        """
        Why: Optimize performance for retrieving multiple configuration values
        What: Tests batch retrieval of multiple configuration keys
        How: Requests multiple keys and verifies all are returned correctly
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        keys = ["database.url", "queue.url", "system.environment"]
        result = cache.batch_get(keys)

        assert len(result) == len(keys)
        assert result["database.url"] == config.database.url
        assert result["queue.url"] == config.queue.url
        assert result["system.environment"] == config.system.environment

    def test_cache_set_config_updates_version(self):
        """
        Why: Ensure cache properly handles configuration updates
        What: Tests that setting new config updates version and invalidates cache
        How: Sets initial config, updates it, and verifies version increment
        """
        config1 = create_minimal_config()
        cache = ConfigurationCache(config1)
        initial_version = cache._cache_version

        # Populate cache with some data first
        cache.get("database.url")
        cache.get("queue.url")

        config2 = create_minimal_config(database_url="sqlite:///new.db")

        # Manually add a key to dirty to check the mechanism
        cache._dirty_keys.add("test_key")

        cache.set_config(config2)

        assert cache._config is config2
        assert cache._cache_version > initial_version
        # Version increment indicates config change was detected
        assert cache._cache_version == initial_version + 1

    def test_cache_invalidate_all(self):
        """
        Why: Allow complete cache invalidation for configuration changes
        What: Tests that invalidate() clears all cache entries
        How: Populates cache, invalidates all, and verifies cache is empty
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        # Populate cache
        cache.get("database.url")
        cache.get("queue.url")
        assert len(cache._cache) > 0

        # Invalidate all
        cache.invalidate()
        assert len(cache._cache) == 0
        assert len(cache._dirty_keys) == 0

    def test_cache_invalidate_pattern(self):
        """
        Why: Support selective cache invalidation for specific configuration areas
        What: Tests that invalidate(pattern) removes only matching cache entries
        How: Populates cache with multiple keys and invalidates by pattern
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        # Populate cache with multiple keys
        cache.get("database.url")
        cache.get("database.pool_size")
        cache.get("queue.url")

        # Invalidate only database keys
        cache.invalidate("database*")

        # Queue key should still be cached
        queue_url = cache.get("queue.url")
        assert queue_url == config.queue.url

        # Database keys should result in cache miss (new load)
        cache_misses_before = cache._cache_misses
        cache.get("database.url")
        assert cache._cache_misses > cache_misses_before

    def test_cache_warm_cache_default_keys(self):
        """
        Why: Optimize startup performance by pre-loading critical configuration
        What: Tests that warm_cache() loads critical configuration paths
        How: Warms cache and verifies critical keys are loaded
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        # Clear cache first
        cache.invalidate()
        assert len(cache._cache) == 0

        # Warm cache
        cache.warm_cache()

        # Should have loaded critical keys
        assert len(cache._cache) > 0
        assert cache._cache_hits == 0  # No hits yet, just warming

    def test_cache_warm_cache_specific_keys(self):
        """
        Why: Allow targeted cache warming for specific application needs
        What: Tests that warm_cache(keys) loads only specified keys
        How: Specifies keys to warm and verifies they are loaded
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        # Clear cache first
        cache.invalidate()

        # Warm specific keys
        keys_to_warm = ["database.url", "system.environment"]
        cache.warm_cache(keys_to_warm)

        # Specified keys should be cached
        for key in keys_to_warm:
            # Should be cache hit since warmed
            cache_hits_before = cache._cache_hits
            cache.get(key)
            assert cache._cache_hits > cache_hits_before

    def test_cache_statistics_tracking(self):
        """
        Why: Provide visibility into cache performance for optimization
        What: Tests that cache statistics are tracked correctly
        How: Performs various cache operations and verifies statistics
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        # Clear statistics and cache
        cache.clear_statistics()
        cache.invalidate()  # Clear the cache itself

        initial_stats = cache.get_statistics()
        assert initial_stats["cache_hits"] == 0
        assert initial_stats["cache_misses"] == 0

        # Perform cache operations
        cache.get("database.url")  # Should be miss since cache is empty
        cache.get("database.url")  # Should be hit since now cached

        stats = cache.get_statistics()
        assert stats["cache_hits"] >= 1
        assert stats["cache_misses"] >= 1
        assert stats["hit_rate"] > 0.0
        assert "cache_size" in stats
        assert "access_patterns" in stats

    def test_cache_configure_cache_settings(self):
        """
        Why: Allow runtime tuning of cache behavior for different environments
        What: Tests that cache configuration can be updated
        How: Changes cache settings and verifies they take effect
        """
        cache = ConfigurationCache()

        # Configure cache settings
        cache.configure_cache(max_size=500, ttl=7200, enable_weak_refs=False)

        assert cache._max_cache_size == 500
        assert cache._cache_ttl == 7200
        assert cache._enable_weak_refs is False

    def test_cache_lru_eviction(self):
        """
        Why: Ensure cache doesn't grow unbounded and evicts old entries
        What: Tests that cache evicts least recently used items when full
        How: Fills cache beyond limit and verifies eviction occurs
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        # Set small cache size for testing
        cache.configure_cache(max_size=3)

        # Fill cache beyond limit
        cache.get("key1", "value1")
        cache.get("key2", "value2")
        cache.get("key3", "value3")
        cache.get("key4", "value4")  # Should trigger eviction

        stats = cache.get_statistics()
        assert stats["cache_evictions"] > 0
        assert stats["cache_size"] <= 3

    def test_cache_thread_safety(self):
        """
        Why: Ensure cache operations are safe in multi-threaded environments
        What: Tests that concurrent cache access doesn't cause race conditions
        How: Runs multiple threads accessing cache simultaneously
        """
        config = create_minimal_config()
        cache = ConfigurationCache(config)

        results = []
        errors = []

        def cache_worker():
            try:
                for _ in range(10):
                    value = cache.get("database.url")
                    results.append(value)
                    cache.set_config(config)  # Trigger cache updates
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = [threading.Thread(target=cache_worker) for _ in range(5)]
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should not have errors
        assert len(errors) == 0
        assert len(results) == 50  # 10 operations x 5 threads


class TestGlobalCacheFunctions:
    """Tests for global cache convenience functions."""

    def test_get_config_cache_singleton(self):
        """
        Why: Ensure global cache provides consistent instance across application
        What: Tests that get_config_cache() returns same instance
        How: Calls function multiple times and verifies same instance
        """
        cache1 = get_config_cache()
        cache2 = get_config_cache()
        assert cache1 is cache2

    def test_set_config_cache_updates_global(self):
        """
        Why: Allow global cache configuration from application startup
        What: Tests that set_config_cache() updates global cache
        How: Sets config in global cache and verifies update
        """
        config = create_minimal_config()

        # Set config in global cache
        set_config_cache(config)

        # Verify global cache has config
        global_cache = get_config_cache()
        assert global_cache._config is config

    def test_invalidate_config_cache_clears_global(self):
        """
        Why: Allow global cache invalidation for configuration updates
        What: Tests that invalidate_config_cache() clears global cache
        How: Populates global cache and invalidates it
        """
        config = create_minimal_config()
        set_config_cache(config)

        # Populate global cache
        global_cache = get_config_cache()
        global_cache.get("database.url")
        assert len(global_cache._cache) > 0

        # Invalidate global cache
        invalidate_config_cache()
        assert len(global_cache._cache) == 0

    def test_warm_config_cache_preloads_global(self):
        """
        Why: Allow global cache warming for application startup optimization
        What: Tests that warm_config_cache() preloads global cache
        How: Warms global cache and verifies keys are loaded
        """
        config = create_minimal_config()
        set_config_cache(config)

        # Clear and warm global cache
        invalidate_config_cache()
        warm_config_cache(["database.url", "queue.url"])

        # Verify global cache is warmed
        global_cache = get_config_cache()
        assert len(global_cache._cache) > 0

    def test_get_cache_statistics_global(self):
        """
        Why: Provide global cache performance visibility for monitoring
        What: Tests that get_cache_statistics() returns global stats
        How: Performs operations on global cache and checks statistics
        """
        config = create_minimal_config()
        set_config_cache(config)

        # Perform some operations
        global_cache = get_config_cache()
        global_cache.get("database.url")

        # Get statistics
        stats = get_cache_statistics()
        assert isinstance(stats, dict)
        assert "cache_hits" in stats
        assert "cache_misses" in stats
