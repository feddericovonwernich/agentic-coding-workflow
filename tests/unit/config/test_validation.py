"""Unit tests for configuration validation functionality.

This module tests the advanced configuration validation system including
runtime checks, dependency validation, and provider-specific validation.
"""

import importlib.util
import os
from unittest.mock import MagicMock, patch

import pytest

from src.config.exceptions import ConfigurationValidationError
from src.config.models import (
    Config,
    DatabaseConfig,
    LLMProvider,
    LLMProviderConfig,
    NotificationChannelConfig,
    NotificationConfig,
    NotificationProvider,
    QueueConfig,
    RepositoryConfig,
    SystemConfig,
)
from src.config.utils import create_minimal_config
from src.config.validation import ConfigurationValidator, validate_config


class TestConfigurationValidator:
    """Tests for ConfigurationValidator class functionality."""

    def test_configuration_validator_initialization(self):
        """
        Why: Ensure ConfigurationValidator initializes with proper state for validation
        What: Tests that validator initializes with empty error and warning lists
        How: Creates validator with config and verifies initial state
        """
        config = create_minimal_config()
        validator = ConfigurationValidator(config)

        assert validator.config is config
        assert validator.validation_errors == []
        assert validator.warnings == []

    def test_validate_all_returns_errors_and_warnings(self):
        """
        Why: Provide comprehensive validation results including both errors and warnings
        What: Tests that validate_all returns tuple of (errors, warnings) lists
        How: Runs validation on config and verifies return format and types
        """
        config = create_minimal_config()
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_validate_all_clears_previous_results(self):
        """
        Why: Ensure each validation run starts with clean state
        What: Tests that validate_all clears previous errors and warnings
        How: Runs validation twice and verifies second run doesn't accumulate errors
        """
        config = create_minimal_config()
        validator = ConfigurationValidator(config)

        # First validation run
        validator.validation_errors.append("fake error")
        validator.warnings.append("fake warning")

        # Second validation run should clear previous results
        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Results should only contain actual validation results, not fake ones
        assert "fake error" not in errors
        assert "fake warning" not in warnings


