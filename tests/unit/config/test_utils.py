"""Unit tests for configuration utility functions.

This module tests utility functions for configuration management including
schema generation, validation helpers, and configuration manipulation utilities.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config.exceptions import ConfigurationError
from src.config.models import Config, DatabaseConfig, SystemConfig
from src.config.utils import (
    create_minimal_config,
    generate_example_config,
    generate_json_schema,
    get_config_summary,
    mask_sensitive_values,
    merge_configs,
    validate_environment_variables,
)


class TestSchemaGeneration:
    """Tests for JSON schema generation functionality."""

    def test_generate_json_schema_for_config_model(self):
        """
        Why: Enable external tooling integration by providing JSON Schema for validation
        What: Tests that generate_json_schema creates valid JSON Schema for Config model
        How: Generates schema for Config model and verifies it contains
             expected structure
        """
        schema = generate_json_schema(Config)

        assert isinstance(schema, dict)
        assert "title" in schema
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema

        # Verify key configuration sections are present
        properties = schema["properties"]
        assert "database" in properties
        assert "queue" in properties
        assert "llm" in properties
        assert "repositories" in properties
        assert "system" in properties

    def test_generate_json_schema_writes_to_file(self):
        """
        Why: Enable schema export for external validation tools and documentation
        What: Tests that schema generation can write JSON Schema to specified file
        How: Generates schema to temporary file and verifies file content matches
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            schema = generate_json_schema(Config, temp_path)

            # Verify file was written
            assert temp_path.exists()

            # Verify file contains valid JSON
            with open(temp_path) as f:
                file_schema = json.load(f)

            assert file_schema == schema
            assert isinstance(file_schema, dict)
        finally:
            temp_path.unlink()

    def test_generate_json_schema_creates_directory(self):
        """
        Why: Handle cases where output directory doesn't exist yet
        What: Tests that schema generation creates parent directories as needed
        How: Specifies output path in non-existent directory and verifies creation
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_path = Path(temp_dir) / "nested" / "dir" / "schema.json"

            schema = generate_json_schema(SystemConfig, nested_path)

            assert nested_path.exists()
            assert nested_path.parent.exists()

            with open(nested_path) as f:
                file_schema = json.load(f)

            assert file_schema == schema


class TestExampleConfigGeneration:
    """Tests for example configuration file generation."""

    def test_generate_example_config_basic(self):
        """
        Why: Provide users with complete example configuration for quick setup
        What: Tests that generate_example_config creates valid YAML configuration
        How: Generates example config and verifies it contains all required sections
        """
        example_yaml = generate_example_config()

        assert isinstance(example_yaml, str)
        assert "system:" in example_yaml
        assert "database:" in example_yaml
        assert "queue:" in example_yaml
        assert "llm:" in example_yaml
        assert "notification:" in example_yaml
        assert "repositories:" in example_yaml

    def test_generate_example_config_with_comments(self):
        """
        Why: Provide user-friendly configuration with explanatory comments
        What: Tests that include_comments=True adds helpful comments to YAML
        How: Generates config with comments and verifies comment presence
        """
        example_yaml = generate_example_config(include_comments=True)

        # Verify comments are present
        assert "# Core system configuration" in example_yaml
        assert "# Database connection settings" in example_yaml
        assert "# Message queue configuration" in example_yaml
        assert "# LLM provider configurations" in example_yaml
        assert "# Notification system settings" in example_yaml
        assert "# Repository monitoring configuration" in example_yaml

    def test_generate_example_config_without_comments(self):
        """
        Why: Generate clean configuration files without comments for production use
        What: Tests that include_comments=False produces comment-free YAML
        How: Generates config without comments and verifies no comments present
        """
        example_yaml = generate_example_config(include_comments=False)

        # Verify no comments are present
        assert "# Core system configuration" not in example_yaml
        assert "# Database connection settings" not in example_yaml

    def test_generate_example_config_with_sensitive_placeholders(self):
        """
        Why: Provide secure defaults that require environment variable configuration
        What: Tests that sensitive placeholders use ${VAR_NAME} format for security
        How: Generates config with placeholders and verifies environment variable format
        """
        example_yaml = generate_example_config(include_sensitive_placeholders=True)

        # Verify environment variable placeholders
        assert "${DATABASE_URL}" in example_yaml
        assert "${ANTHROPIC_API_KEY}" in example_yaml
        assert "${GITHUB_TOKEN}" in example_yaml
        assert "${TELEGRAM_BOT_TOKEN}" in example_yaml

    def test_generate_example_config_without_sensitive_placeholders(self):
        """
        Why: Generate example configuration with sample values for testing
        What: Tests that placeholder=False uses example values instead of env vars
        How: Generates config without placeholders and verifies sample values
        """
        example_yaml = generate_example_config(include_sensitive_placeholders=False)

        # Verify sample values instead of placeholders
        assert "sk-ant-..." in example_yaml
        assert "ghp_..." in example_yaml
        assert "postgresql://user:pass@localhost/db" in example_yaml

    def test_generate_example_config_writes_to_file(self):
        """
        Why: Enable saving example configuration to file for user convenience
        What: Tests that example config can be written to specified file path
        How: Generates example to temporary file and verifies file content
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)

        try:
            example_yaml = generate_example_config(output_path=temp_path)

            # Verify file was written
            assert temp_path.exists()

            # Verify file content matches returned string
            with open(temp_path) as f:
                file_content = f.read()

            assert file_content == example_yaml
        finally:
            temp_path.unlink()


