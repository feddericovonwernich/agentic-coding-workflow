"""Advanced configuration validation helpers.

This module provides comprehensive validation functionality beyond basic
Pydantic validation, including connectivity checks, dependency validation,
and runtime configuration verification.
"""

import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from .exceptions import ConfigurationValidationError
from .models import (
    Config,
    LLMProviderConfig,
    NotificationChannelConfig,
    RepositoryConfig,
)


class ConfigurationValidator:
    """Advanced configuration validator with runtime checks."""

    def __init__(self, config: Config):
        """Initialize validator with configuration.

        Args:
            config: Configuration to validate
        """
        self.config = config
        self.validation_errors: list[str] = []
        self.warnings: list[str] = []

    def validate_all(
        self,
        check_connectivity: bool = False,
        check_dependencies: bool = True,
        check_permissions: bool = False,
    ) -> tuple[list[str], list[str]]:
        """Perform comprehensive configuration validation.

        Args:
            check_connectivity: Whether to test actual connectivity
            check_dependencies: Whether to check for required dependencies
            check_permissions: Whether to check file/directory permissions

        Returns:
            Tuple of (errors, warnings)
        """
        self.validation_errors.clear()
        self.warnings.clear()

        # Basic validation
        self._validate_system_config()
        self._validate_database_config()
        self._validate_queue_config()
        self._validate_llm_configs()
        self._validate_notification_configs()
        self._validate_repository_configs()

        # Advanced validation
        if check_dependencies:
            self._validate_dependencies()

        if check_permissions:
            self._validate_permissions()

        # Runtime connectivity checks
        if check_connectivity:
            asyncio.run(self._validate_connectivity())

        return self.validation_errors.copy(), self.warnings.copy()

    def _validate_system_config(self) -> None:
        """Validate system configuration."""
        system = self.config.system

        # Environment validation
        valid_environments = ["development", "staging", "production", "test"]
        if system.environment not in valid_environments:
            self.warnings.append(
                f"Unknown environment '{system.environment}'. "
                f"Expected one of: {', '.join(valid_environments)}"
            )

        # Timeout validation
        if system.worker_timeout <= 30:
            self.warnings.append(
                f"Worker timeout {system.worker_timeout}s is very low. "
                "Consider using at least 30 seconds for complex operations."
            )
        elif system.worker_timeout > 1800:
            self.warnings.append(
                f"Worker timeout {system.worker_timeout}s is very high. "
                "Long timeouts may hide performance issues."
            )

        # Circuit breaker validation
        if system.circuit_breaker_failure_threshold < 3:
            self.warnings.append(
                "Circuit breaker failure threshold < 3 may cause premature failovers"
            )

        if system.circuit_breaker_timeout > 300:
            self.warnings.append(
                "Circuit breaker timeout > 5 minutes may delay recovery too long"
            )

    def _validate_database_config(self) -> None:
        """Validate database configuration."""
        db = self.config.database

        # URL validation
        try:
            parsed = urlparse(db.url)
            if not parsed.scheme:
                self.validation_errors.append("Database URL missing scheme")
                return

            # Scheme-specific validation
            if parsed.scheme == "postgresql":
                if not parsed.hostname:
                    self.validation_errors.append("PostgreSQL URL missing hostname")
                if not parsed.port and parsed.hostname != "localhost":
                    self.warnings.append(
                        "PostgreSQL URL missing port, using default 5432"
                    )

            elif parsed.scheme == "mysql":
                if not parsed.hostname:
                    self.validation_errors.append("MySQL URL missing hostname")
                if not parsed.port and parsed.hostname != "localhost":
                    self.warnings.append("MySQL URL missing port, using default 3306")

            elif parsed.scheme == "sqlite":
                if parsed.path and parsed.path != ":memory:":
                    db_path = Path(parsed.path)
                    if not db_path.parent.exists():
                        self.validation_errors.append(
                            f"SQLite database directory does not exist: "
                            f"{db_path.parent}"
                        )

        except Exception as e:
            self.validation_errors.append(f"Invalid database URL: {e}")

        # Pool configuration validation
        if db.pool_size > 50:
            self.warnings.append(
                f"Large database pool size ({db.pool_size}) may consume "
                "excessive resources"
            )

        if db.max_overflow > db.pool_size * 2:
            self.warnings.append(
                "Database max_overflow is more than 2x pool_size, "
                "which may indicate misconfiguration"
            )

        if db.pool_timeout > 60:
            self.warnings.append(
                "Long database pool timeout may mask connection issues"
            )

    def _validate_queue_config(self) -> None:
        """Validate queue configuration."""
        queue = self.config.queue

        # Provider-specific validation
        if queue.provider == "redis":
            try:
                parsed = urlparse(queue.url)
                if parsed.scheme != "redis":
                    self.validation_errors.append(
                        f"Redis provider requires redis:// URL, got {parsed.scheme}://"
                    )
                if not parsed.hostname:
                    self.validation_errors.append("Redis URL missing hostname")
            except Exception as e:
                self.validation_errors.append(f"Invalid Redis URL: {e}")

        elif queue.provider == "rabbitmq":
            try:
                parsed = urlparse(queue.url)
                if parsed.scheme not in ["amqp", "amqps"]:
                    self.validation_errors.append(
                        "RabbitMQ provider requires amqp:// or amqps:// URL"
                    )
            except Exception as e:
                self.validation_errors.append(f"Invalid RabbitMQ URL: {e}")

        # Configuration validation
        if queue.visibility_timeout <= 30:
            self.warnings.append(
                "Short queue visibility timeout may cause message duplication"
            )

        if queue.batch_size > 50:
            self.warnings.append(
                "Large batch size may impact memory usage and processing latency"
            )

    def _validate_llm_configs(self) -> None:
        """Validate LLM provider configurations."""
        if not self.config.llm:
            self.validation_errors.append(
                "At least one LLM provider must be configured"
            )
            return

        # Validate default provider
        if self.config.default_llm_provider not in self.config.llm:
            self.validation_errors.append(
                f"Default LLM provider '{self.config.default_llm_provider}' "
                f"not found in configured providers: {list(self.config.llm.keys())}"
            )

        # Validate each provider
        for name, provider in self.config.llm.items():
            self._validate_llm_provider(name, provider)

    def _validate_llm_provider(self, name: str, provider: LLMProviderConfig) -> None:
        """Validate individual LLM provider configuration."""
        # API key validation
        if not provider.api_key or provider.api_key.strip() == "":
            self.validation_errors.append(f"LLM provider '{name}' missing API key")
        elif provider.api_key == "test-key":
            self.warnings.append(f"LLM provider '{name}' using test API key")

        # Model validation
        model_patterns = {
            "anthropic": [r"claude-\d+-.*", r"claude-instant-.*"],
            "openai": [r"gpt-\d+.*", r"text-.*", r"davinci-.*"],
            "azure_openai": [r"gpt-\d+.*"],
            "gemini": [r"gemini-.*", r"models/gemini-.*"],
        }

        if provider.provider.value in model_patterns:
            patterns = model_patterns[provider.provider.value]
            if not any(re.match(pattern, provider.model) for pattern in patterns):
                self.warnings.append(
                    f"LLM provider '{name}' model '{provider.model}' "
                    f"doesn't match expected patterns for {provider.provider.value}"
                )

        # Token limits validation
        if provider.max_tokens >= 50000:  # Warn at 50k+ tokens for cost awareness
            self.warnings.append(
                f"LLM provider '{name}' has very high max_tokens "
                f"({provider.max_tokens}). "
                "This may increase costs significantly."
            )

        # Temperature validation
        if provider.temperature > 1.0:
            self.warnings.append(
                f"LLM provider '{name}' high temperature ({provider.temperature}) "
                "may produce inconsistent results for code analysis"
            )

    def _validate_notification_configs(self) -> None:
        """Validate notification system configuration."""
        notification = self.config.notification

        if not notification.enabled:
            self.warnings.append("Notification system is disabled")
            return

        if not notification.channels:
            self.validation_errors.append(
                "Notification system enabled but no channels configured"
            )
            return

        # Validate channels
        enabled_channels = [ch for ch in notification.channels if ch.enabled]
        if not enabled_channels:
            self.validation_errors.append(
                "Notification system enabled but no channels are enabled"
            )

        for i, channel in enumerate(notification.channels):
            self._validate_notification_channel(f"channel[{i}]", channel)

        # Rate limiting validation
        if notification.max_notifications_per_hour >= 50:  # Warn at high rate limits
            self.warnings.append("High notification rate limit may cause spam")
        elif notification.max_notifications_per_hour < 5:
            self.warnings.append(
                "Low notification rate limit may suppress important alerts"
            )

    def _validate_notification_channel(
        self, name: str, channel: NotificationChannelConfig
    ) -> None:
        """Validate individual notification channel."""
        if channel.provider == "telegram":
            if not channel.telegram_bot_token:
                self.validation_errors.append(f"Telegram {name} missing bot_token")
            elif channel.telegram_bot_token.startswith("${"):
                # Environment variable placeholder
                pass
            elif not re.match(r"^\d+:[A-Za-z0-9_-]+$", channel.telegram_bot_token):
                self.validation_errors.append(
                    f"Telegram {name} invalid bot_token format"
                )

            if not channel.telegram_chat_id:
                self.validation_errors.append(f"Telegram {name} missing chat_id")

        elif channel.provider == "slack":
            if not channel.slack_webhook_url:
                self.validation_errors.append(f"Slack {name} missing webhook_url")
            elif not channel.slack_webhook_url.startswith(
                "${"
            ) and not channel.slack_webhook_url.startswith("https://hooks.slack.com/"):
                self.validation_errors.append(
                    f"Slack {name} webhook_url should start with https://hooks.slack.com/"
                )

        elif channel.provider == "email":
            required_fields = [
                ("email_smtp_host", "SMTP host"),
                ("email_username", "username"),
                ("email_password", "password"),
                ("email_from_address", "from address"),
                ("email_to_addresses", "to addresses"),
            ]

            for field, description in required_fields:
                if not getattr(channel, field):
                    self.validation_errors.append(f"Email {name} missing {description}")

            # Validate email addresses
            if channel.email_from_address and "@" not in channel.email_from_address:
                self.validation_errors.append(
                    f"Email {name} invalid from address format"
                )

            if channel.email_to_addresses:
                for addr in channel.email_to_addresses:
                    if "@" not in addr:
                        self.validation_errors.append(
                            f"Email {name} invalid to address: {addr}"
                        )

    def _validate_repository_configs(self) -> None:
        """Validate repository configurations."""
        if not self.config.repositories:
            self.validation_errors.append("At least one repository must be configured")
            return

        for i, repo in enumerate(self.config.repositories):
            self._validate_repository_config(f"repository[{i}]", repo)

    def _validate_repository_config(self, name: str, repo: RepositoryConfig) -> None:
        """Validate individual repository configuration."""
        # URL validation
        if not repo.url.startswith(("https://github.com/", "git@github.com:")):
            self.validation_errors.append(f"{name} URL must be a GitHub repository")

        # Token validation
        if not repo.auth_token:
            self.validation_errors.append(f"{name} missing auth_token")
        elif repo.auth_token == "test-token":
            self.warnings.append(f"{name} using test auth_token")

        # Polling interval validation
        if repo.polling_interval <= 60:
            self.warnings.append(
                f"{name} polling interval {repo.polling_interval}s is very frequent. "
                "This may hit GitHub API rate limits."
            )
        elif repo.polling_interval > 3600:
            self.warnings.append(
                f"{name} polling interval {repo.polling_interval}s is very infrequent. "
                "Important changes may be delayed."
            )

        # Failure threshold validation
        if repo.failure_threshold < 2:
            self.warnings.append(
                f"{name} low failure threshold may cause premature escalations"
            )
        elif repo.failure_threshold > 20:
            self.warnings.append(
                f"{name} high failure threshold may delay human intervention"
            )

        # Fix categories validation
        from .models import FixCategory

        lint_config = repo.fix_categories.get(FixCategory.LINT, {})
        test_config = repo.fix_categories.get(FixCategory.TEST, {})
        lint_enabled = lint_config.get("enabled", False)
        test_enabled = test_config.get("enabled", False)

        if not lint_enabled and not test_enabled:
            self.warnings.append(f"{name} has no fix categories enabled")

        # Business hours validation
        if repo.business_hours:
            required_fields = ["start", "end"]
            for field in required_fields:
                if field not in repo.business_hours:
                    self.validation_errors.append(
                        f"{name} business_hours missing '{field}' field"
                    )

    def _validate_dependencies(self) -> None:
        """Validate that required dependencies are available."""
        import importlib.util

        if importlib.util.find_spec("yaml") is None:
            self.validation_errors.append("PyYAML is required but not installed")

        if (
            importlib.util.find_spec("redis") is None
            and self.config.queue.provider == "redis"
        ):
            self.validation_errors.append(
                "redis library is required for Redis queue provider"
            )

        if importlib.util.find_spec(
            "psycopg2"
        ) is None and self.config.database.url.startswith("postgresql://"):
            self.validation_errors.append(
                "psycopg2 is required for PostgreSQL database"
            )

        if importlib.util.find_spec(
            "pymysql"
        ) is None and self.config.database.url.startswith("mysql://"):
            self.validation_errors.append("PyMySQL is required for MySQL database")

    def _validate_permissions(self) -> None:
        """Validate file and directory permissions."""
        # Check log directory permissions
        log_dir = Path("/var/log/agentic")
        if log_dir.exists() and not os.access(log_dir, os.W_OK):
            self.warnings.append(f"No write permission for log directory: {log_dir}")

        # Check config file permissions
        if hasattr(self.config, "_config_file_path") and self.config._config_file_path:
            config_path = Path(self.config._config_file_path)
            if config_path.exists():
                # Check if config file is world-readable (security risk)
                import stat

                mode = config_path.stat().st_mode
                if mode & stat.S_IROTH:
                    self.warnings.append(
                        f"Configuration file {config_path} is world-readable. "
                        "This may expose sensitive information."
                    )

    async def _validate_connectivity(self) -> None:
        """Test actual connectivity to external services."""
        # This would contain actual connectivity tests
        # For now, we'll just add placeholders

        # Test database connectivity
        try:
            # db_test = await self._test_database_connection()
            pass  # Placeholder
        except Exception as e:
            self.validation_errors.append(f"Database connectivity test failed: {e}")

        # Test queue connectivity
        try:
            # queue_test = await self._test_queue_connection()
            pass  # Placeholder
        except Exception as e:
            self.validation_errors.append(f"Queue connectivity test failed: {e}")

        # Test LLM provider connectivity
        for name, _provider in self.config.llm.items():
            try:
                # llm_test = await self._test_llm_connection(_provider)
                pass  # Placeholder
            except Exception as e:
                self.validation_errors.append(
                    f"LLM provider '{name}' connectivity test failed: {e}"
                )


