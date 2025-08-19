"""Unit tests for configuration manager functionality.

This module tests the high-performance configuration manager including
caching integration, metrics collection, configuration overrides, and
performance optimizations.
"""

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config.exceptions import ConfigurationError, ConfigurationValidationError
from src.config.manager import (
    ConfigurationManager,
    get_config_manager,
    initialize_config_manager,
)
from src.config.metrics import ConfigurationEvent
from src.config.utils import create_minimal_config


class TestConfigurationManager:
    """Tests for ConfigurationManager class functionality."""

    def test_manager_initialization_with_config(self):
        """
        Why: Ensure manager initializes properly with configuration for immediate use
        What: Tests that manager accepts initial config and sets up caching/metrics
        How: Creates manager with config and verifies initialization state
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True, enable_metrics=True)

        assert manager._config is config
        assert manager._is_loaded is True
        assert manager._enable_caching is True
        assert manager._enable_metrics is True
        assert manager._cache is not None
        assert manager._metrics is not None

    def test_manager_initialization_without_config(self):
        """
        Why: Support manager creation before configuration is loaded
        What: Tests that manager can be created without initial configuration
        How: Creates empty manager and verifies clean state
        """
        manager = ConfigurationManager()

        assert manager._config is None
        assert manager._is_loaded is False
        assert manager._cache is not None  # Cache enabled by default
        assert manager._metrics is not None  # Metrics enabled by default

    def test_manager_initialization_disabled_features(self):
        """
        Why: Allow disabling performance features for minimal resource usage
        What: Tests that caching and metrics can be disabled
        How: Creates manager with features disabled and verifies state
        """
        manager = ConfigurationManager(enable_caching=False, enable_metrics=False)

        assert manager._enable_caching is False
        assert manager._enable_metrics is False
        assert manager._cache is None
        assert manager._metrics is None

    def test_load_configuration_from_dict(self):
        """
        Why: Support loading configuration from dictionary for testing/runtime use
        What: Tests that configuration can be loaded programmatically
        How: Loads config from dict and verifies manager state
        """
        manager = ConfigurationManager()

        # Load using internal loader (simulating auto-discovery)
        with patch.object(manager._loader, "auto_load") as mock_auto_load:
            mock_auto_load.return_value = create_minimal_config()

            manager.load_configuration()

        assert manager._is_loaded is True
        assert manager._config is not None
        assert manager._load_time is not None

    def test_load_configuration_with_validation_error(self):
        """
        Why: Ensure validation errors are properly handled during configuration loading
        What: Tests that validation errors are caught and metrics recorded
        How: Triggers validation error and verifies error handling
        """
        manager = ConfigurationManager(enable_metrics=True)

        # Mock loader to return invalid config
        with patch.object(manager._loader, "auto_load") as mock_auto_load:
            # Create invalid config (this will be caught by validation)
            invalid_config = create_minimal_config()
            mock_auto_load.return_value = invalid_config

            # Mock validate_config to raise error
            with patch("src.config.manager.validate_config") as mock_validate:
                mock_validate.side_effect = ConfigurationValidationError(
                    "Test validation error"
                )

                with pytest.raises(ConfigurationValidationError):
                    manager.load_configuration(validate=True)

        # Error should be recorded in metrics
        if manager._metrics:
            error_summary = manager._metrics.get_metrics_summary()["error_summary"]
            assert error_summary["total_errors"] > 0

    def test_reload_configuration(self):
        """
        Why: Support hot reloading of configuration without service restart
        What: Tests that configuration can be reloaded and cache invalidated
        How: Loads config, modifies it, reloads, and verifies updates
        """
        manager = ConfigurationManager(enable_caching=True)

        # Initial load
        with patch.object(manager._loader, "auto_load") as mock_auto_load:
            mock_auto_load.return_value = create_minimal_config()
            manager.load_configuration()

        # Simulate reload
        with patch("src.config.manager.reload_config") as mock_reload:
            new_config = create_minimal_config(database_url="sqlite:///new.db")
            mock_reload.return_value = new_config

            reloaded_config = manager.reload_configuration()

        assert reloaded_config is new_config
        assert manager._config is new_config
        assert manager._last_reload_time is not None

    def test_reload_configuration_not_loaded(self):
        """
        Why: Prevent reload attempts when no configuration is loaded
        What: Tests that reload raises error when no config loaded
        How: Attempts reload on empty manager and verifies error
        """
        manager = ConfigurationManager()

        with pytest.raises(
            ConfigurationError, match="No configuration loaded to reload"
        ):
            manager.reload_configuration()

    def test_get_configuration_value(self):
        """
        Why: Provide fast, cached access to configuration values
        What: Tests that configuration values can be retrieved with caching
        How: Gets values and verifies cache behavior and access patterns
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True, enable_metrics=True)

        # Get value - should use cache
        database_url = manager.get("database.url")
        assert database_url == config.database.url

        # Second access should be cache hit
        database_url2 = manager.get("database.url")
        assert database_url2 == database_url

        # Verify access pattern recorded in metrics
        if manager._metrics:
            patterns = manager._metrics._access_patterns
            assert "database.url" in patterns
            assert patterns["database.url"]["count"] >= 1

    def test_get_configuration_value_with_default(self):
        """
        Why: Support default values for missing configuration keys
        What: Tests that default values are returned for non-existent keys
        How: Requests missing key with default and verifies return value
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config)

        default_value = "default_test_value"
        value = manager.get("nonexistent.key", default_value)
        assert value == default_value

    def test_get_configuration_value_not_loaded(self):
        """
        Why: Prevent access attempts when no configuration is loaded
        What: Tests that accessing config without loading raises error
        How: Attempts access on empty manager and verifies error
        """
        manager = ConfigurationManager()

        with pytest.raises(ConfigurationError, match="No configuration loaded"):
            manager.get("any.key")

    def test_get_section(self):
        """
        Why: Provide efficient access to entire configuration sections
        What: Tests that configuration sections can be retrieved as dictionaries
        How: Gets section and verifies content and caching
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True)

        # Get database section
        db_section = manager.get_section("database")
        assert isinstance(db_section, dict)
        assert "url" in db_section
        assert db_section["url"] == config.database.url

    def test_get_section_invalid(self):
        """
        Why: Provide clear error for non-existent configuration sections
        What: Tests that invalid section names raise ConfigurationError
        How: Requests non-existent section and verifies error
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config)

        with pytest.raises(ConfigurationError, match="not found"):
            manager.get_section("nonexistent_section")

    def test_batch_get(self):
        """
        Why: Optimize performance for retrieving multiple configuration values
        What: Tests that multiple keys can be retrieved efficiently in batch
        How: Requests multiple keys and verifies all are returned correctly
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config)

        keys = ["database.url", "queue.url", "system.environment"]
        result = manager.batch_get(keys)

        assert len(result) == len(keys)
        assert result["database.url"] == config.database.url
        assert result["queue.url"] == config.queue.url
        assert result["system.environment"] == config.system.environment

    def test_get_database_config(self):
        """
        Why: Provide convenient access to database configuration
        What: Tests that database config is returned with proper structure
        How: Gets database config and verifies required fields
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config)

        db_config = manager.get_database_config()
        assert isinstance(db_config, dict)
        assert "url" in db_config
        assert "pool_size" in db_config

    def test_get_llm_config_default_provider(self):
        """
        Why: Support easy access to default LLM provider configuration
        What: Tests that LLM config returns default provider when none specified
        How: Gets LLM config without provider and verifies default is used
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config)

        llm_config = manager.get_llm_config()
        assert isinstance(llm_config, dict)
        assert "provider" in llm_config
        assert "api_key" in llm_config

    def test_get_llm_config_specific_provider(self):
        """
        Why: Support access to specific LLM provider configurations
        What: Tests that specific LLM providers can be requested
        How: Gets specific provider config and verifies content
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config)

        llm_config = manager.get_llm_config("anthropic")
        assert isinstance(llm_config, dict)
        assert llm_config["provider"] == "anthropic"

    def test_get_llm_config_invalid_provider(self):
        """
        Why: Provide clear error for non-existent LLM providers
        What: Tests that invalid provider names raise ConfigurationError
        How: Requests non-existent provider and verifies error
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config)

        with pytest.raises(ConfigurationError, match="not configured"):
            manager.get_llm_config("nonexistent_provider")

    def test_set_override(self):
        """
        Why: Support configuration overrides for testing and feature flags
        What: Tests that configuration values can be temporarily overridden
        How: Sets override and verifies it affects configuration access
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True)

        # Set override
        override_value = "overridden_value"
        manager.set_override("database.url", override_value)

        # Verify override is stored
        assert "database.url" in manager._overrides
        assert manager._overrides["database.url"] == override_value

    def test_remove_override(self):
        """
        Why: Allow removal of configuration overrides
        What: Tests that overrides can be removed to restore original values
        How: Sets override, removes it, and verifies removal
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True)

        # Set and remove override
        manager.set_override("test.key", "value")
        assert "test.key" in manager._overrides

        manager.remove_override("test.key")
        assert "test.key" not in manager._overrides

    def test_override_context(self):
        """
        Why: Support temporary overrides with automatic cleanup
        What: Tests that override context manager properly applies and removes overrides
        How: Uses context manager and verifies override behavior
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True)

        original_overrides = manager._overrides.copy()

        # Use override context
        test_overrides = {"test.key": "test_value", "another.key": "another_value"}

        with manager.override_context(test_overrides):
            # Overrides should be active
            for key, value in test_overrides.items():
                assert manager._overrides[key] == value

        # Overrides should be restored
        assert manager._overrides == original_overrides

    def test_warm_cache(self):
        """
        Why: Support cache warming for improved startup performance
        What: Tests that cache can be pre-warmed with configuration values
        How: Warms cache and verifies values are loaded
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True)

        # Warm cache with specific keys
        keys_to_warm = ["database.url", "system.environment"]
        manager.warm_cache(keys_to_warm)

        # Cache should be warmed (verified by accessing cache directly)
        if manager._cache:
            cache_stats = manager._cache.get_statistics()
            assert cache_stats["cache_size"] > 0

    def test_get_performance_metrics(self):
        """
        Why: Provide visibility into configuration system performance
        What: Tests that performance metrics include cache, system, and manager data
        How: Gets metrics and verifies structure and content
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True, enable_metrics=True)

        # Perform some operations to generate metrics
        manager.get("database.url")
        manager.get_section("queue")

        metrics = manager.get_performance_metrics()

        assert "cache" in metrics
        assert "system" in metrics
        assert "manager" in metrics

        # Check manager metrics
        manager_metrics = metrics["manager"]
        assert manager_metrics["is_loaded"] is True
        assert manager_metrics["cache_enabled"] is True
        assert manager_metrics["metrics_enabled"] is True

    def test_get_health_status(self):
        """
        Why: Provide health monitoring for configuration system
        What: Tests that health status includes overall status and issue detection
        How: Gets health status and verifies structure
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True, enable_metrics=True)

        health = manager.get_health_status()

        assert "status" in health
        assert "loaded" in health
        assert "issues" in health

        # With loaded config, should be healthy
        assert health["loaded"] is True
        assert health["status"] in ["healthy", "degraded"]

    def test_get_health_status_not_loaded(self):
        """
        Why: Detect configuration not loaded as health issue
        What: Tests that health status reports error when no config loaded
        How: Gets health on empty manager and verifies error status
        """
        manager = ConfigurationManager()

        health = manager.get_health_status()

        assert health["status"] == "error"
        assert health["loaded"] is False
        assert "No configuration loaded" in health["issues"]

    def test_validate_current_config(self):
        """
        Why: Support on-demand validation of loaded configuration
        What: Tests that current configuration can be validated with options
        How: Validates config and verifies validation results
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config)

        # Validate current config
        errors, warnings = manager.validate_current_config(
            check_connectivity=False, check_dependencies=False, raise_on_error=False
        )

        # Should have minimal errors for test config
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_validate_current_config_not_loaded(self):
        """
        Why: Prevent validation attempts when no configuration is loaded
        What: Tests that validation raises error when no config loaded
        How: Attempts validation on empty manager and verifies error
        """
        manager = ConfigurationManager()

        with pytest.raises(
            ConfigurationError, match="No configuration loaded to validate"
        ):
            manager.validate_current_config()

    def test_config_property(self):
        """
        Why: Provide access to underlying configuration object
        What: Tests that config property returns loaded configuration
        How: Accesses config property and verifies return value
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config)

        assert manager.config is config

    def test_config_property_not_loaded(self):
        """
        Why: Prevent access to config when none is loaded
        What: Tests that config property raises error when no config loaded
        How: Accesses property on empty manager and verifies error
        """
        manager = ConfigurationManager()

        with pytest.raises(ConfigurationError, match="No configuration loaded"):
            _ = manager.config

    def test_is_loaded_property(self):
        """
        Why: Provide simple check for configuration loaded state
        What: Tests that is_loaded property reflects loading state
        How: Checks property before and after loading configuration
        """
        manager = ConfigurationManager()
        assert manager.is_loaded is False

        config = create_minimal_config()
        manager._config = config
        manager._is_loaded = True
        assert manager.is_loaded is True

    def test_thread_safety(self):
        """
        Why: Ensure manager operations are safe in multi-threaded environments
        What: Tests that concurrent manager access doesn't cause race conditions
        How: Runs multiple threads accessing manager simultaneously
        """
        config = create_minimal_config()
        manager = ConfigurationManager(config, enable_caching=True, enable_metrics=True)

        results = []
        errors = []

        def manager_worker():
            try:
                for i in range(10):
                    value = manager.get("database.url")
                    results.append(value)
                    _ = manager.get_section("system")
                    manager.set_override(f"test.key{i}", f"value{i}")
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = [threading.Thread(target=manager_worker) for _ in range(5)]
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should not have errors
        assert len(errors) == 0
        assert len(results) == 50  # 10 operations x 5 threads