class TestEnvironmentVariableValidation:
    """Tests for environment variable validation utilities."""

    def test_validate_environment_variables_all_present(self):
        """
        Why: Verify that configuration with all required environment variables is valid
        What: Tests that validate_environment_variables returns empty list
              when all vars set
        How: Creates config with env var placeholders and verifies no missing vars
        """
        # Mock environment variables before creating config
        with patch.dict(
            "os.environ",
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "GITHUB_TOKEN": "ghp_test_token",
            },
        ):
            config = create_minimal_config(
                database_url="${DATABASE_URL}",
                github_token="${GITHUB_TOKEN}",
                repo_url="https://github.com/test/repo",
            )
            missing_vars = validate_environment_variables(config)
            assert missing_vars == []

    def test_validate_environment_variables_missing_database_url(self):
        """
        Why: Detect when critical database configuration is missing from environment
        What: Tests that missing DATABASE_URL is detected in configuration
        How: Creates config with database URL placeholder and verifies detection
        """
        # Clear environment variables and create config with placeholder
        with patch.dict("os.environ", {}, clear=True):
            config_dict = {
                "database": {"url": "sqlite:///:memory:"},  # Start with valid config
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
                    {"url": "https://github.com/test/repo", "auth_token": "test-token"}
                ],
            }
            config = Config(**config_dict)

            # Manually inject placeholder to test the utility function
            # (bypass validation)
            object.__setattr__(config.database, "url", "${DATABASE_URL}")

            missing_vars = validate_environment_variables(config)
            assert "DATABASE_URL" in missing_vars

    def test_validate_environment_variables_missing_llm_keys(self):
        """
        Why: Ensure LLM provider API keys are properly configured via environment
        What: Tests that missing LLM API keys are detected in configuration
        How: Creates config with LLM key placeholders and verifies detection
        """
        # Clear environment variables and create config
        with patch.dict("os.environ", {}, clear=True):
            config_dict = {
                "database": {"url": "sqlite:///:memory:"},
                "queue": {"url": "redis://localhost:6379/0"},
                "llm": {
                    "anthropic": {
                        "provider": "anthropic",
                        "api_key": "test-key",  # Start with valid key
                        "model": "claude-3-sonnet-20240229",
                    },
                    "openai": {
                        "provider": "openai",
                        "api_key": "test-key",  # Start with valid key
                        "model": "gpt-4",
                    },
                },
                "notification": {"enabled": False},
                "repositories": [
                    {"url": "https://github.com/test/repo", "auth_token": "test-token"}
                ],
            }
            config = Config(**config_dict)

            # Manually inject placeholders to test the utility function
            # (bypass validation)
            object.__setattr__(
                config.llm["anthropic"], "api_key", "${ANTHROPIC_API_KEY}"
            )
            object.__setattr__(config.llm["openai"], "api_key", "${OPENAI_API_KEY}")

            missing_vars = validate_environment_variables(config)
            assert "ANTHROPIC_API_KEY" in missing_vars
            assert "OPENAI_API_KEY" in missing_vars

    def test_validate_environment_variables_missing_notification_credentials(self):
        """
        Why: Ensure notification channels have required credentials configured
        What: Tests that missing notification provider credentials are detected
        How: Creates config with notification placeholders and verifies detection
        """
        from src.config.models import NotificationChannelConfig, NotificationProvider

        # Clear environment variables and create config
        with patch.dict("os.environ", {}, clear=True):
            config_dict = {
                "database": {"url": "sqlite:///:memory:"},
                "queue": {"url": "redis://localhost:6379/0"},
                "llm": {
                    "anthropic": {
                        "provider": "anthropic",
                        "api_key": "test-key",
                        "model": "claude-3-sonnet-20240229",
                    }
                },
                "notification": {
                    "enabled": True,
                    "channels": [
                        NotificationChannelConfig(
                            provider=NotificationProvider.TELEGRAM,
                            telegram_bot_token="test-token",
                            telegram_chat_id="test-chat",
                        ),
                        NotificationChannelConfig(
                            provider=NotificationProvider.SLACK,
                            slack_webhook_url="https://test.slack.com/webhook",
                        ),
                    ],
                },
                "repositories": [
                    {"url": "https://github.com/test/repo", "auth_token": "test-token"}
                ],
            }
            config = Config(**config_dict)

            # Manually inject placeholders to test the utility function
            # (bypass validation)
            object.__setattr__(
                config.notification.channels[0],
                "telegram_bot_token",
                "${TELEGRAM_BOT_TOKEN}",
            )
            object.__setattr__(
                config.notification.channels[0],
                "telegram_chat_id",
                "${TELEGRAM_CHAT_ID}",
            )
            object.__setattr__(
                config.notification.channels[1],
                "slack_webhook_url",
                "${SLACK_WEBHOOK_URL}",
            )

            missing_vars = validate_environment_variables(config)
            assert "TELEGRAM_BOT_TOKEN" in missing_vars
            assert "TELEGRAM_CHAT_ID" in missing_vars
            assert "SLACK_WEBHOOK_URL" in missing_vars

    def test_validate_environment_variables_ignores_non_placeholder_values(self):
        """
        Why: Only validate actual environment variable placeholders, not literal values
        What: Tests that literal values (non-${} format) are ignored during validation
        How: Creates config with mix of placeholders and literals, verifies
             only placeholders checked
        """
        # Clear environment and create config with a placeholder that has a default
        # The default will be used, but we can modify the config afterward to test
        with patch.dict("os.environ", {}, clear=True):
            config_data = {
                "database": {"url": "sqlite:///:memory:"},  # Literal value
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
                        "auth_token": "${GITHUB_TOKEN:default-token}",
                        # Placeholder with default
                    }
                ],
            }
            config = Config(**config_data)

            # Manually inject placeholder to test the utility function
            # (bypass validation)
            object.__setattr__(config.repositories[0], "auth_token", "${GITHUB_TOKEN}")

            missing_vars = validate_environment_variables(config)
            # Should only detect GITHUB_TOKEN since database_url is literal
            assert missing_vars == ["GITHUB_TOKEN"]