def validate_config(
    config: Config,
    check_connectivity: bool = False,
    check_dependencies: bool = True,
    check_permissions: bool = False,
    raise_on_error: bool = True,
) -> tuple[list[str], list[str]]:
    """Validate configuration with specified checks.

    Args:
        config: Configuration to validate
        check_connectivity: Whether to test actual connectivity
        check_dependencies: Whether to check for required dependencies
        check_permissions: Whether to check file/directory permissions
        raise_on_error: Whether to raise exception on validation errors

    Returns:
        Tuple of (errors, warnings)

    Raises:
        ConfigurationValidationError: If validation fails and raise_on_error=True
    """
    validator = ConfigurationValidator(config)
    errors, warnings = validator.validate_all(
        check_connectivity=check_connectivity,
        check_dependencies=check_dependencies,
        check_permissions=check_permissions,
    )

    if errors and raise_on_error:
        error_msg = f"Configuration validation failed with {len(errors)} error(s):\n"
        error_msg += "\n".join(f"  - {error}" for error in errors)
        if warnings:
            error_msg += f"\n\nWarnings ({len(warnings)}):\n"
            error_msg += "\n".join(f"  - {warning}" for warning in warnings)

        raise ConfigurationValidationError(error_msg, validation_errors=errors)

    return errors, warnings
