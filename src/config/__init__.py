"""Configuration management system for agentic coding workflow.

This module provides type-safe configuration management with support for:
- YAML configuration files with environment variable substitution
- Hierarchical configuration loading (defaults -> file -> env -> runtime)
- Pydantic-based validation and type safety
- Hot reload capabilities for configuration changes

Example usage:
    from src.config import get_config

    config = get_config()
    database_url = config.database.url
    llm_provider = config.llm.default_provider
"""

from .cache import (
    ConfigurationCache,
    get_cache_statistics,
    get_config_cache,
    invalidate_config_cache,
    set_config_cache,
    warm_config_cache,
)
from .exceptions import (
    ConfigurationError,
    ConfigurationFileError,
    ConfigurationMissingError,
    ConfigurationValidationError,
    EnvironmentVariableError,
)
from .loader import (
    ConfigurationLoader,
    get_config,
    get_loader,
    is_config_loaded,
    load_config,
    reload_config,
)
from .manager import (
    ConfigurationManager,
    get_config_manager,
    initialize_config_manager,
)
from .metrics import (
    ConfigurationEvent,
    ConfigurationMetrics,
    get_config_metrics,
    record_config_event,
    time_operation,
)
from .models import (
    Config,
    DatabaseConfig,
    FixCategory,
    LLMProvider,
    LLMProviderConfig,
    LogLevel,
    NotificationChannelConfig,
    NotificationConfig,
    NotificationPriority,
    NotificationProvider,
    QueueConfig,
    RepositoryConfig,
    SystemConfig,
)
from .utils import (
    create_minimal_config,
    generate_example_config,
    generate_json_schema,
    get_config_summary,
    mask_sensitive_values,
    merge_configs,
    validate_environment_variables,
)
from .validation import (
    ConfigurationValidator,
    validate_config,
)

__all__ = [
    # Core configuration models and types
    "Config",
    # Caching
    "ConfigurationCache",
    # Exceptions
    "ConfigurationError",
    # Metrics and monitoring
    "ConfigurationEvent",
    "ConfigurationFileError",
    # Core loading and management
    "ConfigurationLoader",
    "ConfigurationManager",
    "ConfigurationMetrics",
    "ConfigurationMissingError",
    "ConfigurationValidationError",
    # Validation
    "ConfigurationValidator",
    "DatabaseConfig",
    "EnvironmentVariableError",
    "FixCategory",
    "LLMProvider",
    "LLMProviderConfig",
    "LogLevel",
    "NotificationChannelConfig",
    "NotificationConfig",
    "NotificationPriority",
    "NotificationProvider",
    "QueueConfig",
    "RepositoryConfig",
    "SystemConfig",
    # Utilities
    "create_minimal_config",
    "generate_example_config",
    "generate_json_schema",
    "get_cache_statistics",
    "get_config",
    "get_config_cache",
    "get_config_manager",
    "get_config_metrics",
    "get_config_summary",
    "get_loader",
    "initialize_config_manager",
    "invalidate_config_cache",
    "is_config_loaded",
    "load_config",
    "mask_sensitive_values",
    "merge_configs",
    "record_config_event",
    "reload_config",
    "set_config_cache",
    "time_operation",
    "validate_config",
    "validate_environment_variables",
    "warm_config_cache",
]