class TestSensitiveValueMasking:
    """Tests for sensitive data masking functionality."""

    def test_mask_sensitive_values_basic(self):
        """
        Why: Protect sensitive configuration data when logging or displaying config
        What: Tests that sensitive fields are masked while preserving structure
        How: Creates config dict with sensitive values and verifies masking
        """
        config_dict = {
            "database": {
                "url": "postgresql://user:password@localhost/db",
                "pool_size": 10,
            },
            "llm": {
                "anthropic": {
                    "api_key": "sk-ant-very-secret-key",
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {
                "channels": [
                    {
                        "provider": "telegram",
                        "telegram_bot_token": "123456:ABC-DEF-SECRET",
                        "telegram_chat_id": "-1001234567890",
                    }
                ]
            },
        }

        masked = mask_sensitive_values(config_dict)

        # Verify sensitive values are masked
        assert masked["llm"]["anthropic"]["api_key"] == "********..."
        assert (
            masked["notification"]["channels"][0]["telegram_bot_token"] == "********..."
        )

        # Verify non-sensitive values are preserved
        assert masked["database"]["pool_size"] == 10
        assert masked["llm"]["anthropic"]["model"] == "claude-3-sonnet-20240229"
        assert (
            masked["notification"]["channels"][0]["telegram_chat_id"]
            == "-1001234567890"
        )

    def test_mask_sensitive_values_preserves_environment_placeholders(self):
        """
        Why: Don't mask environment variable placeholders since they're not
             actual secrets
        What: Tests that ${VAR_NAME} placeholders are preserved during masking
        How: Creates config with env var placeholders and verifies they're not masked
        """
        config_dict = {
            "database": {"url": "${DATABASE_URL}"},
            "llm": {
                "anthropic": {
                    "api_key": "${ANTHROPIC_API_KEY}",
                    "model": "claude-3-sonnet-20240229",
                }
            },
        }

        masked = mask_sensitive_values(config_dict)

        # Environment variable placeholders should not be masked
        assert masked["database"]["url"] == "${DATABASE_URL}"
        assert masked["llm"]["anthropic"]["api_key"] == "${ANTHROPIC_API_KEY}"

    def test_mask_sensitive_values_handles_nested_structures(self):
        """
        Why: Ensure masking works correctly in deeply nested configuration structures
        What: Tests that sensitive fields are found and masked at any nesting level
        How: Creates deeply nested config with sensitive values and verifies masking
        """
        config_dict = {
            "services": {
                "authentication": {
                    "providers": {
                        "oauth": {
                            "client_secret": "very-secret-oauth-key",
                            "client_id": "public-client-id",
                        }
                    }
                }
            }
        }

        masked = mask_sensitive_values(config_dict)

        # Verify nested sensitive value is masked
        assert (
            masked["services"]["authentication"]["providers"]["oauth"]["client_secret"]
            == "********..."
        )
        # Verify non-sensitive nested value is preserved
        assert (
            masked["services"]["authentication"]["providers"]["oauth"]["client_id"]
            == "public-client-id"
        )

    def test_mask_sensitive_values_handles_empty_values(self):
        """
        Why: Handle edge cases with empty or None sensitive field values gracefully
        What: Tests that empty sensitive fields don't cause errors during masking
        How: Creates config with empty sensitive fields and verifies no errors
        """
        config_dict = {
            "api_key": "",
            "auth_token": None,
            "password": "   ",  # Whitespace only
            "normal_field": "normal_value",
        }

        masked = mask_sensitive_values(config_dict)

        # Empty values should remain empty (not masked)
        assert masked["api_key"] == ""
        assert masked["auth_token"] is None
        assert masked["password"] == "   "
        assert masked["normal_field"] == "normal_value"


class TestConfigurationSummary:
    """Tests for configuration summary generation."""

    def test_get_config_summary_basic(self):
        """
        Why: Provide overview of configuration for monitoring and debugging
        What: Tests that get_config_summary creates comprehensive configuration overview
        How: Creates config and verifies summary contains expected sections and values
        """
        config = create_minimal_config()
        summary = get_config_summary(config)

        assert isinstance(summary, dict)

        # Verify main sections are present
        assert "system" in summary
        assert "database" in summary
        assert "queue" in summary
        assert "llm" in summary
        assert "notification" in summary
        assert "repositories" in summary

        # Verify system summary
        assert summary["system"]["environment"] == "development"
        assert summary["system"]["log_level"] == "INFO"

        # Verify database summary
        assert summary["database"]["provider"] == "sqlite"

        # Verify LLM summary
        assert "anthropic" in summary["llm"]["providers"]
        assert summary["llm"]["default_provider"] == "anthropic"

    def test_get_config_summary_counts_resources(self):
        """
        Why: Provide quantitative overview of configured resources for capacity planning
        What: Tests that summary includes counts of repositories, channels, providers
        How: Creates config with multiple resources and verifies counts in summary
        """
        from src.config.models import NotificationChannelConfig, NotificationProvider

        config_dict = {
            "database": {"url": "sqlite:///:memory:"},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": "test-key-1",
                    "model": "claude-3-sonnet-20240229",
                },
                "openai": {
                    "provider": "openai",
                    "api_key": "test-key-2",
                    "model": "gpt-4",
                },
            },
            "notification": {
                "enabled": True,
                "channels": [
                    NotificationChannelConfig(provider=NotificationProvider.TELEGRAM),
                    NotificationChannelConfig(provider=NotificationProvider.SLACK),
                    NotificationChannelConfig(provider=NotificationProvider.EMAIL),
                ],
            },
            "repositories": [
                {
                    "url": "https://github.com/test/repo1",
                    "auth_token": "token1",
                    "is_critical": True,
                },
                {
                    "url": "https://github.com/test/repo2",
                    "auth_token": "token2",
                    "is_critical": False,
                },
                {
                    "url": "https://github.com/test/repo3",
                    "auth_token": "token3",
                    "is_critical": True,
                },
            ],
        }
        config = Config(**config_dict)
        summary = get_config_summary(config)

        # Verify resource counts
        assert summary["llm"]["provider_count"] == 2
        assert summary["notification"]["channel_count"] == 3
        assert summary["repositories"]["count"] == 3
        assert summary["repositories"]["critical_count"] == 2

    def test_get_config_summary_masks_sensitive_info(self):
        """
        Why: Ensure summary doesn't expose sensitive configuration details
        What: Tests that summary contains no sensitive values like API keys or tokens
        How: Creates config with sensitive values and verifies they're not in summary
        """
        config = create_minimal_config(github_token="ghp_very_secret_token")
        summary = get_config_summary(config)

        # Convert summary to string to check for sensitive values
        summary_str = str(summary)

        # Verify no sensitive values are in summary
        assert "ghp_very_secret_token" not in summary_str
        assert "test-key" not in summary_str  # LLM API key

        # But verify non-sensitive info is present
        assert "development" in summary_str
        assert "anthropic" in summary_str


