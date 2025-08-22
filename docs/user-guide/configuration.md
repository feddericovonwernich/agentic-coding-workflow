# User Configuration Guide

This guide helps users configure the Agentic Coding Workflow system for their specific needs. Unlike the technical [Configuration Reference](../config/reference.md), this guide focuses on practical user scenarios and common configuration patterns.

## Table of Contents

- [Quick Configuration Templates](#quick-configuration-templates)
- [Repository Configuration](#repository-configuration)
- [Notification Configuration](#notification-configuration)
- [Team Setup](#team-setup)
- [Performance Tuning](#performance-tuning)
- [Environment-Specific Settings](#environment-specific-settings)
- [Configuration Best Practices](#configuration-best-practices)

## Quick Configuration Templates

### Small Team (1-5 repositories)

```yaml
# config.yaml - Small team template
system:
  environment: production
  max_workers: 2
  
repositories:
  - url: "https://github.com/yourorg/main-app"
    name: "main-app"
    polling_interval: 300  # 5 minutes
    auto_fix:
      enabled: true
      categories: [lint, formatting]
      confidence_threshold: 85

llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: claude-3-sonnet-20240229

default_llm_provider: anthropic

database:
  url: "${DATABASE_URL}"
  
queue:
  provider: redis
  url: "${REDIS_URL}"

notification:
  slack:
    enabled: true
    webhook_url: "${SLACK_WEBHOOK_URL}"
    channel: "#dev-alerts"
```

### Enterprise Team (10+ repositories)

```yaml
# config.yaml - Enterprise template
system:
  environment: production
  max_workers: 8
  worker_timeout: 600
  circuit_breaker:
    failure_threshold: 10
    recovery_timeout: 120

repositories:
  # Frontend repositories
  - url: "https://github.com/yourorg/web-app"
    name: "web-app"
    polling_interval: 180
    auto_fix:
      enabled: true
      categories: [lint, formatting, simple_tests]
      confidence_threshold: 90
    notification_channels: [slack-frontend]
    
  # Backend repositories  
  - url: "https://github.com/yourorg/api-service"
    name: "api-service"
    polling_interval: 300
    auto_fix:
      enabled: true
      categories: [lint, formatting]
      confidence_threshold: 85
    notification_channels: [slack-backend]
    
  # Infrastructure repositories
  - url: "https://github.com/yourorg/infrastructure"
    name: "infrastructure"
    polling_interval: 600
    auto_fix:
      enabled: false  # Manual review for infrastructure
    notification_channels: [slack-devops, email-critical]

llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: claude-3-opus-20240229  # More powerful model
    max_tokens: 8192

default_llm_provider: anthropic

database:
  url: "${DATABASE_URL}"
  pool:
    pool_size: 30
    max_overflow: 50

queue:
  provider: redis
  url: "${REDIS_URL}"
  retry_attempts: 5

notification:
  slack:
    enabled: true
    webhook_url: "${SLACK_WEBHOOK_URL}"
    
  email:
    enabled: true
    smtp_server: "${EMAIL_SMTP_SERVER}"
    username: "${EMAIL_USERNAME}"
    password: "${EMAIL_PASSWORD}"
```

## Repository Configuration

### Adding a New Repository

1. **Basic repository setup**:
```yaml
repositories:
  - url: "https://github.com/yourorg/new-repo"
    name: "new-repo"
    polling_interval: 300
```

2. **Configure automatic fixes**:
```yaml
repositories:
  - url: "https://github.com/yourorg/new-repo"
    name: "new-repo"
    polling_interval: 300
    auto_fix:
      enabled: true
      categories:
        - lint          # ESLint, Pylint, etc.
        - formatting    # Prettier, Black, etc.  
        - simple_tests  # Import errors, typos
      confidence_threshold: 80  # 0-100, higher = more conservative
      max_attempts: 3
```

3. **Configure skip patterns** (files to ignore):
```yaml
repositories:
  - url: "https://github.com/yourorg/new-repo"
    name: "new-repo"
    skip_patterns:
      - "*.md"           # Skip markdown files
      - "docs/**"        # Skip documentation
      - "*.json"         # Skip JSON files
      - "test-data/**"   # Skip test data
```

### Repository-Specific Settings

#### High-Traffic Repository
```yaml
# For repositories with frequent PRs
repositories:
  - url: "https://github.com/yourorg/busy-repo"
    polling_interval: 120  # Check every 2 minutes
    auto_fix:
      enabled: true
      categories: [lint, formatting]
      confidence_threshold: 95  # Be very conservative
```

#### Legacy Repository
```yaml
# For older repositories that need careful handling
repositories:
  - url: "https://github.com/yourorg/legacy-app"
    polling_interval: 600  # Check every 10 minutes
    auto_fix:
      enabled: false  # No automatic fixes
    notification_channels: [email-senior-dev]
```

#### Experimental Repository
```yaml
# For testing new features
repositories:
  - url: "https://github.com/yourorg/experimental"
    polling_interval: 60   # Check every minute
    auto_fix:
      enabled: true
      categories: [lint, formatting, simple_tests, documentation]
      confidence_threshold: 70  # More aggressive
```

### Language-Specific Configuration

#### JavaScript/TypeScript Projects
```yaml
repositories:
  - url: "https://github.com/yourorg/frontend-app"
    auto_fix:
      categories: [lint, formatting]
    skip_patterns:
      - "node_modules/**"
      - "dist/**"
      - "build/**"
      - "*.d.ts"
```

#### Python Projects
```yaml
repositories:
  - url: "https://github.com/yourorg/python-api"
    auto_fix:
      categories: [lint, formatting, simple_tests]
    skip_patterns:
      - "__pycache__/**"
      - "*.pyc"
      - ".venv/**"
      - "venv/**"
```

#### Go Projects
```yaml
repositories:
  - url: "https://github.com/yourorg/go-service"
    auto_fix:
      categories: [lint, formatting]
    skip_patterns:
      - "vendor/**"
      - "*.pb.go"
```

## Notification Configuration

### Slack Integration

#### Basic Slack Setup
```yaml
notification:
  slack:
    enabled: true
    webhook_url: "${SLACK_WEBHOOK_URL}"
    channel: "#dev-alerts"
    username: "Agentic Bot"
    icon_emoji: ":robot_face:"
```

#### Multi-Channel Slack Setup
```yaml
notification:
  slack:
    enabled: true
    channels:
      slack-frontend:
        webhook_url: "${SLACK_FRONTEND_WEBHOOK}"
        channel: "#frontend-alerts"
        username: "Frontend Bot"
      slack-backend:
        webhook_url: "${SLACK_BACKEND_WEBHOOK}" 
        channel: "#backend-alerts"
        username: "Backend Bot"
      slack-devops:
        webhook_url: "${SLACK_DEVOPS_WEBHOOK}"
        channel: "#devops-alerts"
        username: "DevOps Bot"
```

### Telegram Integration

```yaml
notification:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
    message_format: markdown
    
    # For multiple chats/groups
    chats:
      dev-team:
        chat_id: "-1001234567890"
        topics: [failures, fixes]
      ops-team:
        chat_id: "-1009876543210"
        topics: [errors, system]
```

### Email Notifications

```yaml
notification:
  email:
    enabled: true
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    username: "${EMAIL_USERNAME}"
    password: "${EMAIL_PASSWORD}"
    from_address: "agentic-bot@yourcompany.com"
    
    # Email lists by priority
    recipients:
      critical:
        - "devops-team@yourcompany.com"
        - "engineering-leads@yourcompany.com"
      normal:
        - "dev-team@yourcompany.com"
```

### Conditional Notifications

```yaml
notification:
  rules:
    # Only notify for high-priority repositories
    - condition: "repository.name in ['main-app', 'api-service']"
      channels: [slack, email-critical]
      
    # Different notifications for different failure types
    - condition: "failure.category == 'security'"
      channels: [email-security, slack-security]
      
    # Quiet hours (no notifications 10 PM - 8 AM)
    - condition: "time.hour >= 22 or time.hour <= 8"
      channels: []  # No notifications during quiet hours
```

## Team Setup

### Frontend Team Configuration

```yaml
# Frontend team - focus on UI/UX repositories
repositories:
  - url: "https://github.com/yourorg/web-app"
    name: "web-app"
    auto_fix:
      enabled: true
      categories: [lint, formatting]  # ESLint, Prettier
      confidence_threshold: 90
    notification_channels: [slack-frontend]
    
  - url: "https://github.com/yourorg/design-system"
    name: "design-system"
    auto_fix:
      enabled: true
      categories: [lint, formatting, documentation]
      confidence_threshold: 95  # Be extra careful with design system
    notification_channels: [slack-frontend, email-design-team]

notification:
  slack:
    channels:
      slack-frontend:
        webhook_url: "${SLACK_FRONTEND_WEBHOOK}"
        channel: "#frontend-alerts"
        message_template: |
          🚨 *{{repository.name}}* - {{failure.type}}
          
          *PR*: {{pr.title}} (#{{pr.number}})
          *Author*: {{pr.author}}
          *Status*: {{#if fix.applied}}✅ Auto-fixed{{else}}❌ Needs review{{/if}}
          
          {{#if fix.applied}}
          *Fix applied*: {{fix.description}}
          {{else}}
          *Issue*: {{failure.summary}}
          *Action needed*: Manual review required
          {{/if}}
```

### Backend Team Configuration

```yaml
# Backend team - focus on APIs and services
repositories:
  - url: "https://github.com/yourorg/api-gateway"
    name: "api-gateway"
    auto_fix:
      enabled: true
      categories: [lint, formatting, simple_tests]
      confidence_threshold: 85
    notification_channels: [slack-backend]
    
  - url: "https://github.com/yourorg/auth-service"
    name: "auth-service"
    auto_fix:
      enabled: false  # Security-sensitive, manual review only
    notification_channels: [slack-backend, email-security]

notification:
  slack:
    channels:
      slack-backend:
        webhook_url: "${SLACK_BACKEND_WEBHOOK}"
        channel: "#backend-alerts"
```

### DevOps Team Configuration

```yaml
# DevOps team - focus on infrastructure and deployment
repositories:
  - url: "https://github.com/yourorg/kubernetes-configs"
    name: "k8s-configs"
    polling_interval: 300
    auto_fix:
      enabled: false  # No auto-fixes for infrastructure
    notification_channels: [slack-devops, email-critical]
    
  - url: "https://github.com/yourorg/terraform"
    name: "terraform"
    polling_interval: 600  # Less frequent checks
    auto_fix:
      enabled: false
    notification_channels: [slack-devops, email-devops-leads]

notification:
  slack:
    channels:
      slack-devops:
        webhook_url: "${SLACK_DEVOPS_WEBHOOK}"
        channel: "#devops-alerts"
        urgency_levels:
          high: "@channel"
          medium: "@here"
          low: ""
```

## Performance Tuning

### High-Volume Configuration

For organizations with many repositories or high PR volume:

```yaml
system:
  max_workers: 16          # Increase worker count
  worker_timeout: 900      # 15 minutes per task
  batch_size: 10          # Process multiple PRs at once
  
database:
  pool:
    pool_size: 50          # Larger connection pool
    max_overflow: 100      # More overflow connections
    pool_timeout: 45       # Longer timeout for busy systems
    
queue:
  provider: redis
  redis:
    max_connections: 100   # More Redis connections
    connection_pool_size: 20
    retry_attempts: 5
    
llm:
  anthropic:
    timeout: 60           # Longer timeout for complex analysis
    max_tokens: 8192      # Allow longer responses
    rate_limits:
      requests_per_minute: 100
      tokens_per_minute: 50000
```

### Resource-Constrained Configuration

For smaller deployments or resource constraints:

```yaml
system:
  max_workers: 2           # Fewer workers
  worker_timeout: 300      # 5 minutes per task
  memory_limit: "1G"       # Memory constraint
  
database:
  pool:
    pool_size: 10          # Smaller pool
    max_overflow: 5        # Limited overflow
    
queue:
  provider: memory         # In-memory queue (simpler)
  
llm:
  anthropic:
    model: claude-3-haiku-20240307  # Faster, cheaper model
    max_tokens: 2048       # Shorter responses
    timeout: 30           # Shorter timeout
```

### Geographic Distribution

For global teams with multiple time zones:

```yaml
system:
  timezone_aware: true
  business_hours:
    start: "09:00"
    end: "17:00"
    timezone: "UTC"
    
notification:
  timezone_routing:
    enabled: true
    regions:
      americas:
        timezone: "America/New_York"
        channels: [slack-americas]
        business_hours: "09:00-17:00"
      europe:
        timezone: "Europe/London"
        channels: [slack-europe]
        business_hours: "09:00-17:00"
      asia:
        timezone: "Asia/Tokyo"
        channels: [slack-asia]
        business_hours: "09:00-17:00"
```

## Environment-Specific Settings

### Development Environment

```yaml
system:
  environment: development
  debug_mode: true
  log_level: DEBUG
  
repositories:
  - url: "https://github.com/yourorg/test-repo"
    name: "test-repo"
    polling_interval: 60    # More frequent for testing
    auto_fix:
      enabled: true
      confidence_threshold: 70  # More aggressive for testing
      
database:
  url: "sqlite:///./dev.db"  # Simple SQLite for development
  
queue:
  provider: memory           # In-memory queue for development
  
notification:
  telegram:
    enabled: true
    chat_id: "${DEV_TELEGRAM_CHAT_ID}"  # Separate dev chat
```

### Staging Environment

```yaml
system:
  environment: staging
  log_level: INFO
  
repositories:
  - url: "https://github.com/yourorg/main-app"
    name: "main-app-staging"
    polling_interval: 300
    auto_fix:
      enabled: true
      confidence_threshold: 85
      
database:
  url: "${STAGING_DATABASE_URL}"
  pool:
    pool_size: 10
    
queue:
  provider: redis
  url: "${STAGING_REDIS_URL}"
  
notification:
  slack:
    enabled: true
    channel: "#staging-alerts"
    webhook_url: "${STAGING_SLACK_WEBHOOK}"
```

### Production Environment

```yaml
system:
  environment: production
  log_level: INFO
  log_format: json
  max_workers: 8
  circuit_breaker:
    enabled: true
    failure_threshold: 10
    
repositories:
  - url: "https://github.com/yourorg/main-app"
    name: "main-app"
    polling_interval: 300
    auto_fix:
      enabled: true
      confidence_threshold: 90  # Conservative for production
      
database:
  url: "${DATABASE_URL}"
  pool:
    pool_size: 30
    max_overflow: 50
    pool_pre_ping: true
    
queue:
  provider: redis
  url: "${REDIS_URL}"
  retry_attempts: 5
  
notification:
  slack:
    enabled: true
    channel: "#prod-alerts"
    webhook_url: "${PROD_SLACK_WEBHOOK}"
    
  email:
    enabled: true
    recipients:
      critical: ["oncall@yourcompany.com"]
      
monitoring:
  sentry:
    enabled: true
    dsn: "${SENTRY_DSN}"
    
  prometheus:
    enabled: true
    port: 8080
    path: "/metrics"
```

## Configuration Best Practices

### Security Best Practices

1. **Use environment variables** for all sensitive data:
```yaml
# ✅ Good
github_token: "${GITHUB_TOKEN}"
api_key: "${ANTHROPIC_API_KEY}"

# ❌ Bad - never put secrets in config files
github_token: "ghp_actual_token_here"
```

2. **Use least-privilege GitHub tokens**:
```bash
# Only grant necessary scopes
# For public repos: public_repo
# For private repos: repo
# Never use admin or org-level permissions unless required
```

3. **Rotate credentials regularly**:
```yaml
# Add rotation reminders to your config
# Last rotated: 2024-01-15
# Next rotation: 2024-04-15
github_token: "${GITHUB_TOKEN}"
```

### Performance Best Practices

1. **Start conservative, then optimize**:
```yaml
# Start with conservative settings
auto_fix:
  confidence_threshold: 90  # High confidence
  categories: [lint]        # Only linting
  
# Gradually expand as you gain confidence
auto_fix:
  confidence_threshold: 85  # Lower threshold
  categories: [lint, formatting, simple_tests]  # More categories
```

2. **Monitor and adjust polling intervals**:
```yaml
# High-activity repos: check more frequently
polling_interval: 180  # 3 minutes

# Low-activity repos: check less frequently  
polling_interval: 900  # 15 minutes
```

3. **Use appropriate LLM models**:
```yaml
# For simple tasks: use faster, cheaper models
llm:
  anthropic:
    model: claude-3-haiku-20240307  # Fast and economical
    
# For complex analysis: use more powerful models
llm:
  anthropic:
    model: claude-3-opus-20240229   # More capable but expensive
```

### Maintenance Best Practices

1. **Document your configuration**:
```yaml
# Configuration for Frontend Team
# Contact: frontend-team@company.com
# Last updated: 2024-01-15
repositories:
  - url: "https://github.com/company/web-app"
    # This is our main customer-facing web application
    # Auto-fix enabled for routine maintenance
    auto_fix:
      enabled: true
```

2. **Version control your configuration**:
```bash
# Store config in git (without secrets)
git add config.yaml
git commit -m "Update polling interval for high-traffic repos"

# Use separate files for secrets
echo "config.local.yaml" >> .gitignore
echo ".env.local" >> .gitignore
```

3. **Test configuration changes**:
```bash
# Validate configuration before applying
python -m src.config.tools.validate --config config.yaml

# Test with a single repository first
python -m src.config.tools.test --repository test-repo
```

### Monitoring Your Configuration

1. **Track key metrics**:
```yaml
monitoring:
  metrics:
    - fix_success_rate
    - false_positive_rate  
    - processing_time
    - queue_depth
    
  alerts:
    - name: "Low fix success rate"
      condition: "fix_success_rate < 0.7"
      severity: warning
      
    - name: "High false positive rate"
      condition: "false_positive_rate > 0.1"
      severity: critical
```

2. **Regular configuration reviews**:
```yaml
# Add review schedules to your config
# Review schedule: Monthly
# Next review: 2024-02-15
# Owner: DevOps Team
```

## Configuration Migration

### Upgrading from Basic to Advanced

When scaling from a small to large deployment:

```yaml
# Phase 1: Basic (1-5 repos)
repositories:
  - url: "https://github.com/org/repo1"
    auto_fix: 
      enabled: true
      categories: [lint]

# Phase 2: Intermediate (5-20 repos)  
repositories:
  - url: "https://github.com/org/repo1"
    auto_fix:
      categories: [lint, formatting]
      confidence_threshold: 85
    notification_channels: [slack-team1]
    
# Phase 3: Advanced (20+ repos)
repositories:
  - url: "https://github.com/org/repo1"  
    auto_fix:
      categories: [lint, formatting, simple_tests]
      confidence_threshold: 85
    notification_channels: [slack-team1]
    skip_patterns: ["docs/**", "*.md"]
    custom_rules:
      - type: "security"
        action: "escalate"
```

### Configuration Validation

Always validate your configuration before deploying:

```bash
# Validate configuration syntax
python -m src.config.tools.validate --config config.yaml

# Test with dry-run mode
python -m src.workers.monitor --dry-run --config config.yaml

# Check connectivity to all services
python -m src.config.tools.validate --check-connectivity
```

---

**Next Steps:**
- **[Monitoring Guide](monitoring.md)** - Set up dashboards and alerts
- **[Troubleshooting Guide](troubleshooting.md)** - Resolve common issues
- **[Configuration Reference](../config/reference.md)** - Complete technical reference