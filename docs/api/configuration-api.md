# Configuration Management API

The Configuration Management API provides a powerful, type-safe configuration system with validation, hot reload, and comprehensive utilities for managing application configuration.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration Loading](#configuration-loading)
- [Configuration Models](#configuration-models)
- [Environment Variable Substitution](#environment-variable-substitution)
- [Validation](#validation)
- [Configuration Utilities](#configuration-utilities)
- [Hot Reload](#hot-reload)
- [Caching and Performance](#caching-and-performance)
- [Testing Support](#testing-support)
- [Best Practices](#best-practices)

## Quick Start

### Basic Configuration Loading

```python
from src.config.loader import load_config

# Load configuration from default locations
config = load_config()

# Access configuration values
print(f"Database URL: {config.database.url}")
print(f"GitHub Token: {config.github.token}")
print(f"LLM Provider: {config.default_llm_provider}")
```

### Custom Configuration File

```python
# Load from specific file
config = load_config("custom-config.yaml")

# Load with validation options
config = load_config(
    config_file="config.yaml",
    validate_environment=True,
    strict_mode=True
)
```

### Minimal Configuration Example

```yaml
# minimal-config.yaml
database:
  url: "${DATABASE_URL:sqlite:///./agentic.db}"

github:
  token: "${GITHUB_TOKEN}"

llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"

default_llm_provider: anthropic
```

## Configuration Loading

### Loading Hierarchy

The configuration system follows a hierarchical loading pattern:

1. **Default values** from Pydantic models
2. **Configuration file** (YAML)
3. **Environment variables** with substitution
4. **Runtime overrides** (if applicable)

```python
from src.config.loader import ConfigurationLoader

# Create loader with custom options
loader = ConfigurationLoader(
    search_paths=[
        "./config.yaml",
        "./configs/production.yaml",
        "/etc/agentic/config.yaml"
    ],
    environment_prefix="AGENTIC_",
    strict_validation=True
)

# Load configuration
config = await loader.load_config()
```

### Auto-Discovery

Configuration files are automatically discovered from multiple locations:

```python
# Default search paths (in order)
search_paths = [
    "./config.yaml",                    # Current directory
    "./config/config.yaml",             # Config subdirectory
    "~/.config/agentic/config.yaml",    # User config directory
    "/etc/agentic/config.yaml"          # System config directory
]

# Override search paths
config = load_config(search_paths=custom_paths)
```

### Loading Options

```python
from src.config.loader import load_config

# Basic loading
config = load_config()

# Advanced loading with options
config = load_config(
    config_file="production.yaml",      # Specific file
    validate_environment=True,          # Validate env vars exist
    strict_mode=True,                   # Strict validation
    cache_enabled=True,                 # Enable caching
    hot_reload=True                     # Enable hot reload
)
```

## Configuration Models

### Root Configuration

The root `Config` model contains all system configuration:

```python
from src.config.models import Config, DatabaseConfig, GitHubConfig

# Access configuration sections
config = load_config()

# Database configuration
db_config: DatabaseConfig = config.database
print(f"Database URL: {db_config.url}")
print(f"Pool Size: {db_config.pool_size}")

# GitHub configuration
github_config: GitHubConfig = config.github
print(f"Token: {github_config.token}")
print(f"Rate Limit: {github_config.rate_limit_buffer}")
```

### Configuration Sections

#### Database Configuration

```python
from src.config.models import DatabaseConfig

# Full database configuration
database_config = DatabaseConfig(
    url="postgresql://user:pass@localhost:5432/agentic",
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    echo_sql=False,
    migration_timeout=300
)

# Minimal configuration (with defaults)
database_config = DatabaseConfig(
    url="sqlite:///./agentic.db"
    # Other values use defaults
)
```

#### GitHub Configuration

```python
from src.config.models import GitHubConfig

# GitHub API configuration
github_config = GitHubConfig(
    token="ghp_your_token_here",
    base_url="https://api.github.com",
    timeout=30,
    max_retries=3,
    rate_limit_buffer=100,
    user_agent="PR-Monitor/1.0"
)
```

#### LLM Provider Configuration

```python
from src.config.models import LLMConfig, AnthropicConfig, OpenAIConfig

# Anthropic configuration
anthropic_config = AnthropicConfig(
    provider="anthropic",
    api_key="sk-ant-your-key",
    model="claude-3-sonnet-20240229",
    max_tokens=4096,
    temperature=0.1
)

# OpenAI configuration
openai_config = OpenAIConfig(
    provider="openai",
    api_key="sk-your-openai-key",
    model="gpt-4",
    max_tokens=4096,
    temperature=0.1,
    organization_id="org-your-org-id"
)

# LLM configuration with multiple providers
llm_config = LLMConfig(
    anthropic=anthropic_config,
    openai=openai_config,
    default_provider="anthropic"
)
```

#### Notification Configuration

```python
from src.config.models import NotificationConfig, TelegramConfig, SlackConfig

# Telegram notification
telegram_config = TelegramConfig(
    enabled=True,
    bot_token="your_bot_token",
    chat_id="your_chat_id",
    parse_mode="Markdown"
)

# Slack notification
slack_config = SlackConfig(
    enabled=True,
    webhook_url="https://hooks.slack.com/services/...",
    channel="#alerts",
    username="AgenticBot"
)

# Complete notification configuration
notification_config = NotificationConfig(
    telegram=telegram_config,
    slack=slack_config,
    email=email_config
)
```

### Configuration Enums

Predefined enums for type safety:

```python
from src.config.models import LogLevel, NotificationPriority, FixCategory

# Use enums for type safety
system_config = SystemConfig(
    log_level=LogLevel.INFO,           # Instead of "INFO"
    environment="production"
)

notification = NotificationConfig(
    default_priority=NotificationPriority.MEDIUM  # Instead of "medium"
)

fix_config = FixConfig(
    enabled_categories=[
        FixCategory.LINT,
        FixCategory.FORMAT
    ]
)
```

## Environment Variable Substitution

### Basic Substitution

Configuration supports environment variable substitution with the `${VAR_NAME}` syntax:

```yaml
# config.yaml
database:
  url: "${DATABASE_URL}"

github:
  token: "${GITHUB_TOKEN}"

llm:
  anthropic:
    api_key: "${ANTHROPIC_API_KEY}"
```

### Default Values

Provide default values using the `${VAR_NAME:default}` syntax:

```yaml
# config.yaml with defaults
database:
  url: "${DATABASE_URL:sqlite:///./agentic.db}"
  pool_size: "${DB_POOL_SIZE:20}"

github:
  rate_limit_buffer: "${GITHUB_RATE_BUFFER:100}"

system:
  log_level: "${LOG_LEVEL:INFO}"
```

### Complex Substitution

Environment variables can be used in complex values:

```yaml
# config.yaml
github:
  base_url: "${GITHUB_BASE_URL:https://api.github.com}"
  user_agent: "${APP_NAME:PR-Monitor}/${APP_VERSION:1.0}"

database:
  url: "postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME}"

notification:
  slack:
    webhook_url: "https://hooks.slack.com/services/${SLACK_WEBHOOK_PATH}"
```

### Environment Variable Validation

Validate that required environment variables are set:

```python
from src.config.utils import validate_environment_variables

# Validate required environment variables
required_vars = [
    "GITHUB_TOKEN",
    "ANTHROPIC_API_KEY",
    "DATABASE_URL"
]

missing_vars = validate_environment_variables(required_vars)
if missing_vars:
    raise ConfigurationError(f"Missing environment variables: {missing_vars}")

# Load configuration after validation
config = load_config()
```

## Validation

### Schema Validation

All configuration is validated using Pydantic models:

```python
from src.config.exceptions import ConfigurationValidationError

try:
    config = load_config("config.yaml")
except ConfigurationValidationError as e:
    print("Configuration validation failed:")
    for error in e.errors:
        print(f"  - {error['loc']}: {error['msg']}")
```

### Custom Validation

Implement custom validation rules:

```python
from src.config.models import Config
from pydantic import field_validator, model_validator

class CustomConfig(Config):
    """Extended configuration with custom validation."""
    
    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v):
        """Validate database URL format."""
        if not v.startswith(('postgresql://', 'sqlite:///')):
            raise ValueError("Database URL must be PostgreSQL or SQLite")
        return v
    
    @model_validator(mode='after')
    def validate_github_and_llm(self):
        """Validate that required services are configured."""
        if not self.github.token:
            raise ValueError("GitHub token is required")
        if not self.llm.anthropic.api_key and not self.llm.openai.api_key:
            raise ValueError("At least one LLM provider must be configured")
        return self
```

### Validation Options

Control validation behavior:

```python
# Strict validation (fail on unknown fields)
config = load_config(strict_mode=True)

# Lenient validation (ignore unknown fields)
config = load_config(strict_mode=False)

# Validate environment variables exist
config = load_config(validate_environment=True)
```

## Configuration Utilities

### Configuration Summary

Get a summary of current configuration:

```python
from src.config.utils import get_config_summary

config = load_config()
summary = get_config_summary(config)

print(summary)
# Output:
# Configuration Summary:
# - Database: PostgreSQL (pool_size=20)
# - GitHub: Configured with token
# - LLM: Anthropic (claude-3-sonnet)
# - Notifications: Telegram, Slack enabled
```

### Generate Example Configuration

Create example configuration files:

```python
from src.config.utils import generate_example_config

# Generate complete example
example_yaml = generate_example_config(include_comments=True)
with open("config.example.yaml", "w") as f:
    f.write(example_yaml)

# Generate minimal example
minimal_yaml = generate_example_config(minimal=True)
with open("config.minimal.yaml", "w") as f:
    f.write(minimal_yaml)
```

### Mask Sensitive Values

Safely log configuration without exposing secrets:

```python
from src.config.utils import mask_sensitive_values

config = load_config()
safe_config = mask_sensitive_values(config)

# Safe to log
logger.info(f"Configuration loaded: {safe_config}")
# Output: GitHub token: ghp_*****, API key: sk-ant-*****
```

### Configuration Comparison

Compare configurations:

```python
from src.config.tools.diff import compare_configs

config1 = load_config("config1.yaml")
config2 = load_config("config2.yaml")

diff = compare_configs(config1, config2)
print(diff)
# Output shows differences between configurations
```

### JSON Schema Generation

Generate JSON schema for external tools:

```python
from src.config.utils import generate_json_schema

# Generate schema for validation
schema = generate_json_schema()

# Save schema for IDE support
with open("config-schema.json", "w") as f:
    json.dump(schema, f, indent=2)
```

## Hot Reload

### Enable Hot Reload

Monitor configuration files for changes:

```python
from src.config.manager import ConfigurationManager

# Create configuration manager with hot reload
manager = ConfigurationManager(
    config_file="config.yaml",
    hot_reload=True,
    reload_interval=5  # Check every 5 seconds
)

# Register reload callback
async def on_config_change(old_config, new_config):
    print("Configuration reloaded!")
    # Update application state

manager.register_reload_callback(on_config_change)

# Start monitoring
await manager.start()

# Get current configuration
config = manager.get_config()
```

### Manual Reload

Reload configuration manually:

```python
# Manual reload
new_config = manager.reload_config()

# Check if configuration changed
if manager.has_changed():
    print("Configuration was updated")
    updated_config = manager.get_config()
```

### Hot Reload Limitations

- **Schema changes**: Cannot reload if model structure changes
- **Environment variables**: New env vars require restart
- **Validation errors**: Invalid configuration prevents reload
- **Performance**: Frequent reloads may impact performance

## Caching and Performance

### Configuration Caching

Configuration is automatically cached for performance:

```python
from src.config.cache import ConfigurationCache

# Configure caching behavior
cache = ConfigurationCache(
    enabled=True,
    ttl=300,          # 5-minute TTL
    max_size=100,     # Max 100 cached configs
    invalidate_on_change=True
)

# Load with caching
config = load_config(cache=cache)
```

### Performance Optimization

Optimize configuration loading:

```python
# Minimize validation overhead
config = load_config(
    cache_enabled=True,        # Enable caching
    validate_on_access=False,  # Validate only once
    lazy_loading=True          # Load sections on demand
)

# Preload configuration at startup
config = load_config()
config.preload_all_sections()  # Load all sections immediately
```

### Memory Usage

Monitor configuration memory usage:

```python
from src.config.metrics import get_config_metrics

metrics = get_config_metrics()
print(f"Memory usage: {metrics.memory_usage_mb} MB")
print(f"Cache hit rate: {metrics.cache_hit_rate}%")
print(f"Load time: {metrics.last_load_time_ms} ms")
```

## Testing Support

### Test Configuration

Create test configurations:

```python
from src.config.testing import create_test_config

# Minimal test configuration
test_config = create_test_config(
    database_url="sqlite:///:memory:",
    github_token="fake-token-for-testing",
    llm_provider="mock"
)

# Use in tests
def test_feature():
    with test_config:
        # Test code using test configuration
        pass
```

### Configuration Fixtures

Use pytest fixtures:

```python
import pytest
from src.config.testing import TestConfigurationManager

@pytest.fixture
def test_config():
    """Provide test configuration."""
    return create_test_config()

@pytest.fixture
def config_manager():
    """Provide test configuration manager."""
    manager = TestConfigurationManager()
    yield manager
    manager.cleanup()

def test_with_config(test_config):
    assert test_config.database.url == "sqlite:///:memory:"
```

### Mock Configuration

Mock configuration for unit tests:

```python
from unittest.mock import patch
from src.config.models import Config

# Mock configuration loading
test_config = Config(
    database=DatabaseConfig(url="sqlite:///:memory:"),
    github=GitHubConfig(token="test-token")
)

with patch('src.config.loader.load_config', return_value=test_config):
    # Test code that uses load_config()
    pass
```

## Best Practices

### Security

```python
# ✅ Use environment variables for secrets
database:
  url: "${DATABASE_URL}"  # From environment

github:
  token: "${GITHUB_TOKEN}"  # From environment

# ❌ Don't hardcode secrets
# github:
#   token: "ghp_hardcoded_token"  # Insecure
```

### Configuration Organization

```python
# ✅ Organize by environment
configs/
├── base.yaml          # Common configuration
├── development.yaml   # Development overrides
├── staging.yaml       # Staging environment
└── production.yaml    # Production environment

# Load environment-specific config
env = os.getenv("ENVIRONMENT", "development")
config = load_config(f"configs/{env}.yaml")
```

### Validation

```python
# ✅ Validate early and fail fast
try:
    config = load_config(validate_environment=True)
except ConfigurationValidationError as e:
    logger.error(f"Configuration invalid: {e}")
    sys.exit(1)

# ✅ Use type hints
def configure_database(db_config: DatabaseConfig) -> None:
    # Type-safe configuration usage
    engine = create_engine(db_config.url)
```

### Performance

```python
# ✅ Load configuration once at startup
config = load_config()

# ✅ Use caching for repeated access
config = load_config(cache_enabled=True)

# ❌ Don't reload configuration repeatedly
# for item in items:
#     config = load_config()  # Inefficient
```

### Testing

```python
# ✅ Use test-specific configuration
test_config = create_test_config(
    database_url="sqlite:///:memory:",
    external_apis_enabled=False
)

# ✅ Isolate configuration in tests
def test_feature():
    with test_config:
        # Test runs with isolated configuration
        pass
```

---

**Next Steps:**
- 📖 **Examples**: Check [Configuration Examples](examples/config-management.py) for complete working code
- 🗄️ **Database**: See [Database API Documentation](database-api.md) for database configuration
- 🧪 **Testing**: Review [Testing Guide](../developer/testing-guide.md) for configuration testing patterns