class TestMinimalConfigCreation:
    """Tests for minimal configuration creation utility."""

    def test_create_minimal_config_default_parameters(self):
        """
        Why: Provide working default configuration for development and testing
        What: Tests that create_minimal_config produces valid Config with defaults
        How: Creates minimal config with no parameters and verifies it's valid
        """
        config = create_minimal_config()

        assert isinstance(config, Config)
        assert config.database.url == "sqlite:///./test.db"
        assert config.queue.url == "redis://localhost:6379/0"
        assert len(config.repositories) == 1
        assert config.repositories[0].url == "https://github.com/example/repo"
        assert config.repositories[0].auth_token == "ghp_test_token_placeholder"

    def test_create_minimal_config_custom_parameters(self):
        """
        Why: Allow customization of minimal config for specific testing scenarios
        What: Tests that create_minimal_config accepts custom parameter values
        How: Creates minimal config with custom values and verifies they're used
        """
        custom_config = create_minimal_config(
            database_url="postgresql://test:pass@localhost/testdb",
            github_token="ghp_custom_token",
            repo_url="https://github.com/custom/repo",
        )

        assert custom_config.database.url == "postgresql://test:pass@localhost/testdb"
        assert custom_config.repositories[0].auth_token == "ghp_custom_token"
        assert custom_config.repositories[0].url == "https://github.com/custom/repo"

    def test_create_minimal_config_handles_invalid_data(self):
        """
        Why: Provide clear error when invalid parameters are passed to minimal config
        What: Tests that invalid configuration data raises ConfigurationError
        How: Passes invalid parameters and verifies appropriate error is raised
        """
        with pytest.raises(
            ConfigurationError, match="Failed to create minimal configuration"
        ):
            create_minimal_config(
                database_url="invalid://url/scheme",  # Invalid database URL
                github_token="valid_token",
                repo_url="https://github.com/test/repo",
            )


