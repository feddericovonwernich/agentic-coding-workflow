# Monitoring & Observability Guide

This guide helps you set up comprehensive monitoring and observability for the Agentic Coding Workflow system to ensure reliable operation and quick problem resolution.

## Table of Contents

- [Quick Start Monitoring](#quick-start-monitoring)
- [Key Metrics to Monitor](#key-metrics-to-monitor)
- [Setting Up Dashboards](#setting-up-dashboards)
- [Alerting Configuration](#alerting-configuration)
- [Log Management](#log-management)
- [Health Checks](#health-checks)
- [Performance Monitoring](#performance-monitoring)
- [Troubleshooting with Metrics](#troubleshooting-with-metrics)

## Quick Start Monitoring

### Essential Monitoring (5-minute setup)

```yaml
# config.yaml - Add monitoring configuration
monitoring:
  enabled: true
  metrics:
    provider: prometheus
    port: 8080
    path: /metrics
  
  health_checks:
    enabled: true
    port: 8081
    path: /health

logging:
  level: INFO
  format: json
  handlers:
    - console
    - file
  
  file:
    path: logs/agentic.log
    max_bytes: 100MB
    backup_count: 5
```

### Basic Health Dashboard

```bash
# Start monitoring stack with Docker Compose
cat > monitoring-compose.yml << EOF
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
    volumes:
      - grafana-data:/var/lib/grafana

volumes:
  grafana-data:
EOF

docker-compose -f monitoring-compose.yml up -d
```

## Key Metrics to Monitor

### System Health Metrics

| Metric | Description | Alert Threshold | Action |
|--------|-------------|-----------------|---------|
| **service_up** | Service availability | < 1 | Restart service |
| **database_connections** | Active DB connections | > 80% of pool | Scale connections |
| **queue_depth** | Pending tasks in queue | > 1000 | Check workers |
| **memory_usage** | System memory usage | > 85% | Check memory leaks |

### Business Logic Metrics

| Metric | Description | Normal Range | Investigation Threshold |
|--------|-------------|--------------|------------------------|
| **prs_monitored** | PRs being monitored | Varies | Drop > 50% |
| **checks_analyzed** | Failed checks analyzed | 10-100/hour | < 5/hour |
| **fixes_applied** | Successful automatic fixes | 5-50/hour | Success rate < 60% |
| **notifications_sent** | Alerts to humans | 1-20/hour | > 50/hour |

### API Performance Metrics

| Metric | Description | Target | Warning | Critical |
|--------|-------------|--------|---------|----------|
| **github_api_latency** | GitHub API response time | < 500ms | > 1s | > 3s |
| **llm_api_latency** | LLM API response time | < 2s | > 5s | > 10s |
| **github_rate_limit** | Remaining API calls | > 1000 | < 500 | < 100 |
| **error_rate** | Failed requests percentage | < 1% | > 5% | > 10% |

## Setting Up Dashboards

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'agentic-workflow'
    static_configs:
      - targets: ['app:8080']
    metrics_path: /metrics
    scrape_interval: 5s
    
  - job_name: 'health-checks'
    static_configs:
      - targets: ['app:8081']
    metrics_path: /health
    scrape_interval: 30s
```

### Grafana Dashboard Templates

#### System Overview Dashboard

```json
{
  "dashboard": {
    "title": "Agentic Workflow - System Overview",
    "panels": [
      {
        "title": "Service Health",
        "targets": [
          {"expr": "service_up", "legendFormat": "{{service}}"}
        ]
      },
      {
        "title": "Queue Depth",
        "targets": [
          {"expr": "queue_depth", "legendFormat": "{{queue}}"}
        ]
      },
      {
        "title": "API Response Times",
        "targets": [
          {"expr": "api_request_duration_seconds", "legendFormat": "{{api}}"}
        ]
      }
    ]
  }
}
```

#### Business Metrics Dashboard

Create dashboards for:

1. **PR Processing Pipeline**
   - PRs discovered per hour
   - Analysis completion rate
   - Fix success rate
   - Time from detection to resolution

2. **API Health**
   - GitHub API rate limits
   - LLM API latency and errors
   - Webhook delivery success

3. **Worker Performance**
   - Tasks processed per worker
   - Worker utilization
   - Error rates by worker type

### Pre-built Dashboard Import

```bash
# Import Grafana dashboard
curl -X POST \
  http://admin:admin123@localhost:3000/api/dashboards/db \
  -H 'Content-Type: application/json' \
  -d @agentic-workflow-dashboard.json
```

## Alerting Configuration

### Critical Alerts (Immediate Response)

```yaml
# alerts.yml - Prometheus alerting rules
groups:
  - name: agentic-workflow-critical
    rules:
      - alert: ServiceDown
        expr: service_up == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.service }} is down"
          
      - alert: HighErrorRate
        expr: error_rate > 0.1
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Error rate is {{ $value }}%"
          
      - alert: DatabaseConnectionsExhausted
        expr: database_connections_active / database_connections_max > 0.9
        for: 1m
        labels:
          severity: critical
```

### Warning Alerts (Monitor Closely)

```yaml
  - name: agentic-workflow-warnings
    rules:
      - alert: HighQueueDepth
        expr: queue_depth > 500
        for: 5m
        labels:
          severity: warning
          
      - alert: SlowAPIResponse
        expr: api_request_duration_seconds > 3
        for: 2m
        labels:
          severity: warning
          
      - alert: LowFixSuccessRate
        expr: fix_success_rate < 0.6
        for: 10m
        labels:
          severity: warning
```

### Notification Channels

```yaml
# config.yaml - Alert notification setup
monitoring:
  alerting:
    enabled: true
    
    channels:
      slack:
        webhook_url: "${SLACK_WEBHOOK_URL}"
        channel: "#devops-alerts"
        username: "AgenticBot"
        
      email:
        smtp_server: "${EMAIL_SMTP_SERVER}"
        to: ["devops@company.com"]
        subject: "Agentic Workflow Alert: {{ .GroupLabels.alertname }}"
        
      pagerduty:
        integration_key: "${PAGERDUTY_KEY}"
        severity_mapping:
          critical: "critical"
          warning: "warning"
```

## Log Management

### Structured Logging Configuration

```yaml
# config.yaml
logging:
  level: INFO
  format: json
  
  fields:
    service: "agentic-workflow"
    version: "1.0.0"
    environment: "production"
    
  handlers:
    console:
      enabled: true
      format: json
      
    file:
      enabled: true
      path: "logs/agentic.log"
      rotation:
        max_bytes: 100MB
        backup_count: 10
        
    syslog:
      enabled: false
      address: "localhost:514"
```

### Log Aggregation with ELK Stack

```yaml
# docker-compose-logging.yml
services:
  elasticsearch:
    image: elasticsearch:8.5.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
      
  logstash:
    image: logstash:8.5.0
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    ports:
      - "5000:5000"
      
  kibana:
    image: kibana:8.5.0
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    ports:
      - "5601:5601"
```

### Key Log Patterns to Monitor

```bash
# Error patterns to alert on
ERROR.*database.*connection
ERROR.*github.*rate.limit
ERROR.*llm.*timeout
CRITICAL.*worker.*crashed

# Performance patterns
SLOW.*query.*duration.*[3-9][0-9]{3}ms
WARN.*queue.*depth.*[1-9][0-9]{3}
INFO.*fix.*applied.*success
```

## Health Checks

### Application Health Endpoints

```python
# Health check implementation in your application
from fastapi import FastAPI
from datetime import datetime

app = FastAPI()

@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/health/detailed")
async def detailed_health():
    """Detailed health check with dependencies."""
    checks = {
        "database": await check_database(),
        "github_api": await check_github_api(),
        "llm_api": await check_llm_api(),
        "queue": await check_queue(),
    }
    
    overall_status = "healthy" if all(
        check["status"] == "healthy" for check in checks.values()
    ) else "unhealthy"
    
    return {
        "status": overall_status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }
```

### External Monitoring Services

#### UptimeRobot Configuration

```bash
# Monitor your health endpoints externally
curl -X POST "https://api.uptimerobot.com/v2/newMonitor" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "api_key=YOUR_API_KEY" \
  -d "format=json" \
  -d "type=1" \
  -d "url=https://your-domain.com/health" \
  -d "friendly_name=Agentic Workflow Health" \
  -d "interval=300"
```

#### Pingdom Setup

```json
{
  "name": "Agentic Workflow API",
  "hostname": "your-domain.com",
  "resolution": 5,
  "type": "http",
  "url": "/health",
  "encryption": true,
  "port": 443,
  "shouldcontain": "healthy",
  "tags": ["production", "api", "critical"]
}
```

## Performance Monitoring

### Application Performance Monitoring (APM)

```yaml
# config.yaml - APM integration
monitoring:
  apm:
    enabled: true
    
    # DataDog APM
    datadog:
      api_key: "${DATADOG_API_KEY}"
      service_name: "agentic-workflow"
      environment: "production"
      
    # New Relic APM  
    newrelic:
      license_key: "${NEWRELIC_LICENSE_KEY}"
      app_name: "Agentic Workflow"
```

### Custom Performance Metrics

```python
# Performance monitoring in your application
import time
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
pr_processing_time = Histogram('pr_processing_seconds', 'Time spent processing PRs')
active_workers = Gauge('active_workers', 'Number of active workers')
github_api_calls = Counter('github_api_calls_total', 'Total GitHub API calls')

# Use in your code
@pr_processing_time.time()
async def process_pr(pr_data):
    github_api_calls.inc()
    # Process PR logic
    return result
```

### Database Performance Monitoring

```sql
-- PostgreSQL monitoring queries
SELECT 
    schemaname,
    tablename,
    attname,
    n_distinct,
    correlation 
FROM pg_stats 
WHERE schemaname = 'public';

-- Query performance
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    rows
FROM pg_stat_statements 
ORDER BY total_time DESC 
LIMIT 10;
```

## Troubleshooting with Metrics

### Common Scenarios and Metrics

#### Scenario: "The system is slow"

**Check These Metrics:**
1. `queue_depth` - Are tasks backing up?
2. `database_connections_active` - Database bottleneck?
3. `github_api_latency` - External API issues?
4. `memory_usage` - Resource constraints?

**Investigation Steps:**
```bash
# Check current queue status
curl http://localhost:8080/metrics | grep queue_depth

# Check database connections
curl http://localhost:8081/health/detailed | jq '.checks.database'

# Review recent error logs
tail -n 100 logs/agentic.log | grep ERROR
```

#### Scenario: "Fixes aren't being applied"

**Check These Metrics:**
1. `fixes_attempted` vs `fixes_successful`
2. `llm_api_errors` - LLM service issues?
3. `github_push_errors` - Git/GitHub problems?

**Investigation Dashboard:**
- Fix success rate over time
- LLM API latency trends
- GitHub API rate limit usage

#### Scenario: "Too many notifications"

**Check These Metrics:**
1. `notifications_sent_total` - Volume trends
2. `analysis_confidence_score` - Are we being too cautious?
3. `fix_category_distribution` - What types are failing?

### Metric-Driven Scaling Decisions

```yaml
# Auto-scaling based on metrics
scaling:
  triggers:
    queue_depth:
      scale_up: "> 100"
      scale_down: "< 10"
      
    cpu_usage:
      scale_up: "> 70%"
      scale_down: "< 30%"
      
    memory_usage:
      scale_up: "> 80%"
      scale_down: "< 40%"
```

## Sample Monitoring Playbook

### Daily Monitoring Tasks

```bash
#!/bin/bash
# daily-check.sh

echo "=== Daily Agentic Workflow Health Check ==="

# Check service status
curl -s http://localhost:8081/health | jq '.status'

# Check key metrics
echo "Queue Depth: $(curl -s http://localhost:8080/metrics | grep queue_depth | awk '{print $2}')"
echo "Error Rate: $(curl -s http://localhost:8080/metrics | grep error_rate | awk '{print $2}')"

# Check disk space for logs
df -h logs/

# Check recent errors
echo "Recent Errors (last hour):"
grep -c ERROR logs/agentic.log | tail -1
```

### Weekly Performance Review

1. **Review Grafana dashboards** for trends
2. **Analyze fix success rates** by category
3. **Check API rate limit usage** trends
4. **Review alert frequency** and accuracy
5. **Update monitoring thresholds** based on learnings

### Monthly Capacity Planning

1. **Analyze growth trends** in PR volume
2. **Review resource utilization** patterns
3. **Plan infrastructure scaling** needs
4. **Update monitoring strategy** based on new requirements

---

**Next Steps:**
- 📊 **Set up basic monitoring**: Start with Prometheus + Grafana
- 🚨 **Configure critical alerts**: Focus on service availability
- 📈 **Create business dashboards**: Track fix success rates
- 🔍 **Implement detailed logging**: Enable JSON structured logs

**Related Guides:**
- [Configuration Guide](configuration.md) - Configure monitoring settings
- [Troubleshooting Guide](troubleshooting.md) - Use metrics for problem resolution
- [Installation Guide](../getting-started/installation.md) - Set up monitoring infrastructure