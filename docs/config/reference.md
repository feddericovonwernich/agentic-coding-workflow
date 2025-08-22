# Configuration Reference

This document provides a complete reference for all configuration options in the Agentic Coding Workflow system. Each section includes field descriptions, types, defaults, validation rules, and examples.

## Table of Contents

- [Root Configuration](#root-configuration)
- [System Configuration](#system-configuration)
- [Database Configuration](#database-configuration)
- [Queue Configuration](#queue-configuration)
- [LLM Provider Configuration](#llm-provider-configuration)
- [Notification Configuration](#notification-configuration)
- [Repository Configuration](#repository-configuration)
- [Environment Variable Substitution](#environment-variable-substitution)
- [Validation Rules](#validation-rules)

## Root Configuration

The root configuration contains all subsystem configurations and serves as the main entry point.

```yaml
# Root configuration structure
system: { }           # Core system settings
database: { }         # Database connection configuration
queue: { }            # Message queue configuration
llm: { }              # LLM provider configurations
default_llm_provider: # Default LLM provider to use
notification: { }     # Notification system configuration
repositories: [ ]     # Repository monitoring configurations
claude_code_sdk: { }  # Claude Code SDK settings
```

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `system` | SystemConfig | No | `{}` | Core system configuration |
| `database` | DatabaseConfig | **Yes** | - | Database configuration |
| `queue` | QueueConfig | **Yes** | - | Message queue configuration |
| `llm` | dict[str, LLMProviderConfig] | **Yes** | - | LLM provider configurations |
| `default_llm_provider` | string | No | `"anthropic"` | Default LLM provider name |
| `notification` | NotificationConfig | No | `{}` | Notification system configuration |
| `repositories` | list[RepositoryConfig] | **Yes** | - | Repository configurations |
| `claude_code_sdk` | dict | No | `{}` | Claude Code SDK configuration |

### Validation Rules

- At least one repository must be configured
- Default LLM provider must exist in the `llm` configuration dictionary
- All referenced notification providers must be properly configured

## System Configuration

Core system settings that affect overall application behavior.

```yaml
system:
  log_level: INFO
  environment: production
  worker_timeout: 300
  max_retry_attempts: 3
  circuit_breaker_failure_threshold: 5
  circuit_breaker_timeout: 60
  metrics_collection_enabled: true
  debug_mode: false
```

### Fields

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `log_level` | LogLevel | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL | System-wide logging level |
| `environment` | string | `"development"` | - | Deployment environment (development, staging, production) |
| `worker_timeout` | integer | `300` | 30-3600 | Maximum worker execution time in seconds |
| `max_retry_attempts` | integer | `3` | 0-10 | Maximum number of retry attempts for failed operations |
| `circuit_breaker_failure_threshold` | integer | `5` | 1-20 | Number of failures before opening circuit breaker |
| `circuit_breaker_timeout` | integer | `60` | 10-300 | Circuit breaker timeout in seconds |
| `metrics_collection_enabled` | boolean | `true` | - | Enable system metrics collection |
| `debug_mode` | boolean | `false` | - | Enable debug mode with verbose logging |

### Examples

**Development Environment**
```yaml
system:
  log_level: DEBUG
  environment: development
  debug_mode: true
  worker_timeout: 600  # Longer timeout for debugging
```

**Production Environment**
```yaml
system:
  log_level: INFO
  environment: production
  circuit_breaker_failure_threshold: 3  # Fail faster in production
  metrics_collection_enabled: true
```

## Database Configuration

Database connection and pool configuration supporting PostgreSQL, MySQL, and SQLite.

```yaml
database:
  url: "${DATABASE_URL}"
  pool_size: 10
  max_overflow: 20
  pool_timeout: 30
  pool_recycle: 3600
  echo: false
```

### Fields

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `url` | string | - | - | **Required** Database connection URL |
| `pool_size` | integer | `10` | 1-100 | Database connection pool size |
| `max_overflow` | integer | `20` | 0-100 | Maximum overflow connections beyond pool size |
| `pool_timeout` | integer | `30` | 1-300 | Timeout in seconds for getting connection from pool |
| `pool_recycle` | integer | `3600` | 300-86400 | Connection recycle time in seconds |
| `echo` | boolean | `false` | - | Enable SQLAlchemy query logging |

### URL Formats

**PostgreSQL**
```yaml
url: "postgresql://user:password@localhost:5432/dbname"
url: "postgresql+psycopg2://user:password@localhost:5432/dbname"
```

**MySQL**
```yaml
url: "mysql://user:password@localhost:3306/dbname"
url: "mysql+pymysql://user:password@localhost:3306/dbname"
```

**SQLite**
```yaml
url: "sqlite:///./local.db"        # Relative path
url: "sqlite:////absolute/path.db" # Absolute path
url: "sqlite:///:memory:"          # In-memory database
```

### Examples

**Local Development**
```yaml
database:
  url: "sqlite:///./dev.db"
  pool_size: 5
  echo: true  # Enable query logging
```

**Production**
```yaml
database:
  url: "${DATABASE_URL}"
  pool_size: 20
  max_overflow: 30
  pool_recycle: 1800  # 30 minutes
```

## Queue Configuration

Message queue configuration supporting Redis, RabbitMQ, and SQS.

```yaml
queue:
  provider: redis
  url: "${REDIS_URL}"
  default_queue: default
  max_retries: 3
  visibility_timeout: 300
  dead_letter_queue_enabled: true
  batch_size: 10
```

### Fields

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `provider` | string | `"redis"` | redis, rabbitmq, sqs | Queue provider type |
| `url` | string | - | - | **Required** Queue connection URL |
| `default_queue` | string | `"default"` | - | Default queue name |
| `max_retries` | integer | `3` | 0-10 | Maximum message retry attempts |
| `visibility_timeout` | integer | `300` | 30-1800 | Message visibility timeout in seconds |
| `dead_letter_queue_enabled` | boolean | `true` | - | Enable dead letter queue for failed messages |
| `batch_size` | integer | `10` | 1-100 | Message batch processing size |

### Provider Examples

**Redis**
```yaml
queue:
  provider: redis
  url: "redis://localhost:6379/0"
  url: "redis://:password@localhost:6379/0"  # With password
  url: "rediss://redis.example.com:6380/0"   # SSL/TLS
```

**RabbitMQ**
```yaml
queue:
  provider: rabbitmq
  url: "amqp://user:password@localhost:5672/"
  default_queue: "agentic_tasks"
```

**Amazon SQS**
```yaml
queue:
  provider: sqs
  url: "https://sqs.region.amazonaws.com/account/queue-name"
  visibility_timeout: 600
  batch_size: 1  # SQS processes one message at a time
```

## LLM Provider Configuration

Configuration for LLM providers including API keys, models, and rate limits.

```yaml
llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: claude-3-sonnet-20240229
    max_tokens: 4000
    temperature: 0.1
    timeout: 60
    rate_limit_rpm: 1000

  openai:
    provider: openai
    api_key: "${OPENAI_API_KEY}"
    model: gpt-4
    max_tokens: 4000
    temperature: 0.1
    timeout: 60
    rate_limit_rpm: 3000

default_llm_provider: anthropic
```

### Fields

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `provider` | LLMProvider | - | anthropic, openai, azure_openai, gemini | **Required** LLM provider type |
| `api_key` | string | - | - | **Required** API key for the provider |
| `model` | string | - | - | **Required** Model name/identifier |
| `endpoint` | string | null | - | Custom API endpoint (for self-hosted deployments) |
| `max_tokens` | integer | `4000` | 100-100000 | Maximum tokens per request |
| `temperature` | float | `0.1` | 0.0-2.0 | Sampling temperature (lower = more deterministic) |
| `timeout` | integer | `60` | 10-300 | Request timeout in seconds |
| `rate_limit_rpm` | integer | null | ≥1 | Rate limit in requests per minute |

### Provider Examples

**Anthropic Claude**
```yaml
anthropic:
  provider: anthropic
  api_key: "${ANTHROPIC_API_KEY}"
  model: claude-3-sonnet-20240229
  max_tokens: 4000
  temperature: 0.0  # Most deterministic
```

**OpenAI GPT**
```yaml
openai:
  provider: openai
  api_key: "${OPENAI_API_KEY}"
  model: gpt-4-turbo-preview
  max_tokens: 4000
  rate_limit_rpm: 3000
```

**Azure OpenAI**
```yaml
azure_openai:
  provider: azure_openai
  api_key: "${AZURE_OPENAI_API_KEY}"
  endpoint: "https://your-resource.openai.azure.com/"
  model: gpt-4
```

**Google Gemini**
```yaml
gemini:
  provider: gemini
  api_key: "${GEMINI_API_KEY}"
  model: gemini-pro
  max_tokens: 8000
```

## Notification Configuration

Multi-channel notification system supporting Telegram, Slack, email, and webhooks.

```yaml
notification:
  enabled: true
  escalation_enabled: true
  escalation_delay: 1800
  max_notifications_per_hour: 10
  
  channels:
    - provider: telegram
      enabled: true
      telegram_bot_token: "${TELEGRAM_BOT_TOKEN}"
      telegram_chat_id: "${TELEGRAM_CHAT_ID}"
    
    - provider: slack
      enabled: true
      slack_webhook_url: "${SLACK_WEBHOOK_URL}"
      slack_channel: "#alerts"
    
    - provider: email
      enabled: false
      email_smtp_host: "${EMAIL_SMTP_HOST}"
      email_smtp_port: 587
      email_username: "${EMAIL_USERNAME}"
      email_password: "${EMAIL_PASSWORD}"
      email_from_address: "${EMAIL_FROM_ADDRESS}"
      email_to_addresses:
        - "admin@example.com"
        - "ops@example.com"
```

### Main Configuration Fields

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `enabled` | boolean | `true` | - | Enable notification system |
| `escalation_enabled` | boolean | `true` | - | Enable escalation notifications |
| `escalation_delay` | integer | `1800` | 300-86400 | Delay before escalation in seconds (30 minutes) |
| `max_notifications_per_hour` | integer | `10` | 1-100 | Maximum notifications per hour to prevent spam |
| `channels` | list[NotificationChannelConfig] | `[]` | - | List of notification channels |

### Channel Configuration

Each notification channel requires provider-specific configuration:

**Telegram Channel**
```yaml
- provider: telegram
  enabled: true
  telegram_bot_token: "${TELEGRAM_BOT_TOKEN}"
  telegram_chat_id: "${TELEGRAM_CHAT_ID}"
```

**Slack Channel**
```yaml
- provider: slack
  enabled: true
  slack_webhook_url: "${SLACK_WEBHOOK_URL}"
  slack_channel: "#alerts"
```

**Email Channel**
```yaml
- provider: email
  enabled: true
  email_smtp_host: "smtp.gmail.com"
  email_smtp_port: 587
  email_username: "${EMAIL_USERNAME}"
  email_password: "${EMAIL_PASSWORD}"
  email_from_address: "noreply@example.com"
  email_to_addresses:
    - "admin@example.com"
```

**Webhook Channel**
```yaml
- provider: webhook
  enabled: true
  webhook_url: "https://api.example.com/webhooks/alerts"
  webhook_headers:
    Authorization: "Bearer ${WEBHOOK_TOKEN}"
    Content-Type: "application/json"
```

### Priority Mapping

The system automatically routes notifications based on priority:

| Priority | Default Channels |
|----------|-----------------|
| `low` | Email |
| `medium` | Slack, Email |
| `high` | Telegram, Slack |
| `critical` | Telegram, Slack, Email |

## Repository Configuration

Configuration for individual GitHub repositories including monitoring settings, fix categories, and skip patterns.

```yaml
repositories:
  - url: https://github.com/your-org/your-repo
    auth_token: "${GITHUB_TOKEN}"
    polling_interval: 300
    failure_threshold: 5
    is_critical: false
    timezone: UTC
    
    skip_patterns:
      pr_labels: ["wip", "draft", "dependencies"]
      check_names: ["codecov/*", "license/*"]
      authors: ["dependabot[bot]"]
    
    fix_categories:
      lint:
        enabled: true
        confidence_threshold: 60
        max_files_changed: 10
      
      test:
        enabled: true
        confidence_threshold: 80
        run_full_test_suite: true
      
      security:
        enabled: false
        always_escalate: true
    
    business_hours:
      start: "09:00"
      end: "17:00"
```

### Main Fields

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `url` | string | - | - | **Required** Repository URL |
| `auth_token` | string | - | - | **Required** GitHub authentication token |
| `polling_interval` | integer | `300` | 60-3600 | PR polling interval in seconds (5 minutes) |
| `failure_threshold` | integer | `5` | 1-20 | Number of failures before human escalation |
| `is_critical` | boolean | `false` | - | Whether this is a critical production repository |
| `timezone` | string | `"UTC"` | - | Repository timezone for business hours calculation |
| `skip_patterns` | dict | See below | - | Patterns to skip during processing |
| `fix_categories` | dict | See below | - | Fix category configuration |
| `business_hours` | dict | null | - | Business hours configuration |

### Skip Patterns

Configure patterns to skip during processing:

```yaml
skip_patterns:
  pr_labels:        # Skip PRs with these labels
    - "wip"
    - "draft" 
    - "dependencies"
    - "security"
  
  check_names:      # Skip checks with these name patterns
    - "codecov/*"
    - "license/*"
    - "dependabot/*"
  
  authors:          # Skip PRs from these authors
    - "dependabot[bot]"
    - "github-actions[bot]"
```

### Fix Categories

Configure automatic fix behavior for different failure types:

```yaml
fix_categories:
  lint:                    # Linting and formatting fixes
    enabled: true
    confidence_threshold: 60        # Minimum confidence to attempt fix
    max_files_changed: 10          # Maximum files that can be changed
  
  format:                  # Code formatting fixes
    enabled: true
    confidence_threshold: 80
    max_files_changed: 20
  
  test:                    # Test failure fixes
    enabled: true
    confidence_threshold: 80        # Higher threshold for test fixes
    run_full_test_suite: true      # Run full test suite after fix
  
  compilation:             # Compilation error fixes
    enabled: true
    confidence_threshold: 75
    max_files_changed: 5
  
  security:                # Security issue fixes
    enabled: false                  # Typically disabled
    always_escalate: true          # Always escalate to humans
  
  infrastructure:          # Infrastructure failure fixes
    enabled: false                  # Typically disabled
    always_escalate: true          # Always escalate to humans
  
  dependencies:            # Dependency update fixes
    enabled: true
    confidence_threshold: 90        # Very high threshold
    max_files_changed: 3           # Usually just package files
```

### Business Hours

Configure business hours for critical repository handling:

```yaml
business_hours:
  start: "09:00"    # Start time in 24-hour format
  end: "17:00"      # End time in 24-hour format
```

## Environment Variable Substitution

The configuration system supports environment variable substitution in all string values using these formats:

### Required Variables
```yaml
database:
  url: "${DATABASE_URL}"  # Must be set, will error if missing
```

### Optional Variables with Defaults
```yaml
queue:
  url: "${REDIS_URL:redis://localhost:6379/0}"  # Uses default if not set
```

### Examples

```yaml
# Required environment variables
api_key: "${ANTHROPIC_API_KEY}"
github_token: "${GITHUB_TOKEN}"

# Optional with defaults
log_level: "${LOG_LEVEL:INFO}"
worker_timeout: "${WORKER_TIMEOUT:300}"
debug_mode: "${DEBUG_MODE:false}"

# Complex combinations
database:
  url: "${DATABASE_URL:postgresql://user:pass@localhost:5432/db}"
  pool_size: "${DB_POOL_SIZE:10}"
```

## Validation Rules

The configuration system enforces various validation rules:

### Schema Validation
- **Type Safety**: All fields must match their declared types
- **Required Fields**: Missing required fields cause validation errors
- **Extra Fields**: Extra fields are forbidden and cause validation errors
- **Enum Values**: Enum fields must use valid enum values

### Business Logic Validation
- **URL Formats**: Database and queue URLs must be valid connection strings
- **Range Validation**: Numeric fields must be within specified ranges
- **Cross-field Validation**: Related fields must be consistent

### Runtime Validation
- **Connectivity Checks**: Optional validation of database and queue connections
- **Dependency Checks**: Optional validation that required services are available
- **Permission Checks**: Optional validation of API key permissions

### Common Validation Errors

**Missing Required Environment Variables**
```
ConfigurationError: Required environment variable 'DATABASE_URL' not found
```

**Invalid URL Format**
```
ValidationError: Database URL must include a valid scheme (postgresql, mysql, sqlite)
```

**Out of Range Values**
```
ValidationError: worker_timeout must be between 30 and 3600 seconds
```

**Invalid Enum Values**
```
ValidationError: log_level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**Cross-field Validation**
```
ValidationError: default_llm_provider 'openai' not found in llm configuration
```

## API Reference

### Configuration Utilities

The configuration system provides various utility functions for advanced usage:

#### Generate Example Configuration

```python
from src.config import generate_example_config

# Generate example config file
example_yaml = generate_example_config(
    output_path="config.example.yaml",
    include_comments=True
)
```

#### Configuration Summary

```python
from src.config import get_config_summary, mask_sensitive_values

config = load_config()

# Get configuration summary for logging
summary = get_config_summary(config)

# Mask sensitive values for safe logging
safe_config = mask_sensitive_values(config.dict())
```

#### Environment Variable Validation

```python
from src.config import validate_environment_variables

config = load_config()
missing_vars = validate_environment_variables(config)

if missing_vars:
    print(f"Missing environment variables: {missing_vars}")
```

#### Advanced Validation

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

#### JSON Schema Generation

Generate JSON Schema for configuration validation in external tools:

```python
from src.config import generate_json_schema, Config

# Generate schema for the entire configuration
schema = generate_json_schema(Config, "config-schema.json")
```

### Error Handling

The configuration system provides specific exceptions for different error types:

- `ConfigurationError`: Base exception for all configuration errors
- `ConfigurationFileError`: File reading/parsing errors
- `ConfigurationValidationError`: Validation failures
- `ConfigurationMissingError`: Missing required configuration
- `EnvironmentVariableError`: Environment variable substitution failures

### Environment Variable Substitution

The system supports two formats for environment variable substitution:

- `${VAR_NAME}` - Required environment variable (throws error if missing)
- `${VAR_NAME:default_value}` - Optional with default value

#### Examples

```yaml
# Basic substitution
database:
  url: "${DATABASE_URL}"  # Required environment variable
  pool_size: "${DB_POOL_SIZE:10}"  # Optional with default value

# Complex substitution
llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: "${ANTHROPIC_MODEL:claude-3-sonnet-20240229}"
```

### Security Considerations

- Configuration files may contain sensitive information (API keys, tokens)
- Use environment variables for sensitive values
- Ensure configuration files have appropriate permissions (600 or 640)
- The system automatically masks sensitive values in logs and error messages

## Configuration Examples

See the [examples directory](../../config/examples/) for complete configuration examples for different environments and use cases.