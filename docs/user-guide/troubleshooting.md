# Troubleshooting Guide

This guide helps you diagnose and resolve common issues with the Agentic Coding Workflow system. Use the symptom-based approach to quickly identify and fix problems.

## Table of Contents

- [Quick Diagnostic Tools](#quick-diagnostic-tools)
- [Common Issues by Category](#common-issues-by-category)
- [System Won't Start](#system-wont-start)
- [GitHub Integration Issues](#github-integration-issues)
- [Database Problems](#database-problems)
- [LLM API Issues](#llm-api-issues)
- [Performance Problems](#performance-problems)
- [Fix Application Failures](#fix-application-failures)
- [Notification Issues](#notification-issues)
- [Getting Help](#getting-help)

## Quick Diagnostic Tools

### Health Check Commands

```bash
# Basic system health
curl http://localhost:8081/health

# Detailed component status
curl http://localhost:8081/health/detailed | jq

# Service metrics
curl http://localhost:8080/metrics

# Database connectivity test
python -c "
import asyncio
from src.database import get_connection_manager
from src.config import load_config

async def test_db():
    config = load_config()
    manager = get_connection_manager(config.database)
    async with manager.get_session() as session:
        await session.execute('SELECT 1')
        print('✅ Database OK')

asyncio.run(test_db())
"
```

### Log Analysis

```bash
# Recent errors
tail -n 100 logs/agentic.log | grep ERROR

# Failed GitHub API calls
grep -E "(github|api).*error" logs/agentic.log | tail -10

# LLM API issues
grep -E "(anthropic|openai).*error" logs/agentic.log | tail -10

# Worker status
grep -E "worker.*(started|stopped|error)" logs/agentic.log | tail -20
```

## Common Issues by Category

### 🚨 Critical Issues (Immediate Action Required)

| Symptom | Likely Cause | Quick Fix |
|---------|--------------|-----------|
| System won't start | Configuration error | Check `config.yaml` syntax |
| All PRs ignored | GitHub token invalid | Verify `GITHUB_TOKEN` |
| Database connection failed | DB not running | Start database service |
| Workers crashing | Memory/resource limits | Check system resources |

### ⚠️ Warning Issues (Monitor and Plan Fix)

| Symptom | Likely Cause | Action Plan |
|---------|--------------|-------------|
| Slow PR processing | High queue depth | Scale workers or optimize |
| Occasional API timeouts | Rate limiting | Implement better retry logic |
| Some fixes failing | LLM prompt issues | Review and tune prompts |
| Notifications delayed | Queue backup | Check notification service |

### 📊 Information Issues (Track and Optimize)

| Symptom | Likely Cause | Optimization |
|---------|--------------|--------------|
| Low fix success rate | Conservative settings | Tune confidence thresholds |
| High notification volume | Broad monitoring scope | Refine repository filters |
| Resource usage growth | Normal scaling needs | Plan capacity expansion |

## System Won't Start

### Configuration File Issues

**Symptom:** `Configuration file not found` or `Invalid configuration`

**Diagnosis:**
```bash
# Check config file exists
ls -la config.yaml

# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Check environment variables
env | grep -E "(GITHUB|ANTHROPIC|OPENAI|DATABASE)"
```

**Solutions:**

1. **Missing config file:**
   ```bash
   cp config.example.yaml config.yaml
   # Edit with your values
   ```

2. **YAML syntax errors:**
   ```bash
   # Common issues:
   # - Incorrect indentation
   # - Missing quotes around URLs with special chars
   # - Invalid environment variable substitution
   
   # Test configuration loading
   python -c "from src.config import load_config; load_config()"
   ```

3. **Environment variable issues:**
   ```bash
   # Check .env file exists and is readable
   cat .env
   
   # Source environment variables
   set -a; source .env; set +a
   ```

### Permission Issues

**Symptom:** `Permission denied` errors

**Diagnosis:**
```bash
# Check file permissions
ls -la config.yaml .env logs/

# Check user/group ownership
id
ps aux | grep agentic
```

**Solutions:**
```bash
# Fix file permissions
chmod 600 .env config.yaml
chmod 755 logs/

# Create logs directory if missing
mkdir -p logs
```

### Port Conflicts

**Symptom:** `Address already in use` or `Port binding failed`

**Diagnosis:**
```bash
# Check what's using your ports
netstat -tlnp | grep -E "(8080|8081)"
lsof -i :8080
```

**Solutions:**
```bash
# Change ports in config.yaml
monitoring:
  metrics:
    port: 9080  # Different port
  health_checks:
    port: 9081  # Different port
    
# Or stop conflicting services
sudo kill $(lsof -t -i:8080)
```

## GitHub Integration Issues

### Authentication Problems

**Symptom:** `HTTP 401 Unauthorized` or `Bad credentials`

**Diagnosis:**
```bash
# Test GitHub token manually
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/rate_limit

# Check token scopes
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/user | jq '.scopes'
```

**Solutions:**

1. **Invalid or missing token:** See [Installation Guide - GitHub Token Setup](../getting-started/installation.md#github-token-setup) for detailed token creation
2. **Insufficient permissions:** Token needs `repo` scope - see installation guide for complete requirements  
3. **Token expired:** Generate new token following the installation guide

### Repository Access Issues

**Symptom:** `Repository not found` or `Not authorized to access repository`

**Diagnosis:**
```bash
# Test repository access
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/owner/repo

# Check organization membership (if applicable)
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/user/memberships/orgs
```

**Solutions:**
1. Verify repository URL in configuration
2. Ensure token has access to the repository
3. For organization repos, check organization member permissions
4. Consider using GitHub App with repository-specific permissions

### Rate Limiting Issues

**Symptom:** `HTTP 403 Forbidden` with `rate limit exceeded`

**Diagnosis:**
```bash
# Check current rate limit status
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/rate_limit | jq

# Monitor rate limit in logs
grep "rate.limit" logs/agentic.log | tail -10
```

**Solutions:**
1. **Reduce polling frequency:**
   ```yaml
   repositories:
     - url: "https://github.com/owner/repo"
       polling_interval: 600  # Increase from 300 to 600 seconds
   ```

2. **Implement backoff strategy:**
   ```yaml
   github:
     rate_limiting:
       enabled: true
       requests_per_hour: 4500  # Leave buffer from 5000 limit
       backoff_factor: 2
   ```

3. **Use GitHub App authentication (higher limits):**
   ```yaml
   github:
     auth:
       type: app
       app_id: "${GITHUB_APP_ID}"
       private_key_path: "${GITHUB_APP_PRIVATE_KEY_PATH}"
       installation_id: "${GITHUB_APP_INSTALLATION_ID}"
   ```

## Database Problems

### Connection Issues

**Symptom:** `Connection refused` or `Database connection failed`

**Diagnosis:**
```bash
# Test database connectivity
pg_isready -h localhost -p 5432  # PostgreSQL
sqlite3 agentic.db ".databases"   # SQLite

# Check database URL format
echo $DATABASE_URL

# Test connection with Python
python -c "
import asyncio
from sqlalchemy import create_engine
from src.config import load_config

config = load_config()
print(f'Database URL: {config.database.url}')
"
```

**Solutions:**

1. **PostgreSQL not running:**
   ```bash
   # Start PostgreSQL service
   sudo systemctl start postgresql
   # Or with Docker
   docker start agentic-postgres
   ```

2. **Wrong connection parameters:**
   ```bash
   # Check PostgreSQL is listening
   sudo netstat -tlnp | grep 5432
   
   # Test with psql
   psql "$DATABASE_URL"
   ```

3. **SQLite file permissions:**
   ```bash
   # Check SQLite file permissions
   ls -la agentic.db
   
   # Fix permissions
   chmod 664 agentic.db
   ```

### Migration Issues

**Symptom:** `Table doesn't exist` or `Database schema out of date`

**Solutions:**
1. **Run pending migrations:** `alembic upgrade head`
2. **For detailed migration troubleshooting:** See [Installation Guide - Database Migrations](../getting-started/installation.md#database-migrations)
3. **For development database reset:** See [Development Guidelines](../../DEVELOPMENT_GUIDELINES.md)

### Performance Issues

**Symptom:** Slow database queries or connection timeouts

**Diagnosis:**
```bash
# Check database connections
python -c "
from src.config import load_config
config = load_config()
print(f'Pool size: {config.database.pool_size}')
print(f'Max overflow: {config.database.max_overflow}')
"

# Monitor active connections (PostgreSQL)
psql -c "SELECT count(*) FROM pg_stat_activity;"

# Check slow queries (PostgreSQL)
psql -c "SELECT query, mean_time, calls FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"
```

**Solutions:**
1. **Increase connection pool:**
   ```yaml
   database:
     pool_size: 20
     max_overflow: 30
     pool_timeout: 30
   ```

2. **Add database indexes:**
   ```bash
   # Create migration for indexes
   alembic revision -m "add_performance_indexes"
   ```

3. **Optimize queries:**
   - Review slow query logs
   - Add appropriate database indexes
   - Consider query optimization

## LLM API Issues

### Authentication Failures

**Symptom:** `HTTP 401 Unauthorized` for Anthropic/OpenAI

**Diagnosis:**
```bash
# Test Anthropic API
curl -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
  -H "Content-Type: application/json" \
  https://api.anthropic.com/v1/messages

# Test OpenAI API  
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  https://api.openai.com/v1/models
```

**Solutions:**
1. **Invalid API key:**
   - Get new key from provider console
   - Ensure no extra spaces in environment variable

2. **API key format:**
   ```bash
   # Anthropic keys start with 'sk-ant-'
   # OpenAI keys start with 'sk-'
   echo $ANTHROPIC_API_KEY | cut -c1-10
   ```

### Rate Limiting and Quotas

**Symptom:** `HTTP 429 Too Many Requests` or quota exceeded

**Diagnosis:**
```bash
# Check recent API usage in logs
grep -E "(anthropic|openai).*429" logs/agentic.log | tail -10

# Monitor API call frequency
grep -c "llm.*request" logs/agentic.log | tail -1
```

**Solutions:**
1. **Implement request throttling:**
   ```yaml
   llm:
     anthropic:
       rate_limit:
         requests_per_minute: 50
         concurrent_requests: 5
   ```

2. **Add retry with exponential backoff:**
   ```yaml
   llm:
     retry:
       max_attempts: 3
       backoff_factor: 2
       max_delay: 60
   ```

3. **Consider multiple LLM providers:**
   ```yaml
   llm:
     providers:
       - anthropic
       - openai
     failover:
       enabled: true
   ```

### Model Response Issues

**Symptom:** Poor fix quality or unexpected responses

**Diagnosis:**
```bash
# Check recent LLM interactions
grep -A 10 -B 5 "llm.*response" logs/agentic.log | tail -50

# Analyze fix success rates
grep -c "fix.*success" logs/agentic.log | tail -1
grep -c "fix.*failed" logs/agentic.log | tail -1
```

**Solutions:**
1. **Tune prompts:**
   - Review prompt templates in configuration
   - Add more context to prompts
   - Use different models for different tasks

2. **Adjust confidence thresholds:**
   ```yaml
   analysis:
     confidence_threshold: 0.8  # Increase for more conservative fixes
     categories:
       lint: 0.9
       format: 0.95
       test: 0.7
   ```

## Performance Problems

### High Memory Usage

**Symptom:** System running out of memory or frequent crashes

**Diagnosis:**
```bash
# Check memory usage
free -h
ps aux --sort=-%mem | head -20

# Check for memory leaks
python -c "
import psutil
import os
process = psutil.Process(os.getpid())
print(f'Memory: {process.memory_info().rss / 1024 / 1024:.2f} MB')
"
```

**Solutions:**
1. **Reduce worker concurrency:**
   ```yaml
   workers:
     monitor:
       concurrency: 2  # Reduce from default
     analyzer:
       concurrency: 1
   ```

2. **Add memory limits:**
   ```yaml
   # docker-compose.yml
   services:
     app:
       deploy:
         resources:
           limits:
             memory: 1g
   ```

3. **Implement garbage collection:**
   ```python
   # Add to worker code
   import gc
   gc.collect()  # Force garbage collection periodically
   ```

### Slow Processing

**Symptom:** PRs taking too long to process

**Diagnosis:**
```bash
# Check queue depth
curl http://localhost:8080/metrics | grep queue_depth

# Check worker utilization
ps aux | grep -E "(monitor|analyzer|fixer)" 

# Review processing times in logs
grep "processing.*duration" logs/agentic.log | tail -20
```

**Solutions:**
1. **Scale workers horizontally:**
   ```yaml
   workers:
     analyzer:
       instances: 3  # Run multiple analyzer workers
     fixer:
       instances: 2
   ```

2. **Optimize database queries:**
   - Add database indexes
   - Use connection pooling
   - Implement query caching

3. **Parallel processing:**
   ```yaml
   processing:
     parallel:
       enabled: true
       max_concurrent_prs: 5
   ```

## Fix Application Failures

### Git/GitHub Push Failures

**Symptom:** Fixes analyzed but not applied to PRs

**Diagnosis:**
```bash
# Check recent push attempts
grep -E "git.*(push|error)" logs/agentic.log | tail -20

# Verify GitHub token permissions
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/owner/repo/collaborators/$(whoami)
```

**Solutions:**
1. **Insufficient GitHub permissions:**
   - Token needs `repo` scope with write access
   - User must be collaborator on repository
   - Check branch protection rules

2. **Git configuration:**
   ```bash
   # Configure git identity for commits
   git config --global user.name "Agentic Bot"
   git config --global user.email "agentic-bot@noreply.github.com"
   ```

3. **Branch protection conflicts:**
   - Verify bot user is exempt from protection rules
   - Or configure to create separate fix PRs instead of direct pushes

### Fix Quality Issues

**Symptom:** Fixes applied but break the code

**Diagnosis:**
```bash
# Check fix success rates
grep -A 5 "fix.*applied" logs/agentic.log | tail -20

# Review recent fix attempts
grep -B 5 -A 10 "fix.*validation" logs/agentic.log | tail -30
```

**Solutions:**
1. **Enable fix validation:**
   ```yaml
   fixing:
     validation:
       enabled: true
       run_tests: true
       check_syntax: true
   ```

2. **Implement rollback mechanism:**
   ```yaml
   fixing:
     rollback:
       enabled: true
       on_test_failure: true
   ```

3. **Reduce fix scope:**
   ```yaml
   fixing:
     categories:
       lint: true
       format: true
       test: false  # Disable complex fixes
   ```

## Notification Issues

### Missing Notifications

**Symptom:** Issues occurring but no notifications sent

**Diagnosis:**
```bash
# Check notification attempts
grep -E "notification.*(sent|failed)" logs/agentic.log | tail -20

# Test notification channels
curl -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{"text": "Test notification"}'
```

**Solutions:**
1. **Verify notification configuration:**
   ```yaml
   notification:
     enabled: true
     channels:
       slack:
         webhook_url: "${SLACK_WEBHOOK_URL}"
   ```

2. **Check channel permissions:**
   - Slack: Verify webhook URL is correct
   - Telegram: Check bot token and chat ID
   - Email: Verify SMTP settings

3. **Test notification triggers:**
   ```bash
   # Manually trigger test notification
   python -c "
   from src.notification import send_notification
   send_notification('Test message', 'info')
   "
   ```

### Notification Spam

**Symptom:** Too many notifications being sent

**Diagnosis:**
```bash
# Count notifications per hour
grep "notification.*sent" logs/agentic.log | \
  grep "$(date '+%Y-%m-%d %H')" | wc -l

# Analyze notification reasons
grep -o "notification.*reason:[^,]*" logs/agentic.log | sort | uniq -c
```

**Solutions:**
1. **Implement notification throttling:**
   ```yaml
   notification:
     throttling:
       enabled: true
       max_per_hour: 10
       duplicate_suppression: 300  # seconds
   ```

2. **Adjust notification criteria:**
   ```yaml
   notification:
     triggers:
       analysis_confidence_below: 0.5  # Only notify for very uncertain cases
       fix_attempts_exceeded: 3
   ```

## Getting Help

### Self-Service Diagnostics

Run the comprehensive diagnostic script:

```bash
#!/bin/bash
# diagnostic.sh - Comprehensive system check

echo "=== Agentic Workflow Diagnostic Report ==="
echo "Generated: $(date)"
echo

# Basic system info
echo "--- System Information ---"
echo "OS: $(uname -a)"
echo "Python: $(python --version)"
echo "Disk Space: $(df -h /)"
echo "Memory: $(free -h)"
echo

# Configuration check
echo "--- Configuration Status ---"
if [ -f config.yaml ]; then
    echo "✅ Config file exists"
    python -c "from src.config import load_config; load_config(); print('✅ Config loads successfully')" 2>/dev/null || echo "❌ Config has errors"
else
    echo "❌ Config file missing"
fi

# Environment variables
echo "--- Environment Variables ---"
[ -n "$GITHUB_TOKEN" ] && echo "✅ GITHUB_TOKEN set" || echo "❌ GITHUB_TOKEN missing"
[ -n "$ANTHROPIC_API_KEY" ] && echo "✅ ANTHROPIC_API_KEY set" || echo "❌ ANTHROPIC_API_KEY missing"
[ -n "$DATABASE_URL" ] && echo "✅ DATABASE_URL set" || echo "❌ DATABASE_URL missing"

# Service health
echo "--- Service Health ---"
curl -s http://localhost:8081/health > /dev/null && echo "✅ Health endpoint responding" || echo "❌ Health endpoint not responding"

# Recent errors
echo "--- Recent Errors (last 24h) ---"
find logs/ -name "*.log" -mtime -1 -exec grep -l ERROR {} \; 2>/dev/null | head -5 | while read log; do
    echo "File: $log"
    grep ERROR "$log" | tail -3
    echo
done

echo "=== End Diagnostic Report ==="
```

### Collecting Debug Information

When reporting issues, include:

1. **System information:**
   ```bash
   uname -a
   python --version
   pip freeze | grep -E "(agentic|anthropic|openai)"
   ```

2. **Configuration (sanitized):**
   ```bash
   # Remove sensitive data before sharing
   sed 's/api_key:.*/api_key: [REDACTED]/g' config.yaml
   ```

3. **Recent logs:**
   ```bash
   # Last 100 lines with timestamps
   tail -n 100 logs/agentic.log | grep -E "(ERROR|CRITICAL|WARNING)"
   ```

4. **Metrics snapshot:**
   ```bash
   curl -s http://localhost:8080/metrics > metrics-$(date +%s).txt
   ```

### Community Support

1. **[GitHub Issues](https://github.com/feddericovonwernich/agentic-coding-workflow/issues)**
   - Bug reports with diagnostic information
   - Feature requests
   - Configuration help

2. **[GitHub Discussions](https://github.com/feddericovonwernich/agentic-coding-workflow/discussions)**
   - General questions
   - Best practices sharing
   - Community solutions

3. **Documentation**
   - [Configuration Guide](configuration.md)
   - [Monitoring Guide](monitoring.md)
   - [Installation Guide](../getting-started/installation.md)

### Escalation Path

For urgent production issues:

1. **Check monitoring dashboards** for system status
2. **Review this troubleshooting guide** for immediate fixes
3. **Collect diagnostic information** using tools above
4. **Create GitHub issue** with all relevant information
5. **Tag as urgent** if it's a production outage

---

**Remember:** Most issues can be resolved by checking configuration, verifying API credentials, and reviewing logs. When in doubt, start with the [Quick Diagnostic Tools](#quick-diagnostic-tools) section.