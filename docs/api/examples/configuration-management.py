#!/usr/bin/env python3
"""
Configuration Management Examples

This module demonstrates comprehensive usage of the configuration management
system, including loading, validation, environment substitution, and hot reload.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from src.config.cache import ConfigurationCache
from src.config.exceptions import (
    ConfigurationNotFoundError,
    ConfigurationValidationError,
    EnvironmentVariableError,
)
from src.config.loader import load_config
from src.config.manager import ConfigurationManager
from src.config.models import (
    AnthropicConfig,
    Config,
    DatabaseConfig,
    GitHubConfig,
    LLMConfig,
    NotificationChannelConfig,
    NotificationConfig,
)
from src.config.utils import (
    generate_example_config,
    get_config_summary,
    mask_sensitive_values,
    validate_environment_variables,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfigurationExamples:
    """Examples of configuration management patterns."""

    def __init__(self):
        """Initialize configuration examples."""
        self.temp_dir = Path(tempfile.mkdtemp())
        logger.info(f"Using temporary directory: {self.temp_dir}")

    def create_example_config(self) -> Path:
        """Create example configuration file."""
        config_content = """
# Example Configuration
system:
  log_level: INFO
  environment: development
  worker_timeout: 120

database:
  url: "${DATABASE_URL:sqlite:///./example.db}"
  pool_size: "${DB_POOL_SIZE:10}"
  echo: false

github:
  token: "${GITHUB_TOKEN}"
  base_url: "https://api.github.com"
  timeout: 30
  max_retries: 3

llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: claude-3-sonnet-20240229
    max_tokens: 4000
    temperature: 0.1

default_llm_provider: anthropic

notification:
  enabled: true
  channels:
    - provider: telegram
      enabled: true
      telegram_bot_token: "${TELEGRAM_BOT_TOKEN}"
      telegram_chat_id: "${TELEGRAM_CHAT_ID}"

    - provider: slack
      enabled: false
      slack_webhook_url: "${SLACK_WEBHOOK_URL}"
      slack_channel: "#alerts"
"""
        config_path = self.temp_dir / "config.yaml"
        config_path.write_text(config_content.strip())
        return config_path

    async def example_basic_loading(self):
        """Example: Basic configuration loading."""
        logger.info("=== Basic Configuration Loading ===")

        # Create example config
        config_path = self.create_example_config()

        try:
            # Load configuration
            config = load_config(str(config_path))

            logger.info("Configuration loaded successfully!")
            logger.info(f"Environment: {config.system.environment}")
            logger.info(f"Database URL: {config.database.url}")
            logger.info(f"GitHub token set: {'Yes' if config.github.token else 'No'}")
            logger.info(f"Default LLM provider: {config.default_llm_provider}")

            # Access nested configuration
            if config.llm.anthropic:
                logger.info(f"Anthropic model: {config.llm.anthropic.model}")

        except ConfigurationNotFoundError:
            logger.error("Configuration file not found")
        except ConfigurationValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

    async def example_environment_variables(self):
        """Example: Environment variable handling."""
        logger.info("=== Environment Variable Handling ===")

        # Set some environment variables
        os.environ.update(
            {
                "DATABASE_URL": "postgresql://user:pass@localhost/testdb",
                "GITHUB_TOKEN": "ghp_example_token_12345",
                "ANTHROPIC_API_KEY": "sk-ant-example-key",
                "DB_POOL_SIZE": "20",
                "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF",
                "TELEGRAM_CHAT_ID": "987654321",
            }
        )

        config_path = self.create_example_config()

        try:
            # Load with environment substitution
            config = load_config(str(config_path))

            logger.info("Environment variables resolved:")
            logger.info(f"Database URL: {config.database.url}")
            logger.info(f"Database pool size: {config.database.pool_size}")
            logger.info(f"GitHub token: {config.github.token[:10]}...")

            # Demonstrate validation
            required_vars = ["GITHUB_TOKEN", "ANTHROPIC_API_KEY", "DATABASE_URL"]

            missing_vars = validate_environment_variables(required_vars)
            if missing_vars:
                logger.warning(f"Missing environment variables: {missing_vars}")
            else:
                logger.info("All required environment variables are set")

        except EnvironmentVariableError as e:
            logger.error(f"Environment variable error: {e}")
        except Exception as e:
            logger.error(f"Error with environment variables: {e}")

    async def example_configuration_validation(self):
        """Example: Configuration validation and error handling."""
        logger.info("=== Configuration Validation ===")

        # Create invalid configuration
        invalid_config = """
system:
  log_level: INVALID_LEVEL
  worker_timeout: -1

database:
  url: "invalid_url"
  pool_size: "not_a_number"

github:
  timeout: "invalid_timeout"

