# Configuration Security Best Practices

Security is critical when managing configuration that includes API keys, database credentials, and other sensitive information. This guide provides comprehensive security best practices for the Agentic Coding Workflow configuration system.

## Table of Contents

- [Environment Variable Security](#environment-variable-security)
- [Credential Management](#credential-management)  
- [File Permissions](#file-permissions)
- [Network Security](#network-security)
- [Secrets Management](#secrets-management)
- [Deployment Security](#deployment-security)
- [Monitoring and Auditing](#monitoring-and-auditing)
- [Common Security Mistakes](#common-security-mistakes)

## Environment Variable Security

### ✅ Use Environment Variables for Secrets

**DO**: Store all sensitive values in environment variables
```yaml
# config.yaml
database:
  url: "${DATABASE_URL}"
llm:
  anthropic:
    api_key: "${ANTHROPIC_API_KEY}"
notification:
  channels:
    - provider: telegram
      telegram_bot_token: "${TELEGRAM_BOT_TOKEN}"
```

**DON'T**: Store secrets directly in configuration files
```yaml
# ❌ NEVER DO THIS
database:
  url: "postgresql://user:password123@localhost:5432/db"
llm:
  anthropic:
    api_key: "sk-ant-actual-api-key-here"
```

### Environment Variable Naming

Use consistent, descriptive naming conventions:

**Good Examples**
```bash
export DATABASE_URL="..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GITHUB_TOKEN="ghp_..."
export TELEGRAM_BOT_TOKEN="..."
export REDIS_URL="redis://..."
```

**Bad Examples**
```bash
export DB="..."           # Too vague
export KEY="..."          # Which key?
export TELEGRAM="..."     # Missing context
export SECRET="..."       # Meaningless
```

### Environment Variable Validation

Validate environment variables on application startup:

```python
import os
from src.config import validate_environment_variables

# Check for missing required variables
required_vars = [
    "DATABASE_URL",
    "GITHUB_TOKEN", 
    "ANTHROPIC_API_KEY"
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {missing_vars}")
```

## Credential Management

### API Key Security

**GitHub Tokens**
- Use fine-grained personal access tokens when possible
- Limit token scope to only required permissions
- Set appropriate expiration dates
- Use different tokens for different environments

```bash
# Development token (limited scope)
export GITHUB_TOKEN="ghp_dev_token_with_limited_scope"

# Production token (minimal required permissions)  
export GITHUB_TOKEN="ghp_prod_token_minimal_perms"
```

**LLM Provider Keys**
- Never share API keys between environments
- Use separate keys for development, staging, production
- Monitor API key usage and set up billing alerts
- Rotate keys regularly

```bash
# Separate keys per environment
export ANTHROPIC_API_KEY_DEV="sk-ant-dev-..."
export ANTHROPIC_API_KEY_PROD="sk-ant-prod-..."
```

### Database Credentials

**Connection String Security**
```bash
# ✅ Good: Use connection pooling and SSL
export DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=require"

# ❌ Bad: Plain text, no SSL
export DATABASE_URL="postgresql://user:password@host:5432/db"
```

**Database User Permissions**
- Use least privilege principle
- Create dedicated database users for the application
- Grant only necessary permissions
- Use different users for read/write operations if possible

```sql
-- Create application-specific user
CREATE USER agentic_app WITH PASSWORD 'secure_password';

-- Grant minimal required permissions
GRANT CONNECT ON DATABASE agentic TO agentic_app;
GRANT USAGE ON SCHEMA public TO agentic_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agentic_app;

-- Revoke dangerous permissions
REVOKE CREATE ON SCHEMA public FROM agentic_app;
```

## File Permissions

### Configuration File Security

Set restrictive permissions on configuration files:

```bash
# Set secure permissions (owner read/write only)
chmod 600 config.yaml
chmod 600 .env

# Verify permissions
ls -la config.yaml .env
# Should show: -rw------- (600)
```

### Directory Security

Secure configuration directories:

```bash
# Home directory config
mkdir -p ~/.agentic
chmod 700 ~/.agentic
chmod 600 ~/.agentic/config.yaml

# System config
sudo mkdir -p /etc/agentic
sudo chmod 755 /etc/agentic
sudo chmod 600 /etc/agentic/config.yaml
sudo chown root:root /etc/agentic/config.yaml
```

### Git Security

Prevent accidental commits of sensitive files:

**.gitignore**
```gitignore
# Configuration files with secrets
config.yaml
config.local.yaml
config.*.yaml
!config.example.yaml

# Environment files  
.env
.env.local
.env.*.local

# Runtime files that might contain secrets
*.log
*.pid
tmp/
logs/
```

**.gitattributes** (Additional protection)
```gitattributes
# Prevent accidental commits of sensitive files
config.yaml filter=git-crypt diff=git-crypt
.env filter=git-crypt diff=git-crypt
```

## Network Security

### TLS/SSL Configuration

Always use encrypted connections:

**Database Connections**
```yaml
database:
  # PostgreSQL with SSL
  url: "${DATABASE_URL}?sslmode=require"
  
  # MySQL with SSL
  url: "${DATABASE_URL}?ssl=true&sslmode=REQUIRED"
```

**Redis Connections**
```yaml
queue:
  # Redis with TLS
  url: "rediss://username:password@host:6380/0"
  
  # Redis with SSL certificate verification
  url: "rediss://host:6380/0?ssl_cert_reqs=required"
```

**API Endpoints**
```yaml
llm:
  anthropic:
    endpoint: "https://api.anthropic.com"  # Always HTTPS
  
  custom:
    endpoint: "https://your-api.com/v1"    # Never HTTP
```

### Network Segmentation

Use network security controls:

**Firewall Rules**
```bash
# Allow only necessary ports
sudo ufw allow 22    # SSH
sudo ufw allow 443   # HTTPS
sudo ufw deny 5432   # PostgreSQL (internal only)
sudo ufw deny 6379   # Redis (internal only)
```

**VPC/Network Policies** (Cloud environments)
- Place databases in private subnets
- Use security groups to limit access
- Enable VPC flow logs for monitoring
- Use VPN or bastion hosts for administrative access

## Secrets Management

### Cloud Secrets Management

**AWS Secrets Manager**
```python
import boto3
from src.config import Config

def load_secrets_from_aws():
    client = boto3.client('secretsmanager')
    
    # Load database credentials
    db_secret = client.get_secret_value(SecretId='prod/database')
    os.environ['DATABASE_URL'] = db_secret['SecretString']
    
    # Load API keys
    api_secret = client.get_secret_value(SecretId='prod/api-keys')
    secrets = json.loads(api_secret['SecretString'])
    os.environ['ANTHROPIC_API_KEY'] = secrets['anthropic_key']
```

**Azure Key Vault**
```python
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

def load_secrets_from_azure():
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url="https://vault.vault.azure.net/", credential=credential)
    
    os.environ['DATABASE_URL'] = client.get_secret("database-url").value
    os.environ['ANTHROPIC_API_KEY'] = client.get_secret("anthropic-api-key").value
```

**Kubernetes Secrets**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: agentic-secrets
type: Opaque
data:
  database-url: <base64-encoded-url>
  anthropic-api-key: <base64-encoded-key>
  github-token: <base64-encoded-token>
```

### HashiCorp Vault Integration

```python
import hvac

def load_secrets_from_vault():
    client = hvac.Client(url='https://vault.example.com')
    client.token = os.environ['VAULT_TOKEN']
    
    # Read secrets
    secret = client.secrets.kv.v2.read_secret_version(path='agentic/prod')
    
    os.environ['DATABASE_URL'] = secret['data']['data']['database_url']
    os.environ['ANTHROPIC_API_KEY'] = secret['data']['data']['anthropic_key']
```

## Deployment Security

### Container Security

**Docker Secrets**
```dockerfile
# Use multi-stage builds to avoid secrets in final image
FROM python:3.11 as builder
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /root/.local /root/.local

# Don't copy config files into image
COPY src/ /app/src/
WORKDIR /app

# Use secrets at runtime
CMD ["python", "-m", "src.main"]
```

**Docker Compose with Secrets**
```yaml
version: '3.8'
services:
  agentic:
    image: agentic-workflow
    secrets:
      - database_url
      - anthropic_api_key
    environment:
      DATABASE_URL_FILE: /run/secrets/database_url
      ANTHROPIC_API_KEY_FILE: /run/secrets/anthropic_api_key

secrets:
  database_url:
    external: true
  anthropic_api_key:
    external: true
```

### Kubernetes Security

**Secret Management**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentic-workflow
spec:
  template:
    spec:
      containers:
      - name: agentic
        image: agentic-workflow:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: agentic-secrets
              key: database-url
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: agentic-secrets
              key: anthropic-api-key
```

**Service Account and RBAC**
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: agentic-service-account
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: secret-reader
rules:
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: read-secrets
subjects:
- kind: ServiceAccount
  name: agentic-service-account
roleRef:
  kind: Role
  name: secret-reader
  apiGroup: rbac.authorization.k8s.io
```

## Monitoring and Auditing

### Configuration Access Logging

Enable audit logging for configuration access:

```python
from src.config import ConfigurationManager
import logging

# Setup audit logger
audit_logger = logging.getLogger('config.audit')
handler = logging.FileHandler('config_audit.log')
audit_logger.addHandler(handler)

# Log configuration access
manager = ConfigurationManager(enable_metrics=True)

# Access patterns are automatically tracked
config = manager.get_database_config()
audit_logger.info(f"Database config accessed by {os.getenv('USER')}")
```

### Metrics and Alerting

Monitor for security-relevant events:

```python
from src.config.metrics import get_config_metrics

metrics = get_config_metrics()

# Alert on unusual access patterns
access_patterns = metrics.get_access_patterns_summary()
if access_patterns.get('total_accesses', 0) > 1000:  # Unusual activity
    send_security_alert("High configuration access rate detected")

# Alert on configuration errors
error_summary = metrics.get_metrics_summary()['error_summary']
if error_summary.get('total_errors', 0) > 10:
    send_security_alert("High configuration error rate")
```

### Security Scanning

Regularly scan for security issues:

**Automated Secret Scanning**
```bash
# Use tools like git-secrets, truffleHog, or detect-secrets
pip install detect-secrets
detect-secrets scan --all-files > .secrets.baseline

# Regular scans in CI/CD
detect-secrets audit .secrets.baseline
```

**Configuration Validation**
```python
from src.config import validate_config, ConfigurationValidator

def security_audit_config():
    config = load_config()
    validator = ConfigurationValidator(config)
    
    # Comprehensive validation including security checks
    errors, warnings = validator.validate_all(
        check_connectivity=True,
        check_permissions=True, 
        check_security=True
    )
    
    if errors:
        send_security_alert(f"Configuration security issues: {errors}")
```

## Common Security Mistakes

### ❌ Configuration in Source Control

**Mistake**: Committing configuration files with secrets
```bash
git add config.yaml  # Contains secrets
git commit -m "Add config"
```

**Solution**: Use .gitignore and environment variables
```bash
echo "config.yaml" >> .gitignore
git add .gitignore
```

### ❌ Overprivileged Access

**Mistake**: Using admin credentials for application
```yaml
database:
  url: "postgresql://postgres:admin_password@host/db"  # Admin user
```

**Solution**: Create dedicated user with minimal permissions
```yaml
database:
  url: "postgresql://app_user:app_password@host/db"    # Limited user
```

### ❌ Plain Text Logging

**Mistake**: Logging configuration values
```python
logger.info(f"Using API key: {config.anthropic.api_key}")  # Exposes secret
```

**Solution**: Use masked values for logging
```python
from src.config.utils import mask_sensitive_values

safe_config = mask_sensitive_values(config.dict())
logger.info(f"Configuration loaded: {safe_config}")
```

### ❌ Insecure Defaults

**Mistake**: Using insecure default values
```yaml
database:
  url: "${DATABASE_URL:sqlite:///insecure.db}"  # Default may be insecure
```

**Solution**: Require explicit configuration
```yaml
database:
  url: "${DATABASE_URL}"  # No default, must be explicitly set
```

### ❌ Shared Credentials

**Mistake**: Using same credentials across environments
```bash
# Same key for dev and prod
export ANTHROPIC_API_KEY="sk-ant-shared-key"
```

**Solution**: Environment-specific credentials
```bash
# Development
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY_DEV}"

# Production  
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY_PROD}"
```

## Security Checklist

Use this checklist to verify your configuration security:

### Environment Variables
- [ ] All secrets stored in environment variables
- [ ] No hardcoded credentials in configuration files
- [ ] Environment variables use descriptive names
- [ ] Required variables validated on startup

### File Security
- [ ] Configuration files have restrictive permissions (600)
- [ ] Configuration directories secured (700)
- [ ] Sensitive files in .gitignore
- [ ] No secrets in version control history

### Network Security
- [ ] All connections use TLS/SSL
- [ ] Certificate verification enabled
- [ ] Network access properly restricted
- [ ] Firewall rules configured

### Credentials Management
- [ ] Unique credentials per environment
- [ ] API keys have appropriate scope
- [ ] Regular credential rotation
- [ ] Centralized secrets management

### Monitoring
- [ ] Configuration access logging enabled
- [ ] Security metrics monitored
- [ ] Automated security scanning
- [ ] Alert thresholds configured

### Deployment
- [ ] Secrets injected at runtime
- [ ] Container images don't contain secrets
- [ ] Kubernetes secrets properly configured
- [ ] Service accounts have minimal permissions

## Getting Help

- **Security Vulnerabilities**: Report through responsible disclosure
- **Configuration Security Questions**: Check troubleshooting guide
- **Best Practices Updates**: Monitor security advisories
- **Compliance Requirements**: Consult security team for specific requirements