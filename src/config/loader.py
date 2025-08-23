"""Configuration loading and management system.

This module provides functionality to load configuration from YAML files,
validate the configuration, and manage the global configuration instance.
It supports hierarchical configuration loading with environment variable
substitution and comprehensive error reporting.

The loading hierarchy is:
1. Default values from Pydantic models
2. Configuration file (YAML)
3. Environment variables
4. Runtime overrides
"""

import os
from pathlib import Path
from typing import Any

import yaml

from .exceptions import (
    ConfigurationError,
    ConfigurationFileError,
    ConfigurationValidationError,
)
from .models import Config


class ConfigurationLoader:
    """Handles loading and validation of configuration from various sources."""

    def __init__(self) -> None:
        """Initialize configuration loader."""
        self._config: Config | None = None
        self._config_file_path: Path | None = None
        self._loaded_from_sources: dict[str, bool] = {
            "file": False,
            "env": False,
            "defaults": True,
        }

    def load_from_file(self, config_path: str | Path, validate: bool = True) -> Config:
        """Load configuration from a YAML file.

        Args:
            config_path: Path to the YAML configuration file
            validate: Whether to validate the configuration after loading

        Returns:
            Loaded and validated configuration

        Raises:
            ConfigurationFileError: If file cannot be read or parsed
            ConfigurationValidationError: If configuration validation fails
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise ConfigurationFileError(f"Configuration file not found: {config_path}")

        if not config_path.is_file():
            raise ConfigurationFileError(
                f"Configuration path is not a file: {config_path}"
            )

        try:
            with open(config_path, encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            if config_data is None:
                config_data = {}

        except yaml.YAMLError as e:
            raise ConfigurationFileError(
                f"Failed to parse YAML configuration: {e}"
            ) from e
        except OSError as e:
            raise ConfigurationFileError(
                f"Failed to read configuration file: {e}"
            ) from e

        try:
            self._config = Config(**config_data)
            self._config_file_path = config_path.resolve()
            self._loaded_from_sources["file"] = True

            if validate:
                self._validate_configuration()

        except Exception as e:
            raise ConfigurationValidationError(
                f"Configuration validation failed: {e}"
            ) from e

        return self._config

    def load_from_dict(
        self, config_data: dict[str, Any], validate: bool = True
    ) -> Config:
        """Load configuration from a dictionary.

        Args:
            config_data: Configuration data dictionary
            validate: Whether to validate the configuration after loading

        Returns:
            Loaded and validated configuration

        Raises:
            ConfigurationValidationError: If configuration validation fails
        """
        try:
            self._config = Config(**config_data)
            self._loaded_from_sources["dict"] = True

            if validate:
                self._validate_configuration()

        except Exception as e:
            raise ConfigurationValidationError(
                f"Configuration validation failed: {e}"
            ) from e

        return self._config

    def load_default(self) -> Config:
        """Load configuration with default values only.

        This creates a minimal configuration that requires manual setup
        of required fields like database URL and repository configurations.

        Returns:
            Configuration with default values

        Raises:
            ConfigurationValidationError: If default configuration is invalid
        """
        try:
            # Create minimal configuration for testing/development
            minimal_config = {
                "database": {"url": "sqlite:///./test.db"},
                "queue": {"url": "redis://localhost:6379/0"},
                "llm": {
                    "anthropic": {
                        "provider": "anthropic",
                        "api_key": "test-key",
                        "model": "claude-3-sonnet-20240229",
                    }
                },
                "repositories": [
                    {
                        "url": "https://github.com/example/repo",
                        "auth_token": "test-token",
                    }
                ],
            }

            self._config = Config(**minimal_config)  # type: ignore[arg-type]
            return self._config

        except Exception as e:
            raise ConfigurationValidationError(
                f"Failed to create default configuration: {e}"
            ) from e

    def find_config_file(self, filename: str = "config.yaml") -> Path | None:
        """Find configuration file in standard locations.

        Search order:
        1. Current working directory
        2. AGENTIC_CONFIG_PATH environment variable
        3. ~/.agentic/
        4. /etc/agentic/

        Args:
            filename: Configuration filename to search for

        Returns:
            Path to found configuration file, or None if not found
        """
        search_paths = []

        # 1. Current working directory
        search_paths.append(Path.cwd() / filename)

        # 2. Environment variable
        env_path_str = os.getenv("AGENTIC_CONFIG_PATH")
        if env_path_str:
            env_path = Path(env_path_str)
            if env_path.is_file():
                search_paths.append(env_path)
            else:
                search_paths.append(env_path / filename)

        # 3. User config directory
        home = Path.home()
        search_paths.append(home / ".agentic" / filename)

        # 4. System config directory
        search_paths.append(Path("/etc/agentic") / filename)

        for path in search_paths:
            if path.exists() and path.is_file():
                return path

        return None

    def auto_load(self, config_filename: str = "config.yaml") -> Config:
        """Automatically load configuration from standard locations.

        Args:
            config_filename: Configuration filename to search for

        Returns:
            Loaded configuration

        Raises:
            ConfigurationFileError: If no configuration file is found
            ConfigurationValidationError: If configuration validation fails
        """
        config_path = self.find_config_file(config_filename)

        if config_path is None:
            raise ConfigurationFileError(
                f"No configuration file '{config_filename}' found in standard locations"
            )

        return self.load_from_file(config_path)

    def _validate_configuration(self) -> None:
        """Validate the loaded configuration.

        Performs additional validation beyond Pydantic model validation,
        including cross-component validation and runtime checks.

        Raises:
            ConfigurationValidationError: If validation fails
        """
        if self._config is None:
            raise ConfigurationValidationError("No configuration loaded")

        # Validate database connectivity can be established
        self._validate_database_config()

        # Validate queue configuration
        self._validate_queue_config()

        # Validate LLM provider configurations
        self._validate_llm_configs()

        # Validate notification configurations
        self._validate_notification_configs()

        # Validate repository configurations
        self._validate_repository_configs()

    def _validate_database_config(self) -> None:
        """Validate database configuration."""
        if self._config is None:
            raise RuntimeError("No configuration loaded for database validation")
        db_config = self._config.database

        # Basic URL validation is done in the model
        # Here we could add runtime connectivity checks if needed

        if db_config.pool_size <= 0:
            raise ConfigurationValidationError(
                "Database pool size must be greater than 0"
            )

    def _validate_queue_config(self) -> None:
        """Validate queue configuration."""
        if self._config is None:
            raise RuntimeError("No configuration loaded for queue validation")
        queue_config = self._config.queue

        if queue_config.provider == "redis" and not queue_config.url.startswith(
            "redis://"
        ):
            raise ConfigurationValidationError(
                "Redis queue provider requires URL starting with 'redis://'"
            )

    def _validate_llm_configs(self) -> None:
        """Validate LLM provider configurations."""
        if self._config is None:
            raise RuntimeError("No configuration loaded for LLM validation")
        if not self._config.llm:
            raise ConfigurationValidationError(
                "At least one LLM provider must be configured"
            )

        # Validate default provider exists
        if self._config.default_llm_provider not in self._config.llm:
            raise ConfigurationValidationError(
                f"Default LLM provider '{self._config.default_llm_provider}' "
                f"not found in configured providers"
            )

        # Validate each provider configuration
        for provider_name, provider_config in self._config.llm.items():
            if not provider_config.api_key:
                raise ConfigurationValidationError(
                    f"API key required for LLM provider '{provider_name}'"
                )

    def _validate_notification_configs(self) -> None:
        """Validate notification configurations."""
        if self._config is None:
            raise RuntimeError("No configuration loaded for notification validation")
        if not self._config.notification.enabled:
            return

        if not self._config.notification.channels:
            raise ConfigurationValidationError(
                "At least one notification channel must be configured "
                "when notifications are enabled"
            )

        # Validate provider-specific configuration
        for channel in self._config.notification.channels:
            if channel.provider == "telegram":
                if not channel.telegram_bot_token or not channel.telegram_chat_id:
                    raise ConfigurationValidationError(
                        "Telegram provider requires bot_token and chat_id"
                    )
            elif channel.provider == "slack":
                if not channel.slack_webhook_url:
                    raise ConfigurationValidationError(
                        "Slack provider requires webhook_url"
                    )
            elif channel.provider == "email" and not all(
                [
                    channel.email_smtp_host,
                    channel.email_username,
                    channel.email_password,
                    channel.email_from_address,
                    channel.email_to_addresses,
                ]
            ):
                raise ConfigurationValidationError(
                    "Email provider requires smtp_host, username, password, "
                    "from_address, and to_addresses"
                )

    def _validate_repository_configs(self) -> None:
        """Validate repository configurations."""
        if self._config is None:
            raise RuntimeError("No configuration loaded for repository validation")
        if not self._config.repositories:
            raise ConfigurationValidationError(
                "At least one repository must be configured"
            )

        for repo in self._config.repositories:
            if not repo.auth_token:
                raise ConfigurationValidationError(
                    f"Authentication token required for repository {repo.url}"
                )

    @property
    def config(self) -> Config | None:
        """Get the loaded configuration."""
        return self._config

    @property
    def config_file_path(self) -> Path | None:
        """Get the path to the loaded configuration file."""
        return self._config_file_path

    @property
    def is_loaded(self) -> bool:
        """Check if configuration has been loaded."""
        return self._config is not None

    def get_loading_info(self) -> dict[str, Any]:
        """Get information about configuration loading sources.

        Returns:
            Dictionary containing loading source information
        """
        return {
            "loaded": self.is_loaded,
            "config_file": str(self._config_file_path)
            if self._config_file_path
            else None,
            "sources": self._loaded_from_sources.copy(),
            "config_summary": self._get_config_summary() if self.is_loaded else None,
        }

    def _get_config_summary(self) -> dict[str, Any]:
        """Get a summary of the loaded configuration.

        Returns:
            Configuration summary without sensitive information
        """
        if not self._config:
            return {}

        return {
            "system": {
                "environment": self._config.system.environment,
                "log_level": self._config.system.log_level.value,
                "debug_mode": self._config.system.debug_mode,
            },
            "database": {
                "url_scheme": self._config.database.url.split("://")[0]
                if "://" in self._config.database.url
                else "unknown",
                "pool_size": self._config.database.pool_size,
            },
            "queue": {
                "provider": self._config.queue.provider,
                "default_queue": self._config.queue.default_queue,
            },
            "llm_providers": list(self._config.llm.keys()),
            "default_llm_provider": self._config.default_llm_provider,
            "notification_enabled": self._config.notification.enabled,
            "notification_channels": len(self._config.notification.channels),
            "repositories": len(self._config.repositories),
        }


# Global configuration loader instance
_loader = ConfigurationLoader()


def load_config(
    config_path: str | Path | None = None, auto_discover: bool = True
) -> Config:
    """Load configuration from file or auto-discovery.

    Args:
        config_path: Explicit path to configuration file
        auto_discover: Whether to auto-discover configuration file if path not provided

    Returns:
        Loaded configuration

    Raises:
        ConfigurationError: If configuration cannot be loaded or is invalid
    """
    global _loader

    try:
        if config_path:
            return _loader.load_from_file(config_path)
        elif auto_discover:
            return _loader.auto_load()
        else:
            return _loader.load_default()
    except (ConfigurationFileError, ConfigurationValidationError) as e:
        raise ConfigurationError(f"Failed to load configuration: {e}") from e


def get_config() -> Config:
    """Get the currently loaded configuration.

    Returns:
        Current configuration instance

    Raises:
        ConfigurationError: If no configuration has been loaded
    """
    global _loader

    if not _loader.is_loaded or _loader.config is None:
        raise ConfigurationError("No configuration loaded. Call load_config() first.")

    return _loader.config


def get_loader() -> ConfigurationLoader:
    """Get the global configuration loader instance.

    Returns:
        Configuration loader instance
    """
    global _loader
    return _loader


def reload_config() -> Config:
    """Reload configuration from the same source.

    Returns:
        Reloaded configuration

    Raises:
        ConfigurationError: If no configuration was previously loaded or reload fails
    """
    global _loader

    if not _loader.is_loaded:
        raise ConfigurationError(
            "Cannot reload: no configuration was previously loaded"
        )

    if _loader.config_file_path:
        return _loader.load_from_file(_loader.config_file_path)
    else:
        # Fallback to auto-discovery
        return _loader.auto_load()


def is_config_loaded() -> bool:
    """Check if configuration has been loaded.

    Returns:
        True if configuration is loaded, False otherwise
    """
    global _loader
    return _loader.is_loaded
