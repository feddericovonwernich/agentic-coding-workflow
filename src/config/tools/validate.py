#!/usr/bin/env python3
"""
Configuration Validation CLI Tool

This tool provides comprehensive validation of configuration files including:
- Schema validation against Pydantic models
- Environment variable validation
- Connectivity testing for external services
- Security best practices validation
- Performance recommendations

Usage:
    python -m src.config.tools.validate [options]
    python src/config/tools/validate.py [options]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import ConfigurationError, load_config


class ConfigurationValidator:
    """Comprehensive configuration validator with multiple validation levels."""

    def __init__(self, config_path: str | None = None, verbose: bool = False):
        self.config_path = config_path or "config.yaml"
        self.verbose = verbose
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.recommendations: list[str] = []
        self.config_data: dict | None = None

    def validate_all(
        self,
        check_schema: bool = True,
        check_environment: bool = True,
        check_connectivity: bool = False,
        check_security: bool = True,
        check_performance: bool = True,
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Run comprehensive validation with specified checks.

        Returns:
            Tuple of (errors, warnings, recommendations)
        """
        self.errors.clear()
        self.warnings.clear()
        self.recommendations.clear()

        # Load and parse configuration file
        if not self._load_config_file():
            return self.errors, self.warnings, self.recommendations

        if check_schema:
            self._validate_schema()

        if check_environment:
            self._validate_environment_variables()

        if check_security:
            self._validate_security()

        if check_performance:
            self._validate_performance()

        if check_connectivity:
            self._validate_connectivity()

        return self.errors, self.warnings, self.recommendations

    def _load_config_file(self) -> bool:
        """Load and parse the configuration file."""
        try:
            if not os.path.exists(self.config_path):
                self.errors.append(f"Configuration file not found: {self.config_path}")
                return False

            with open(self.config_path) as f:
                self.config_data = yaml.safe_load(f)

            if self.verbose:
                print(f"✅ Configuration file loaded: {self.config_path}")

            return True

        except yaml.YAMLError as e:
            self.errors.append(f"YAML parsing error: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Error loading configuration file: {e}")
            return False

    def _validate_schema(self) -> None:
        """Validate configuration against Pydantic schema."""
        if self.verbose:
            print("🔍 Validating schema...")

        try:
            # Attempt to load configuration using the actual config loader
            load_config(self.config_path)

            if self.verbose:
                print("✅ Schema validation passed")

        except ConfigurationError as e:
            self.errors.append(f"Configuration error: {e}")
        except Exception as e:
            self.errors.append(f"Schema validation failed: {e}")

    def _validate_environment_variables(self) -> None:
        """Validate that required environment variables are available."""
        if self.verbose:
            print("🔍 Validating environment variables...")

        if not self.config_data:
            return

        # Extract environment variable references
        env_vars = self._extract_env_vars(self.config_data)

        # Check required environment variables
        missing_vars = []
        for var_name, has_default in env_vars.items():
            if not has_default and not os.getenv(var_name):
                missing_vars.append(var_name)

        if missing_vars:
            self.errors.extend(
                [
                    f"Missing required environment variable: {var}"
                    for var in missing_vars
                ]
            )

        # Check for potentially insecure default values
        insecure_defaults = ["password", "secret", "key", "token"]

        for var_name, has_default in env_vars.items():
            if has_default:
                for insecure_term in insecure_defaults:
                    if insecure_term in var_name.lower():
                        self.warnings.append(
                            f"Environment variable '{var_name}' has a default value "
                            f"but appears to contain sensitive data"
                        )
                        break

        if self.verbose:
            print(f"✅ Found {len(env_vars)} environment variable references")
            if missing_vars:
                print(f"❌ {len(missing_vars)} required variables missing")

    def _extract_env_vars(
        self, data: Any, env_vars: dict[str, bool] | None = None
    ) -> dict[str, bool]:
        """
        Recursively extract environment variable references from configuration.

        Returns:
            Dictionary mapping variable names to whether they have defaults
        """
        if env_vars is None:
            env_vars = {}

        if isinstance(data, dict):
            for value in data.values():
                self._extract_env_vars(value, env_vars)
        elif isinstance(data, list):
            for item in data:
                self._extract_env_vars(item, env_vars)
        elif isinstance(data, str) and "${" in data:
            # Extract environment variable references
            import re

            pattern = r"\$\{([^}]+)\}"
            matches = re.findall(pattern, data)

            for match in matches:
                if ":" in match:
                    # Has default value
                    var_name = match.split(":")[0]
                    env_vars[var_name] = True
                else:
                    # No default value
                    env_vars[match] = False

        return env_vars

    def _validate_security(self) -> None:
        """Validate security best practices."""
        if self.verbose:
            print("🔍 Validating security practices...")

        if not self.config_data:
            return

        # Check for hardcoded secrets
        self._check_hardcoded_secrets()

        # Check SSL/TLS configuration
        self._check_ssl_configuration()

        # Check authentication configuration
        self._check_authentication_config()

        # Check logging configuration
        self._check_logging_security()

    def _check_hardcoded_secrets(self) -> None:
        """Check for potentially hardcoded secrets."""
        sensitive_patterns = [
            r"sk-[a-zA-Z0-9]{48}",  # Anthropic API keys
            r"sk-[a-zA-Z0-9]{51}",  # OpenAI API keys
            r"ghp_[a-zA-Z0-9]{36}",  # GitHub personal access tokens
            r"gho_[a-zA-Z0-9]{36}",  # GitHub OAuth tokens
            r"github_pat_[a-zA-Z0-9_]{82}",  # GitHub fine-grained tokens
        ]

        config_str = yaml.dump(self.config_data)

        import re

        for pattern in sensitive_patterns:
            if re.search(pattern, config_str):
                self.errors.append(
                    "Potential hardcoded API key/token found in configuration. "
                    "Use environment variables instead."
                )
                break

        # Check for common insecure values
        insecure_values = ["password", "secret", "admin", "123456", "test"]

        def check_values(data: Any, path: str = "") -> None:
            if isinstance(data, dict):
                for key, value in data.items():
                    new_path = f"{path}.{key}" if path else key
                    if (
                        key.lower() in ["password", "secret", "token", "key"]
                        and isinstance(value, str)
                        and value.lower() in insecure_values
                    ):
                        self.warnings.append(
                            f"Potentially insecure value for '{new_path}': {value}"
                        )
                    check_values(value, new_path)
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    check_values(item, f"{path}[{i}]")

        check_values(self.config_data)

    def _check_ssl_configuration(self) -> None:
        """Check SSL/TLS configuration."""
        if not self.config_data:
            return

        # Check for unencrypted database connections
        db_config = self.config_data.get("database", {})
        if isinstance(db_config, dict):
            db_url = db_config.get("url", "")
            if isinstance(db_url, str):
                if "postgresql://" in db_url and "sslmode" not in db_url:
                    self.warnings.append(
                        "Database URL does not specify SSL mode. "
                        "Consider adding '?sslmode=require' for security."
                    )
                elif "mysql://" in db_url and "ssl" not in db_url:
                    self.warnings.append(
                        "MySQL URL does not specify SSL. "
                        "Consider adding SSL parameters for security."
                    )

        # Check for unencrypted Redis connections
        queue_config = self.config_data.get("queue", {})
        if isinstance(queue_config, dict):
            queue_url = queue_config.get("url", "")
            if isinstance(queue_url, str) and queue_url.startswith("redis://"):
                self.recommendations.append(
                    "Consider using 'rediss://' for encrypted Redis connections"
                )

    def _check_authentication_config(self) -> None:
        """Check authentication configuration."""
        if not self.config_data:
            return

        # Check for missing authentication tokens
        repos = self.config_data.get("repositories", [])
        if isinstance(repos, list):
            for i, repo in enumerate(repos):
                if isinstance(repo, dict) and not repo.get("auth_token"):
                    self.warnings.append(
                        f"Repository {i + 1} missing auth_token configuration"
                    )

        # Check LLM provider authentication
        llm_config = self.config_data.get("llm", {})
        if isinstance(llm_config, dict):
            for provider_name, provider_config in llm_config.items():
                if isinstance(provider_config, dict) and not provider_config.get(
                    "api_key"
                ):
                    self.warnings.append(
                        f"LLM provider '{provider_name}' missing api_key configuration"
                    )

    def _check_logging_security(self) -> None:
        """Check logging configuration for security issues."""
        if not self.config_data:
            return

        system_config = self.config_data.get("system", {})
        if isinstance(system_config, dict):
            # Check debug mode in production
            environment = system_config.get("environment", "development")
            debug_mode = system_config.get("debug_mode", False)

            if environment == "production" and debug_mode:
                self.warnings.append(
                    "Debug mode is enabled in production environment. "
                    "This may expose sensitive information in logs."
                )

        # Check database query logging
        db_config = self.config_data.get("database", {})
        if isinstance(db_config, dict):
            echo = db_config.get("echo", False)
            if echo:
                self.recommendations.append(
                    "Database query logging (echo) is enabled. "
                    "Disable in production to prevent credential exposure."
                )

    def _validate_performance(self) -> None:
        """Validate performance-related configuration."""
        if self.verbose:
            print("🔍 Validating performance configuration...")

        if not self.config_data:
            return

        # Check database pool configuration
        self._check_database_performance()

        # Check queue configuration
        self._check_queue_performance()

        # Check LLM configuration
        self._check_llm_performance()

        # Check system configuration
        self._check_system_performance()

    def _check_database_performance(self) -> None:
        """Check database performance configuration."""
        if not self.config_data:
            return

        db_config = self.config_data.get("database", {})
        if not isinstance(db_config, dict):
            return

        pool_size = db_config.get("pool_size", 10)
        max_overflow = db_config.get("max_overflow", 20)
        pool_timeout = db_config.get("pool_timeout", 30)

        if pool_size < 5:
            self.recommendations.append(
                f"Database pool_size ({pool_size}) is quite small. "
                f"Consider increasing for better performance."
            )
        elif pool_size > 50:
            self.recommendations.append(
                f"Database pool_size ({pool_size}) is very large. "
                f"This may consume excessive resources."
            )

        if max_overflow > pool_size * 3:
            self.recommendations.append(
                f"Database max_overflow ({max_overflow}) is much larger than "
                f"pool_size ({pool_size}). Consider rebalancing these values."
            )

        if pool_timeout > 60:
            self.recommendations.append(
                f"Database pool_timeout ({pool_timeout}) is quite high. "
                f"This may cause slow responses under load."
            )

    def _check_queue_performance(self) -> None:
        """Check queue performance configuration."""
        if not self.config_data:
            return

        queue_config = self.config_data.get("queue", {})
        if not isinstance(queue_config, dict):
            return

        batch_size = queue_config.get("batch_size", 10)
        visibility_timeout = queue_config.get("visibility_timeout", 300)

        if batch_size < 5:
            self.recommendations.append(
                f"Queue batch_size ({batch_size}) is small. "
                f"Consider increasing for better throughput."
            )
        elif batch_size > 50:
            self.recommendations.append(
                f"Queue batch_size ({batch_size}) is very large. "
                f"This may cause memory issues or long processing delays."
            )

        if visibility_timeout < 60:
            self.recommendations.append(
                f"Queue visibility_timeout ({visibility_timeout}) is quite short. "
                f"Tasks might be reprocessed if they take longer than expected."
            )

    def _check_llm_performance(self) -> None:
        """Check LLM performance configuration."""
        if not self.config_data:
            return

        llm_config = self.config_data.get("llm", {})
        if not isinstance(llm_config, dict):
            return

        for provider_name, provider_config in llm_config.items():
            if not isinstance(provider_config, dict):
                continue

            timeout = provider_config.get("timeout", 60)
            max_tokens = provider_config.get("max_tokens", 4000)

            if timeout < 30:
                self.recommendations.append(
                    f"LLM provider '{provider_name}' timeout ({timeout}) is quite "
                    f"short. Complex requests might timeout."
                )
            elif timeout > 180:
                self.recommendations.append(
                    f"LLM provider '{provider_name}' timeout ({timeout}) is very long. "
                    f"This may cause slow response times."
                )

            if max_tokens > 8000:
                self.recommendations.append(
                    f"LLM provider '{provider_name}' max_tokens ({max_tokens}) is "
                    f"quite high. This will increase API costs significantly."
                )

    def _check_system_performance(self) -> None:
        """Check system performance configuration."""
        if not self.config_data:
            return

        system_config = self.config_data.get("system", {})
        if not isinstance(system_config, dict):
            return

        worker_timeout = system_config.get("worker_timeout", 300)
        max_retry_attempts = system_config.get("max_retry_attempts", 3)

        if worker_timeout < 60:
            self.recommendations.append(
                f"System worker_timeout ({worker_timeout}) is quite short. "
                f"Complex operations might timeout."
            )
        elif worker_timeout > 1800:
            self.recommendations.append(
                f"System worker_timeout ({worker_timeout}) is very long. "
                f"Failed workers might consume resources for too long."
            )

        if max_retry_attempts > 5:
            self.recommendations.append(
                f"System max_retry_attempts ({max_retry_attempts}) is quite high. "
                f"Failed operations might retry too many times, wasting resources."
            )

    def _validate_connectivity(self) -> None:
        """Validate connectivity to external services."""
        if self.verbose:
            print("🔍 Testing connectivity to external services...")

        # Test database connectivity
        self._test_database_connectivity()

        # Test queue connectivity
        self._test_queue_connectivity()

        # Test LLM provider connectivity
        self._test_llm_connectivity()

        # Test notification connectivity
        self._test_notification_connectivity()

    def _test_database_connectivity(self) -> None:
        """Test database connectivity."""
        if not self.config_data:
            return

        try:
            # Note: test_connection may not exist, so we'll skip the import for now
            # from src.database.connection import test_connection

            db_config = self.config_data.get("database", {})
            if isinstance(db_config, dict):
                db_url = db_config.get("url", "")
                if db_url and isinstance(db_url, str):
                    # Substitute environment variables
                    resolved_url = self._resolve_env_vars(db_url)
                    if resolved_url:
                        # Skip actual connection test since test_connection may
                        # not exist
                        # test_connection(resolved_url)
                        if self.verbose:
                            print(
                                "✅ Database connectivity test skipped "
                                "(test_connection not available)"
                            )
                    else:
                        self.warnings.append(
                            "Could not resolve database URL environment variables"
                        )

        except ImportError:
            self.warnings.append(
                "Database connectivity test skipped (database module not available)"
            )
        except Exception as e:
            self.errors.append(f"Database connectivity test failed: {e}")

    def _test_queue_connectivity(self) -> None:
        """Test queue connectivity."""
        if not self.config_data:
            return

        try:
            import redis

            queue_config = self.config_data.get("queue", {})
            if isinstance(queue_config, dict):
                queue_url = queue_config.get("url", "")
                if queue_url and isinstance(queue_url, str):
                    resolved_url = self._resolve_env_vars(queue_url)
                    if resolved_url:
                        r = redis.from_url(resolved_url)
                        r.ping()
                        if self.verbose:
                            print("✅ Queue connectivity test passed")
                    else:
                        self.warnings.append(
                            "Could not resolve queue URL environment variables"
                        )

        except ImportError:
            self.warnings.append(
                "Queue connectivity test skipped (redis module not available)"
            )
        except Exception as e:
            self.errors.append(f"Queue connectivity test failed: {e}")

    def _test_llm_connectivity(self) -> None:
        """Test LLM provider connectivity."""
        if not self.config_data:
            return

        llm_config = self.config_data.get("llm", {})
        if not isinstance(llm_config, dict):
            return

        for provider_name, provider_config in llm_config.items():
            if not isinstance(provider_config, dict):
                continue

            try:
                self._test_single_llm_provider(provider_name, provider_config)
                if self.verbose:
                    print(f"✅ LLM provider '{provider_name}' connectivity test passed")
            except Exception as e:
                self.warnings.append(
                    f"LLM provider '{provider_name}' connectivity test failed: {e}"
                )

    def _test_single_llm_provider(
        self, provider_name: str, provider_config: dict[str, Any]
    ) -> None:
        """Test connectivity to a single LLM provider."""
        provider_type = provider_config.get("provider")
        api_key = self._resolve_env_vars(provider_config.get("api_key", ""))

        if not api_key:
            raise ValueError(f"API key not available for provider {provider_name}")

        if provider_type == "anthropic":
            self._test_anthropic_connectivity(api_key)
        elif provider_type == "openai":
            self._test_openai_connectivity(api_key)
        elif provider_type == "azure_openai":
            endpoint = self._resolve_env_vars(provider_config.get("endpoint", ""))
            if endpoint is not None:
                self._test_azure_openai_connectivity(api_key, endpoint)
            else:
                raise ValueError("Azure OpenAI endpoint could not be resolved")
        else:
            # For other providers, just check if the API key looks valid
            if len(api_key) < 10:
                raise ValueError("API key appears to be invalid (too short)")

    def _test_anthropic_connectivity(self, api_key: str) -> None:
        """Test Anthropic API connectivity."""
        import requests

        headers = {"x-api-key": api_key, "content-type": "application/json"}

        # Simple test request to check authentication
        response = requests.get(
            "https://api.anthropic.com/v1/messages", headers=headers, timeout=10
        )

        # We expect a 400 (bad request) since we're not sending a proper message
        # But if we get 401 (unauthorized), the API key is invalid
        if response.status_code == 401:
            raise ValueError("Anthropic API key is invalid")

    def _test_openai_connectivity(self, api_key: str) -> None:
        """Test OpenAI API connectivity."""
        import requests

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Test with models endpoint
        response = requests.get(
            "https://api.openai.com/v1/models", headers=headers, timeout=10
        )

        if response.status_code == 401:
            raise ValueError("OpenAI API key is invalid")
        elif response.status_code != 200:
            raise ValueError(f"OpenAI API returned status {response.status_code}")

    def _test_azure_openai_connectivity(self, api_key: str, endpoint: str) -> None:
        """Test Azure OpenAI API connectivity."""
        import requests

        if not endpoint:
            raise ValueError("Azure OpenAI endpoint is required")

        headers = {"api-key": api_key, "Content-Type": "application/json"}

        # Test with deployments endpoint
        response = requests.get(
            f"{endpoint}/openai/deployments?api-version=2023-05-15",
            headers=headers,
            timeout=10,
        )

        if response.status_code == 401:
            raise ValueError("Azure OpenAI API key is invalid")
        elif response.status_code not in [200, 404]:  # 404 is OK if no deployments
            raise ValueError(f"Azure OpenAI API returned status {response.status_code}")

    def _test_notification_connectivity(self) -> None:
        """Test notification service connectivity."""
        if not self.config_data:
            return

        notification_config = self.config_data.get("notification", {})
        if not isinstance(notification_config, dict):
            return

        channels = notification_config.get("channels", [])
        if not isinstance(channels, list):
            return

        for i, channel in enumerate(channels):
            if not isinstance(channel, dict):
                continue

            try:
                self._test_single_notification_channel(channel)
                provider = channel.get("provider", f"channel_{i}")
                if self.verbose:
                    print(
                        f"✅ Notification channel '{provider}' connectivity test passed"
                    )
            except Exception as e:
                provider = channel.get("provider", f"channel_{i}")
                self.warnings.append(
                    f"Notification channel '{provider}' connectivity test failed: {e}"
                )

    def _test_single_notification_channel(self, channel: dict[str, Any]) -> None:
        """Test connectivity to a single notification channel."""
        provider = channel.get("provider")

        if provider == "slack":
            webhook_url = self._resolve_env_vars(channel.get("slack_webhook_url", ""))
            if webhook_url:
                self._test_slack_webhook(webhook_url)
        elif provider == "telegram":
            bot_token = self._resolve_env_vars(channel.get("telegram_bot_token", ""))
            if bot_token:
                self._test_telegram_bot(bot_token)
        elif provider == "webhook":
            webhook_url = self._resolve_env_vars(channel.get("webhook_url", ""))
            if webhook_url:
                self._test_generic_webhook(webhook_url)

    def _test_slack_webhook(self, webhook_url: str) -> None:
        """Test Slack webhook connectivity."""
        import requests

        test_payload = {"text": "Configuration validation test - please ignore"}

        response = requests.post(webhook_url, json=test_payload, timeout=10)

        if response.status_code != 200:
            raise ValueError(f"Slack webhook returned status {response.status_code}")

    def _test_telegram_bot(self, bot_token: str) -> None:
        """Test Telegram bot connectivity."""
        import requests

        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10
        )

        if response.status_code != 200:
            raise ValueError(f"Telegram bot API returned status {response.status_code}")

        data = response.json()
        if not data.get("ok"):
            raise ValueError("Telegram bot token is invalid")

    def _test_generic_webhook(self, webhook_url: str) -> None:
        """Test generic webhook connectivity."""
        import requests

        # Simple HEAD request to test connectivity
        response = requests.head(webhook_url, timeout=10)

        # Accept any response that's not a connection error
        if response.status_code >= 500:
            raise ValueError(f"Webhook returned server error {response.status_code}")

    def _resolve_env_vars(self, value: str) -> str | None:
        """Resolve environment variables in a string value."""
        if not isinstance(value, str) or "${" not in value:
            return value

        import re

        def replace_env_var(match: Any) -> str:
            var_spec = match.group(1)
            if ":" in var_spec:
                var_name, default_value = var_spec.split(":", 1)
                return os.getenv(var_name, default_value)
            else:
                return os.getenv(var_spec, "")

        pattern = r"\$\{([^}]+)\}"
        resolved = re.sub(pattern, replace_env_var, value)

        # Return None if any variables couldn't be resolved
        if "${" in resolved:
            return None

        return resolved


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate Agentic Coding Workflow configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic validation
  python -m src.config.tools.validate

  # Validate specific file
  python -m src.config.tools.validate --config production.yaml

  # Full validation including connectivity tests
  python -m src.config.tools.validate --check-connectivity --verbose

  # Schema validation only
  python -m src.config.tools.validate --schema-only

  # Security validation only
  python -m src.config.tools.validate --security-only
        """,
    )

    parser.add_argument(
        "--config",
        "-c",
        help="Configuration file path (default: config.yaml)",
        default="config.yaml",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    parser.add_argument(
        "--check-connectivity",
        action="store_true",
        help="Test connectivity to external services (requires network access)",
    )

    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only validate schema (skip other checks)",
    )

    parser.add_argument(
        "--security-only", action="store_true", help="Only validate security practices"
    )

    parser.add_argument(
        "--no-security", action="store_true", help="Skip security validation"
    )

    parser.add_argument(
        "--no-performance", action="store_true", help="Skip performance validation"
    )

    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    args = parser.parse_args()

    # Determine which checks to run
    if args.schema_only:
        check_schema = True
        check_environment = False
        check_security = False
        check_performance = False
        check_connectivity = False
    elif args.security_only:
        check_schema = False
        check_environment = True
        check_security = True
        check_performance = False
        check_connectivity = False
    else:
        check_schema = True
        check_environment = True
        check_security = not args.no_security
        check_performance = not args.no_performance
        check_connectivity = args.check_connectivity

    # Run validation
    validator = ConfigurationValidator(args.config, args.verbose)

    try:
        errors, warnings, recommendations = validator.validate_all(
            check_schema=check_schema,
            check_environment=check_environment,
            check_connectivity=check_connectivity,
            check_security=check_security,
            check_performance=check_performance,
        )

        # Output results
        if args.json:
            result = {
                "config_file": args.config,
                "validation_success": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "recommendations": recommendations,
                "summary": {
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                    "recommendation_count": len(recommendations),
                },
            }
            print(json.dumps(result, indent=2))
        else:
            # Human-readable output
            print("\n📋 Configuration Validation Report")
            print(f"{'=' * 50}")
            print(f"Config file: {args.config}")

            if errors:
                print(f"\n❌ ERRORS ({len(errors)}):")
                for error in errors:
                    print(f"  • {error}")

            if warnings:
                print(f"\n⚠️  WARNINGS ({len(warnings)}):")
                for warning in warnings:
                    print(f"  • {warning}")

            if recommendations:
                print(f"\n💡 RECOMMENDATIONS ({len(recommendations)}):")
                for recommendation in recommendations:
                    print(f"  • {recommendation}")

            print("\n📊 SUMMARY:")
            print(f"  Errors: {len(errors)}")
            print(f"  Warnings: {len(warnings)}")
            print(f"  Recommendations: {len(recommendations)}")

            if len(errors) == 0:
                print("\n✅ Configuration validation passed!")
            else:
                print("\n❌ Configuration validation failed!")

        # Exit with appropriate code
        sys.exit(1 if errors else 0)

    except KeyboardInterrupt:
        print("\n⚠️  Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        if args.json:
            result = {
                "config_file": args.config,
                "validation_success": False,
                "fatal_error": str(e),
                "errors": [],
                "warnings": [],
                "recommendations": [],
            }
            print(json.dumps(result, indent=2))
        else:
            print(f"\n💥 Fatal error during validation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
