"""Pydantic configuration models for the agentic coding workflow system.

This module defines all configuration schemas with type safety, validation,
and environment variable substitution support. Models are organized by
system component for clarity and maintainability.

The configuration hierarchy follows this structure:
- Config: Root configuration containing all subsystems
- SystemConfig: Core system settings (timeouts, retry limits)
- Component-specific configs: Database, Queue, LLM providers, etc.

Environment variables are substituted using the format ${VAR_NAME} with
optional defaults: ${VAR_NAME:default_value}
"""

import os
import re
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class LogLevel(str, Enum):
    """Supported logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class NotificationPriority(str, Enum):
    """Notification priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FixCategory(str, Enum):
    """Types of check failures that can be automatically fixed."""

    LINT = "lint"
    FORMAT = "format"
    TEST = "test"
    COMPILATION = "compilation"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"
    DEPENDENCIES = "dependencies"


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    GEMINI = "gemini"


class NotificationProvider(str, Enum):
    """Supported notification providers."""

    TELEGRAM = "telegram"
    SLACK = "slack"
    EMAIL = "email"
    WEBHOOK = "webhook"


class BaseConfigModel(BaseModel):
    """Base configuration model with environment variable substitution."""

    class Config:
        """Pydantic model configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        validate_assignment = True
        extra = "forbid"  # Prevent extra fields

    @model_validator(mode="before")
    def substitute_env_vars(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Substitute environment variables in string values.

        Supports formats:
        - ${VAR_NAME} - Required environment variable
        - ${VAR_NAME:default} - Optional with default value

        Args:
            values: Raw configuration values

        Returns:
            Configuration values with environment variables substituted

        Raises:
            ValueError: If required environment variable is missing
        """

        def substitute_value(value: Any) -> Any:
            if isinstance(value, str):
                # Pattern: ${VAR_NAME} or ${VAR_NAME:default}
                pattern = r"\$\{([^}:]+)(?::([^}]*))?\}"

                def replacer(match: re.Match[str]) -> str:
                    var_name = match.group(1)
                    default_value = (
                        match.group(2) if match.group(2) is not None else None
                    )

                    env_value = os.getenv(var_name)
                    if env_value is not None:
                        return env_value
                    elif default_value is not None:
                        return default_value
                    else:
                        raise ValueError(
                            f"Required environment variable '{var_name}' not found"
                        )

                return re.sub(pattern, replacer, value)
            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_value(item) for item in value]
            else:
                return value

        return {key: substitute_value(value) for key, value in values.items()}


class SystemConfig(BaseConfigModel):
    """Core system configuration settings."""

    log_level: LogLevel = Field(
        default=LogLevel.INFO, description="System-wide logging level"
    )

    environment: str = Field(
        default="development",
        description="Deployment environment (development, staging, production)",
    )

    worker_timeout: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Maximum worker execution time in seconds",
    )

    max_retry_attempts: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retry attempts for failed operations",
    )

    circuit_breaker_failure_threshold: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of failures before opening circuit breaker",
    )

    circuit_breaker_timeout: int = Field(
        default=60, ge=10, le=300, description="Circuit breaker timeout in seconds"
    )

    metrics_collection_enabled: bool = Field(
        default=True, description="Enable system metrics collection"
    )

    debug_mode: bool = Field(
        default=False, description="Enable debug mode with verbose logging"
    )