class TestConfigMerging:
    """Tests for configuration merging functionality."""

    def test_merge_configs_basic(self):
        """
        Why: Enable configuration composition from multiple sources
        What: Tests that merge_configs combines multiple configuration dictionaries
        How: Creates two config dicts and verifies they merge correctly
        """
        base_config = {
            "database": {"url": "sqlite:///:memory:", "pool_size": 5},
            "system": {"environment": "development", "debug_mode": False},
        }

        override_config = {
            "database": {"pool_size": 10},  # Override pool_size
            "queue": {"url": "redis://localhost:6379/0"},  # New section
        }

        merged = merge_configs(base_config, override_config)

        # Verify merge behavior
        assert merged["database"]["url"] == "sqlite:///:memory:"  # Preserved from base
        assert merged["database"]["pool_size"] == 10  # Overridden
        assert merged["system"]["environment"] == "development"  # Preserved from base
        assert (
            merged["queue"]["url"] == "redis://localhost:6379/0"
        )  # Added from override

    def test_merge_configs_deep_nesting(self):
        """
        Why: Support merging of deeply nested configuration structures
        What: Tests that merge_configs handles deep nesting correctly without
              overwriting siblings
        How: Creates configs with deep nesting and verifies proper deep merge behavior
        """
        base_config = {
            "services": {
                "llm": {
                    "anthropic": {"api_key": "base_key", "model": "base_model"},
                    "openai": {"api_key": "openai_key"},
                }
            }
        }

        override_config = {
            "services": {
                "llm": {
                    "anthropic": {"model": "new_model"},  # Override model, keep api_key
                    "gemini": {"api_key": "gemini_key"},  # Add new provider
                }
            }
        }

        merged = merge_configs(base_config, override_config)

        # Verify deep merge preserves and overrides correctly
        assert (
            merged["services"]["llm"]["anthropic"]["api_key"] == "base_key"
        )  # Preserved
        assert (
            merged["services"]["llm"]["anthropic"]["model"] == "new_model"
        )  # Overridden
        assert (
            merged["services"]["llm"]["openai"]["api_key"] == "openai_key"
        )  # Preserved
        assert merged["services"]["llm"]["gemini"]["api_key"] == "gemini_key"  # Added

    def test_merge_configs_multiple_sources(self):
        """
        Why: Support configuration composition from many sources
             (base, env-specific, local overrides)
        What: Tests that merge_configs can handle multiple configuration dictionaries
        How: Creates three config dicts and verifies proper precedence order
        """
        base_config = {"setting": "base", "base_only": "base_value"}
        env_config = {"setting": "env", "env_only": "env_value"}
        local_config = {"setting": "local", "local_only": "local_value"}

        merged = merge_configs(base_config, env_config, local_config)

        # Verify last config wins for conflicts
        assert merged["setting"] == "local"
        # Verify unique settings are preserved
        assert merged["base_only"] == "base_value"
        assert merged["env_only"] == "env_value"
        assert merged["local_only"] == "local_value"

    def test_merge_configs_empty_input(self):
        """
        Why: Handle edge case of empty configuration input gracefully
        What: Tests that merge_configs handles empty input correctly
        How: Calls merge_configs with no arguments and empty dict, verifies results
        """
        # No arguments
        merged = merge_configs()
        assert merged == {}

        # Empty dictionaries
        merged = merge_configs({}, {})
        assert merged == {}

        # One empty, one with data
        config = {"key": "value"}
        merged = merge_configs({}, config)
        assert merged == config

    def test_merge_configs_preserves_original(self):
        """
        Why: Ensure merge operation doesn't modify original configuration dictionaries
        What: Tests that merge_configs creates new dict without modifying inputs
        How: Creates configs, merges them, and verifies originals are unchanged
        """
        original_config = {"database": {"pool_size": 5}}
        override_config = {"database": {"pool_size": 10}}

        merged = merge_configs(original_config, override_config)

        # Verify original is unchanged
        assert original_config["database"]["pool_size"] == 5
        assert override_config["database"]["pool_size"] == 10
        # Verify merged has override value
        assert merged["database"]["pool_size"] == 10
