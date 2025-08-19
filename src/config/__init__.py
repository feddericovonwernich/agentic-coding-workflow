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
    "Config",
    "ConfigurationError",
    "ConfigurationFileError",
    "ConfigurationLoader",
    "ConfigurationMissingError",
    "ConfigurationValidationError",
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
    "create_minimal_config",
    "generate_example_config",
    "generate_json_schema",
    "get_config",
    "get_config_summary",
    "get_loader",
    "is_config_loaded",
    "load_config",
    "mask_sensitive_values",
    "merge_configs",
    "reload_config",
    "validate_config",
    "validate_environment_variables",
]