llm:
  anthropic:
    provider: anthropic
    temperature: 5.0  # Invalid temperature > 2.0
"""

        invalid_config_path = self.temp_dir / "invalid_config.yaml"
        invalid_config_path.write_text(invalid_config.strip())

        try:
            # Attempt to load invalid configuration
            load_config(str(invalid_config_path))
            logger.warning("Invalid configuration was loaded (unexpected)")

        except ConfigurationValidationError as e:
            logger.info("Configuration validation caught errors (expected):")
            for i, error in enumerate(e.errors[:3], 1):  # Show first 3 errors
                logger.info(f"  {i}. {error['loc']}: {error['msg']}")

            if len(e.errors) > 3:
                logger.info(f"  ... and {len(e.errors) - 3} more errors")

        # Example: Custom validation
        try:
            # Create configuration with custom validation
            DatabaseConfig(
                url="postgresql://user:pass@localhost/db", pool_size=20, echo=False
            )
            logger.info("Custom configuration validation passed")

        except Exception as e:
            logger.error(f"Custom validation failed: {e}")

    async def example_configuration_utilities(self):
        """Example: Configuration utilities and helpers."""
        logger.info("=== Configuration Utilities ===")

        config_path = self.create_example_config()

        # Set environment variables for complete config
        os.environ.update(
            {
                "DATABASE_URL": "postgresql://user:pass@localhost/db",
                "GITHUB_TOKEN": "ghp_secret_token_123",
                "ANTHROPIC_API_KEY": "sk-ant-secret-key",
                "TELEGRAM_BOT_TOKEN": "bot_secret_token",
                "TELEGRAM_CHAT_ID": "123456789",
            }
        )

        try:
            config = load_config(str(config_path))

            # Generate configuration summary
            summary = get_config_summary(config)
            logger.info("Configuration Summary:")
            logger.info(summary)

            # Mask sensitive values for logging
            safe_config = mask_sensitive_values(config)
            logger.info("\nMasked configuration (safe for logging):")
            logger.info(f"Database URL: {safe_config.database.url}")
            logger.info(f"GitHub token: {safe_config.github.token}")
            logger.info(f"Anthropic API key: {safe_config.llm.anthropic.api_key}")

            # Generate example configuration
            example_yaml = generate_example_config(include_comments=True)
            example_path = self.temp_dir / "generated_example.yaml"
            example_path.write_text(example_yaml)
            logger.info(f"\nGenerated example config saved to: {example_path}")

        except Exception as e:
            logger.error(f"Error with configuration utilities: {e}")

    async def example_hot_reload(self):
        """Example: Hot reload functionality."""
        logger.info("=== Hot Reload Example ===")

        config_path = self.create_example_config()

        try:
            # Create configuration manager with hot reload
            manager = ConfigurationManager(
                config_file=str(config_path),
                hot_reload=True,
                reload_interval=1,  # Check every second for demo
            )

            # Register reload callback
            reload_count = 0

            async def on_config_change(old_config, new_config):
                nonlocal reload_count
                reload_count += 1
                logger.info(f"Configuration reloaded! (#{reload_count})")
                logger.info(f"Old environment: {old_config.system.environment}")
                logger.info(f"New environment: {new_config.system.environment}")

            manager.register_reload_callback(on_config_change)

            # Start hot reload monitoring
            await manager.start()

            # Get initial configuration
            config = manager.get_config()
            logger.info(f"Initial environment: {config.system.environment}")

            # Simulate configuration change
            logger.info("Simulating configuration change...")
            await asyncio.sleep(2)

            # Modify configuration file
            modified_content = config_path.read_text().replace(
                "environment: development", "environment: staging"
            )
            config_path.write_text(modified_content)

            # Wait for reload to be detected
            await asyncio.sleep(3)

            # Check updated configuration
            updated_config = manager.get_config()
            logger.info(f"Updated environment: {updated_config.system.environment}")

            # Stop monitoring
            await manager.stop()

        except Exception as e:
            logger.error(f"Error with hot reload: {e}")

    async def example_configuration_caching(self):
        """Example: Configuration caching for performance."""
        logger.info("=== Configuration Caching ===")

        config_path = self.create_example_config()

        try:
            # Configure caching
            cache = ConfigurationCache(
                enabled=True,
                ttl=300,  # 5 minutes
                max_size=10,
                invalidate_on_change=True,
            )

            # Load configuration with caching
            start_time = asyncio.get_event_loop().time()
            config1 = load_config(str(config_path), cache=cache)
            first_load_time = asyncio.get_event_loop().time() - start_time

            # Load again (should be cached)
            start_time = asyncio.get_event_loop().time()
            config2 = load_config(str(config_path), cache=cache)
            cached_load_time = asyncio.get_event_loop().time() - start_time

            logger.info(f"First load time: {first_load_time:.4f}s")
            logger.info(f"Cached load time: {cached_load_time:.4f}s")
            logger.info(f"Cache hit ratio: {cache.get_hit_ratio():.2%}")

            # Verify configurations are identical
            assert config1.system.environment == config2.system.environment
            logger.info("Cached configuration matches original")

        except Exception as e:
            logger.error(f"Error with configuration caching: {e}")

    async def example_programmatic_configuration(self):
        """Example: Creating configuration programmatically."""
        logger.info("=== Programmatic Configuration ===")

        try:
            # Create configuration objects directly
            database_config = DatabaseConfig(
                url="postgresql://user:pass@localhost:5432/mydb",
                pool_size=25,
                max_overflow=40,
                pool_timeout=20,
                echo=False,
            )

            github_config = GitHubConfig(
                token="ghp_programmatic_token",
                base_url="https://api.github.com",
                timeout=30,
                max_retries=3,
                rate_limit_buffer=100,
            )

            anthropic_config = AnthropicConfig(
                provider="anthropic",
                api_key="sk-ant-programmatic-key",
                model="claude-3-sonnet-20240229",
                max_tokens=4000,
                temperature=0.1,
            )

            llm_config = LLMConfig(anthropic=anthropic_config)

            # Create notification channel
            telegram_channel = NotificationChannelConfig(
                provider="telegram",
                enabled=True,
                telegram_bot_token="bot_token",
                telegram_chat_id="chat_id",
            )

            notification_config = NotificationConfig(
                enabled=True, channels=[telegram_channel]
            )

            # Combine into full configuration
            config = Config(
                database=database_config,
                github=github_config,
                llm=llm_config,
                notification=notification_config,
                default_llm_provider="anthropic",
            )

            logger.info("Programmatic configuration created successfully!")
            logger.info(f"Database pool size: {config.database.pool_size}")
            logger.info(f"GitHub timeout: {config.github.timeout}")
            logger.info(f"LLM model: {config.llm.anthropic.model}")
            logger.info(f"Notification channels: {len(config.notification.channels)}")

        except Exception as e:
            logger.error(f"Error creating programmatic configuration: {e}")

    async def example_configuration_comparison(self):
        """Example: Compare different configurations."""
        logger.info("=== Configuration Comparison ===")

        # Create two different configurations
        config1_content = """
