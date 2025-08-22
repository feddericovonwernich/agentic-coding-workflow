# Installation Guide

This guide provides comprehensive installation instructions for the Agentic Coding Workflow system across different environments and deployment scenarios.

## Table of Contents

- [System Requirements](#system-requirements)
- [Installation Methods](#installation-methods)
- [Environment Setup](#environment-setup)
- [Database Configuration](#database-configuration)
- [Service Dependencies](#service-dependencies)
- [Verification](#verification)
- [Environment-Specific Setup](#environment-specific-setup)

## System Requirements

### Minimum Requirements

| Component | Requirement |
|-----------|-------------|
| **OS** | Linux, macOS, or Windows with WSL2 |
| **Python** | 3.11 or higher |
| **Memory** | 2GB RAM minimum, 4GB recommended |
| **Storage** | 5GB available disk space |
| **Network** | Internet access for API calls |

### Recommended Requirements

| Component | Requirement |
|-----------|-------------|
| **Memory** | 8GB RAM for production workloads |
| **CPU** | 2+ cores |
| **Storage** | 20GB+ for logs and database |
| **Database** | PostgreSQL 12+ for production |

### External Dependencies

- **GitHub Personal Access Token** with `repo` scope
- **LLM API Access**: Anthropic Claude or OpenAI GPT
- **Docker** (recommended for database and services)

## Installation Methods

### Method 1: Direct Installation (Recommended)

```bash
# Clone the repository
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "from src.config import load_config; print('✅ Installation successful')"
```

### Method 2: Docker Installation

```bash
# Clone repository
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow

# Build Docker image
docker build -t agentic-coding-workflow .

# Run with Docker Compose
docker-compose up -d
```

### Method 3: Development Installation

```bash
# Clone repository
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow

# Install in development mode with dev dependencies
pip install -e .
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

## Environment Setup

### 1. Create Environment Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit with your specific values
nano .env  # or your preferred editor
```

### 2. Required Environment Variables

```bash
# GitHub Integration
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
# Scope: repo (for private repos) or public_repo (for public repos only)

# LLM Provider Configuration
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx
# OR
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxx

# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/agentic_workflow
# For development: sqlite:///./agentic.db

# Queue Configuration (optional)
REDIS_URL=redis://localhost:6379/0
# For development: can use memory queue

# Notification Configuration (optional)
TELEGRAM_BOT_TOKEN=1234567890:xxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/xxx/xxx

# Email notifications (optional)
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
```

### 3. GitHub Token Setup

1. **Create Personal Access Token**:
   - Go to GitHub Settings → Developer settings → Personal access tokens
   - Generate new token (classic)
   - Select scopes: `repo`, `workflow`, `read:org`

2. **For GitHub Apps** (advanced):
   ```bash
   # If using GitHub App instead of PAT
   GITHUB_APP_ID=123456
   GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem
   GITHUB_APP_INSTALLATION_ID=12345678
   ```

### 4. LLM Provider Setup

#### Anthropic Claude Setup
```bash
# Get API key from https://console.anthropic.com/
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxx

# Optional: Model selection
ANTHROPIC_MODEL=claude-3-sonnet-20240229  # Default
# Options: claude-3-opus-20240229, claude-3-haiku-20240307
```

#### OpenAI Setup
```bash
# Get API key from https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxx

# Optional: Model and organization
OPENAI_MODEL=gpt-4  # Default
OPENAI_ORG_ID=org-xxxxxxxxxx  # If using organization
```

## Database Configuration

### SQLite (Development)

```bash
# Simple file-based database
DATABASE_URL=sqlite:///./agentic.db

# Create database and run migrations
alembic upgrade head
```

### PostgreSQL (Production)

#### Option 1: Local PostgreSQL

```bash
# Install PostgreSQL
sudo apt install postgresql postgresql-contrib  # Ubuntu/Debian
brew install postgresql  # macOS

# Create database and user
sudo -u postgres psql
CREATE DATABASE agentic_workflow;
CREATE USER agentic_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE agentic_workflow TO agentic_user;
\q

# Update environment
DATABASE_URL=postgresql://agentic_user:secure_password@localhost:5432/agentic_workflow
```

#### Option 2: Docker PostgreSQL

```bash
# Start PostgreSQL container
docker run -d \
  --name agentic-postgres \
  -e POSTGRES_DB=agentic_workflow \
  -e POSTGRES_USER=agentic_user \
  -e POSTGRES_PASSWORD=secure_password \
  -p 5432:5432 \
  postgres:15-alpine

# Update environment
DATABASE_URL=postgresql://agentic_user:secure_password@localhost:5432/agentic_workflow
```

#### Option 3: Hosted Database

Popular hosted options:
- **AWS RDS**: `postgresql://user:pass@rds-instance.amazonaws.com:5432/agentic`
- **Google Cloud SQL**: `postgresql://user:pass@google-sql-ip:5432/agentic`
- **Heroku Postgres**: `postgresql://user:pass@host:5432/database`
- **Railway**: `postgresql://user:pass@railway.app:5432/database`

### Database Migrations

```bash
# Run migrations to create tables
alembic upgrade head

# Verify database setup
python -c "from src.database import get_connection_manager; print('✅ Database connected')"
```

## Service Dependencies

### Redis Queue (Optional but Recommended)

#### Local Redis
```bash
# Install Redis
sudo apt install redis-server  # Ubuntu/Debian
brew install redis  # macOS

# Start Redis
redis-server

# Update environment
REDIS_URL=redis://localhost:6379/0
```

#### Docker Redis
```bash
# Start Redis container
docker run -d \
  --name agentic-redis \
  -p 6379:6379 \
  redis:7-alpine

# Update environment
REDIS_URL=redis://localhost:6379/0
```

#### Hosted Redis
- **Redis Cloud**: Free tier available
- **AWS ElastiCache**: Production Redis service
- **Railway**: Redis addon

### Docker Compose (All Services)

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: agentic_workflow
      POSTGRES_USER: agentic_user
      POSTGRES_PASSWORD: secure_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    build: .
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql://agentic_user:secure_password@postgres:5432/agentic_workflow
      REDIS_URL: redis://redis:6379/0
    env_file:
      - .env

volumes:
  postgres_data:
```

## Verification

### 1. Test Installation

```bash
# Test basic imports
python -c "
from src.config import load_config
from src.database import get_connection_manager
print('✅ Core modules loaded successfully')
"
```

### 2. Test Configuration

```bash
# Create minimal test config
cat > test-config.yaml << EOF
repositories:
  - url: "https://github.com/octocat/Hello-World"
    name: "test-repo"

llm:
  anthropic:
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"

default_llm_provider: anthropic

database:
  url: "${DATABASE_URL}"

queue:
  provider: memory
EOF

# Test configuration loading
python -c "
from src.config import load_config
config = load_config('test-config.yaml')
print('✅ Configuration loaded successfully')
"
```

### 3. Test Database Connection

```bash
# Test database connectivity
python -c "
import asyncio
from src.database import get_connection_manager
from src.config import load_config

async def test_db():
    config = load_config()
    manager = get_connection_manager(config.database)
    async with manager.get_session() as session:
        result = await session.execute('SELECT 1')
        print('✅ Database connection successful')

asyncio.run(test_db())
"
```

### 4. Test GitHub API

```bash
# Test GitHub token
python -c "
import os
import requests

token = os.getenv('GITHUB_TOKEN')
response = requests.get(
    'https://api.github.com/rate_limit',
    headers={'Authorization': f'token {token}'}
)
if response.status_code == 200:
    print('✅ GitHub API access successful')
    print(f'Rate limit: {response.json()[\"rate\"][\"remaining\"]}/{response.json()[\"rate\"][\"limit\"]}')
else:
    print('❌ GitHub API access failed')
    print(f'Status: {response.status_code}')
"
```

### 5. Test LLM Provider

```bash
# Test Anthropic
python -c "
import os
import requests

api_key = os.getenv('ANTHROPIC_API_KEY')
if api_key:
    print('✅ Anthropic API key configured')
else:
    print('❌ Anthropic API key not found')
"

# Test OpenAI
python -c "
import os

api_key = os.getenv('OPENAI_API_KEY')
if api_key:
    print('✅ OpenAI API key configured')
else:
    print('❌ OpenAI API key not found')
"
```

## Environment-Specific Setup

### Development Environment

```bash
# Additional development tools
pip install -r requirements-dev.txt

# Code quality tools
ruff check .
mypy src/

# Run tests
pytest tests/ -v
```

### Staging Environment

```bash
# Use production-like database
DATABASE_URL=postgresql://user:pass@staging-db:5432/agentic_staging

# Enable detailed logging
LOG_LEVEL=DEBUG

# Use staging notification channels
TELEGRAM_CHAT_ID=staging_chat_id
```

### Production Environment

```bash
# Production database with connection pooling
DATABASE_URL=postgresql://user:pass@prod-db:5432/agentic_prod
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30

# Production Redis
REDIS_URL=redis://prod-redis:6379/0

# Error monitoring
SENTRY_DSN=https://your-sentry-dsn

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

## Next Steps

After successful installation:

1. **[First Deployment](first-deployment.md)** - Deploy your first monitoring setup
2. **[User Configuration Guide](../user-guide/configuration.md)** - Customize for your needs
3. **[Monitoring Guide](../user-guide/monitoring.md)** - Set up observability

## Troubleshooting

### Common Installation Issues

**ImportError: No module named 'src'**
```bash
# Ensure you're in the project directory
cd agentic-coding-workflow
pip install -e .
```

**Database connection failed**
```bash
# Check database is running
pg_isready -h localhost -p 5432  # PostgreSQL
redis-cli ping  # Redis
```

**GitHub API rate limit exceeded**
```bash
# Check your token permissions and usage
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit
```

For more detailed troubleshooting, see the [User Troubleshooting Guide](../user-guide/troubleshooting.md).

---

**Next**: [First Deployment Guide](first-deployment.md) | **Support**: [Create an issue](https://github.com/feddericovonwernich/agentic-coding-workflow/issues)