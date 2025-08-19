# Configuration System

The configuration system provides type-safe, validated configuration management for the agentic coding workflow system. It supports YAML files with environment variable substitution, comprehensive validation, and hierarchical configuration loading.

## Quick Start

```python
from src.config import load_config, get_config

# Load configuration from file
config = load_config("config.yaml")

# Or auto-discover configuration file
config = load_config()  # Searches standard locations

# Access configuration
database_url = config.database.url
llm_provider = config.llm[config.default_llm_provider]
```

## Configuration File Format

Configuration is defined in YAML format with support for environment variable substitution:

```yaml
# config.yaml
database:
  url: "${DATABASE_URL}"  # Required environment variable
  pool_size: "${DB_POOL_SIZE:10}"  # Optional with default value

llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: claude-3-sonnet-20240229
```

## Environment Variable Substitution

The system supports two formats for environment variable substitution:

- `${VAR_NAME}` - Required environment variable (throws error if missing)
- `${VAR_NAME:default_value}` - Optional with default value

## Configuration Sections

### System Configuration
Core system settings including logging, timeouts, and circuit breaker configuration.

### Database Configuration  
Database connection settings with pool configuration and connection management.

### Queue Configuration
Message queue settings for Redis, RabbitMQ, or SQS providers.

### LLM Provider Configuration
Configuration for multiple LLM providers including API keys, models, and cost tracking.

### Notification Configuration
Multi-channel notification system with Telegram, Slack, and email support.

### Repository Configuration
Per-repository settings including polling intervals, skip patterns, and fix categories.

## Validation

The configuration system provides multiple levels of validation:

1. **Schema Validation**: Pydantic models ensure type safety and required fields
2. **Business Logic Validation**: Cross-field validation and consistency checks
3. **Runtime Validation**: Optional connectivity and dependency checks

```python
from src.config import validate_config, ConfigurationValidator

# Basic validation
errors, warnings = validate_config(config)

# Advanced validation with connectivity checks
validator = ConfigurationValidator(config)
errors, warnings = validator.validate_all(
    check_connectivity=True,
    check_dependencies=True,
    check_permissions=True
)
```

## Utilities

### Generate Example Configuration

```python
from src.config import generate_example_config

# Generate example config file
example_yaml = generate_example_config(
    output_path="config.example.yaml",
    include_comments=True
)
```

### Configuration Summary

```python
from src.config import get_config_summary, mask_sensitive_values

config = load_config()

# Get configuration summary for logging
summary = get_config_summary(config)

# Mask sensitive values for safe logging
safe_config = mask_sensitive_values(config.dict())
```

### Environment Variable Validation

```python
from src.config import validate_environment_variables

config = load_config()
missing_vars = validate_environment_variables(config)

if missing_vars:
    print(f"Missing environment variables: {missing_vars}")
```

## Configuration Loading Hierarchy

The system searches for configuration files in this order:

1. Explicit path provided to `load_config()`
2. Current working directory (`./config.yaml`)
3. `AGENTIC_CONFIG_PATH` environment variable
4. User config directory (`~/.agentic/config.yaml`)
5. System config directory (`/etc/agentic/config.yaml`)

## Error Handling

The configuration system provides specific exceptions for different error types:

- `ConfigurationError`: Base exception for all configuration errors
- `ConfigurationFileError`: File reading/parsing errors
- `ConfigurationValidationError`: Validation failures
- `ConfigurationMissingError`: Missing required configuration
- `EnvironmentVariableError`: Environment variable substitution failures

## Testing Support

For testing, you can create minimal configurations:

```python
from src.config import create_minimal_config

# Create minimal config for testing
test_config = create_minimal_config(
    database_url="sqlite:///test.db",
    github_token="test-token",
    repo_url="https://github.com/test/repo"
)
```

## JSON Schema Generation

Generate JSON Schema for configuration validation in external tools:

```python
from src.config import generate_json_schema, Config

# Generate schema for the entire configuration
schema = generate_json_schema(Config, "config-schema.json")
```

## Security Considerations

- Configuration files may contain sensitive information (API keys, tokens)
- Use environment variables for sensitive values
- Ensure configuration files have appropriate permissions (600 or 640)
- The system automatically masks sensitive values in logs and error messages

## Configuration Hot Reload

Configuration can be reloaded without restarting the application:

```python
from src.config import reload_config

# Reload configuration from the same source
updated_config = reload_config()
```

Note: Hot reload should be used carefully in production environments as it may cause inconsistent state if workers are processing tasks during reload.