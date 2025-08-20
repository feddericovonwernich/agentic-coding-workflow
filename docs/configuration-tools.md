# Configuration Tools Documentation

This document provides comprehensive guidance on using the configuration validation and comparison tools included in the Agentic Coding Workflow system.

## Overview

The configuration tools help ensure configuration correctness, security, and consistency across different environments. There are two main tools:

1. **Configuration Validator** (`validate.py`) - Validates configuration files for correctness, security, and performance
2. **Configuration Diff** (`diff.py`) - Compares configuration files and identifies important differences

## Configuration Validator

### Purpose

The Configuration Validator performs comprehensive validation of configuration files, checking for:
- Schema compliance with Pydantic models
- Missing or invalid environment variables
- Security best practices and potential vulnerabilities
- Performance optimization opportunities
- External service connectivity (optional)

### Usage

#### Basic Usage

```bash
# Validate default config.yaml
python -m src.config.tools.validate

# Validate a specific configuration file
python -m src.config.tools.validate --config production.yaml
```

#### Advanced Usage

```bash
# Enable verbose output for detailed information
python -m src.config.tools.validate --verbose

# Test connectivity to external services (requires network access)
python -m src.config.tools.validate --check-connectivity --verbose

# Get JSON output for automation/CI pipelines
python -m src.config.tools.validate --json

# Validate only the schema (skip other checks)
python -m src.config.tools.validate --schema-only

# Focus only on security validation
python -m src.config.tools.validate --security-only

# Skip security checks (not recommended)
python -m src.config.tools.validate --no-security

# Skip performance checks
python -m src.config.tools.validate --no-performance
```

### Validation Categories

#### Schema Validation
- Validates configuration structure against Pydantic models
- Ensures all required fields are present
- Checks data types and formats

#### Environment Variable Validation  
- Identifies missing required environment variables
- Detects potentially insecure default values for sensitive variables
- Validates environment variable references in configuration

#### Security Validation
- **Hardcoded Secrets Detection**: Scans for API keys, tokens, and passwords in configuration
- **SSL/TLS Configuration**: Checks for unencrypted database and queue connections
- **Authentication Configuration**: Validates API keys and authentication tokens
- **Logging Security**: Identifies potential security issues in logging configuration

#### Performance Validation
- **Database Configuration**: Validates connection pool settings and timeouts
- **Queue Configuration**: Checks batch sizes and visibility timeouts
- **LLM Configuration**: Validates timeout and rate limiting settings
- **System Configuration**: Reviews worker timeouts and retry settings

#### Connectivity Testing (Optional)
- **Database Connectivity**: Tests database connections
- **Queue Connectivity**: Tests Redis/queue connections  
- **LLM Provider Connectivity**: Tests API connectivity for Anthropic, OpenAI, Azure OpenAI
- **Notification Connectivity**: Tests Slack, Telegram, and webhook endpoints

### Output Formats

#### Human-Readable Output (Default)
```
📋 Configuration Validation Report
==================================================
Config file: production.yaml

❌ ERRORS (2):
  • Missing required environment variable: GITHUB_TOKEN
  • Configuration error: Invalid API key format

⚠️  WARNINGS (3):
  • Database URL does not specify SSL mode
  • LLM provider timeout is quite short
  • Debug mode enabled in production environment

💡 RECOMMENDATIONS (1):
  • Consider increasing database pool size for better performance

📊 SUMMARY:
  Errors: 2
  Warnings: 3
  Recommendations: 1

❌ Configuration validation failed!
```

#### JSON Output (for automation)
```json
{
  "config_file": "production.yaml",
  "validation_success": false,
  "errors": [
    "Missing required environment variable: GITHUB_TOKEN"
  ],
  "warnings": [
    "Database URL does not specify SSL mode"
  ],
  "recommendations": [
    "Consider increasing database pool size for better performance"
  ],
  "summary": {
    "error_count": 1,
    "warning_count": 1,
    "recommendation_count": 1
  }
}
```

## Configuration Diff Tool

### Purpose

The Configuration Diff tool compares configuration files between environments and identifies:
- Added, removed, or changed configuration values
- Security-sensitive changes requiring special attention
- Performance-critical modifications
- Type changes that might break compatibility
- Provides migration recommendations

### Usage

#### Basic Usage

```bash
# Compare two configuration files
python -m src.config.tools.diff config1.yaml config2.yaml

# Compare development and production configs
python -m src.config.tools.diff config/examples/development.yaml config/examples/production.yaml
```

#### Advanced Usage

```bash
# Enable verbose output
python -m src.config.tools.diff --verbose config1.yaml config2.yaml

# Get JSON output for automation
python -m src.config.tools.diff --json config1.yaml config2.yaml

# Show actual values (be careful with sensitive data!)
python -m src.config.tools.diff --show-values config1.yaml config2.yaml

# Focus on security-related changes only
python -m src.config.tools.diff --security-focus config1.yaml config2.yaml

# Focus on performance-related changes only
python -m src.config.tools.diff --performance-focus config1.yaml config2.yaml

# Filter by severity level (low, medium, high, critical)
python -m src.config.tools.diff --severity-filter high config1.yaml config2.yaml
```

### Difference Types

- **Added**: New configuration keys introduced
- **Removed**: Configuration keys that were removed
- **Changed**: Configuration values that were modified
- **Type Changed**: Configuration values that changed data types

### Severity Levels

