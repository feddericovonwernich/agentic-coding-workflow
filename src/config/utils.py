"""Configuration utilities and helper functions.

This module provides utility functions for working with configuration,
including schema generation, validation helpers, and configuration
management utilities.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .exceptions import ConfigurationError
from .models import Config


def generate_json_schema(
    model_class: type[BaseModel], output_path: str | Path | None = None
) -> dict[str, Any]:
    """Generate JSON Schema for a configuration model.

    Args:
        model_class: Pydantic model class to generate schema for
        output_path: Optional path to write schema file

    Returns:
        JSON Schema dictionary
    """
    schema = model_class.schema()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)

    return schema


def generate_example_config(
    output_path: str | Path | None = None,
    include_comments: bool = True,
    include_sensitive_placeholders: bool = True,
) -> str:
    """Generate an example configuration file.

    Args:
        output_path: Optional path to write example config
        include_comments: Whether to include explanatory comments
        include_sensitive_placeholders: Whether to include placeholder values for
            sensitive fields

    Returns:
        Example configuration as YAML string
    """
    import yaml

    example_config = {
        "system": {
            "log_level": "INFO",
            "environment": "production",
            "worker_timeout": 300,
            "max_retry_attempts": 3,
            "circuit_breaker_failure_threshold": 5,
            "circuit_breaker_timeout": 60,
            "metrics_collection_enabled": True,
            "debug_mode": False,
        },
        "database": {
            "url": "${DATABASE_URL}"
            if include_sensitive_placeholders
            else "postgresql://user:pass@localhost/db",
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 30,
            "pool_recycle": 3600,
            "echo": False,
        },
        "queue": {
            "provider": "redis",
            "url": "${REDIS_URL:redis://localhost:6379/0}",
            "default_queue": "default",
            "max_retries": 3,
            "visibility_timeout": 300,
            "dead_letter_queue_enabled": True,
            "batch_size": 10,
        },
        "llm": {
            "anthropic": {
                "provider": "anthropic",
                "api_key": "${ANTHROPIC_API_KEY}"
                if include_sensitive_placeholders
                else "sk-ant-...",
                "model": "claude-3-sonnet-20240229",
                "max_tokens": 4000,
                "temperature": 0.1,
                "timeout": 60,
                "rate_limit_rpm": 1000,
            },
            "openai": {
                "provider": "openai",
                "api_key": "${OPENAI_API_KEY}"
                if include_sensitive_placeholders
                else "sk-...",
                "model": "gpt-4",
                "max_tokens": 4000,
                "temperature": 0.1,
                "timeout": 60,
                "rate_limit_rpm": 3000,
            },
        },
        "default_llm_provider": "anthropic",
        "notification": {
            "enabled": True,
            "escalation_enabled": True,
            "escalation_delay": 1800,
            "max_notifications_per_hour": 10,
            "channels": [
                {
                    "provider": "telegram",
                    "enabled": True,
                    "telegram_bot_token": "${TELEGRAM_BOT_TOKEN}"
                    if include_sensitive_placeholders
                    else "123456:ABC-DEF...",
                    "telegram_chat_id": "${TELEGRAM_CHAT_ID}"
                    if include_sensitive_placeholders
                    else "-1001234567890",
                },
                {
                    "provider": "slack",
                    "enabled": True,
                    "slack_webhook_url": "${SLACK_WEBHOOK_URL}"
                    if include_sensitive_placeholders
                    else "https://hooks.slack.com/...",
                    "slack_channel": "#alerts",
                },
            ],
        },
        "repositories": [
            {
                "url": "https://github.com/your-org/your-repo",
                "auth_token": "${GITHUB_TOKEN}"
                if include_sensitive_placeholders
                else "ghp_...",
                "polling_interval": 300,
                "failure_threshold": 5,
                "skip_patterns": {
                    "pr_labels": ["wip", "draft", "dependencies"],
                    "check_names": ["codecov/*", "license/*"],
                    "authors": ["dependabot[bot]"],
                },
                "fix_categories": {
                    "lint": {
                        "enabled": True,
                        "confidence_threshold": 60,
                        "max_files_changed": 10,
                    },
                    "test": {
                        "enabled": True,
                        "confidence_threshold": 80,
                        "run_full_test_suite": True,
                    },
                    "security": {"enabled": False, "always_escalate": True},
                    "infrastructure": {"enabled": False, "always_escalate": True},
                },
                "is_critical": False,
                "timezone": "UTC",
            }
        ],
        "claude_code_sdk": {
            "timeout": 300,
            "max_concurrent_fixes": 3,
            "test_validation_enabled": True,
        },
    }

    # Convert to YAML
    yaml_content = yaml.dump(
        example_config,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        allow_unicode=True,
    )

    if include_comments:
        yaml_content = _add_config_comments(yaml_content)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

    return yaml_content


def _add_config_comments(yaml_content: str) -> str:
    """Add explanatory comments to YAML configuration.

    Args:
        yaml_content: YAML configuration content

    Returns:
        YAML content with comments
    """
    lines = yaml_content.split("\n")
    commented_lines = []

    for line in lines:
        if line.strip() == "system:":
            commented_lines.append("# Core system configuration")
        elif line.strip() == "database:":
            commented_lines.append("# Database connection settings")
        elif line.strip() == "queue:":
            commented_lines.append("# Message queue configuration")
        elif line.strip() == "llm:":
            commented_lines.append("# LLM provider configurations")
        elif line.strip() == "notification:":
            commented_lines.append("# Notification system settings")
        elif line.strip() == "repositories:":
            commented_lines.append("# Repository monitoring configuration")
        elif line.strip() == "claude_code_sdk:":
            commented_lines.append("# Claude Code SDK settings")

        commented_lines.append(line)

    return "\n".join(commented_lines)


def validate_environment_variables(config: Config) -> list[str]:
    """Validate that all required environment variables are set.

    Args:
        config: Configuration to validate

    Returns:
        List of missing environment variables
    """
    missing_vars = []

    # Check database URL
    if "${" in config.database.url:
        missing_vars.append("DATABASE_URL")

    # Check queue URL
    if "${" in config.queue.url:
        missing_vars.append("REDIS_URL")

    # Check LLM API keys
    for _provider_name, provider_config in config.llm.items():
        if "${" in provider_config.api_key:
            var_name = f"{provider_config.provider.upper()}_API_KEY"
            missing_vars.append(var_name)

    # Check notification credentials
    for channel in config.notification.channels:
        if channel.provider == "telegram":
            if channel.telegram_bot_token and "${" in channel.telegram_bot_token:
                missing_vars.append("TELEGRAM_BOT_TOKEN")
            if channel.telegram_chat_id and "${" in channel.telegram_chat_id:
                missing_vars.append("TELEGRAM_CHAT_ID")
        elif channel.provider == "slack":
            if channel.slack_webhook_url and "${" in channel.slack_webhook_url:
                missing_vars.append("SLACK_WEBHOOK_URL")

    # Check repository tokens
    for repo in config.repositories:
        if "${" in repo.auth_token:
            missing_vars.append("GITHUB_TOKEN")

    return list(set(missing_vars))  # Remove duplicates


def mask_sensitive_values(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive values in configuration dictionary for logging.

    Args:
        config_dict: Configuration dictionary

    Returns:
        Configuration dictionary with sensitive values masked
    """
    import copy

    masked_config = copy.deepcopy(config_dict)

    sensitive_patterns = [
        "password",
        "token",
        "key",
        "secret",
        "credential",
        "webhook_url",
        "api_key",
        "auth_token",
    ]

    def mask_recursive(obj: Any, path: str = "") -> Any:
        if isinstance(obj, dict):
            return {
                k: mask_recursive(v, f"{path}.{k}" if path else k)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [mask_recursive(item, f"{path}[{i}]") for i, item in enumerate(obj)]
        elif isinstance(obj, str):
            # Check if this field should be masked
            field_name = path.split(".")[-1].lower()
            if (
                any(pattern in field_name for pattern in sensitive_patterns)
                and obj
                and obj.strip()
                and not obj.startswith("${")
            ):
                return f"{'*' * min(len(obj), 8)}..."

        return obj

    return mask_recursive(masked_config)  # type: ignore[no-any-return]


def get_config_summary(config: Config) -> dict[str, Any]:
    """Get a summary of configuration for logging/monitoring.

    Args:
        config: Configuration to summarize

    Returns:
        Configuration summary dictionary
    """
    return {
        "system": {
            "environment": config.system.environment,
            "log_level": config.system.log_level.value,
            "debug_mode": config.system.debug_mode,
            "worker_timeout": config.system.worker_timeout,
            "max_retry_attempts": config.system.max_retry_attempts,
        },
        "database": {
            "provider": config.database.url.split("://")[0]
            if "://" in config.database.url
            else "unknown",
            "pool_size": config.database.pool_size,
            "pool_timeout": config.database.pool_timeout,
        },
        "queue": {
            "provider": config.queue.provider,
            "default_queue": config.queue.default_queue,
            "max_retries": config.queue.max_retries,
        },
        "llm": {
            "providers": list(config.llm.keys()),
            "default_provider": config.default_llm_provider,
            "provider_count": len(config.llm),
        },
        "notification": {
            "enabled": config.notification.enabled,
            "channel_count": len(config.notification.channels),
            "escalation_enabled": config.notification.escalation_enabled,
        },
        "repositories": {
            "count": len(config.repositories),
            "critical_count": sum(
                1 for repo in config.repositories if repo.is_critical
            ),
            "total_skip_patterns": sum(
                len(repo.skip_patterns.get("pr_labels", []))
                + len(repo.skip_patterns.get("check_names", []))
                + len(repo.skip_patterns.get("authors", []))
                for repo in config.repositories
                if repo.skip_patterns
            ),
        },
    }


def create_minimal_config(
    database_url: str = "sqlite:///./test.db",
    github_token: str | None = None,
    repo_url: str = "https://github.com/example/repo",
) -> Config:
    """Create a minimal configuration for testing/development.

    Args:
        database_url: Database connection URL
        github_token: GitHub authentication token (uses GITHUB_TOKEN env var if None)
        repo_url: Repository URL to monitor

    Returns:
        Minimal configuration instance

    Raises:
        ConfigurationError: If configuration creation fails
    """

    # Use test placeholders if not provided (for testing/development)
    if github_token is None:
        github_token = "ghp_test_token_placeholder"  # nosec B105

    # Use test placeholder for API key
    api_key = "sk-ant-test-key-placeholder"

    try:
        config_data = {
            "database": {"url": database_url},
            "queue": {"url": "redis://localhost:6379/0"},
            "llm": {
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": api_key,
                    "model": "claude-3-sonnet-20240229",
                }
            },
            "notification": {"enabled": False},
            "repositories": [{"url": repo_url, "auth_token": github_token}],
        }

        return Config(**config_data)  # type: ignore[arg-type]
    except Exception as e:
        raise ConfigurationError(f"Failed to create minimal configuration: {e}") from e


def merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
    """Merge multiple configuration dictionaries with deep merging.

    Later configurations override earlier ones.

    Args:
        *configs: Configuration dictionaries to merge

    Returns:
        Merged configuration dictionary
    """
    import copy

    def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries."""
        result = copy.deepcopy(base)

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)

        return result

    if not configs:
        return {}

    merged = copy.deepcopy(configs[0])
    for config in configs[1:]:
        merged = deep_merge(merged, config)

    return merged
