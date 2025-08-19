"""Unit tests for configuration models.

This module tests the Pydantic configuration models, validation logic,
and environment variable substitution functionality.
"""

import os
from typing import Any
from unittest.mock import patch

import pytest

from src.config.exceptions import ConfigurationValidationError
from src.config.models import (
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


class TestSystemConfig:
    """Tests for SystemConfig model validation and defaults."""

    def test_system_config_default_values(self):
        """
        Why: Ensure SystemConfig provides sensible defaults for production use
        What: Tests that default values are set correctly for all system settings
        How: Creates SystemConfig with no parameters and verifies default values
        """
        config = SystemConfig()

        assert config.log_level == LogLevel.INFO
        assert config.environment == "development"
        assert config.worker_timeout == 300
        assert config.max_retry_attempts == 3
        assert config.circuit_breaker_failure_threshold == 5
        assert config.circuit_breaker_timeout == 60
        assert config.metrics_collection_enabled is True
        assert config.debug_mode is False

    def test_system_config_validates_worker_timeout_range(self):
        """
        Why: Prevent system misconfiguration that could cause worker hangs or
             premature timeouts
        What: Tests that worker_timeout field validates against reasonable bounds
              (30-3600s)
        How: Tests both valid values within range and invalid values outside range
        """
        # Valid timeout values
        config = SystemConfig(worker_timeout=30)
        assert config.worker_timeout == 30

        config = SystemConfig(worker_timeout=3600)
        assert config.worker_timeout == 3600

        # Invalid timeout values
        with pytest.raises(
            ValueError, match="Input should be greater than or equal to 30"
        ):
            SystemConfig(worker_timeout=29)

        with pytest.raises(
            ValueError, match="Input should be less than or equal to 3600"
        ):
            SystemConfig(worker_timeout=3601)

    def test_system_config_validates_retry_attempts_range(self):
        """
        Why: Ensure retry attempts are within reasonable bounds to prevent
             infinite loops
        What: Tests that max_retry_attempts validates against 0-10 range
        How: Tests boundary values and invalid values outside the range
        """
        # Valid retry values
        config = SystemConfig(max_retry_attempts=0)
        assert config.max_retry_attempts == 0

        config = SystemConfig(max_retry_attempts=10)
        assert config.max_retry_attempts == 10

        # Invalid retry values
        with pytest.raises(
            ValueError, match="Input should be greater than or equal to 0"
        ):
            SystemConfig(max_retry_attempts=-1)

        with pytest.raises(
            ValueError, match="Input should be less than or equal to 10"
        ):
            SystemConfig(max_retry_attempts=11)


class TestDatabaseConfig:
    """Tests for DatabaseConfig model validation and URL parsing."""

    def test_database_config_validates_url_format(self):
        """
        Why: Ensure database URLs are properly formatted to prevent connection failures
        What: Tests URL validation for different database schemes
              (postgresql, mysql, sqlite)
        How: Tests valid URLs for each scheme and invalid URLs that should
             raise ValueError
        """
        # Valid URLs
        valid_urls = [
            "postgresql://user:pass@localhost:5432/db",
            "mysql://user:pass@localhost:3306/db",
            "sqlite:///path/to/db.sqlite",
            "sqlite:///:memory:",
        ]

        for url in valid_urls:
            config = DatabaseConfig(url=url)
            assert config.url == url

    def test_database_config_rejects_invalid_urls(self):
        """
        Why: Prevent application startup with malformed database URLs
        What: Tests that invalid URL formats raise appropriate validation errors
        How: Tests empty URLs, missing schemes, and unsupported database types
        """
        # Empty URL
        with pytest.raises(ValueError, match="Database URL cannot be empty"):
            DatabaseConfig(url="")

        # Missing scheme
        with pytest.raises(
            ValueError, match="Invalid database URL format.*Unsupported database scheme"
        ):
            DatabaseConfig(url="user:pass@localhost:5432/db")

        # Unsupported scheme
        with pytest.raises(
            ValueError, match="Invalid database URL format.*Unsupported database scheme"
        ):
            DatabaseConfig(url="oracle://user:pass@localhost:1521/db")

    def test_database_config_validates_pool_settings(self):
        """
        Why: Ensure database connection pool is configured within reasonable limits
        What: Tests validation of pool_size, max_overflow, and timeout parameters
        How: Tests boundary values and verifies they are within expected ranges
        """
        config = DatabaseConfig(
            url="sqlite:///:memory:",
            pool_size=1,
            max_overflow=0,
            pool_timeout=1,
            pool_recycle=300,
        )
        assert config.pool_size == 1
        assert config.max_overflow == 0
        assert config.pool_timeout == 1
        assert config.pool_recycle == 300

    def test_database_config_default_values(self):
        """
        Why: Ensure sensible defaults are provided for production database usage
        What: Tests that default pool configuration values are reasonable
        How: Creates config with only URL and verifies all default values
        """
        config = DatabaseConfig(url="postgresql://user:pass@localhost/db")

        assert config.pool_size == 10
        assert config.max_overflow == 20
        assert config.pool_timeout == 30
        assert config.pool_recycle == 3600
        assert config.echo is False


class TestQueueConfig:
    """Tests for QueueConfig model validation and provider-specific settings."""

    def test_queue_config_validates_supported_providers(self):
        """
        Why: Ensure only supported queue providers are used to prevent runtime errors
        What: Tests that provider field accepts only redis, rabbitmq, sqs
              (case-insensitive)
        How: Tests valid providers and verifies unsupported providers raise ValueError
        """
        # Valid providers (case insensitive)
        valid_providers = ["redis", "REDIS", "rabbitmq", "RABBITMQ", "sqs", "SQS"]

        for provider in valid_providers:
            config = QueueConfig(provider=provider, url="redis://localhost:6379/0")
            assert config.provider == provider.lower()

        # Invalid provider
        with pytest.raises(
            ValueError, match="Unsupported queue provider: invalidprovider"
        ):
            QueueConfig(provider="invalidprovider", url="redis://localhost:6379/0")

    def test_queue_config_default_values(self):
        """
        Why: Provide sensible defaults for queue configuration in production
        What: Tests that default queue settings are appropriate for typical usage
        How: Creates config with minimal parameters and verifies defaults
        """
        config = QueueConfig(url="redis://localhost:6379/0")

        assert config.provider == "redis"
        assert config.default_queue == "default"
        assert config.max_retries == 3
        assert config.visibility_timeout == 300
        assert config.dead_letter_queue_enabled is True
        assert config.batch_size == 10

    def test_queue_config_validates_parameter_ranges(self):
        """
        Why: Ensure queue parameters are within reasonable operational bounds
        What: Tests validation of max_retries, visibility_timeout, and batch_size ranges
        How: Tests boundary values and invalid values for each parameter
        """
        # Test max_retries bounds (0-10)
        config = QueueConfig(url="redis://localhost:6379/0", max_retries=0)
        assert config.max_retries == 0

        config = QueueConfig(url="redis://localhost:6379/0", max_retries=10)
        assert config.max_retries == 10

        # Test visibility_timeout bounds (30-1800)
        config = QueueConfig(url="redis://localhost:6379/0", visibility_timeout=30)
        assert config.visibility_timeout == 30

        config = QueueConfig(url="redis://localhost:6379/0", visibility_timeout=1800)
        assert config.visibility_timeout == 1800

        # Test batch_size bounds (1-100)
        config = QueueConfig(url="redis://localhost:6379/0", batch_size=1)
        assert config.batch_size == 1

        config = QueueConfig(url="redis://localhost:6379/0", batch_size=100)
        assert config.batch_size == 100


class TestLLMProviderConfig:
    """Tests for LLM provider configuration validation."""

    def test_llm_provider_config_validates_api_key(self):
        """
        Why: Ensure LLM providers have valid API keys to prevent authentication failures
        What: Tests that API key validation rejects empty or whitespace-only keys
        How: Tests valid keys are accepted and invalid keys raise ValueError
        """
        # Valid API key
        config = LLMProviderConfig(
            provider=LLMProvider.ANTHROPIC,
            api_key="sk-ant-valid-key",
            model="claude-3-sonnet-20240229",
        )
        assert config.api_key == "sk-ant-valid-key"

        # Empty API key
        with pytest.raises(ValueError, match="API key cannot be empty"):
            LLMProviderConfig(
                provider=LLMProvider.ANTHROPIC,
                api_key="",
                model="claude-3-sonnet-20240229",
            )

        # Whitespace-only API key
        with pytest.raises(ValueError, match="API key cannot be empty"):
            LLMProviderConfig(
                provider=LLMProvider.ANTHROPIC,
                api_key="   ",
                model="claude-3-sonnet-20240229",
            )

    def test_llm_provider_config_validates_parameter_ranges(self):
        """
        Why: Ensure LLM parameters are within valid ranges to prevent API errors
        What: Tests max_tokens, temperature, timeout, and rate_limit_rpm validation
        How: Tests boundary values and invalid values for each parameter
        """
        # Valid configuration
        config = LLMProviderConfig(
            provider=LLMProvider.ANTHROPIC,
            api_key="sk-ant-test",
            model="claude-3-sonnet-20240229",
            max_tokens=100,  # minimum
            temperature=0.0,  # minimum
            timeout=10,  # minimum
            rate_limit_rpm=1,  # minimum
        )
        assert config.max_tokens == 100
        assert config.temperature == 0.0
        assert config.timeout == 10
        assert config.rate_limit_rpm == 1

        # Test maximum values
        config = LLMProviderConfig(
            provider=LLMProvider.ANTHROPIC,
            api_key="sk-ant-test",
            model="claude-3-sonnet-20240229",
            max_tokens=100000,  # maximum
            temperature=2.0,  # maximum
            timeout=300,  # maximum
        )
        assert config.max_tokens == 100000
        assert config.temperature == 2.0
        assert config.timeout == 300

    def test_llm_provider_config_default_values(self):
        """
        Why: Provide reasonable defaults for LLM configuration in production
        What: Tests that default values are set for optional parameters
        How: Creates minimal config and verifies default values
        """
        config = LLMProviderConfig(
            provider=LLMProvider.ANTHROPIC,
            api_key="sk-ant-test",
            model="claude-3-sonnet-20240229",
        )

        assert config.endpoint is None
        assert config.max_tokens == 4000
        assert config.temperature == 0.1
        assert config.timeout == 60
        assert config.rate_limit_rpm is None

    def test_llm_provider_config_strips_whitespace_from_api_key(self):
        """
        Why: Handle common user input errors with API keys containing whitespace
        What: Tests that leading/trailing whitespace is stripped from API keys
        How: Provides API key with whitespace and verifies it's cleaned
        """
        config = LLMProviderConfig(
            provider=LLMProvider.ANTHROPIC,
            api_key="  sk-ant-test-key  ",
            model="claude-3-sonnet-20240229",
        )
        assert config.api_key == "sk-ant-test-key"


class TestNotificationChannelConfig:
    """Tests for notification channel configuration validation."""

    def test_notification_channel_config_default_enabled(self):
        """
        Why: Ensure notification channels are enabled by default for
             operational visibility
        What: Tests that enabled field defaults to True
        How: Creates config without enabled parameter and verifies default
        """
        config = NotificationChannelConfig(provider=NotificationProvider.TELEGRAM)
        assert config.enabled is True

    def test_notification_channel_config_provider_specific_fields(self):
        """
        Why: Ensure provider-specific fields are properly handled for
             different notification types
        What: Tests that optional fields for different providers can be set correctly
        How: Creates configs for different providers and verifies field assignment
        """
        # Telegram configuration
        telegram_config = NotificationChannelConfig(
            provider=NotificationProvider.TELEGRAM,
            telegram_bot_token="123456:ABC-DEF",
            telegram_chat_id="-1001234567890",
        )
        assert telegram_config.telegram_bot_token == "123456:ABC-DEF"
        assert telegram_config.telegram_chat_id == "-1001234567890"

        # Slack configuration
        slack_config = NotificationChannelConfig(
            provider=NotificationProvider.SLACK,
            slack_webhook_url="https://hooks.slack.com/services/...",
            slack_channel="#alerts",
        )
        assert slack_config.slack_webhook_url == "https://hooks.slack.com/services/..."
        assert slack_config.slack_channel == "#alerts"

        # Email configuration
        email_config = NotificationChannelConfig(
            provider=NotificationProvider.EMAIL,
            email_smtp_host="smtp.gmail.com",
            email_smtp_port=587,
            email_username="user@example.com",
            email_password="password",
            email_from_address="noreply@example.com",
            email_to_addresses=["admin@example.com", "team@example.com"],
        )
        assert email_config.email_smtp_host == "smtp.gmail.com"
        assert email_config.email_smtp_port == 587
        assert email_config.email_to_addresses == [
            "admin@example.com",
            "team@example.com",
        ]


class TestNotificationConfig:
    """Tests for notification system configuration."""

    def test_notification_config_default_values(self):
        """
        Why: Ensure notification system has sensible defaults for production use
        What: Tests default values for notification settings and rate limiting
        How: Creates config with no parameters and verifies all defaults
        """
        config = NotificationConfig()

        assert config.enabled is True
        assert config.escalation_enabled is True
        assert config.escalation_delay == 1800  # 30 minutes
        assert config.max_notifications_per_hour == 10
        assert len(config.channels) == 0  # Empty list by default

        # Test default priority mapping
        assert (
            NotificationProvider.EMAIL
            in config.priority_mapping[NotificationPriority.LOW]
        )
        assert (
            NotificationProvider.TELEGRAM
            in config.priority_mapping[NotificationPriority.CRITICAL]
        )

    def test_notification_config_validates_escalation_delay_range(self):
        """
        Why: Ensure escalation delays are reasonable to balance responsiveness
             and spam prevention
        What: Tests that escalation_delay validates against 300-86400 second range
        How: Tests boundary values and invalid values outside the range
        """
        # Valid delay values
        config = NotificationConfig(escalation_delay=300)  # 5 minutes
        assert config.escalation_delay == 300

        config = NotificationConfig(escalation_delay=86400)  # 24 hours
        assert config.escalation_delay == 86400

        # Invalid delay values
        with pytest.raises(
            ValueError, match="Input should be greater than or equal to 300"
        ):
            NotificationConfig(escalation_delay=299)

        with pytest.raises(
            ValueError, match="Input should be less than or equal to 86400"
        ):
            NotificationConfig(escalation_delay=86401)

    def test_notification_config_validates_rate_limits(self):
        """
        Why: Prevent notification spam while ensuring important alerts are delivered
        What: Tests that max_notifications_per_hour validates against 1-100 range
        How: Tests boundary values and invalid values outside the range
        """
        # Valid rate limit values
        config = NotificationConfig(max_notifications_per_hour=1)
        assert config.max_notifications_per_hour == 1

        config = NotificationConfig(max_notifications_per_hour=100)
        assert config.max_notifications_per_hour == 100

        # Invalid rate limit values
        with pytest.raises(
            ValueError, match="Input should be greater than or equal to 1"
        ):
            NotificationConfig(max_notifications_per_hour=0)

        with pytest.raises(
            ValueError, match="Input should be less than or equal to 100"
        ):
            NotificationConfig(max_notifications_per_hour=101)


class TestRepositoryConfig:
    """Tests for repository configuration validation."""

    def test_repository_config_validates_github_urls(self):
        """
        Why: Ensure only GitHub repositories are supported by the system
        What: Tests that repository URLs are validated to be GitHub URLs
        How: Tests valid GitHub URL formats and rejects non-GitHub URLs
        """
        # Valid GitHub URLs
        valid_urls = [
            "https://github.com/owner/repo",
            "https://github.com/org/complex-repo-name",
            "git@github.com:owner/repo.git",
        ]

        for url in valid_urls:
            config = RepositoryConfig(url=url, auth_token="ghp_test_token")
            assert config.url == url

        # Invalid URLs (non-GitHub)
        invalid_urls = [
            "https://gitlab.com/owner/repo",
            "https://bitbucket.org/owner/repo",
            "http://github.com/owner/repo",  # Not HTTPS
            "github.com/owner/repo",  # Missing protocol
        ]

        for url in invalid_urls:
            with pytest.raises(
                ValueError, match="Only GitHub repositories are supported"
            ):
                RepositoryConfig(url=url, auth_token="ghp_test_token")

    def test_repository_config_validates_auth_token(self):
        """
        Why: Ensure authentication tokens are provided for GitHub API access
        What: Tests that auth_token validation rejects empty or whitespace-only tokens
        How: Tests valid tokens are accepted and invalid tokens raise ValueError
        """
        # Valid token
        config = RepositoryConfig(
            url="https://github.com/owner/repo", auth_token="ghp_valid_token"
        )
        assert config.auth_token == "ghp_valid_token"

        # Empty token
        with pytest.raises(ValueError, match="Authentication token cannot be empty"):
            RepositoryConfig(url="https://github.com/owner/repo", auth_token="")

        # Whitespace-only token
        with pytest.raises(ValueError, match="Authentication token cannot be empty"):
            RepositoryConfig(url="https://github.com/owner/repo", auth_token="   ")

    def test_repository_config_strips_whitespace_from_auth_token(self):
        """
        Why: Handle common user input errors with tokens containing whitespace
        What: Tests that leading/trailing whitespace is stripped from auth tokens
        How: Provides token with whitespace and verifies it's cleaned
        """
        config = RepositoryConfig(
            url="https://github.com/owner/repo", auth_token="  ghp_test_token  "
        )
        assert config.auth_token == "ghp_test_token"

    def test_repository_config_default_values(self):
        """
        Why: Provide sensible defaults for repository monitoring configuration
        What: Tests that default values are appropriate for typical GitHub
              repository monitoring
        How: Creates minimal config and verifies all default values
        """
        config = RepositoryConfig(
            url="https://github.com/owner/repo", auth_token="ghp_test_token"
        )

        assert config.polling_interval == 300  # 5 minutes
        assert config.failure_threshold == 5
        assert config.is_critical is False
        assert config.timezone == "UTC"
        assert config.business_hours is None

        # Test default skip patterns
        assert "wip" in config.skip_patterns["pr_labels"]
        assert "draft" in config.skip_patterns["pr_labels"]
        assert "dependencies" in config.skip_patterns["pr_labels"]
        assert "codecov/*" in config.skip_patterns["check_names"]
        assert "dependabot[bot]" in config.skip_patterns["authors"]

        # Test default fix categories
        assert config.fix_categories[FixCategory.LINT]["enabled"] is True
        assert config.fix_categories[FixCategory.TEST]["enabled"] is True
        assert config.fix_categories[FixCategory.SECURITY]["enabled"] is False
        assert config.fix_categories[FixCategory.INFRASTRUCTURE]["enabled"] is False

    def test_repository_config_validates_polling_interval_range(self):
        """
        Why: Ensure polling intervals are reasonable to avoid GitHub API rate limits
        What: Tests that polling_interval validates against 60-3600 second range
        How: Tests boundary values and invalid values outside the range
        """
        # Valid intervals
        config = RepositoryConfig(
            url="https://github.com/owner/repo",
            auth_token="ghp_test_token",
            polling_interval=60,
        )
        assert config.polling_interval == 60

        config = RepositoryConfig(
            url="https://github.com/owner/repo",
            auth_token="ghp_test_token",
            polling_interval=3600,
        )
        assert config.polling_interval == 3600

        # Invalid intervals
        with pytest.raises(
            ValueError, match="Input should be greater than or equal to 60"
        ):
            RepositoryConfig(
                url="https://github.com/owner/repo",
                auth_token="ghp_test_token",
                polling_interval=59,
            )

        with pytest.raises(
            ValueError, match="Input should be less than or equal to 3600"
        ):
            RepositoryConfig(
                url="https://github.com/owner/repo",
                auth_token="ghp_test_token",
                polling_interval=3601,
            )

    def test_repository_config_validates_failure_threshold_range(self):
        """
        Why: Ensure failure thresholds balance automation with human intervention
        What: Tests that failure_threshold validates against 1-20 range
        How: Tests boundary values and invalid values outside the range
        """
        # Valid thresholds
        config = RepositoryConfig(
            url="https://github.com/owner/repo",
            auth_token="ghp_test_token",
            failure_threshold=1,
        )
        assert config.failure_threshold == 1

        config = RepositoryConfig(
            url="https://github.com/owner/repo",
            auth_token="ghp_test_token",
            failure_threshold=20,
        )
        assert config.failure_threshold == 20

        # Invalid thresholds
        with pytest.raises(
            ValueError, match="Input should be greater than or equal to 1"
        ):
            RepositoryConfig(
                url="https://github.com/owner/repo",
                auth_token="ghp_test_token",
                failure_threshold=0,
            )

        with pytest.raises(
            ValueError, match="Input should be less than or equal to 20"
        ):
            RepositoryConfig(
                url="https://github.com/owner/repo",
                auth_token="ghp_test_token",
                failure_threshold=21,
            )


class TestEnvironmentVariableSubstitution:
    """Tests for environment variable substitution functionality."""

    def test_environment_variable_substitution_required_vars(self):
        """
        Why: Ensure required environment variables are properly substituted
             in configuration
        What: Tests that ${VAR_NAME} format substitutes environment variables
              correctly
        How: Sets environment variables and verifies they are substituted in
             config values
        """
        with patch.dict(
            os.environ, {"TEST_DB_URL": "postgresql://test:pass@localhost/db"}
        ):
            config = DatabaseConfig(url="${TEST_DB_URL}")
            assert config.url == "postgresql://test:pass@localhost/db"

    def test_environment_variable_substitution_with_defaults(self):
        """
        Why: Allow optional environment variables with fallback defaults
        What: Tests that ${VAR_NAME:default} format uses defaults when env
              var is missing
        How: Tests both cases where env var exists and where it's missing with default
        """
        # Test with environment variable set
        with patch.dict(os.environ, {"TEST_QUEUE_URL": "redis://custom:6379/1"}):
            config = QueueConfig(url="${TEST_QUEUE_URL:redis://localhost:6379/0}")
            assert config.url == "redis://custom:6379/1"

        # Test with environment variable not set (use default)
        with patch.dict(os.environ, {}, clear=True):
            config = QueueConfig(url="${MISSING_QUEUE_URL:redis://localhost:6379/0}")
            assert config.url == "redis://localhost:6379/0"

    def test_environment_variable_substitution_missing_required(self):
        """
        Why: Prevent configuration loading when required environment
             variables are missing
        What: Tests that missing required environment variables raise ValueError
        How: Attempts to load config with missing required env var and verifies error
        """
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(
                ValueError,
                match="Required environment variable 'MISSING_VAR' not found",
            ),
        ):
            DatabaseConfig(url="${MISSING_VAR}")

    def test_environment_variable_substitution_in_nested_structures(self):
        """
        Why: Ensure environment variable substitution works in complex
             nested configurations
        What: Tests substitution in lists, dictionaries, and nested objects
        How: Creates config with env vars in various nested positions and
             verifies substitution
        """
        with patch.dict(
            os.environ,
            {
                "BOT_TOKEN": "123456:ABC-DEF",
                "CHAT_ID": "-1001234567890",
                "WEBHOOK_URL": "https://hooks.slack.com/test",
            },
        ):
            notification_config = NotificationConfig(
                channels=[
                    NotificationChannelConfig(
                        provider=NotificationProvider.TELEGRAM,
                        telegram_bot_token="${BOT_TOKEN}",
                        telegram_chat_id="${CHAT_ID}",
                    ),
                    NotificationChannelConfig(
                        provider=NotificationProvider.SLACK,
                        slack_webhook_url="${WEBHOOK_URL}",
                    ),
                ]
            )

            assert (
                notification_config.channels[0].telegram_bot_token == "123456:ABC-DEF"
            )
            assert notification_config.channels[0].telegram_chat_id == "-1001234567890"
            assert (
                notification_config.channels[1].slack_webhook_url
                == "https://hooks.slack.com/test"
            )

    def test_environment_variable_substitution_multiple_vars_in_string(self):
        """
        Why: Support complex configuration strings with multiple environment variables
        What: Tests that multiple ${VAR} references in a single string are
              all substituted
        How: Creates string with multiple env var references and verifies
             all are substituted
        """
        with patch.dict(
            os.environ, {"DB_HOST": "localhost", "DB_PORT": "5432", "DB_NAME": "testdb"}
        ):
            config = DatabaseConfig(
                url="postgresql://user:pass@${DB_HOST}:${DB_PORT}/${DB_NAME}"
            )
            assert config.url == "postgresql://user:pass@localhost:5432/testdb"