- **Critical**: Security-sensitive removals, file loading errors
- **High**: Security-sensitive changes, type changes, environment changes
- **Medium**: Performance-critical changes, feature toggles
- **Low**: Minor configuration adjustments

### Security-Sensitive Paths

The tool automatically identifies security-sensitive configuration paths:
- Database URLs and credentials
- API keys and authentication tokens
- Notification service credentials  
- Repository authentication tokens

### Performance-Critical Paths

Performance-critical configuration paths are monitored for:
- Database pool settings
- Queue batch sizes and timeouts
- LLM provider rate limits and timeouts
- System worker configurations

### Output Formats

#### Human-Readable Output (Default)
```
📋 Configuration Comparison Report
============================================================
Baseline:   development.yaml
Comparison: production.yaml

📊 SUMMARY:
  Total differences: 8
  Critical: 1
  High: 2
  Medium: 3
  Low: 2

🚨 CRITICAL CHANGES:
  • system.environment (changed)

🔒 SECURITY CHANGES:
  • database.url (changed)
  • llm.anthropic.api_key (changed)

⚡ PERFORMANCE CHANGES:
  • database.pool_size (changed)
  • queue.batch_size (changed)

📝 DETAILED DIFFERENCES:

🚨 🔄 system.environment
   Configuration value changed: system.environment
   Old: development
   New: production
   Recommendations:
   • CRITICAL: Environment changed - ensure deployment target is correct
   • Review all environment-specific configurations

🔴 🔄 database.pool_size
   Configuration value changed: database.pool_size
   Old: 5
   New: 20
   Recommendations:
   • Performance-critical value changed - monitor system performance
   • Test database connectivity after applying changes
```

#### JSON Output (for automation)
```json
{
  "comparison": {
    "config1": "development.yaml",
    "config2": "production.yaml"
  },
  "summary": {
    "total_differences": 8,
    "by_severity": {
      "critical": 1,
      "high": 2,
      "medium": 3,
      "low": 2
    },
    "critical_changes": [
      {
        "path": "system.environment",
        "type": "changed",
        "description": "Configuration value changed: system.environment"
      }
    ]
  },
  "differences": [
    {
      "path": "system.environment",
      "type": "changed",
      "severity": "critical",
      "description": "Configuration value changed: system.environment",
      "old_value": "development",
      "new_value": "production",
      "recommendations": [
        "CRITICAL: Environment changed - ensure deployment target is correct"
      ]
    }
  ]
}
```

## Integration with CI/CD

### Validation in CI Pipeline

```yaml
# Example GitHub Actions workflow
- name: Validate Configuration
  run: |
    python -m src.config.tools.validate --json config/production.yaml > validation-report.json
    # Fail if validation errors exist
    if [ $(jq '.summary.error_count' validation-report.json) -gt 0 ]; then
      echo "Configuration validation failed"
      exit 1
    fi
```

### Configuration Drift Detection

```yaml
# Example configuration drift detection
- name: Check Configuration Drift  
  run: |
    python -m src.config.tools.diff --json \
      config/production-baseline.yaml config/production.yaml \
      > config-drift-report.json
    
    # Alert on critical changes
    if [ $(jq '.summary.by_severity.critical' config-drift-report.json) -gt 0 ]; then
      echo "Critical configuration changes detected"
      # Send alert to operations team
    fi
```

## Best Practices

### Development Workflow

1. **Validate Early**: Run validation during development before committing
```bash
python -m src.config.tools.validate --config config/development.yaml
```

2. **Compare Before Deploy**: Always compare configurations before deployment
```bash
python -m src.config.tools.diff config/staging.yaml config/production.yaml
```

3. **Security Review**: Use security-focused validation for production configs
```bash
python -m src.config.tools.validate --security-only config/production.yaml
```

### Environment Management

1. **Environment-Specific Validation**: Validate each environment's configuration
2. **Baseline Tracking**: Keep baseline configurations for drift detection
3. **Sensitive Data**: Never commit configurations with real secrets - use environment variables

### Automation Integration

1. **CI/CD Integration**: Include validation in your CI/CD pipelines
2. **Monitoring**: Set up automated configuration drift detection
3. **Alerting**: Alert operations teams on critical configuration changes

## Troubleshooting

### Common Issues

#### Missing Environment Variables
```bash
# Use verbose mode to see which variables are missing
python -m src.config.tools.validate --verbose
```

#### Connectivity Test Failures
```bash
# Run with connectivity tests to identify network issues
python -m src.config.tools.validate --check-connectivity --verbose
```

#### Configuration Parsing Errors
- Ensure YAML syntax is correct
- Check for proper indentation
- Validate environment variable references use `${VAR_NAME}` format

### Getting Help

- Use `--help` with either tool for command-line help
- Check the verbose output for detailed validation information
- Review the JSON output for programmatic integration

## Examples

### Example Configuration Files

The system includes example configuration files in `config/examples/`:
- `development.yaml` - Development environment configuration
- `production.yaml` - Production environment configuration  
- `features/cost-optimization.yaml` - Cost-optimized configuration
- `features/enhanced-security.yaml` - Security-hardened configuration

### Validate Example Configs

```bash
# Validate development configuration
python -m src.config.tools.validate --config config/examples/development.yaml

# Compare cost-optimized vs security-enhanced configs
python -m src.config.tools.diff \
  config/examples/features/cost-optimization.yaml \
  config/examples/features/enhanced-security.yaml \
  --verbose
```

This comprehensive tooling ensures your configuration management is robust, secure, and maintainable across all environments.