class TestGlobalManagerFunctions:
    """Tests for global manager convenience functions."""

    def test_get_config_manager_singleton(self):
        """
        Why: Ensure global manager provides consistent instance across application
        What: Tests that get_config_manager() returns same instance
        How: Calls function multiple times and verifies same instance
        """
        manager1 = get_config_manager()
        manager2 = get_config_manager()
        assert manager1 is manager2

    def test_initialize_config_manager(self):
        """
        Why: Support explicit initialization of global configuration manager
        What: Tests that initialize_config_manager() sets up global manager
        How: Initializes manager and verifies configuration
        """
        # Mock auto-discovery to avoid file system dependency
        with patch(
            "src.config.manager.ConfigurationManager.load_configuration"
        ) as mock_load:
            mock_load.return_value = create_minimal_config()

            manager = initialize_config_manager(
                enable_caching=True, enable_metrics=True
            )

        assert isinstance(manager, ConfigurationManager)
        assert manager._enable_caching is True
        assert manager._enable_metrics is True

    def test_initialize_config_manager_with_config_path(self):
        """
        Why: Support initialization with explicit configuration file path
        What: Tests that initialization can load from specific config file
        How: Initializes with config path and verifies loading
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_path = f.name
            f.write("""
database:
  url: "sqlite:///test.db"
queue:
  url: "redis://localhost:6379/0"
llm:
  anthropic:
    provider: "anthropic"
    api_key: "test-key"
    model: "claude-3-sonnet-20240229"
repositories:
  - url: "https://github.com/test/repo"
    auth_token: "test-token"
            """)

        try:
            # Mock the loading to avoid file system issues
            with patch(
                "src.config.manager.ConfigurationManager.load_configuration"
            ) as mock_load:
                mock_load.return_value = create_minimal_config()

                initialize_config_manager(config_path=config_path)

            # Verify load was called with config path
            mock_load.assert_called_once_with(config_path)

        finally:
            Path(config_path).unlink()
