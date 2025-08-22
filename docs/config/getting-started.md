# Configuration Technical Quick Start

> **📚 Navigation**: This guide covers **technical configuration setup** for developers who need to understand the configuration system internals. For complete environment setup, see **[Installation Guide](../getting-started/installation.md)**. For user scenarios and templates, see **[User Configuration Guide](../user-guide/configuration.md)**.

## Purpose

This guide focuses on the **technical aspects** of the configuration system - file management, validation, programmatic usage, and advanced features. It's designed for developers who need to understand how the configuration system works internally.

## Prerequisites

- Completed [basic installation and environment setup](../getting-started/installation.md)
- Understanding of YAML configuration format
- Python development experience

## Configuration File Management

### Step 1: Configuration File Setup

```bash
# Copy the example configuration
cp config.example.yaml config.yaml
```

This creates your local configuration file that won't be committed to version control.

### Step 2: Development-Specific Configuration

**Configuration-specific variables for development and debugging:**

```bash
# Enable configuration debugging
export CONFIG_DEBUG=true

# Configuration file validation
export CONFIG_VALIDATE_ON_LOAD=true

# Override default config location
export CONFIG_FILE_PATH=./config-dev.yaml
```

> **Note**: For complete environment variable setup (API keys, database URLs, etc.), see the **[Installation Guide](../getting-started/installation.md#environment-setup)**.

## Technical Configuration Structure

### Step 3: Minimal Technical Configuration

Create a minimal configuration for technical development:

```yaml
# Minimal technical configuration for developers
system:
  environment: development
  log_level: DEBUG
  debug_mode: true

database:
  url: "${DATABASE_URL}"
  pool_size: 5

queue:
  provider: redis
  url: "${REDIS_URL:redis://localhost:6379/0}"

llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: claude-3-sonnet-20240229

default_llm_provider: anthropic

repositories:
  - url: https://github.com/your-username/test-repo
    auth_token: "${GITHUB_TOKEN}"
    polling_interval: 300
```

> **For comprehensive configuration examples and user scenarios**, see the **[User Configuration Guide](../user-guide/configuration.md)**.

## Configuration Validation and Testing

### Step 4: Configuration Validation

Use the built-in validation tools to ensure your configuration is correct:

```python
from src.config import load_config, validate_config

# Load and validate configuration
try:
    config = load_config()
    print("✅ Configuration loaded successfully!")
    
    # Validate configuration
    errors, warnings = validate_config(config)
    
    if errors:
        print("❌ Configuration errors:", errors)
    elif warnings:
        print("⚠️  Configuration warnings:", warnings)
    else:
        print("✅ Configuration validation passed!")
        
except Exception as e:
    print(f"❌ Configuration error: {e}")
```

### Step 5: Configuration Testing

Verify that your configuration integrates properly with system components:

```python
from src.config import load_config

config = load_config()

# Test configuration loading
print(f"Environment: {config.system.environment}")
print(f"Debug mode: {config.system.debug_mode}")

# Test provider configuration
llm_config = config.llm[config.default_llm_provider]
print(f"LLM Provider: {llm_config.provider}")

# Test repository configuration
print(f"Monitoring {len(config.repositories)} repositories")
```

## Programmatic Usage

### Loading Configuration

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

### Configuration Loading Hierarchy

The system searches for configuration files in this order:

1. Explicit path provided to `load_config()`
2. Current working directory (`./config.yaml`)
3. `AGENTIC_CONFIG_PATH` environment variable
4. User config directory (`~/.agentic/config.yaml`)
5. System config directory (`/etc/agentic/config.yaml`)

### Testing Support

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

### Configuration Hot Reload

Configuration can be reloaded without restarting the application:

```python
from src.config import reload_config

# Reload configuration from the same source
updated_config = reload_config()
```

Note: Hot reload should be used carefully in production environments as it may cause inconsistent state if workers are processing tasks during reload.

## Advanced Technical Configuration

### Configuration Loading Behavior

Understanding how the configuration system searches for and loads files:

```python
from src.config import load_config

# Load with explicit validation
config = load_config(
    config_file="config.yaml",
    validate_environment=True,
    strict_mode=True  # Fail on warnings
)

# Load with custom search paths
config = load_config(
    search_paths=["./configs/", "/etc/agentic/"],
    fallback_to_minimal=False
)
```

### Environment-Specific Technical Settings

Technical configuration patterns for different environments:

```yaml
# Development - optimized for debugging
system:
  environment: development
  debug_mode: true
  log_level: DEBUG
  hot_reload: true

# Testing - optimized for CI/CD
system:
  environment: testing
  debug_mode: false
  log_level: WARNING
  timeout_multiplier: 2.0

# Production - optimized for performance
system:
  environment: production
  debug_mode: false
  log_level: INFO
  worker_pool_size: 16
```

## Advanced Configuration Topics

### Next Steps for Technical Configuration

Now that you understand the technical configuration system:

1. **Advanced Features**: Read the [full technical reference](reference.md) for all configuration options
2. **Security Implementation**: Review [security best practices](security.md) for production systems
3. **Configuration Tools**: Explore [configuration tools and utilities](tools.md) for validation and management
4. **API Integration**: See [Configuration API documentation](../api/configuration-api.md) for programmatic usage

### Technical Troubleshooting

#### Configuration System Issues

**Configuration file search problems**:
```bash
# Debug configuration file discovery
python -c "
from src.config.loader import ConfigLoader
loader = ConfigLoader(debug=True)
loader.discover_config_file()
"
```

**Configuration validation failures**:
```bash
# Run comprehensive configuration validation
python -c "
from src.config import load_config, validate_config
config = load_config()
errors, warnings = validate_config(config, verbose=True)
print(f'Errors: {errors}')
print(f'Warnings: {warnings}')
"
```

**Environment variable substitution issues**:
```bash
# Test environment variable resolution
python -c "
from src.config.models import BaseConfigModel
test_config = {'url': '\${TEST_VAR:default_value}'}
result = BaseConfigModel.substitute_env_vars(test_config)
print(f'Result: {result}')
"
```

> **For environment setup and service connectivity issues**, see the **[Installation Troubleshooting Guide](../getting-started/installation.md#troubleshooting)** and **[User Troubleshooting Guide](../user-guide/troubleshooting.md)**.

## Technical Configuration Resources

### Getting Help with Configuration

- **Technical configuration issues**: See [configuration troubleshooting guide](troubleshooting.md)
- **User scenario setup**: Check [user configuration guide](../user-guide/configuration.md)
- **Environment setup problems**: See [installation troubleshooting](../getting-started/installation.md#troubleshooting)
- **Complete technical reference**: Read [configuration reference](reference.md)
- **Configuration security**: Review [security best practices](security.md)
- **Programmatic usage**: See [Configuration API](../api/configuration-api.md)