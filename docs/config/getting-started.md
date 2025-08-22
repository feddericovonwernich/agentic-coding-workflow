# Getting Started with Configuration

This guide will help you set up the configuration system in under 15 minutes. Follow these steps to get running quickly.

## Prerequisites

- Python 3.9 or higher
- Basic understanding of YAML format
- Environment variables setup capability

## Step 1: Copy Example Configuration (2 minutes)

Start by copying the example configuration file:

```bash
# Copy the example configuration
cp config.example.yaml config.yaml
```

This creates your local configuration file that won't be committed to version control.

## Step 2: Set Required Environment Variables (5 minutes)

The configuration system requires certain environment variables. Create a `.env` file or set them in your shell:

### Minimal Required Variables

```bash
# Database Configuration
export DATABASE_URL="sqlite:///./agentic.db"  # For local development

# GitHub Integration
export GITHUB_TOKEN="ghp_your_github_token_here"

# LLM Provider (choose one)
export ANTHROPIC_API_KEY="sk-ant-your_anthropic_key_here"
# OR
export OPENAI_API_KEY="sk-your_openai_key_here"
```

### Optional but Recommended

```bash
# Redis for production-like queue
export REDIS_URL="redis://localhost:6379/0"

# Notifications (optional for development)
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
export TELEGRAM_CHAT_ID="your_telegram_chat_id"
```

## Step 3: Basic Configuration Setup (3 minutes)

Edit your `config.yaml` file to customize for your environment:

```yaml
# Minimal development configuration
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

# Configure your preferred LLM provider
llm:
  anthropic:  # or openai
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: claude-3-sonnet-20240229
    max_tokens: 4000

default_llm_provider: anthropic  # or openai

# Add your repositories
repositories:
  - url: https://github.com/your-username/your-repo
    auth_token: "${GITHUB_TOKEN}"
    polling_interval: 300
```

## Step 4: Validate Configuration (2 minutes)

Test your configuration to ensure everything is set up correctly:

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

## Step 5: Test Integration (3 minutes)

Verify that your configuration works with the actual services:

```python
from src.config import load_config

config = load_config()

# Test database connection
print(f"Database URL: {config.database.url}")

# Test LLM provider
llm_config = config.llm[config.default_llm_provider]
print(f"Using LLM provider: {llm_config.provider}")

# Test repository configuration
for repo in config.repositories:
    print(f"Monitoring repository: {repo.url}")
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

## Common Quick Setup Scenarios

### Local Development (SQLite + In-Memory Queue)

```yaml
system:
  environment: development
  debug_mode: true

database:
  url: "sqlite:///./dev.db"

queue:
  provider: redis
  url: "redis://localhost:6379/0"
```

### Docker Development

```yaml
system:
  environment: development

database:
  url: "postgresql://user:pass@db:5432/agentic"

queue:
  provider: redis
  url: "redis://redis:6379/0"
```

### Cloud Development

```yaml
system:
  environment: staging

database:
  url: "${DATABASE_URL}"  # From cloud provider

queue:
  provider: sqs
  url: "${SQS_QUEUE_URL}"
```

## Next Steps

Now that you have basic configuration working:

1. **Explore Examples**: Check out [environment examples](../../config/examples/) for your deployment scenario
2. **Learn Security**: Review [security best practices](security.md) before production
3. **Understand Features**: Read the [full reference](reference.md) for advanced features
4. **Troubleshoot Issues**: Bookmark the [troubleshooting guide](troubleshooting.md)

## Troubleshooting Quick Setup

### Configuration File Not Found
```bash
# Ensure config.yaml exists in the right location
ls -la config.yaml

# Or specify explicit path
export AGENTIC_CONFIG_PATH="/path/to/your/config.yaml"
```

### Environment Variables Not Set
```bash
# Check if variables are set
env | grep -E "(DATABASE_URL|GITHUB_TOKEN|ANTHROPIC_API_KEY)"

# Source your .env file if using one
source .env
```

### Database Connection Issues
```bash
# Test database connectivity
python -c "
from src.config import load_config
from src.database import test_connection
config = load_config()
test_connection(config.database.url)
"
```

### LLM Provider Issues
```bash
# Verify API key format
python -c "
import os
key = os.getenv('ANTHROPIC_API_KEY')
print(f'Key format: {key[:7]}...{key[-4:] if key else None}')
print(f'Key length: {len(key) if key else 0}')
"
```

## Getting Help

- **Configuration validation errors**: See [troubleshooting guide](troubleshooting.md)
- **Environment-specific setup**: Check [examples directory](../../config/examples/)
- **Advanced features**: Read [configuration reference](reference.md)
- **Security questions**: Review [security guide](security.md)