class TestSystemConfigValidation:
    """Tests for system configuration validation."""

    def test_system_config_validates_environment_warnings(self):
        """
        Why: Warn users about non-standard environment values that might indicate typos
        What: Tests that unknown environment values generate warnings
        How: Creates config with non-standard environment and verifies warning
        """
        config_data = {
            "system": {"environment": "unknown_env"},
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
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about unknown environment
        warning_found = any("Unknown environment" in warning for warning in warnings)
        assert warning_found

    def test_system_config_validates_timeout_warnings(self):
        """
        Why: Warn about potentially problematic timeout values that might cause issues
        What: Tests that very low or very high timeouts generate warnings
        How: Creates configs with extreme timeouts and verifies warnings
        """
        # Test very low timeout (at the warning threshold)
        low_timeout_config = SystemConfig(worker_timeout=30)  # At warning threshold
        config_data = {
            "system": low_timeout_config.model_dump(),
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
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about low timeout
        warning_found = any("very low" in warning for warning in warnings)
        assert warning_found

    def test_system_config_validates_circuit_breaker_warnings(self):
        """
        Why: Warn about circuit breaker settings that might cause premature failures
        What: Tests that low failure thresholds and high timeouts generate warnings
        How: Creates configs with problematic circuit breaker settings and
             verifies warnings
        """
        # Test low failure threshold
        system_config = SystemConfig(circuit_breaker_failure_threshold=2)
        config_data = {
            "system": system_config.model_dump(),
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
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about low threshold
        warning_found = any("premature failovers" in warning for warning in warnings)
        assert warning_found


class TestDatabaseConfigValidation:
    """Tests for database configuration validation."""

    def test_database_config_validates_postgresql_hostname(self):
        """
        Why: Ensure PostgreSQL connections have proper hostname configuration
        What: Tests that PostgreSQL URLs without hostnames generate errors
        How: Creates config with invalid PostgreSQL URL and verifies error
        """
        config_data = {
            "database": {"url": "postgresql:///missing_host"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate error about missing hostname
        error_found = any(
            "PostgreSQL URL missing hostname" in error for error in errors
        )
        assert error_found

    def test_database_config_validates_pool_size_warnings(self):
        """
        Why: Warn about database pool configurations that might cause resource issues
        What: Tests that large pool sizes and mismatched overflow settings
              generate warnings
        How: Creates configs with problematic pool settings and verifies warnings
        """
        # Test large pool size
        db_config = DatabaseConfig(url="sqlite:///:memory:", pool_size=60)
        config_data = {
            "database": db_config.model_dump(),
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about large pool size
        warning_found = any(
            "Large database pool size" in warning for warning in warnings
        )
        assert warning_found

    def test_database_config_validates_sqlite_directory_exists(self):
        """
        Why: Ensure SQLite database directories exist to prevent runtime errors
        What: Tests that SQLite URLs with non-existent directories generate errors
        How: Creates config with SQLite URL pointing to non-existent directory
        """
        config_data = {
            "database": {"url": "sqlite:///nonexistent/directory/db.sqlite"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate error about non-existent directory
        error_found = any("directory does not exist" in error for error in errors)
        assert error_found


class TestQueueConfigValidation:
    """Tests for queue configuration validation."""

    def test_queue_config_validates_redis_url_scheme(self):
        """
        Why: Ensure Redis queue provider URLs use correct scheme for connectivity
        What: Tests that non-redis:// URLs with redis provider generate errors
        How: Creates config with mismatched provider and URL scheme
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {
                "provider": "redis",
                "url": "http://localhost:6379/0",  # Wrong scheme for redis
            },
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate error about wrong URL scheme
        error_found = any(
            "Redis provider requires redis://" in error for error in errors
        )
        assert error_found

    def test_queue_config_validates_visibility_timeout_warnings(self):
        """
        Why: Warn about queue settings that might cause message processing issues
        What: Tests that short visibility timeouts and large batch sizes
              generate warnings
        How: Creates configs with problematic queue settings and verifies warnings
        """
        # Test short visibility timeout
        queue_config = QueueConfig(
            url="redis://localhost:6379/0",
            visibility_timeout=30,  # At minimum threshold
        )
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": queue_config.model_dump(),
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about short timeout
        warning_found = any(
            "Short queue visibility timeout" in warning for warning in warnings
        )
        assert warning_found


class TestLLMConfigValidation:
    """Tests for LLM provider configuration validation."""

    def test_llm_config_validates_missing_api_keys(self):
        """
        Why: Ensure all LLM providers have API keys to prevent authentication failures
        What: Tests that missing API keys generate validation errors
        How: Creates LLM config with empty API key and verifies error
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "valid-key",  # Start with valid key
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)

        # Manually set empty API key to test validation logic
        # (bypass Pydantic validation)
        object.__setattr__(config.llm["anthropic"], "api_key", "")

        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate error about missing API key
        error_found = any("missing API key" in error for error in errors)
        assert error_found

    def test_llm_config_validates_test_api_keys(self):
        """
        Why: Warn about test API keys that might not work in production
        What: Tests that test API keys generate warnings for production awareness
        How: Creates LLM config with test API key and verifies warning
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",  # Test API key
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about test API key
        warning_found = any("using test API key" in warning for warning in warnings)
        assert warning_found

    def test_llm_config_validates_high_token_limits(self):
        """
        Why: Warn about high token limits that might cause unexpected costs
        What: Tests that very high max_tokens values generate cost warnings
        How: Creates LLM config with high token limit and verifies warning
        """
        llm_config = LLMProviderConfig(
            provider=LLMProvider.ANTHROPIC,
            api_key="sk-ant-test",
            model="claude-3-sonnet-20240229",
            max_tokens=60000,  # High - above warning threshold
        )
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {"anthropic": llm_config.model_dump()},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about high token limit
        warning_found = any("very high max_tokens" in warning for warning in warnings)
        assert warning_found

    def test_llm_config_validates_missing_cost_tracking(self):
        """
        Why: Warn when cost tracking information is missing for budget monitoring
        What: Tests that missing cost information generates warnings
        How: Creates LLM config without cost fields and verifies warning
        """
        llm_config = LLMProviderConfig(
            provider=LLMProvider.ANTHROPIC,
            api_key="sk-ant-test",
            model="claude-3-sonnet-20240229",
            # cost fields omitted
        )
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {"anthropic": llm_config.model_dump()},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about missing cost information
        warning_found = any(
            "missing cost information" in warning for warning in warnings
        )
        assert warning_found


class TestNotificationConfigValidation:
    """Tests for notification configuration validation."""

    def test_notification_config_validates_missing_channels(self):
        """
        Why: Ensure notification system has at least one channel when enabled
        What: Tests that enabled notifications without channels generate errors
        How: Creates notification config with enabled=True but no channels
        """
        notification_config = NotificationConfig(
            enabled=True,
            channels=[],  # No channels configured
        )
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
            "notification": notification_config.model_dump(),
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate error about no channels
        error_found = any("no channels configured" in error for error in errors)
        assert error_found

    def test_notification_config_validates_telegram_credentials(self):
        """
        Why: Ensure Telegram channels have required credentials for message delivery
        What: Tests that Telegram channels without bot_token or chat_id generate errors
        How: Creates Telegram channel config with missing credentials
        """
        telegram_channel = NotificationChannelConfig(
            provider=NotificationProvider.TELEGRAM,
            # Missing telegram_bot_token and telegram_chat_id
        )
        notification_config = NotificationConfig(
            enabled=True, channels=[telegram_channel]
        )
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
            "notification": notification_config.model_dump(),
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate errors about missing Telegram credentials
        bot_token_error = any("missing bot_token" in error for error in errors)
        chat_id_error = any("missing chat_id" in error for error in errors)
        assert bot_token_error
        assert chat_id_error

    def test_notification_config_validates_rate_limit_warnings(self):
        """
        Why: Warn about notification rate limits that might be too high or too low
        What: Tests that extreme rate limit values generate warnings
        How: Creates notification configs with extreme rate limits and verifies warnings
        """
        # Test high rate limit
        notification_config = NotificationConfig(
            enabled=True,
            max_notifications_per_hour=80,  # High - triggers warning
            channels=[NotificationChannelConfig(provider=NotificationProvider.EMAIL)],
        )
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
            "notification": notification_config.model_dump(),
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about high rate limit
        warning_found = any(
            "High notification rate limit" in warning for warning in warnings
        )
        assert warning_found


class TestRepositoryConfigValidation:
    """Tests for repository configuration validation."""

    def test_repository_config_validates_github_urls(self):
        """
        Why: Ensure only GitHub repositories are configured since that's what
             the system supports
        What: Tests that non-GitHub URLs generate validation errors
        How: Creates repository config with non-GitHub URL and verifies error
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
            "notification": {"enabled": False},
            "repositories": [
                {
                    "url": "https://github.com/test/repo",
                    # Start with valid GitHub URL
                    "auth_token": "test-token",
                }
            ],
        }
        config = Config(**config_data)

        # Manually set non-GitHub URL to test validation logic
        # (bypass Pydantic validation)
        object.__setattr__(
            config.repositories[0], "url", "https://gitlab.com/test/repo"
        )

        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate error about non-GitHub URL
        error_found = any(
            "URL must be a GitHub repository" in error for error in errors
        )
        assert error_found

    def test_repository_config_validates_polling_interval_warnings(self):
        """
        Why: Warn about polling intervals that might hit rate limits or delay processing
        What: Tests that very frequent or infrequent polling generates warnings
        How: Creates repository configs with extreme polling intervals and
             verifies warnings
        """
        # Test very frequent polling
        repo_config = RepositoryConfig(
            url="https://github.com/test/repo",
            auth_token="test-token",
            polling_interval=60,  # Very frequent (minimum allowed)
        )
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
            "repositories": [repo_config.model_dump()],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about frequent polling
        warning_found = any("very frequent" in warning for warning in warnings)
        assert warning_found

    def test_repository_config_validates_test_tokens(self):
        """
        Why: Warn about test authentication tokens that won't work in production
        What: Tests that test tokens generate warnings for production awareness
        How: Creates repository config with test token and verifies warning
        """
        repo_config = RepositoryConfig(
            url="https://github.com/test/repo",
            auth_token="test-token",  # Test token
        )
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
            "repositories": [repo_config.model_dump()],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about test token
        warning_found = any("using test auth_token" in warning for warning in warnings)
        assert warning_found

    def test_repository_config_validates_no_fix_categories_enabled(self):
        """
        Why: Warn when no fix categories are enabled since the system won't fix anything
        What: Tests that repositories with all fix categories disabled generate warnings
        How: Creates repository config with all fix categories disabled and
             verifies warning
        """
        repo_config = RepositoryConfig(
            url="https://github.com/test/repo",
            auth_token="ghp_real_token",
            fix_categories={
                "lint": {"enabled": False},
                "test": {"enabled": False},
                "compilation": {"enabled": False},
            },
        )
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
            "repositories": [repo_config.model_dump()],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        errors, warnings = validator.validate_all(
            check_connectivity=False, check_dependencies=False, check_permissions=False
        )

        # Should generate warning about no fix categories enabled
        warning_found = any(
            "no fix categories enabled" in warning for warning in warnings
        )
        assert warning_found


class TestGlobalValidationFunction:
    """Tests for the global validate_config function."""

    def test_validate_config_with_valid_configuration(self):
        """
        Why: Verify that valid configurations pass validation without errors
        What: Tests that validate_config returns empty error list for valid config
        How: Creates valid config and verifies validation passes
        """
        config = create_minimal_config()

        errors, warnings = validate_config(
            config,
            check_connectivity=False,
            check_dependencies=False,
            check_permissions=False,
            raise_on_error=False,
        )

        # Valid config should have no errors
        assert len(errors) == 0

    def test_validate_config_raises_on_error_by_default(self):
        """
        Why: Provide fail-fast behavior by default when configuration is invalid
        What: Tests that validate_config raises exception by default when errors found
        How: Creates invalid config and verifies exception is raised
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "valid-key",  # Start with valid config
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)

        # Manually create validation error condition (bypass Pydantic validation)
        # Empty the LLM config to trigger validation error
        config.llm.clear()  # This will cause "at least one LLM provider" error

        with pytest.raises(
            ConfigurationValidationError, match="Configuration validation failed"
        ):
            validate_config(
                config,
                check_connectivity=False,
                check_dependencies=False,
                check_permissions=False,
                # raise_on_error defaults to True
            )

    def test_validate_config_returns_errors_when_raise_disabled(self):
        """
        Why: Allow collection of all validation errors for comprehensive reporting
        What: Tests that validate_config returns errors instead of raising
              when configured
        How: Creates invalid config with raise_on_error=False and verifies error return
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "valid-key",  # Start with valid config
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)

        # Manually create validation error condition (bypass Pydantic validation)
        config.llm.clear()  # This will cause "at least one LLM provider" error

        errors, warnings = validate_config(
            config,
            check_connectivity=False,
            check_dependencies=False,
            check_permissions=False,
            raise_on_error=False,
        )

        # Should return errors instead of raising
        assert len(errors) > 0
        error_found = any(
            "At least one LLM provider must be configured" in error for error in errors
        )
        assert error_found

    def test_validate_config_includes_warnings_in_exception_message(self):
        """
        Why: Provide comprehensive error information including warnings for debugging
        What: Tests that validation exceptions include both errors and
              warnings in message
        How: Creates config with both errors and warnings and verifies exception content
        """
        # Create config that will have both errors and warnings
        config_data = {
            "system": {"environment": "unknown_env"},  # Warning
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "valid-key",  # Start with valid config
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)

        # Manually create validation error condition (bypass Pydantic validation)
        config.llm.clear()  # This will cause "at least one LLM provider" error

        with pytest.raises(ConfigurationValidationError) as exc_info:
            validate_config(
                config,
                check_connectivity=False,
                check_dependencies=False,
                check_permissions=False,
            )

        exception_message = str(exc_info.value)

        # Exception should include both error and warning information
        assert "error(s)" in exception_message
        assert "Warning" in exception_message
        assert "At least one LLM provider must be configured" in exception_message
        assert "Unknown environment" in exception_message


class TestDependencyValidation:
    """Tests for dependency validation functionality."""

    def test_dependency_validation_detects_missing_yaml(self):
        """
        Why: Ensure required dependencies are available for configuration loading
        What: Tests that missing PyYAML dependency is detected during validation
        How: Mocks missing yaml module and verifies error detection
        """
        config = create_minimal_config()
        validator = ConfigurationValidator(config)

        # Mock missing yaml library - patch the function after it's imported
        original_find_spec = importlib.util.find_spec

        def mock_find_spec(name):
            if name == "yaml":
                return None
            return original_find_spec(name)

        with patch("importlib.util.find_spec", mock_find_spec):
            errors, warnings = validator.validate_all(
                check_connectivity=False,
                check_dependencies=True,
                check_permissions=False,
            )

        # Should detect missing PyYAML
        error_found = any(
            "PyYAML is required but not installed" in error for error in errors
        )
        assert error_found

    def test_dependency_validation_detects_missing_redis_for_redis_queue(self):
        """
        Why: Ensure Redis library is available when Redis queue provider is configured
        What: Tests that missing redis library is detected for Redis queue
              configurations
        How: Creates config with Redis queue and mocks missing redis library
        """
        config_data = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {
                "provider": "redis",  # Redis provider
                "url": "redis://localhost:6379/0",
            },
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "repositories": [
                {"url": "https://github.com/test/repo", "auth_token": "test-token"}
            ],
        }
        config = Config(**config_data)
        validator = ConfigurationValidator(config)

        # Mock missing redis library - patch the function after it's imported
        original_find_spec = importlib.util.find_spec

        def mock_find_spec(name):
            if name == "redis":
                return None
            return original_find_spec(name)

        with patch("importlib.util.find_spec", mock_find_spec):
            errors, warnings = validator.validate_all(
                check_connectivity=False,
                check_dependencies=True,
                check_permissions=False,
            )

        # Should detect missing redis library
        error_found = any(
            "redis library is required for Redis queue provider" in error
            for error in errors
        )
        assert error_found