class TestFullConfigValidation:
    """Tests for complete Config model validation and cross-field dependencies."""

    def test_config_validates_default_llm_provider_exists(self):
        """
        Why: Ensure the default LLM provider is actually configured to
             prevent runtime errors
        What: Tests that default_llm_provider must exist in the llm
              configuration dictionary
        How: Creates config with mismatched default provider and verifies
             validation error
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "default_llm_provider": "openai",  # Not in llm config
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        with pytest.raises(
            ValueError,
            match="Default LLM provider 'openai' not found in llm configuration",
        ):
            Config(**config_data)

    def test_config_validates_repositories_not_empty(self):
        """
        Why: Ensure at least one repository is configured for the system to monitor
        What: Tests that repositories list cannot be empty
        How: Creates config with empty repositories list and verifies validation error
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [],  # Empty list
        }

        with pytest.raises(
            ValueError, match="At least one repository must be configured"
        ):
            Config(**config_data)

    def test_config_creates_successfully_with_valid_data(self):
        """
        Why: Verify that valid configuration data creates a working Config instance
        What: Tests successful creation of Config with all required fields properly set
        How: Creates complete valid config and verifies all fields are set correctly
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "default_llm_provider": "anthropic",
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        config = Config(**config_data)

        assert config.database.url == "sqlite:///:memory:"
        assert config.queue.url == "redis://localhost:6379/0"
        assert "anthropic" in config.llm
        assert config.default_llm_provider == "anthropic"
        assert len(config.repositories) == 1
        assert config.repositories[0].url == "https://github.com/test/repo"

    def test_config_validates_extra_fields_forbidden(self):
        """
        Why: Prevent typos and misconfiguration by rejecting unknown
             configuration fields
        What: Tests that extra fields not defined in the model are rejected
        How: Adds unknown field to config data and verifies validation error
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
            "unknown_field": "should_be_rejected",  # Extra field
        }

        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            Config(**config_data)

    def test_config_default_values_are_set(self):
        """
        Why: Ensure configuration provides sensible defaults for optional fields
        What: Tests that default values are properly set for optional
              configuration sections
        How: Creates minimal config and verifies default values for optional fields
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "ghp_test_token"}
            ],
        }

        config = Config(**config_data)

        # Test default values
        assert config.default_llm_provider == "anthropic"
        assert config.system.environment == "development"
        assert config.notification.enabled is True
        assert config.claude_code_sdk == {}  # Empty dict default