class DatabaseConfig(BaseConfigModel):
    """Database connection and pool configuration."""

    url: str = Field(description="Database connection URL")

    pool_size: int = Field(
        default=10, ge=1, le=100, description="Database connection pool size"
    )

    max_overflow: int = Field(
        default=20,
        ge=0,
        le=100,
        description="Maximum overflow connections beyond pool size",
    )

    pool_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Timeout in seconds for getting connection from pool",
    )

    pool_recycle: int = Field(
        default=3600, ge=300, le=86400, description="Connection recycle time in seconds"
    )

    echo: bool = Field(default=False, description="Enable SQLAlchemy query logging")

    @field_validator("url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v:
            raise ValueError("Database URL cannot be empty")

        try:
            parsed = urlparse(v)
            if not parsed.scheme:
                raise ValueError("Database URL must include scheme")
            if parsed.scheme not in ["postgresql", "mysql", "sqlite"]:
                raise ValueError("Unsupported database scheme")
        except Exception as e:
            raise ValueError(f"Invalid database URL format: {e}") from e

        return v


class QueueConfig(BaseConfigModel):
    """Message queue configuration."""

    provider: str = Field(
        default="redis", description="Queue provider (redis, rabbitmq, sqs)"
    )

    url: str = Field(description="Queue connection URL")

    default_queue: str = Field(default="default", description="Default queue name")

    max_retries: int = Field(
        default=3, ge=0, le=10, description="Maximum message retry attempts"
    )

    visibility_timeout: int = Field(
        default=300, ge=30, le=1800, description="Message visibility timeout in seconds"
    )

    dead_letter_queue_enabled: bool = Field(
        default=True, description="Enable dead letter queue for failed messages"
    )

    batch_size: int = Field(
        default=10, ge=1, le=100, description="Message batch processing size"
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate queue provider."""
        supported = ["redis", "rabbitmq", "sqs"]
        if v.lower() not in supported:
            raise ValueError(f"Unsupported queue provider: {v}")
        return v.lower()


class LLMProviderConfig(BaseConfigModel):
    """Configuration for a specific LLM provider."""

    provider: LLMProvider = Field(description="LLM provider type")

    api_key: str = Field(description="API key for the provider")

    model: str = Field(description="Model name/identifier")

    endpoint: str | None = Field(
        default=None,
        description="Custom API endpoint (for self-hosted or regional deployments)",
    )

    max_tokens: int = Field(
        default=4000, ge=100, le=100000, description="Maximum tokens per request"
    )

    temperature: float = Field(
        default=0.1, ge=0.0, le=2.0, description="Sampling temperature"
    )

    timeout: int = Field(
        default=60, ge=10, le=300, description="Request timeout in seconds"
    )

    rate_limit_rpm: int | None = Field(
        default=None, ge=1, description="Rate limit in requests per minute"
    )


    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key is not empty."""
        if not v or v.strip() == "":
            raise ValueError("API key cannot be empty")
        return v.strip()


class NotificationChannelConfig(BaseConfigModel):
    """Configuration for a notification channel."""

    provider: NotificationProvider = Field(description="Notification provider type")

    enabled: bool = Field(
        default=True, description="Whether this notification channel is enabled"
    )

    # Provider-specific configuration
    telegram_bot_token: str | None = Field(
        default=None, description="Telegram bot token"
    )

    telegram_chat_id: str | None = Field(default=None, description="Telegram chat ID")

    slack_webhook_url: str | None = Field(default=None, description="Slack webhook URL")

    slack_channel: str | None = Field(default=None, description="Slack channel name")

    email_smtp_host: str | None = Field(
        default=None, description="SMTP server hostname"
    )

    email_smtp_port: int | None = Field(default=587, description="SMTP server port")

    email_username: str | None = Field(default=None, description="SMTP username")

    email_password: str | None = Field(default=None, description="SMTP password")

    email_from_address: str | None = Field(
        default=None, description="Email from address"
    )

    email_to_addresses: list[str] | None = Field(
        default=None, description="List of recipient email addresses"
    )

    webhook_url: str | None = Field(default=None, description="Generic webhook URL")

    webhook_headers: dict[str, str] | None = Field(
        default=None, description="Custom headers for webhook requests"
    )

    @field_validator("provider")
    @classmethod
    def validate_provider_config(cls, v: str) -> str:
        """Validate provider-specific configuration."""
        # This will be enhanced in the validation logic
        return v


class NotificationConfig(BaseConfigModel):
    """Notification system configuration."""

    enabled: bool = Field(default=True, description="Enable notification system")

    channels: list[NotificationChannelConfig] = Field(
        default_factory=list, description="List of notification channels"
    )

    escalation_enabled: bool = Field(
        default=True, description="Enable escalation notifications"
    )

    escalation_delay: int = Field(
        default=1800,  # 30 minutes
        ge=300,
        le=86400,
        description="Delay before escalation in seconds",
    )

    max_notifications_per_hour: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum notifications per hour to prevent spam",
    )

    priority_mapping: dict[NotificationPriority, list[NotificationProvider]] = Field(
        default_factory=lambda: {
            NotificationPriority.LOW: [NotificationProvider.EMAIL],
            NotificationPriority.MEDIUM: [
                NotificationProvider.SLACK,
                NotificationProvider.EMAIL,
            ],
            NotificationPriority.HIGH: [
                NotificationProvider.TELEGRAM,
                NotificationProvider.SLACK,
            ],
            NotificationPriority.CRITICAL: [
                NotificationProvider.TELEGRAM,
                NotificationProvider.SLACK,
                NotificationProvider.EMAIL,
            ],
        },
        description="Mapping of priority levels to notification providers",
    )


class RepositoryConfig(BaseConfigModel):
    """Configuration for a specific GitHub repository."""

    url: str = Field(description="Repository URL")

    auth_token: str = Field(description="GitHub authentication token")

    polling_interval: int = Field(
        default=300,  # 5 minutes
        ge=60,
        le=3600,
        description="PR polling interval in seconds",
    )

    failure_threshold: int = Field(
        default=5, ge=1, le=20, description="Number of failures before human escalation"
    )

    skip_patterns: dict[str, list[str]] | None = Field(
        default_factory=lambda: {
            "pr_labels": ["wip", "draft", "dependencies"],
            "check_names": ["codecov/*", "license/*"],
            "authors": ["dependabot[bot]"],
        },
        description="Patterns to skip during processing",
    )

    fix_categories: dict[FixCategory, dict[str, Any]] = Field(
        default_factory=lambda: dict[FixCategory, dict[str, Any]](
            {
                FixCategory.LINT: {
                    "enabled": True,
                    "confidence_threshold": 60,
                    "max_files_changed": 10,
                },
                FixCategory.TEST: {
                    "enabled": True,
                    "confidence_threshold": 80,
                    "run_full_test_suite": True,
                },
                FixCategory.SECURITY: {"enabled": False, "always_escalate": True},
                FixCategory.INFRASTRUCTURE: {"enabled": False, "always_escalate": True},
            }
        ),
        description="Fix category configuration",
    )

    is_critical: bool = Field(
        default=False, description="Whether this is a critical production repository"
    )

    timezone: str = Field(
        default="UTC", description="Repository timezone for business hours calculation"
    )

    business_hours: dict[str, str] | None = Field(
        default=None, description="Business hours configuration (start/end times)"
    )

    @field_validator("url")
    @classmethod
    def validate_repository_url(cls, v: str) -> str:
        """Validate repository URL format."""
        if not v.startswith(("https://github.com/", "git@github.com:")):
            raise ValueError("Only GitHub repositories are supported")
        return v

    @field_validator("auth_token")
    @classmethod
    def validate_auth_token(cls, v: str) -> str:
        """Validate authentication token."""
        if not v or v.strip() == "":
            raise ValueError("Authentication token cannot be empty")
        return v.strip()


class Config(BaseConfigModel):
    """Root configuration containing all subsystem configurations."""

    system: SystemConfig = Field(
        default_factory=SystemConfig, description="Core system configuration"
    )

    database: DatabaseConfig = Field(description="Database configuration")

    queue: QueueConfig = Field(description="Message queue configuration")

    llm: dict[str, LLMProviderConfig] = Field(description="LLM provider configurations")

    default_llm_provider: str = Field(
        default="anthropic", description="Default LLM provider name"
    )

    notification: NotificationConfig = Field(
        default_factory=NotificationConfig,
        description="Notification system configuration",
    )

    repositories: list[RepositoryConfig] = Field(
        description="Repository configurations"
    )

    claude_code_sdk: dict[str, Any] = Field(
        default_factory=dict, description="Claude Code SDK configuration"
    )

    @field_validator("repositories")
    @classmethod
    def validate_repositories_not_empty(cls, v: list[Any]) -> list[Any]:
        """Ensure at least one repository is configured."""
        if not v:
            raise ValueError("At least one repository must be configured")
        return v

    @model_validator(mode="after")
    def validate_consistent_configuration(self) -> "Config":
        """Validate cross-field consistency."""
        # Validate default LLM provider exists
        if self.default_llm_provider not in self.llm:
            raise ValueError(
                f"Default LLM provider '{self.default_llm_provider}' "
                "not found in llm configuration"
            )

        # Validate notification channels reference configured providers
        if self.notification and self.notification.channels:
            for _channel in self.notification.channels:
                # Provider-specific validation will be added here
                pass

        return self
