# Configuration Technical Troubleshooting Guide

> **📚 Navigation**: This guide covers **technical configuration validation and debugging issues**. For environment setup problems, see **[Installation Troubleshooting](../getting-started/installation.md#troubleshooting)**. For operational issues after configuration, see **[User Troubleshooting Guide](../user-guide/troubleshooting.md)**.

This guide helps developers and advanced users diagnose and resolve technical configuration system issues, validation problems, and programmatic configuration management challenges.

## Table of Contents

- [Quick Configuration Diagnostics](#quick-configuration-diagnostics)
- [Schema Validation Issues](#schema-validation-issues)
- [Environment Variable Substitution](#environment-variable-substitution)
- [Configuration Loading Problems](#configuration-loading-problems)
- [Programmatic Configuration Issues](#programmatic-configuration-issues)
- [Configuration Performance Issues](#configuration-performance-issues)
- [Advanced Debugging](#advanced-debugging)
- [Getting Help](#getting-help)

## Quick Configuration Diagnostics

> **📋 Prerequisites**: For basic environment setup (missing files, Python installation), see **[Installation Troubleshooting](../getting-started/installation.md#troubleshooting)**.

### Configuration System Health Check

```python
# Comprehensive configuration diagnostic
from src.config import load_config, validate_config
from src.config.tools import ConfigurationValidator
import logging

def diagnose_configuration():
    print("=== Configuration System Diagnostic ===")
    
    # 1. Configuration loading
    try:
        config = load_config()
        print("✅ Configuration loads successfully")
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        return False
    
    # 2. Schema validation
    try:
        validator = ConfigurationValidator(config)
        errors, warnings = validator.validate_full()
        if errors:
            print(f"❌ Schema validation errors: {len(errors)}")
            for error in errors[:3]:  # Show first 3 errors
                print(f"   - {error}")
        else:
            print("✅ Schema validation passed")
    except Exception as e:
        print(f"❌ Schema validation failed: {e}")
    
    # 3. Environment variable resolution
    try:
        from src.config.utils import check_environment_variables
        missing_vars = check_environment_variables(config)
        if missing_vars:
            print(f"⚠️ Missing environment variables: {missing_vars}")
        else:
            print("✅ All environment variables resolved")
    except Exception as e:
        print(f"❌ Environment variable check failed: {e}")
    
    print("=== End Diagnostic ===")

# Run diagnostic
diagnose_configuration()
```

### Configuration Validation Quick Check

```bash
# Use built-in configuration validation tool
python -m src.config.tools validate --verbose

# Check specific configuration sections
python -c "
from src.config import load_config
config = load_config()

# Validate critical sections
sections = ['database', 'llm', 'github', 'notification']
for section in sections:
    if hasattr(config, section):
        print(f'✅ {section}: configured')
    else:
        print(f'❌ {section}: missing')
"
```

## Schema Validation Issues

### Issue: Pydantic Validation Errors

**Symptoms:**
```
pydantic.ValidationError: 2 validation errors for Config
database.pool_size
  ensure this value is greater than 0 (type=value_error.number.not_gt; limit_value=0)
llm.anthropic.api_key
  field required (type=value_error.missing)
```

**Diagnosis:**
```python
# Detailed validation error analysis
from src.config import load_config
from pydantic import ValidationError

try:
    config = load_config()
except ValidationError as e:
    print("Validation errors found:")
    for error in e.errors():
        field_path = ' → '.join(str(loc) for loc in error['loc'])
        print(f"  {field_path}: {error['msg']}")
        print(f"    Input value: {error['input']}")
        print(f"    Error type: {error['type']}")
        print()
```

**Solutions:**

1. **Fix data types:**
   ```yaml
   # ❌ Wrong data type
   database:
     pool_size: "20"  # String instead of int
   
   # ✅ Correct data type
   database:
     pool_size: 20    # Integer
   ```

2. **Add missing required fields:**
   ```yaml
   # ❌ Missing required field
   llm:
     anthropic: {}    # Missing api_key
   
   # ✅ Include required fields
   llm:
     anthropic:
       api_key: "${ANTHROPIC_API_KEY}"
   ```

3. **Validate value ranges:**
   ```yaml
   # ❌ Invalid range
   database:
     pool_size: -1    # Negative value
   
   # ✅ Valid range
   database:
     pool_size: 20    # Positive integer
   ```

### Issue: Custom Validation Rule Failures

**Symptoms:**
```
ValueError: GitHub repositories must have unique URLs
ValueError: Default LLM provider 'openai' not found in configuration
```

**Diagnosis:**
```python
# Check custom validation rules
from src.config import load_config
from src.config.validators import ConfigValidator

try:
    config = load_config()
    validator = ConfigValidator(config)
    
    # Run custom validations
    business_rules_errors = validator.validate_business_rules()
    cross_field_errors = validator.validate_cross_field_references()
    
    print("Business rule errors:", business_rules_errors)
    print("Cross-field errors:", cross_field_errors)
    
except Exception as e:
    print(f"Custom validation error: {e}")
```

**Solutions:**

1. **Fix cross-field references:**
   ```yaml
   # ❌ Reference to non-existent provider
   default_llm_provider: openai
   llm:
     anthropic: {...}  # openai not configured
   
   # ✅ Reference existing provider
   default_llm_provider: anthropic
   llm:
     anthropic: {...}
   ```

2. **Ensure unique constraints:**
   ```yaml
   # ❌ Duplicate repository URLs
   repositories:
     - url: "https://github.com/org/repo"
     - url: "https://github.com/org/repo"  # Duplicate
   
   # ✅ Unique repository URLs
   repositories:
     - url: "https://github.com/org/repo1"
     - url: "https://github.com/org/repo2"
   ```

### ❌ YAML Parsing Errors

**Symptoms**
```
yaml.scanner.ScannerError: while scanning a simple key
  in "config.yaml", line 15, column 1
```

**Common Causes**
- Invalid YAML syntax
- Incorrect indentation
- Missing quotes around special characters
- Unicode encoding issues

**Solutions**

1. **Validate YAML syntax**
   ```bash
   # Test YAML parsing
   python -c "import yaml; yaml.safe_load(open('config.yaml'))"
   
   # Or use online validator: https://yaml-online-parser.appspot.com/
   ```

2. **Fix common syntax issues**
   ```yaml
   # ❌ Wrong indentation
   database:
     url: "postgresql://..."
       pool_size: 10  # Too much indentation
   
   # ✅ Correct indentation  
   database:
     url: "postgresql://..."
     pool_size: 10
   ```

   ```yaml
   # ❌ Missing quotes for special characters
   password: p@ssw0rd!
   
   # ✅ Quoted special characters
   password: "p@ssw0rd!"
   ```

3. **Check file encoding**
   ```bash
   file config.yaml  # Should show UTF-8
   ```

### ❌ Environment Variable Substitution Fails

**Symptoms**
```
ValueError: Required environment variable 'DATABASE_URL' not found
```

**Common Causes**
- Environment variable not set
- Variable name mismatch
- Incorrect substitution syntax
- Variable set in different shell session

**Solutions**

1. **Check if variable is set**
   ```bash
   echo $DATABASE_URL
   env | grep DATABASE_URL
   ```

2. **Set missing variables**
   ```bash
   export DATABASE_URL="postgresql://user:pass@localhost:5432/db"
   ```

3. **Fix substitution syntax**
   ```yaml
   # ❌ Wrong syntax
   url: "$DATABASE_URL"
   url: "$(DATABASE_URL)"
   
   # ✅ Correct syntax
   url: "${DATABASE_URL}"
   url: "${DATABASE_URL:default_value}"
   ```

4. **Use .env file**
   ```bash
   # Create .env file
   echo "DATABASE_URL=postgresql://..." > .env
   
   # Source it
   source .env
   ```

## Database Configuration Issues

### ❌ Database Connection Failed

**Symptoms**
```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) 
could not connect to server: Connection refused
```

**Diagnosis**
```python
# Test database connectivity
from src.database.connection import test_connection

try:
    test_connection("postgresql://user:pass@localhost:5432/db")
    print("✅ Database connection successful")
except Exception as e:
    print(f"❌ Database connection failed: {e}")
```

**Common Solutions**

1. **Check database service**
   ```bash
   # PostgreSQL
   sudo systemctl status postgresql
   sudo systemctl start postgresql
   
   # Docker
   docker ps | grep postgres
   docker start postgres_container
   ```

2. **Verify connection parameters**
   ```bash
   # Test with psql
   psql "postgresql://user:pass@localhost:5432/db"
   
   # Test with telnet
   telnet localhost 5432
   ```

3. **Check database URL format**
   ```yaml
   # ✅ Correct formats
   url: "postgresql://user:pass@localhost:5432/dbname"
   url: "mysql://user:pass@localhost:3306/dbname" 
   url: "sqlite:///./local.db"
   
   # ❌ Common mistakes
   url: "postgres://..."  # Should be postgresql://
   url: "postgresql://localhost/db"  # Missing user/pass
   ```

### ❌ Database Authentication Failed

**Symptoms**
```
psycopg2.OperationalError: FATAL: password authentication failed for user "username"
```

**Solutions**

1. **Verify credentials**
   ```bash
   # Test authentication
   psql -h localhost -U username -d dbname
   ```

2. **Check pg_hba.conf** (PostgreSQL)
   ```bash
   # Find config location
   sudo -u postgres psql -c "SHOW hba_file;"
   
   # Edit authentication rules
   sudo vim /etc/postgresql/14/main/pg_hba.conf
   ```

3. **Reset password**
   ```sql
   -- As postgres superuser
   ALTER USER username PASSWORD 'new_password';
   ```

## LLM Provider Issues

### ❌ API Key Authentication Failed

**Symptoms**
```
anthropic.AuthenticationError: API key not valid
openai.error.AuthenticationError: Incorrect API key provided
```

**Diagnosis**
```python
# Test API key format
import os

key = os.getenv('ANTHROPIC_API_KEY')
if key:
    print(f"Key format: {key[:7]}...{key[-4:]}")
    print(f"Key length: {len(key)}")
    print(f"Starts correctly: {key.startswith('sk-ant-')}")
else:
    print("❌ API key not set")
```

**Solutions**

1. **Verify API key format**
   ```bash
   # Anthropic keys start with sk-ant-
   echo $ANTHROPIC_API_KEY | grep "^sk-ant-"
   
   # OpenAI keys start with sk-
   echo $OPENAI_API_KEY | grep "^sk-"
   ```

2. **Check key permissions**
   - Log into provider dashboard
   - Verify key is active and not expired
   - Check usage limits and billing

3. **Test with curl**
   ```bash
   # Anthropic
   curl -H "x-api-key: $ANTHROPIC_API_KEY" \
        -H "content-type: application/json" \
        https://api.anthropic.com/v1/messages
   
   # OpenAI  
   curl -H "Authorization: Bearer $OPENAI_API_KEY" \
        https://api.openai.com/v1/models
   ```

### ❌ Rate Limit Exceeded

**Symptoms**
```
anthropic.RateLimitError: Rate limit exceeded
openai.error.RateLimitError: You exceeded your current quota
```

**Solutions**

1. **Check usage and limits**
   - Review API provider dashboard
   - Monitor request rates and quotas

2. **Adjust rate limiting in config**
   ```yaml
   llm:
     anthropic:
       rate_limit_rpm: 500  # Reduce from default
       timeout: 120         # Increase timeout
   ```

3. **Implement backoff strategy**
   ```python
   import time
   from functools import wraps
   
   def retry_with_backoff(max_retries=3):
       def decorator(func):
           @wraps(func)
           def wrapper(*args, **kwargs):
               for attempt in range(max_retries):
                   try:
                       return func(*args, **kwargs)
                   except RateLimitError:
                       if attempt < max_retries - 1:
                           wait_time = 2 ** attempt
                           time.sleep(wait_time)
                       else:
                           raise
               return wrapper
       return decorator
   ```

## Queue Configuration Issues

### ❌ Redis Connection Failed

**Symptoms**
```
redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379. Connection refused.
```

**Diagnosis**
```python
# Test Redis connectivity
import redis

try:
    r = redis.from_url("redis://localhost:6379/0")
    r.ping()
    print("✅ Redis connection successful")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")
```

**Solutions**

1. **Check Redis service**
   ```bash
   # Check if Redis is running
   sudo systemctl status redis
   sudo systemctl start redis
   
   # Or with Docker
   docker ps | grep redis
   docker start redis_container
   ```

2. **Test Redis CLI**
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

3. **Check Redis configuration**
   ```bash
   # Check Redis config
   redis-cli CONFIG GET "*"
   
   # Check if password is required
   redis-cli CONFIG GET requirepass
   ```

### ❌ Queue Authentication Issues

**Symptoms**
```
redis.exceptions.AuthenticationError: Authentication required
```

**Solutions**

1. **Add password to URL**
   ```yaml
   queue:
     url: "redis://:password@localhost:6379/0"
   ```

2. **Use Redis AUTH**
   ```bash
   redis-cli -a your_password ping
   ```

## Notification Configuration Issues

### ❌ Telegram Bot Issues

**Symptoms**
```
telegram.error.Unauthorized: Unauthorized
```

**Diagnosis**
```python
# Test Telegram bot
import requests

bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
url = f"https://api.telegram.org/bot{bot_token}/getMe"

response = requests.get(url)
print(f"Bot info: {response.json()}")
```

**Solutions**

1. **Verify bot token**
   - Check token format: should be `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
   - Verify bot exists in Telegram

2. **Check chat ID**
   ```bash
   # Get chat updates to find chat ID
   curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"
   ```

### ❌ Slack Webhook Issues

**Symptoms**
```
requests.exceptions.HTTPError: 400 Client Error: Bad Request
```

**Solutions**

1. **Verify webhook URL format**
   ```
   https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX
   ```

2. **Test webhook**
   ```bash
   curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"Test message"}' \
        $SLACK_WEBHOOK_URL
   ```

## Repository Configuration Issues

### ❌ GitHub Authentication Failed

**Symptoms**
```
github.GithubException: 401 {'message': 'Bad credentials'}
```

**Diagnosis**
```python
# Test GitHub token
import requests

headers = {'Authorization': f'token {os.getenv("GITHUB_TOKEN")}'}
response = requests.get('https://api.github.com/user', headers=headers)
print(f"GitHub API response: {response.status_code}")
```

**Solutions**

1. **Verify token format**
   ```bash
   # Classic tokens start with ghp_
   echo $GITHUB_TOKEN | grep "^ghp_"
   
   # Fine-grained tokens start with github_pat_
   echo $GITHUB_TOKEN | grep "^github_pat_"
   ```

2. **Check token permissions**
   - Go to GitHub Settings > Developer settings > Personal access tokens
   - Verify token has required scopes: `repo`, `workflow`

3. **Test token**
   ```bash
   curl -H "Authorization: token $GITHUB_TOKEN" \
        https://api.github.com/user
   ```

## Performance Issues

### ❌ Slow Configuration Loading

**Symptoms**
- Application takes long time to start
- Configuration access is slow
- High memory usage

**Diagnosis**
```python
# Enable performance metrics
from src.config import ConfigurationManager
import time

start = time.time()
manager = ConfigurationManager(enable_metrics=True)
config = manager.load_configuration()
load_time = time.time() - start

print(f"Configuration load time: {load_time:.2f}s")

# Check cache performance
metrics = manager.get_performance_metrics()
print(f"Cache hit rate: {metrics.get('cache', {}).get('hit_rate', 0):.2%}")
```

**Solutions**

1. **Enable caching**
   ```python
   manager = ConfigurationManager(
       enable_caching=True,  # Enable caching
       enable_metrics=True   # Monitor performance
   )
   ```

2. **Pre-warm cache**
   ```python
   # Warm critical configuration paths
   manager.warm_cache([
       'database.url',
       'default_llm_provider',
       'system.environment'
   ])
   ```

3. **Optimize configuration file**
   - Remove unused configuration sections
   - Use environment variables for dynamic values
   - Minimize validation overhead

## Validation Issues

### ❌ Cross-Field Validation Errors

**Symptoms**
```
ValidationError: default_llm_provider 'openai' not found in llm configuration
```

**Solutions**

1. **Ensure referenced providers exist**
   ```yaml
   # ❌ Missing provider
   default_llm_provider: openai
   llm:
     anthropic: { ... }  # openai missing
   
   # ✅ Provider exists
   default_llm_provider: openai
   llm:
     openai: { ... }      # openai configured
     anthropic: { ... }
   ```

2. **Check notification channel references**
   ```yaml
   notification:
     channels:
       - provider: telegram  # Must be valid NotificationProvider
         telegram_bot_token: "${TELEGRAM_BOT_TOKEN}"
   ```

## Debug Mode

Enable debug mode for detailed troubleshooting:

```yaml
system:
  debug_mode: true
  log_level: DEBUG
```

```python
# Verbose configuration loading
import logging
logging.basicConfig(level=logging.DEBUG)

from src.config import load_config
config = load_config()  # Will show detailed debug info
```

## Getting Help

### Configuration Validation Tool

Use the built-in validation tool:

```bash
# Validate current configuration  
python -m src.config.tools validate

# Validate specific file
python -m src.config.tools validate --config config.yaml

# Include connectivity checks
python -m src.config.tools validate --check-connectivity
```

### Health Check

Check overall system health:

```python
from src.config import ConfigurationManager

manager = ConfigurationManager(enable_metrics=True)
config = manager.load_configuration()

health = manager.get_health_status()
print(f"Health status: {health['status']}")
if health['issues']:
    print(f"Issues: {health['issues']}")
```

### Support Channels

- **Configuration errors**: Check this troubleshooting guide first
- **Environment-specific issues**: See [examples](../../config/examples/) directory
- **Security concerns**: Review [security guide](security.md)
- **Performance issues**: Enable metrics and check cache statistics
- **Bug reports**: File an issue with configuration details and error logs

### Collecting Debug Information

When reporting issues, include:

```bash
# System information
python --version
pip list | grep -E "(pydantic|yaml|redis|psycopg2)"

# Configuration validation
python -c "
from src.config import load_config, validate_config, mask_sensitive_values
try:
    config = load_config()
    errors, warnings = validate_config(config)
    safe_config = mask_sensitive_values(config.dict())
    print(f'Config loaded: {bool(config)}')
    print(f'Errors: {len(errors)}')
    print(f'Warnings: {len(warnings)}')
    print(f'Config summary: {list(safe_config.keys())}')
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
"

# Environment variables (without values)
env | grep -E "(DATABASE|REDIS|GITHUB|ANTHROPIC|OPENAI)" | cut -d= -f1
```