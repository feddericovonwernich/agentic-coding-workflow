# First Deployment Guide

This guide walks you through deploying the Agentic Coding Workflow system for the first time in a production or production-like environment. Follow this step-by-step walkthrough to ensure a smooth deployment.

## Pre-Deployment Checklist

Before starting deployment, ensure you have:

- [ ] Completed [Installation Guide](installation.md)
- [ ] Production database (PostgreSQL) accessible
- [ ] Redis instance for job queuing
- [ ] GitHub repository with CI/CD checks configured
- [ ] Valid API keys for LLM provider
- [ ] Monitoring/alerting system ready (optional)
- [ ] Backup strategy planned

## Deployment Scenarios

Choose your deployment scenario:

- [**Scenario A**: Single Server Deployment](#scenario-a-single-server-deployment) (Recommended for small teams)
- [**Scenario B**: Docker Compose Deployment](#scenario-b-docker-compose-deployment) (Recommended for containerized environments)
- [**Scenario C**: Kubernetes Deployment](#scenario-c-kubernetes-deployment) (For scalable production)

---

## Scenario A: Single Server Deployment

### Step 1: Server Preparation (5 minutes)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3.11 python3.11-venv postgresql-client redis-tools git

# Create dedicated user
sudo useradd -m -s /bin/bash agentic
sudo su - agentic
```

### Step 2: Application Setup (10 minutes)

**Prerequisites:** Complete the [Installation Guide](installation.md) for your environment first.

```bash
# Clone repository (if not already done)
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow

# Follow installation guide for dependencies and environment setup
# Then return here for production-specific configuration
```

### Step 3: Production Configuration (15 minutes)

```bash
# Create production environment file
cat > .env << 'EOF'
# Production Environment Configuration

# System Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_FORMAT=json

# Database Configuration
DATABASE_URL=postgresql://agentic_user:SECURE_PASSWORD@db-host:5432/agentic_prod
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600
DATABASE_POOL_PRE_PING=true

# Queue Configuration
REDIS_URL=redis://redis-host:6379/0

# GitHub Integration
GITHUB_TOKEN=ghp_YOUR_PRODUCTION_TOKEN

# LLM Provider
ANTHROPIC_API_KEY=sk-ant-YOUR_PRODUCTION_KEY

# Notifications
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_PRODUCTION_CHAT_ID

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Security
SECRET_KEY=your-very-secure-secret-key-here
ALLOWED_HOSTS=your-domain.com

# Monitoring
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
EOF

# Secure the environment file
chmod 600 .env
```

### Step 4: Production Config File (10 minutes)

```bash
# Create production configuration
cat > config.yaml << 'EOF'
# Production Configuration
system:
  environment: production
  debug_mode: false
  log_level: INFO
  log_format: json
  max_workers: 4
  worker_timeout: 300
  circuit_breaker:
    failure_threshold: 5
    recovery_timeout: 60
    half_open_max_calls: 3

database:
  url: "${DATABASE_URL}"
  pool:
    pool_size: "${DATABASE_POOL_SIZE:20}"
    max_overflow: "${DATABASE_MAX_OVERFLOW:30}"
    pool_timeout: "${DATABASE_POOL_TIMEOUT:30}"
    pool_recycle: "${DATABASE_POOL_RECYCLE:3600}"
    pool_pre_ping: "${DATABASE_POOL_PRE_PING:true}"

queue:
  provider: redis
  url: "${REDIS_URL}"
  retry_attempts: 3
  retry_delay: 5
  max_queue_size: 1000

llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: claude-3-sonnet-20240229
    max_tokens: 4096
    temperature: 0.2
    timeout: 30

default_llm_provider: anthropic

repositories:
  - url: "https://github.com/YOUR_ORG/YOUR_REPO"
    name: "your-main-repo"
    polling_interval: 300
    auto_fix:
      enabled: true
      categories:
        - lint
        - formatting
        - simple_tests
      confidence_threshold: 85
      max_attempts: 3
    
    skip_patterns:
      - "*.md"
      - "docs/**"
      - "*.txt"
    
    notification_channels:
      - telegram
      - slack

notification:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
    message_format: markdown
    
  slack:
    enabled: true
    webhook_url: "${SLACK_WEBHOOK_URL}"
    channel: "#dev-alerts"
    username: "Agentic Bot"
    
  email:
    enabled: false
    
claude_code_sdk:
  timeout: 120
  retry_attempts: 3
EOF
```

### Step 5: Database Migration (5 minutes)

```bash
# Run database migrations
alembic upgrade head

# Verify database setup
python -c "
import asyncio
from src.config import load_config
from src.database import get_connection_manager

async def test():
    config = load_config()
    manager = get_connection_manager(config.database)
    async with manager.get_session() as session:
        result = await session.execute('SELECT 1')
        print('✅ Database connection successful')

asyncio.run(test())
"
```

### Step 6: Service Setup (10 minutes)

Create systemd service files:

```bash
# Create systemd service file
sudo tee /etc/systemd/system/agentic-monitor.service << 'EOF'
[Unit]
Description=Agentic Coding Workflow Monitor
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=agentic
Group=agentic
WorkingDirectory=/home/agentic/agentic-coding-workflow
Environment=PATH=/home/agentic/agentic-coding-workflow/.venv/bin
ExecStart=/home/agentic/agentic-coding-workflow/.venv/bin/python -m src.workers.monitor
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/agentic/agentic-coding-workflow

[Install]
WantedBy=multi-user.target
EOF

# Create analyzer service
sudo tee /etc/systemd/system/agentic-analyzer.service << 'EOF'
[Unit]
Description=Agentic Coding Workflow Analyzer
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=agentic
Group=agentic
WorkingDirectory=/home/agentic/agentic-coding-workflow
Environment=PATH=/home/agentic/agentic-coding-workflow/.venv/bin
ExecStart=/home/agentic/agentic-coding-workflow/.venv/bin/python -m src.workers.analyzer
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/agentic/agentic-coding-workflow

[Install]
WantedBy=multi-user.target
EOF

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable agentic-monitor agentic-analyzer
sudo systemctl start agentic-monitor agentic-analyzer
```

### Step 7: Verification (5 minutes)

```bash
# Check service status
sudo systemctl status agentic-monitor agentic-analyzer

# Check logs
sudo journalctl -u agentic-monitor -f
sudo journalctl -u agentic-analyzer -f

# Test configuration
python -c "from src.config import load_config; config = load_config(); print('✅ Configuration loaded')"
```

---

## Scenario B: Docker Compose Deployment

### Step 1: Docker Compose Setup (10 minutes)

```bash
# Clone repository
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow

# Create production docker-compose file
cat > docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: agentic_workflow
      POSTGRES_USER: agentic_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    ports:
      - "5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentic_user"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  agentic-monitor:
    build: .
    command: python -m src.workers.monitor
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://agentic_user:${POSTGRES_PASSWORD}@postgres:5432/agentic_workflow
      - REDIS_URL=redis://redis:6379/0
    env_file:
      - .env
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./logs:/app/logs
    restart: unless-stopped

  agentic-analyzer:
    build: .
    command: python -m src.workers.analyzer
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://agentic_user:${POSTGRES_PASSWORD}@postgres:5432/agentic_workflow
      - REDIS_URL=redis://redis:6379/0
    env_file:
      - .env
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./logs:/app/logs
    restart: unless-stopped

  agentic-fixer:
    build: .
    command: python -m src.workers.fixer
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://agentic_user:${POSTGRES_PASSWORD}@postgres:5432/agentic_workflow
      - REDIS_URL=redis://redis:6379/0
    env_file:
      - .env
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./logs:/app/logs
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
EOF
```

### Step 2: Environment Setup (5 minutes)

```bash
# Create production environment
cat > .env << 'EOF'
# Production Docker Environment
ENVIRONMENT=production
POSTGRES_PASSWORD=very_secure_password_here

# GitHub Integration
GITHUB_TOKEN=ghp_YOUR_TOKEN

# LLM Provider  
ANTHROPIC_API_KEY=sk-ant-YOUR_KEY

# Notifications
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK

# Monitoring
SENTRY_DSN=https://your-sentry-dsn
EOF

chmod 600 .env
```

### Step 3: Deploy Services (5 minutes)

```bash
# Build and start services
docker-compose -f docker-compose.prod.yml up -d

# Run database migrations
docker-compose -f docker-compose.prod.yml exec agentic-monitor alembic upgrade head

# Check service health
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs -f
```

---

## Scenario C: Kubernetes Deployment

### Step 1: Create Kubernetes Manifests (15 minutes)

```bash
# Create namespace
kubectl create namespace agentic-workflow

# Create secrets
kubectl create secret generic agentic-secrets \
  --from-literal=github-token=ghp_YOUR_TOKEN \
  --from-literal=anthropic-api-key=sk-ant-YOUR_KEY \
  --from-literal=postgres-password=secure_password \
  --namespace=agentic-workflow

# Create ConfigMap for configuration
kubectl create configmap agentic-config \
  --from-file=config.yaml \
  --namespace=agentic-workflow
```

### Step 2: Deploy Database and Redis (10 minutes)

```yaml
# postgresql.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: agentic-workflow
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        env:
        - name: POSTGRES_DB
          value: agentic_workflow
        - name: POSTGRES_USER
          value: agentic_user
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: agentic-secrets
              key: postgres-password
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: postgres-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 20Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: agentic-workflow
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
```

### Step 3: Deploy Application Services (10 minutes)

```yaml
# agentic-monitor.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentic-monitor
  namespace: agentic-workflow
spec:
  replicas: 2
  selector:
    matchLabels:
      app: agentic-monitor
  template:
    metadata:
      labels:
        app: agentic-monitor
    spec:
      containers:
      - name: agentic-monitor
        image: agentic-coding-workflow:latest
        command: ["python", "-m", "src.workers.monitor"]
        env:
        - name: DATABASE_URL
          value: postgresql://agentic_user:$(POSTGRES_PASSWORD)@postgres:5432/agentic_workflow
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: agentic-secrets
              key: postgres-password
        - name: GITHUB_TOKEN
          valueFrom:
            secretKeyRef:
              name: agentic-secrets
              key: github-token
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: agentic-secrets
              key: anthropic-api-key
        volumeMounts:
        - name: config
          mountPath: /app/config.yaml
          subPath: config.yaml
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
      volumes:
      - name: config
        configMap:
          name: agentic-config
```

---

## Post-Deployment Verification

### Comprehensive Health Check (10 minutes)

```bash
# 1. Service Health Check
curl -f http://localhost:8080/health || echo "Health endpoint not responding"

# 2. Database Connection
python -c "
import asyncio
from src.database import get_connection_manager
from src.config import load_config

async def test_db():
    config = load_config()
    manager = get_connection_manager(config.database)
    async with manager.get_session() as session:
        result = await session.execute('SELECT COUNT(*) FROM repositories')
        print(f'✅ Database: {result.scalar()} repositories configured')

asyncio.run(test_db())
"

# 3. Queue Connection
python -c "
from src.config import load_config
config = load_config()
print(f'✅ Queue configured: {config.queue.provider}')
"

# 4. GitHub API Test
python -c "
import os, requests
token = os.getenv('GITHUB_TOKEN')
response = requests.get('https://api.github.com/rate_limit', 
                       headers={'Authorization': f'token {token}'})
print(f'✅ GitHub API: {response.json()[\"rate\"][\"remaining\"]} requests remaining')
"

# 5. LLM Provider Test
python -c "
import os
anthropic_key = os.getenv('ANTHROPIC_API_KEY')
openai_key = os.getenv('OPENAI_API_KEY')
print(f'✅ LLM Provider: {\"Anthropic\" if anthropic_key else \"OpenAI\" if openai_key else \"None\"}')
"
```

### Test End-to-End Workflow (15 minutes)

1. **Create a test PR** with a linting issue in your monitored repository
2. **Monitor logs** to see the system detect the PR
3. **Verify analysis** runs and categorizes the failure
4. **Check for automatic fix** (if enabled for linting issues)
5. **Confirm notifications** are sent to configured channels

```bash
# Monitor system logs during test
# For systemd services:
sudo journalctl -u agentic-monitor -f

# For Docker Compose:
docker-compose -f docker-compose.prod.yml logs -f

# For Kubernetes:
kubectl logs -f deployment/agentic-monitor -n agentic-workflow
```

## Monitoring and Alerting Setup

### Prometheus Metrics (Optional)

```yaml
# Add to your deployment
- name: prometheus-metrics
  image: prom/node-exporter
  ports:
  - containerPort: 9100
```

### Log Aggregation

```bash
# Configure log shipping to your preferred system
# Examples: ELK Stack, Splunk, DataDog, New Relic

# For structured JSON logs
export LOG_FORMAT=json
```

### Health Check Endpoints

```bash
# Set up monitoring URLs
curl http://your-deployment/health
curl http://your-deployment/metrics
curl http://your-deployment/ready
```

## Backup and Recovery

### Database Backups

```bash
# Automated backup script
#!/bin/bash
BACKUP_DIR="/backups/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

pg_dump $DATABASE_URL > $BACKUP_DIR/agentic_backup.sql
gzip $BACKUP_DIR/agentic_backup.sql

# Keep 30 days of backups
find /backups -type d -mtime +30 -exec rm -rf {} \;
```

### Configuration Backups

```bash
# Backup configuration and secrets
tar -czf config_backup_$(date +%Y%m%d).tar.gz \
  config.yaml .env docker-compose.prod.yml
```

## Troubleshooting Common Issues

### Services Won't Start
```bash
# Check dependencies
systemctl status postgresql redis-server
docker-compose ps
kubectl get pods -n agentic-workflow

# Check logs
journalctl -u agentic-monitor --since "1 hour ago"
```

### High Memory Usage
```bash
# Adjust worker settings in config.yaml
system:
  max_workers: 2  # Reduce from default
  worker_timeout: 180  # Reduce timeout
```

### GitHub Rate Limiting
```bash
# Check rate limit status
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit

# Increase polling interval in config
repositories:
  - polling_interval: 600  # Check every 10 minutes instead of 5
```

## Next Steps

🎉 **Congratulations!** Your production deployment is complete.

### Operational Tasks

1. **[User Guide](../user-guide/README.md)** - Day-to-day operations
2. **[Monitoring Guide](../user-guide/monitoring.md)** - Set up dashboards
3. **[Configuration Guide](../user-guide/configuration.md)** - Tune for your needs

### Scaling

- **Horizontal scaling**: Add more worker instances
- **Database scaling**: Configure read replicas
- **Queue scaling**: Redis cluster or separate queues per worker type

---

**Deployment Complete** ✅ | **Time**: ~60 minutes | **Next**: [User Guide](../user-guide/README.md)