"""High-performance configuration manager with caching and monitoring.

This module provides a comprehensive configuration management API that integrates
caching, metrics collection, and performance optimization features. It serves as
the primary interface for all configuration access throughout the application.

The manager provides:
- Type-safe configuration access with caching
- Performance monitoring and metrics collection
- Thread-safe operations for concurrent access
- Configuration validation and health monitoring
- Batch operations for efficient startup
- Hot reload capabilities with cache invalidation
"""

import threading
import time
from contextlib import contextmanager
from typing import Any, TypeVar

from .cache import ConfigurationCache, set_config_cache
from .exceptions import ConfigurationError
from .loader import ConfigurationLoader, reload_config
from .metrics import (
    ConfigurationEvent,
    ConfigurationMetrics,
    time_operation,
)
from .models import Config
from .validation import validate_config

T = TypeVar("T")


class ConfigurationManager:
    """High-performance configuration manager with caching and monitoring.

    This manager provides the primary API for configuration access throughout
    the application. It integrates caching for performance, metrics for
    monitoring, and validation for safety.
    """

    def __init__(
        self,
        config: Config | None = None,
        enable_caching: bool = True,
        enable_metrics: bool = True,
    ) -> None:
        """Initialize configuration manager.

        Args:
            config: Optional initial configuration
            enable_caching: Whether to enable configuration caching
            enable_metrics: Whether to enable metrics collection
        """
        self._config: Config | None = config
        self._loader = ConfigurationLoader()
        self._lock = threading.RLock()

        # Performance features
        self._enable_caching = enable_caching
        self._enable_metrics = enable_metrics

        # Initialize cache and metrics if enabled
        self._cache: ConfigurationCache | None = None
        self._metrics: ConfigurationMetrics | None = None

        if enable_caching:
            self._cache = ConfigurationCache(config)

        if enable_metrics:
            self._metrics = ConfigurationMetrics()

        # Manager state
        self._is_loaded = config is not None
        self._load_time: float | None = None
        self._last_reload_time: float | None = None

        # Configuration overrides for testing/feature flags
        self._overrides: dict[str, Any] = {}
        self._override_stack: list[dict[str, Any]] = []

    @time_operation("load_config")
    def load_configuration(
        self,
        config_path: str | None = None,
        auto_discover: bool = True,
        validate: bool = True,
    ) -> Config:
        """Load configuration with performance tracking.

        Args:
            config_path: Optional explicit configuration file path
            auto_discover: Whether to auto-discover config file if path not provided
            validate: Whether to validate configuration after loading

        Returns:
            Loaded and validated configuration

        Raises:
            ConfigurationError: If configuration cannot be loaded
            ConfigurationValidationError: If validation fails
        """
        with self._lock:
            start_time = time.time()

            try:
                # Load configuration using existing loader
                if config_path:
                    config = self._loader.load_from_file(config_path, validate=False)
                elif auto_discover:
                    config = self._loader.auto_load()
                else:
                    config = self._loader.load_default()

                # Validate if requested
                if validate:
                    validation_start = time.time()
                    validate_config(config, raise_on_error=True)
                    validation_time = time.time() - validation_start

                    if self._metrics:
                        self._metrics.record_event(
                            ConfigurationEvent.CONFIG_VALIDATED,
                            {"validation_time": validation_time},
                        )

                # Store configuration
                self._config = config
                self._is_loaded = True
                self._load_time = time.time() - start_time

                # Update cache if enabled
                if self._cache:
                    self._cache.set_config(config)
                    set_config_cache(config)  # Update global cache

                # Record metrics
                if self._metrics:
                    self._metrics.record_event(
                        ConfigurationEvent.CONFIG_LOADED, {"load_time": self._load_time}
                    )

                return config

            except Exception as e:
                # Record error metrics
                if self._metrics:
                    self._metrics.record_error(
                        "config_load_error", str(e), {"config_path": config_path}
                    )
                raise

    @time_operation("reload_config")
    def reload_configuration(self, validate: bool = True) -> Config:
        """Reload configuration with cache invalidation.

        Args:
            validate: Whether to validate reloaded configuration

        Returns:
            Reloaded configuration

        Raises:
            ConfigurationError: If reload fails
        """
        with self._lock:
            if not self._is_loaded:
                raise ConfigurationError("No configuration loaded to reload")

            start_time = time.time()

            try:
                # Reload using existing configuration path
                config = reload_config()

                # Validate if requested
                if validate:
                    validate_config(config, raise_on_error=True)

                # Update internal state
                self._config = config
                self._last_reload_time = time.time() - start_time

                # Invalidate cache and update with new config
                if self._cache:
                    self._cache.invalidate()
                    self._cache.set_config(config)
                    set_config_cache(config)

                # Record metrics
                if self._metrics:
                    self._metrics.record_event(
                        ConfigurationEvent.CONFIG_RELOADED,
                        {"reload_time": self._last_reload_time},
                    )

                return config

            except Exception as e:
                if self._metrics:
                    self._metrics.record_error("config_reload_error", str(e))
                raise

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with caching and metrics.

        Args:
            key: Configuration key in dot notation
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if not self._is_loaded:
            raise ConfigurationError("No configuration loaded")

        # Record access pattern
        if self._metrics:
            self._metrics.record_access_pattern(key, "read")

        # Try cache first if enabled
        if self._cache:
            return self._cache.get(key, default)

        # Fallback to direct access
        try:
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

    def get_section(self, section: str) -> dict[str, Any]:
        """Get entire configuration section with caching.

        Args:
            section: Configuration section name

        Returns:
            Section configuration as dictionary

        Raises:
            ConfigurationError: If section not found
        """
        if not self._is_loaded:
            raise ConfigurationError("No configuration loaded")

        # Record access pattern
        if self._metrics:
            self._metrics.record_access_pattern(f"section:{section}", "read")

        # Try cache first if enabled
        if self._cache:
            return self._cache.get_section(section)

        # Fallback to direct access
        try:
            section_obj: Any = getattr(self._config, section)

            if hasattr(section_obj, "model_dump"):
                model_result: dict[str, Any] = section_obj.model_dump()
                return model_result
            elif hasattr(section_obj, "dict"):
                dict_result: dict[str, Any] = section_obj.dict()
                return dict_result
            elif isinstance(section_obj, dict):
                return dict(section_obj)
            else:
                return dict(section_obj) if section_obj else {}

        except AttributeError as e:
            raise ConfigurationError(
                f"Configuration section '{section}' not found"
            ) from e

    def batch_get(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple configuration values efficiently.

        Args:
            keys: List of configuration keys to retrieve

        Returns:
            Dictionary mapping keys to values
        """
        if not self._is_loaded:
            raise ConfigurationError("No configuration loaded")

        # Use cache batch operation if available
        if self._cache:
            return self._cache.batch_get(keys)

        # Fallback to individual gets
        result = {}
        for key in keys:
            result[key] = self.get(key)

        return result

    def get_database_config(self) -> dict[str, Any]:
        """Get database configuration with type safety.

        Returns:
            Database configuration dictionary
        """
        return self.get_section("database")

    def get_llm_config(self, provider: str | None = None) -> dict[str, Any]:
        """Get LLM provider configuration with fallback.

        Args:
            provider: Optional specific provider name.
                     If None, uses default provider.

        Returns:
            LLM provider configuration as dictionary

        Raises:
            ConfigurationError: If provider not found
        """
        if provider is None:
            provider = self.get("default_llm_provider")

        llm_configs = self.get_section("llm")

        if provider not in llm_configs:
            raise ConfigurationError(f"LLM provider '{provider}' not configured")

        config_obj: Any = llm_configs[provider]

        # Convert to dict if it's a Pydantic model
        if hasattr(config_obj, "model_dump"):
            model_dump_result: dict[str, Any] = config_obj.model_dump()
            return model_dump_result
        elif hasattr(config_obj, "dict"):
            dict_method_result: dict[str, Any] = config_obj.dict()
            return dict_method_result
        elif isinstance(config_obj, dict):
            return dict(config_obj)
        else:
            # Fallback - try to convert to dict
            return dict(config_obj) if config_obj else {}

    def get_queue_config(self) -> dict[str, Any]:
        """Get queue configuration.

        Returns:
            Queue configuration dictionary
        """
        return self.get_section("queue")

    def get_notification_config(self) -> dict[str, Any]:
        """Get notification configuration.

        Returns:
            Notification configuration dictionary
        """
        return self.get_section("notification")

    def get_repository_configs(self) -> list[dict[str, Any]]:
        """Get all repository configurations.

        Returns:
            List of repository configuration dictionaries
        """
        if not self._config:
            raise ConfigurationError("No configuration loaded")

        return [
            repo.model_dump() if hasattr(repo, "model_dump") else dict(repo)
            for repo in self._config.repositories
        ]

    def set_override(self, key: str, value: Any) -> None:
        """Set configuration override for testing or feature flags.

        Args:
            key: Configuration key to override
            value: Override value
        """
        with self._lock:
            self._overrides[key] = value

            # Invalidate cache for this key
            if self._cache:
                self._cache.invalidate(key)

    def remove_override(self, key: str) -> None:
        """Remove configuration override.

        Args:
            key: Configuration key override to remove
        """
        with self._lock:
            self._overrides.pop(key, None)

            # Invalidate cache for this key
            if self._cache:
                self._cache.invalidate(key)

    @contextmanager
    def override_context(self, overrides: dict[str, Any]) -> Any:
        """Context manager for temporary configuration overrides.

        Args:
            overrides: Dictionary of key-value overrides

        Example:
            with manager.override_context({"debug_mode": True}):
                # Configuration temporarily overridden
                debug_enabled = manager.get("system.debug_mode")
        """
        # Save current overrides and apply new ones
        saved_overrides = self._overrides.copy()
        self._override_stack.append(saved_overrides)

        try:
            self._overrides.update(overrides)

            # Invalidate cache for overridden keys
            if self._cache:
                for key in overrides:
                    self._cache.invalidate(key)

            yield

        finally:
            # Restore previous overrides
            self._overrides = self._override_stack.pop()

            # Invalidate cache again
            if self._cache:
                for key in overrides:
                    self._cache.invalidate(key)

    def warm_cache(self, keys: list[str] | None = None) -> None:
        """Pre-load configuration values into cache.

        Args:
            keys: Optional specific keys to warm. If None, warms critical paths.
        """
        if not self._cache:
            return

        self._cache.warm_cache(keys)

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get configuration system performance metrics.

        Returns:
            Dictionary containing performance metrics
        """
        metrics = {}

        # Cache metrics
        if self._cache:
            metrics["cache"] = self._cache.get_statistics()

        # System metrics
        if self._metrics:
            metrics["system"] = self._metrics.get_metrics_summary()

        # Manager-specific metrics
        metrics["manager"] = {
            "is_loaded": self._is_loaded,
            "load_time": self._load_time,
            "last_reload_time": self._last_reload_time,
            "cache_enabled": self._enable_caching,
            "metrics_enabled": self._enable_metrics,
            "active_overrides": len(self._overrides),
        }

        return metrics

    def get_health_status(self) -> dict[str, Any]:
        """Get configuration system health status.

        Returns:
            Health status information
        """
        health: dict[str, Any] = {
            "status": "healthy",
            "loaded": self._is_loaded,
            "issues": [],
        }

        # Check basic health
        if not self._is_loaded:
            health["status"] = "error"
            health["issues"].append("No configuration loaded")

        # Check metrics health if available
        if self._metrics:
            metrics_summary = self._metrics.get_metrics_summary()
            health["metrics_health"] = metrics_summary.get("health_status", "unknown")

            if metrics_summary.get("error_summary", {}).get("total_errors", 0) > 0:
                issues = health["issues"]
                if isinstance(issues, list):
                    issues.append("Configuration errors detected")

        # Check cache health if available
        if self._cache:
            cache_stats = self._cache.get_statistics()
            if cache_stats.get("hit_rate", 1.0) < 0.5:
                issues = health["issues"]
                if isinstance(issues, list):
                    issues.append("Low cache hit rate")

        # Update overall status based on issues
        if health["issues"]:
            health["status"] = (
                "degraded" if health["status"] == "healthy" else health["status"]
            )

        return health

    def validate_current_config(
        self,
        check_connectivity: bool = False,
        check_dependencies: bool = False,
        raise_on_error: bool = True,
    ) -> tuple[list[str], list[str]]:
        """Validate currently loaded configuration.

        Args:
            check_connectivity: Whether to check external connectivity
            check_dependencies: Whether to check system dependencies
            raise_on_error: Whether to raise exception on validation errors

        Returns:
            Tuple of (errors, warnings) lists

        Raises:
            ConfigurationValidationError: If validation fails and raise_on_error=True
        """
        if not self._is_loaded or not self._config:
            raise ConfigurationError("No configuration loaded to validate")

        return validate_config(
            self._config,
            check_connectivity=check_connectivity,
            check_dependencies=check_dependencies,
            raise_on_error=raise_on_error,
        )

    @property
    def config(self) -> Config:
        """Get the underlying configuration object.

        Returns:
            Current configuration instance

        Raises:
            ConfigurationError: If no configuration is loaded
        """
        if not self._is_loaded or not self._config:
            raise ConfigurationError("No configuration loaded")
        return self._config

    @property
    def is_loaded(self) -> bool:
        """Check if configuration is loaded."""
        return self._is_loaded


# Global configuration manager instance
_global_manager: ConfigurationManager | None = None
_manager_lock = threading.Lock()


def get_config_manager() -> ConfigurationManager:
    """Get the global configuration manager instance.

    Returns:
        Global configuration manager instance
    """
    global _global_manager

    if _global_manager is None:
        with _manager_lock:
            if _global_manager is None:
                _global_manager = ConfigurationManager()

    return _global_manager


def initialize_config_manager(
    config_path: str | None = None,
    enable_caching: bool = True,
    enable_metrics: bool = True,
) -> ConfigurationManager:
    """Initialize the global configuration manager.

    Args:
        config_path: Optional configuration file path
        enable_caching: Whether to enable caching
        enable_metrics: Whether to enable metrics

    Returns:
        Initialized configuration manager
    """
    global _global_manager

    with _manager_lock:
        _global_manager = ConfigurationManager(
            enable_caching=enable_caching, enable_metrics=enable_metrics
        )

        # Load configuration if path provided
        if True:  # Always auto-discover by default
            _global_manager.load_configuration(config_path)

    return _global_manager