system:
  environment: development
  log_level: DEBUG

database:
  pool_size: 10
  echo: true

github:
  timeout: 30
"""

        config2_content = """
system:
  environment: production
  log_level: INFO

database:
  pool_size: 20
  echo: false

github:
  timeout: 60
  max_retries: 5
"""

        config1_path = self.temp_dir / "config1.yaml"
        config2_path = self.temp_dir / "config2.yaml"

        config1_path.write_text(config1_content.strip())
        config2_path.write_text(config2_content.strip())

        try:
            config1 = load_config(str(config1_path))
            config2 = load_config(str(config2_path))

            # Compare configurations
            differences = []

            if config1.system.environment != config2.system.environment:
                differences.append(
                    f"Environment: {config1.system.environment} -> "
                    f"{config2.system.environment}"
                )

            if config1.system.log_level != config2.system.log_level:
                differences.append(
                    f"Log level: {config1.system.log_level} -> "
                    f"{config2.system.log_level}"
                )

            if config1.database.pool_size != config2.database.pool_size:
                differences.append(
                    f"Pool size: {config1.database.pool_size} -> "
                    f"{config2.database.pool_size}"
                )

            if config1.database.echo != config2.database.echo:
                differences.append(
                    f"Database echo: {config1.database.echo} -> {config2.database.echo}"
                )

            if config1.github.timeout != config2.github.timeout:
                differences.append(
                    f"GitHub timeout: {config1.github.timeout} -> "
                    f"{config2.github.timeout}"
                )

            logger.info("Configuration differences found:")
            for diff in differences:
                logger.info(f"  - {diff}")

        except Exception as e:
            logger.error(f"Error comparing configurations: {e}")

    def cleanup(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir)
        logger.info("Cleaned up temporary files")


async def comprehensive_configuration_example():
    """Comprehensive example demonstrating all configuration patterns."""
    examples = ConfigurationExamples()

    try:
        await examples.example_basic_loading()
        await examples.example_environment_variables()
        await examples.example_configuration_validation()
        await examples.example_configuration_utilities()
        await examples.example_hot_reload()
        await examples.example_configuration_caching()
        await examples.example_programmatic_configuration()
        await examples.example_configuration_comparison()

    except Exception as e:
        logger.error(f"Example execution failed: {e}")

    finally:
        examples.cleanup()


if __name__ == "__main__":
    # Run comprehensive examples
    asyncio.run(comprehensive_configuration_example())
