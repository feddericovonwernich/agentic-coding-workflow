# User Operational Troubleshooting Guide

> **📚 Navigation**: This guide focuses on **operational troubleshooting for users running the system**. For installation and environment setup issues, see **[Installation Troubleshooting](../getting-started/installation.md#troubleshooting)**. For configuration validation problems, see **[Configuration Troubleshooting](../config/troubleshooting.md)**.

This guide helps you diagnose and resolve common operational issues when running the Agentic Coding Workflow system in day-to-day usage.

## Table of Contents

- [Quick Diagnostic Tools](#quick-diagnostic-tools)
- [Common Operational Issues](#common-operational-issues)
- [PR Processing Problems](#pr-processing-problems)
- [System Performance Issues](#system-performance-issues)
- [Fix Application Problems](#fix-application-problems)
- [Notification Problems](#notification-problems)
- [Monitoring and Health Issues](#monitoring-and-health-issues)
- [Getting Help](#getting-help)

## Quick Diagnostic Tools

> **📋 Prerequisites**: These diagnostics assume the system is installed and configured. If you get connection errors or configuration problems, see **[Installation Troubleshooting](../getting-started/installation.md#troubleshooting)**.

### System Health Checks

```bash
# Check if system is running
curl http://localhost:8081/health

# Detailed component status
curl http://localhost:8081/health/detailed | jq

# View recent system activity
curl http://localhost:8080/metrics | grep -E "(processed|failed|queue)"

# Check worker processes
ps aux | grep -E "(monitor|analyzer|fixer)" | grep -v grep
```

### Operational Log Analysis

```bash
# Check for processing issues
grep -E "(pr.*processing|analysis.*failed|fix.*error)" logs/agentic.log | tail -10

# Monitor notification delivery
grep -E "(notification.*sent|notification.*failed)" logs/agentic.log | tail -5

# Review queue status
grep -E "(queue.*depth|worker.*idle|worker.*busy)" logs/agentic.log | tail -10

# Check for rate limiting
grep -E "(rate.*limit|too.*many.*requests|throttle)" logs/agentic.log | tail -5
```

### Quick PR Processing Check

```bash
# Check if PRs are being detected
curl http://localhost:8080/metrics | grep "prs_monitored"

# Check analysis queue
curl http://localhost:8080/metrics | grep "analysis_queue_depth"

# Recent PR processing activity
grep -E "(pr.*#[0-9]+|processing.*pull.*request)" logs/agentic.log | tail -10
```

## Common Operational Issues

### 🚨 Critical Operational Issues (Immediate Action Required)

| Symptom | Likely Cause | Quick Fix |
|---------|--------------|-----------|
| No PRs being processed | Worker stopped or GitHub API issue | Check worker status: `ps aux \| grep monitor` |
| All analyses failing | LLM API key exhausted/expired | Check API usage in provider dashboard |
| Notifications not sending | Notification service configuration | Test notification manually |
| High memory usage / crashes | Resource exhaustion | Check system resources: `free -h` |

### ⚠️ Warning Issues (Monitor and Plan Fix)

| Symptom | Likely Cause | Action Plan |
|---------|--------------|-------------|
| Slow PR processing | High queue depth or API rate limits | Scale workers or tune polling intervals |
| Intermittent fix failures | LLM model inconsistency | Review confidence thresholds |
| Missing some PRs | Repository access or webhook issues | Verify repository permissions |
| Occasional notification delays | Queue backup or external service issues | Monitor notification service health |

### 📊 Information Issues (Track and Optimize)

| Symptom | Likely Cause | Optimization |
|---------|--------------|--------------|
| Low fix success rate | Conservative confidence settings | Tune analysis confidence thresholds |
| High notification volume | Broad monitoring scope or noisy repos | Refine repository and alert filters |
| Growing resource usage | Normal scaling with repo/PR growth | Plan capacity expansion |

## PR Processing Problems

> **📋 Prerequisites**: If you're getting connection or configuration errors, see **[Installation Troubleshooting](../getting-started/installation.md#troubleshooting)** first.

### Issue: No PRs Being Detected

**Symptoms:**
- System is running but no PRs appear in logs
- Metrics show zero PRs monitored: `curl http://localhost:8080/metrics | grep "prs_monitored"`

**Diagnosis:**
```bash
# Check if monitor worker is running
ps aux | grep monitor | grep -v grep

# Check repository access
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/your-org/your-repo/pulls

# Review monitor logs
grep -E "(monitor|repository|polling)" logs/agentic.log | tail -10
```

**Solutions:**

1. **Monitor worker not running:**
   ```bash
   # Start monitor worker
   python -m workers.monitor &
   
   # Or restart all services
   docker-compose restart
   ```

2. **Repository access issues:**
   ```bash
   # Verify repository URL in config.yaml
   grep -A 5 "repositories:" config.yaml
   
   # Test repository access manually
   curl -H "Authorization: token $GITHUB_TOKEN" \
     "https://api.github.com/repos/owner/repo"
   ```

3. **Polling configuration:**
   ```yaml
   # config.yaml - adjust polling
   repositories:
     - url: "https://github.com/owner/repo"
       polling_interval: 300  # Check every 5 minutes
       states: ["open"]       # Monitor open PRs
   ```

### Issue: PRs Detected But Not Analyzed

**Symptoms:**
- PRs show in monitoring logs but no analysis occurs
- Analysis queue is growing: `curl http://localhost:8080/metrics | grep "analysis_queue_depth"`

**Diagnosis:**
```bash
# Check analyzer worker status
ps aux | grep analyzer | grep -v grep

# Check for analysis errors
grep -E "(analysis.*failed|analyzer.*error)" logs/agentic.log | tail -10

# Check LLM API connectivity
curl -H "x-api-key: $ANTHROPIC_API_KEY" \
  https://api.anthropic.com/v1/messages
```

**Solutions:**

1. **Analyzer worker not running:**
   ```bash
   # Start analyzer worker
   python -m workers.analyzer &
   ```

2. **LLM API issues:**
   - Check API key validity in provider dashboard
   - Verify account has sufficient credits
   - Monitor for rate limiting in logs

3. **Analysis configuration:**
   ```yaml
   # config.yaml - tune analysis settings
   analysis:
     confidence_threshold: 0.7  # Lower for more analyses
     timeout: 120              # Increase timeout
   ```

### Issue: Analyses Complete But No Fixes Applied

**Symptoms:**
- Analysis logs show successful completion
- No fixes are being applied to PRs

**Diagnosis:**
```bash
# Check fixer worker status
ps aux | grep fixer | grep -v grep

# Check for fix application errors
grep -E "(fix.*failed|fixer.*error|github.*push)" logs/agentic.log | tail -10

# Verify GitHub token has write permissions
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/owner/repo/collaborators/$(whoami)
```

**Solutions:**

1. **Fixer worker not running:**
   ```bash
   # Start fixer worker
   python -m workers.fixer &
   ```

2. **GitHub permissions:**
   - Ensure token has `repo` scope with write access
   - Verify bot user is repository collaborator
   - Check branch protection rules don't block bot pushes

3. **Fix application settings:**
   ```yaml
   # config.yaml - adjust fix behavior
   fixing:
     enabled: true
     apply_immediately: true    # Apply fixes without human approval
     categories:
       lint: true
       format: true
       test: false             # Disable risky fixes
   ```

## System Performance Issues

### Issue: High Memory Usage

**Symptoms:**
- System consuming excessive memory
- Out of memory errors in logs
- Worker processes being killed

**Diagnosis:**
```bash
# Check system memory usage
free -h

# Check process memory consumption
ps aux --sort=-%mem | head -10

# Monitor memory over time
watch -n 5 'free -h && ps aux --sort=-%mem | head -5'
```

**Solutions:**

1. **Reduce worker concurrency:**
   ```yaml
   # config.yaml - reduce resource usage
   workers:
     monitor:
       concurrency: 1      # Reduce concurrent operations
     analyzer:
       concurrency: 2      # Limit LLM requests
     fixer:
       concurrency: 1      # Reduce GitHub operations
   ```

2. **Optimize database connection pooling:**
   ```yaml
   # config.yaml - reduce database connections
   database:
     pool_size: 5          # Reduce from default 20
     max_overflow: 10      # Reduce from default 30
   ```

3. **Implement resource monitoring:**
   ```bash
   # Add memory monitoring script
   cat > scripts/monitor_resources.sh << 'EOF'
   #!/bin/bash
   while true; do
       echo "$(date): Memory: $(free -h | grep Mem | awk '{print $3"/"$2}')"
       sleep 60
   done >> logs/resource_usage.log &
   EOF
   ```

### Issue: Slow Processing Speed

**Symptoms:**
- PRs taking long time to process
- Growing queue depths
- Users reporting delays

**Diagnosis:**
```bash
# Check queue depths
curl http://localhost:8080/metrics | grep -E "(queue_depth|processing_time)"

# Monitor processing times
grep -E "(processing.*duration|analysis.*took)" logs/agentic.log | tail -10

# Check worker utilization
ps aux | grep -E "(monitor|analyzer|fixer)" | grep -v grep
```

**Solutions:**

1. **Scale workers horizontally:**
   ```yaml
   # config.yaml - increase worker instances
   workers:
     analyzer:
       instances: 3        # Run multiple analyzer workers
     fixer:
       instances: 2        # Multiple fixer workers
   ```

2. **Optimize polling and processing:**
   ```yaml
   # config.yaml - balance frequency vs. load
   repositories:
     - url: "https://github.com/owner/repo"
       polling_interval: 300    # Reduce from 180 if overloaded
       batch_size: 10          # Process multiple PRs together
   ```

3. **Enable parallel processing:**
   ```yaml
   # config.yaml - parallel operations
   processing:
     parallel_analysis: true
     max_concurrent_prs: 5     # Analyze multiple PRs simultaneously
   ```

### Issue: API Rate Limiting

**Symptoms:**
- `HTTP 429` errors in logs
- Processing delays
- "Rate limit exceeded" messages

**Diagnosis:**
```bash
# Check current GitHub rate limit
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/rate_limit

# Monitor rate limiting in logs
grep -E "(rate.*limit|429|too.*many)" logs/agentic.log | tail -10

# Check LLM API usage
grep -E "(anthropic.*limit|openai.*limit)" logs/agentic.log | tail -5
```

**Solutions:**

1. **Implement intelligent rate limiting:**
   ```yaml
   # config.yaml - rate limit management
   github:
     rate_limiting:
       enabled: true
       buffer_percentage: 20    # Keep 20% buffer
       backoff_multiplier: 2    # Exponential backoff
   
   llm:
     anthropic:
       rate_limit_rpm: 500     # Requests per minute
       concurrent_requests: 3   # Max parallel requests
   ```

2. **Optimize API usage patterns:**
   ```yaml
   # config.yaml - reduce API calls
   monitoring:
     cache_duration: 300       # Cache GitHub responses
     incremental_updates: true # Only fetch changes
   ```

3. **Distribute load across time:**
   ```yaml
   # config.yaml - spread load
   repositories:
     - url: "https://github.com/owner/repo1"
       polling_interval: 300
     - url: "https://github.com/owner/repo2" 
       polling_interval: 450    # Offset polling times
   ```

## Fix Application Problems

### Issue: Fixes Not Being Applied

**Symptoms:**
- Analysis completes successfully but no fixes appear on PRs
- Manual fix application works but automated doesn't

**Diagnosis:**
```bash
# Check if fixes are being generated
grep -E "(fix.*generated|fix.*applied)" logs/agentic.log | tail -10

# Check GitHub push attempts
grep -E "(github.*push|git.*commit)" logs/agentic.log | tail -10

# Test GitHub write permissions
curl -H "Authorization: token $GITHUB_TOKEN" \
  -X POST https://api.github.com/repos/owner/repo/issues/1/comments \
  -d '{"body": "Test comment"}'
```

**Solutions:**

1. **Enable automatic fix application:**
   ```yaml
   # config.yaml
   fixing:
     enabled: true
     auto_apply: true          # Apply fixes automatically
     require_approval: false   # Don't wait for human approval
   ```

2. **Check fix categories:**
   ```yaml
   # config.yaml - ensure categories are enabled
   fixing:
     categories:
       lint: true       # Code linting fixes
       format: true     # Code formatting fixes
       imports: true    # Import organization
       types: true      # Type annotation fixes
   ```

3. **Verify branch protection settings:**
   - Bot user must be exempt from branch protection
   - Or configure to create separate PRs instead of direct pushes

### Issue: Poor Fix Quality

**Symptoms:**
- Fixes are applied but break the code
- Tests fail after fixes are applied
- Users report that fixes make code worse

**Diagnosis:**
```bash
# Check fix success/failure rates
grep -E "(fix.*success|fix.*failed)" logs/agentic.log | tail -20

# Review fix validation logs
grep -E "(validation.*failed|syntax.*error)" logs/agentic.log | tail -10

# Check confidence scores
grep -E "confidence.*[0-9]\.[0-9]" logs/agentic.log | tail -10
```

**Solutions:**

1. **Increase confidence thresholds:**
   ```yaml
   # config.yaml - be more conservative
   analysis:
     confidence_threshold: 0.85  # Increase from 0.7
     categories:
       lint: 0.9      # Very high confidence for linting
       format: 0.95   # Near certain for formatting
       test: 0.7      # Lower for test fixes
   ```

2. **Enable fix validation:**
   ```yaml
   # config.yaml - validate before applying
   fixing:
     validation:
       enabled: true
       run_tests: true        # Run tests before applying
       syntax_check: true     # Check syntax validity
       rollback_on_failure: true
   ```

3. **Limit fix categories:**
   ```yaml
   # config.yaml - disable risky fixes
   fixing:
     categories:
       lint: true       # Safe linting fixes
       format: true     # Safe formatting fixes
       test: false      # Disable test modifications
       refactor: false  # Disable complex refactoring
   ```

### Issue: Fixes Applied to Wrong Files

**Symptoms:**
- Fixes appear in unexpected files
- Changes outside of PR diff context

**Diagnosis:**
```bash
# Review fix scope in logs
grep -E "(analyzing.*file|fixing.*file)" logs/agentic.log | tail -20

# Check file filtering
grep -E "(file.*ignored|file.*included)" logs/agentic.log | tail -10
```

**Solutions:**

1. **Configure file scope:**
   ```yaml
   # config.yaml - limit fix scope
   fixing:
     scope:
       files: "diff_only"     # Only fix files in PR diff
       extensions: [".py", ".js", ".ts"]  # Limit to specific types
       exclude_patterns:
         - "*/migrations/*"
         - "*/vendor/*"
         - "*/.git/*"
   ```

2. **Review analysis prompts:**
   - Ensure LLM prompts clearly specify file scope
   - Add context about PR boundaries

## Notification Problems

> **📋 Prerequisites**: For notification service configuration issues, see **[Installation Troubleshooting](../getting-started/installation.md#troubleshooting)**. This section covers operational notification problems.

### Issue: Notifications Not Being Sent

**Symptoms:**
- System detects issues but no notifications are received
- Notification service appears configured but silent

**Diagnosis:**
```bash
# Check notification attempts in logs
grep -E "(notification.*sent|notification.*failed)" logs/agentic.log | tail -10

# Test notification service manually
python -c "
from src.notification import NotificationService
from src.config import load_config

config = load_config()
service = NotificationService(config)
service.send_test_notification('Test from troubleshooting')
"

# Check notification triggers
grep -E "(trigger.*notification|alert.*condition)" logs/agentic.log | tail -10
```

**Solutions:**

1. **Verify notification triggers are configured:**
   ```yaml
   # config.yaml - ensure triggers are enabled
   notification:
     triggers:
       analysis_failed: true
       fix_applied: true
       rate_limit_reached: true
       system_error: true
   ```

2. **Check notification channels are enabled:**
   ```yaml
   # config.yaml - enable notification channels
   notification:
     channels:
       telegram:
         enabled: true
       slack:
         enabled: true  
       email:
         enabled: false  # Disable if not configured
   ```

3. **Test individual notification channels:**
   ```bash
   # Test Slack webhook
   curl -X POST "$SLACK_WEBHOOK_URL" \
     -H 'Content-Type: application/json' \
     -d '{"text": "Test from troubleshooting"}'
   
   # Test Telegram bot
   curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
     -d "chat_id=${TELEGRAM_CHAT_ID}&text=Test from troubleshooting"
   ```

### Issue: Too Many Notifications (Spam)

**Symptoms:**
- Receiving excessive notifications
- Notification fatigue from team members
- Important alerts getting lost in noise

**Diagnosis:**
```bash
# Count notifications per hour
grep "notification.*sent" logs/agentic.log | \
  grep "$(date '+%Y-%m-%d %H')" | wc -l

# Analyze notification reasons
grep -o "notification.*reason:[^,]*" logs/agentic.log | sort | uniq -c | sort -nr

# Check notification frequency
grep -E "(notification.*sent)" logs/agentic.log | tail -20
```

**Solutions:**

1. **Implement notification throttling:**
   ```yaml
   # config.yaml - reduce notification frequency
   notification:
     throttling:
       enabled: true
       max_per_hour: 5           # Maximum 5 notifications per hour
       duplicate_window: 300     # Suppress duplicates within 5 minutes
       escalation_delay: 1800    # Wait 30 minutes before escalating
   ```

2. **Adjust notification criteria:**
   ```yaml
   # config.yaml - be more selective
   notification:
     triggers:
       analysis_confidence_below: 0.5    # Only low-confidence issues
       fix_attempts_exceeded: 3          # After multiple failures
       rate_limit_threshold: 0.8         # Only near rate limits
   ```

3. **Configure notification levels:**
   ```yaml
   # config.yaml - priority-based notifications
   notification:
     levels:
       critical: ["system_error", "all_workers_down"]
       warning: ["fix_failed", "analysis_timeout"] 
       info: []  # Disable info-level notifications
   ```

### Issue: Delayed or Missing Critical Notifications

**Symptoms:**
- Critical issues not notified immediately
- Notifications arriving too late to be actionable

**Diagnosis:**
```bash
# Check notification delivery times
grep -E "(notification.*queued|notification.*sent)" logs/agentic.log | tail -20

# Monitor notification queue depth
curl http://localhost:8080/metrics | grep "notification_queue_depth"

# Check for notification service errors
grep -E "(notification.*error|notification.*timeout)" logs/agentic.log | tail -10
```

**Solutions:**

1. **Prioritize critical notifications:**
   ```yaml
   # config.yaml - priority queuing
   notification:
     priority:
       critical: 0      # Immediate delivery
       warning: 30      # 30 second delay
       info: 300        # 5 minute delay
   ```

2. **Configure multiple notification channels:**
   ```yaml
   # config.yaml - redundant channels for critical alerts
   notification:
     critical_channels:
       - telegram
       - slack
       - email    # Multiple channels for critical issues
   ```

3. **Implement notification monitoring:**
   ```bash
   # Add notification health check
   cat > scripts/check_notifications.sh << 'EOF'
   #!/bin/bash
   # Send test notification and verify delivery
   python -c "
   from src.notification import send_notification
   import time
   
   start = time.time()
   send_notification('Health check notification', 'info')
   duration = time.time() - start
   print(f'Notification sent in {duration:.2f}s')
   "
   EOF
   ```

## Monitoring and Health Issues

### Issue: Health Checks Failing

**Symptoms:**
- Health endpoint returns errors: `curl http://localhost:8081/health`
- Load balancer removing service from rotation
- Monitoring dashboard shows service as down

**Diagnosis:**
```bash
# Check health endpoint directly
curl -v http://localhost:8081/health

# Check detailed health status
curl http://localhost:8081/health/detailed | jq

# Review health check logs
grep -E "(health.*check|health.*fail)" logs/agentic.log | tail -10
```

**Solutions:**

1. **Check individual component health:**
   ```bash
   # Test database connectivity
   python -c "
   from src.database import test_connection
   from src.config import load_config
   
   config = load_config()
   try:
       test_connection(config.database.url)
       print('✅ Database OK')
   except Exception as e:
       print(f'❌ Database failed: {e}')
   "
   
   # Test queue connectivity  
   redis-cli ping
   ```

2. **Configure health check timeouts:**
   ```yaml
   # config.yaml - adjust health check sensitivity
   monitoring:
     health_checks:
       timeout: 30          # Increase timeout
       retry_attempts: 3    # Retry failed checks
       check_interval: 60   # Check every minute
   ```

3. **Implement graceful degradation:**
   ```yaml
   # config.yaml - continue with limited functionality
   monitoring:
     health_checks:
       fail_on_database: false    # Continue without database
       fail_on_queue: false       # Continue without queue
       required_components: ["config"]  # Only fail on critical components
   ```

### Issue: Metrics Not Being Collected

**Symptoms:**
- Metrics endpoint returns empty: `curl http://localhost:8080/metrics`
- Monitoring dashboard shows no data
- Unable to track system performance

**Diagnosis:**
```bash
# Check metrics endpoint
curl -v http://localhost:8080/metrics

# Check metrics collection in logs
grep -E "(metrics.*collected|metrics.*error)" logs/agentic.log | tail -10

# Verify metrics configuration
grep -A 10 "monitoring:" config.yaml
```

**Solutions:**

1. **Enable metrics collection:**
   ```yaml
   # config.yaml - ensure metrics are enabled
   monitoring:
     metrics:
       enabled: true
       port: 8080
       path: "/metrics"
       collection_interval: 30  # Collect every 30 seconds
   ```

2. **Configure metrics categories:**
   ```yaml
   # config.yaml - specify what to collect
   monitoring:
     metrics:
       categories:
         system: true      # CPU, memory, disk
         application: true # PR processing, queue depths  
         database: true    # Connection pools, query times
         external: true    # API response times
   ```

3. **Test metrics collection manually:**
   ```bash
   # Manual metrics check
   python -c "
   from src.monitoring import collect_metrics
   metrics = collect_metrics()
   for key, value in metrics.items():
       print(f'{key}: {value}')
   "
   ```


## Getting Help

### Operational Diagnostics

Run this comprehensive operational health check:

```bash
#!/bin/bash
# operational_diagnostic.sh - System operational health check

echo "=== Agentic Workflow Operational Diagnostic ==="
echo "Generated: $(date)"
echo

# System health
echo "--- System Health ---"
curl -s http://localhost:8081/health > /dev/null && echo "✅ Health endpoint OK" || echo "❌ Health endpoint failed"

# Worker status
echo "--- Worker Status ---"
ps aux | grep -E "(monitor|analyzer|fixer)" | grep -v grep | wc -l | xargs echo "Active workers:"

# Queue status
echo "--- Queue Status ---"
curl -s http://localhost:8080/metrics | grep -E "queue_depth|processed|failed" | head -5

# Recent activity
echo "--- Recent Activity (last hour) ---"
grep "$(date '+%Y-%m-%d %H')" logs/agentic.log | grep -E "(pr.*#[0-9]+|analysis.*complete|fix.*applied)" | wc -l | xargs echo "PRs processed:"

# Notification status
echo "--- Notification Status ---"
grep "$(date '+%Y-%m-%d')" logs/agentic.log | grep -E "notification.*sent" | wc -l | xargs echo "Notifications sent today:"

# Error summary
echo "--- Error Summary (last 24h) ---"
find logs/ -name "*.log" -mtime -1 -exec grep -c ERROR {} \; 2>/dev/null | awk '{sum+=$1} END {print "Total errors:", sum}'

echo "=== End Operational Diagnostic ==="
```

### Collecting Operational Information

When reporting operational issues, include:

```bash
# Operational status snapshot
echo "=== Operational Status ==="
date
curl -s http://localhost:8081/health | jq '.' 2>/dev/null || curl -s http://localhost:8081/health
curl -s http://localhost:8080/metrics | grep -E "(processed|failed|queue|rate)"

echo -e "\n=== Recent Activity ==="
grep -E "(pr.*#[0-9]+|analysis|fix.*applied|notification)" logs/agentic.log | tail -20

echo -e "\n=== Resource Usage ==="
free -h
ps aux --sort=-%mem | head -5

echo -e "\n=== Configuration Summary ==="
grep -E "(repositories:|notification:|workers:)" config.yaml
```

### Support Resources

#### For Operational Issues
- **[User Troubleshooting Guide](troubleshooting.md)** - This guide for operational problems
- **[Monitoring Guide](monitoring.md)** - Understanding system metrics and alerts
- **[Configuration Guide](configuration.md)** - Tuning operational settings

#### For Setup/Configuration Issues
- **[Installation Troubleshooting](../getting-started/installation.md#troubleshooting)** - Environment and setup problems
- **[Configuration Troubleshooting](../config/troubleshooting.md)** - Configuration validation issues
- **[Troubleshooting Hub](../troubleshooting-hub.md)** - Find the right guide for your issue

#### Community Support
- **[GitHub Issues](https://github.com/feddericovonwernich/agentic-coding-workflow/issues)** - Report operational bugs and issues
- **[GitHub Discussions](https://github.com/feddericovonwernich/agentic-coding-workflow/discussions)** - Community help and best practices

### Escalation Process

For operational issues that can't be resolved:

1. **Immediate Actions:**
   - Run operational diagnostic script above
   - Check recent logs for errors: `grep ERROR logs/agentic.log | tail -20`
   - Verify system health: `curl http://localhost:8081/health`

2. **Document the Issue:**
   - Symptom description (what's not working)
   - Impact assessment (how many PRs affected)
   - Timeline (when did it start)
   - Recent changes (configuration, updates, etc.)

3. **Create GitHub Issue:**
   - Include operational diagnostic output
   - Add relevant log excerpts
   - Tag with appropriate labels (bug, operational, urgent)

---

**Quick Resolution Tips:** Most operational issues stem from resource constraints, API rate limits, or notification configuration problems. Start with system resource checks and API quotas before diving deeper.