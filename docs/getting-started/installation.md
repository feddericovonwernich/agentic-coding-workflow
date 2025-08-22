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

> **📚 Navigation**: This section covers **environment setup and installation troubleshooting**. For operational issues after installation, see **[User Troubleshooting Guide](../user-guide/troubleshooting.md)**. For configuration validation problems, see **[Configuration Troubleshooting](../config/troubleshooting.md)**.

### Quick Diagnosis

```bash
# Run comprehensive installation check
python -c "
import sys
import os

print('=== Installation Health Check ===')
print(f'Python version: {sys.version}')
print(f'Working directory: {os.getcwd()}')

# Check modules
try:
    from src.config import load_config
    print('✅ Core modules importable')
except ImportError as e:
    print(f'❌ Import error: {e}')

# Check environment variables
required_vars = ['GITHUB_TOKEN', 'ANTHROPIC_API_KEY', 'DATABASE_URL']
for var in required_vars:
    if os.getenv(var):
        print(f'✅ {var} set')
    else:
        print(f'❌ {var} missing')

print('=== End Health Check ===')
"
```

### Python Environment Issues

#### Issue: ImportError: No module named 'src'

**Symptoms:**
```
ImportError: No module named 'src'
ModuleNotFoundError: No module named 'src.config'
```

**Solutions:**

1. **Install in development mode:**
   ```bash
   # Ensure you're in the project root directory
   cd agentic-coding-workflow
   pip install -e .
   ```

2. **Check Python path:**
   ```bash
   # Add current directory to Python path
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   
   # Verify path
   python -c "import sys; print(sys.path)"
   ```

3. **Verify directory structure:**
   ```bash
   # Should show src/ directory with __init__.py
   ls -la src/
   ```

#### Issue: Dependency Installation Failures

**Symptoms:**
```
ERROR: Failed building wheel for package
Unable to install requirements
```

**Solutions:**

1. **Update pip and setuptools:**
   ```bash
   pip install --upgrade pip setuptools wheel
   ```

2. **Install with verbose output:**
   ```bash
   pip install -r requirements.txt -v
   ```

3. **Use binary packages:**
   ```bash
   pip install --only-binary=all -r requirements.txt
   ```

4. **For specific package failures:**
   ```bash
   # Install system dependencies (Ubuntu/Debian)
   sudo apt-get update
   sudo apt-get install python3-dev libpq-dev gcc
   
   # Or on macOS
   brew install postgresql
   ```

#### Issue: Virtual Environment Problems

**Symptoms:**
```
Command 'python' not found
pip: command not found
```

**Solutions:**

1. **Recreate virtual environment:**
   ```bash
   # Remove existing environment
   rm -rf .venv
   
   # Create new environment
   python3 -m venv .venv
   source .venv/bin/activate
   
   # Verify activation
   which python
   which pip
   ```

2. **Check Python version:**
   ```bash
   python --version  # Should be 3.11+
   ```

### Environment Variable Issues

#### Issue: Environment Variables Not Set

**Symptoms:**
```
ValueError: Required environment variable 'GITHUB_TOKEN' not found
KeyError: 'ANTHROPIC_API_KEY'
```

**Diagnosis:**
```bash
# Check which variables are missing
python -c "
import os
required = ['GITHUB_TOKEN', 'ANTHROPIC_API_KEY', 'DATABASE_URL', 'REDIS_URL']
for var in required:
    value = os.getenv(var)
    if value:
        print(f'✅ {var}: {var[:10]}...' if len(var) > 10 else f'✅ {var}: set')
    else:
        print(f'❌ {var}: not set')
"
```

**Solutions:**

1. **Create .env file:**
   ```bash
   # Copy and edit example
   cp .env.example .env
   nano .env  # Edit with your values
   ```

2. **Set variables directly:**
   ```bash
   # Set temporarily (current session)
   export GITHUB_TOKEN="your_github_token_here"
   export ANTHROPIC_API_KEY="your_anthropic_key_here"
   export DATABASE_URL="postgresql://user:pass@localhost:5432/db"
   
   # Make permanent (add to ~/.bashrc or ~/.zshrc)
   echo 'export GITHUB_TOKEN="your_token"' >> ~/.bashrc
   ```

3. **Verify variable loading:**
   ```bash
   # Source environment file
   set -a && source .env && set +a
   
   # Test loading
   python -c "import os; print('GitHub token:', 'SET' if os.getenv('GITHUB_TOKEN') else 'NOT SET')"
   ```

#### Issue: GitHub Token Authentication

**Symptoms:**
```
github.GithubException: 401 {'message': 'Bad credentials'}
requests.exceptions.HTTPError: 401 Client Error: Unauthorized
```

**Solutions:**

1. **Verify token format:**
   ```bash
   # Classic tokens start with 'ghp_'
   echo $GITHUB_TOKEN | grep '^ghp_' || echo "❌ Invalid token format"
   
   # Fine-grained tokens start with 'github_pat_'
   echo $GITHUB_TOKEN | grep '^github_pat_' || echo "❌ Invalid token format"
   ```

2. **Test token manually:**
   ```bash
   curl -H "Authorization: token $GITHUB_TOKEN" \
        https://api.github.com/user
   ```

3. **Check token permissions:**
   ```bash
   # Check scopes (classic tokens)
   curl -H "Authorization: token $GITHUB_TOKEN" \
        https://api.github.com/user | jq '.scopes'
   
   # Token needs: repo, workflow scopes
   ```

4. **Create new token:**
   - Go to GitHub Settings → Developer settings → Personal access tokens
   - Generate new token with `repo` and `workflow` scopes
   - Copy the token immediately (you won't see it again)

#### Issue: LLM API Key Problems

**Symptoms:**
```
anthropic.AuthenticationError: API key not valid
openai.error.AuthenticationError: Incorrect API key provided
```

**Solutions:**

1. **Verify Anthropic API key:**
   ```bash
   # Check key format (should start with 'sk-ant-')
   echo $ANTHROPIC_API_KEY | grep '^sk-ant-' || echo "❌ Invalid Anthropic key format"
   
   # Test API key
   curl -H "x-api-key: $ANTHROPIC_API_KEY" \
        -H "content-type: application/json" \
        https://api.anthropic.com/v1/messages \
        -d '{"model":"claude-3-haiku-20240307","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
   ```

2. **Verify OpenAI API key:**
   ```bash
   # Check key format (should start with 'sk-')
   echo $OPENAI_API_KEY | grep '^sk-' || echo "❌ Invalid OpenAI key format"
   
   # Test API key
   curl -H "Authorization: Bearer $OPENAI_API_KEY" \
        https://api.openai.com/v1/models
   ```

3. **Check account status:**
   - Log into Anthropic Console / OpenAI Dashboard
   - Verify account is active and has credits
   - Check usage limits and billing status

### Database Setup Issues

#### Issue: Database Connection Failed

**Symptoms:**
```
sqlalchemy.exc.OperationalError: could not connect to server
psycopg2.OperationalError: connection to server refused
redis.exceptions.ConnectionError: Error connecting to Redis
```

**Solutions:**

1. **PostgreSQL setup:**
   ```bash
   # Install PostgreSQL
   # Ubuntu/Debian:
   sudo apt-get install postgresql postgresql-contrib
   
   # macOS:
   brew install postgresql
   brew services start postgresql
   
   # Create database and user
   sudo -u postgres createdb agentic_workflow
   sudo -u postgres createuser --interactive agentic_user
   ```

2. **Docker database setup:**
   ```bash
   # Start PostgreSQL with Docker
   docker run --name agentic-postgres \
     -e POSTGRES_DB=agentic_workflow \
     -e POSTGRES_USER=agentic_user \
     -e POSTGRES_PASSWORD=your_password \
     -p 5432:5432 \
     -d postgres:15
   
   # Start Redis
   docker run --name agentic-redis \
     -p 6379:6379 \
     -d redis:7-alpine
   ```

3. **Test connections:**
   ```bash
   # Test PostgreSQL
   pg_isready -h localhost -p 5432
   psql "postgresql://agentic_user:password@localhost:5432/agentic_workflow"
   
   # Test Redis
   redis-cli ping  # Should return PONG
   ```

4. **Database URL configuration:**
   ```bash
   # PostgreSQL
   export DATABASE_URL="postgresql://agentic_user:password@localhost:5432/agentic_workflow"
   
   # Redis
   export REDIS_URL="redis://localhost:6379/0"
   
   # SQLite (for development)
   export DATABASE_URL="sqlite:///./agentic.db"
   ```

#### Issue: Database Migration Failures

**Symptoms:**
```
alembic.util.exc.CommandError: Can't locate revision identified by
sqlalchemy.exc.OperationalError: relation does not exist
```

**Solutions:**

1. **Run initial migrations:**
   ```bash
   # Generate initial migration (if needed)
   alembic revision --autogenerate -m "Initial migration"
   
   # Apply migrations
   alembic upgrade head
   
   # Verify migration
   alembic current
   ```

2. **Reset migration state:**
   ```bash
   # Drop all tables and start fresh
   python -c "
   from src.database import engine, Base
   import asyncio
   
   async def reset_db():
       async with engine.begin() as conn:
           await conn.run_sync(Base.metadata.drop_all)
           await conn.run_sync(Base.metadata.create_all)
   
   asyncio.run(reset_db())
   "
   
   # Re-run migrations
   alembic stamp head
   ```

### Service Dependencies

#### Issue: Docker Not Available

**Symptoms:**
```
Cannot connect to the Docker daemon
docker: command not found
```

**Solutions:**

1. **Install Docker:**
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   
   # Log out and back in, then test
   docker run hello-world
   ```

2. **Start Docker service:**
   ```bash
   # Linux
   sudo systemctl start docker
   sudo systemctl enable docker
   
   # macOS/Windows: Start Docker Desktop application
   ```

3. **Alternative without Docker:**
   ```bash
   # Use local services instead
   # Install PostgreSQL locally
   sudo apt-get install postgresql
   
   # Install Redis locally
   sudo apt-get install redis-server
   ```

#### Issue: Port Conflicts

**Symptoms:**
```
Error: Port 5432 is already in use
bind: address already in use
```

**Solutions:**

1. **Check what's using the port:**
   ```bash
   # Check specific port
   lsof -i :5432
   netstat -tulpn | grep :5432
   
   # Kill conflicting process
   sudo kill -9 <PID>
   ```

2. **Use different ports:**
   ```bash
   # Start services on different ports
   docker run -p 5433:5432 postgres:15  # PostgreSQL on 5433
   docker run -p 6380:6379 redis:7      # Redis on 6380
   
   # Update environment variables
   export DATABASE_URL="postgresql://user:pass@localhost:5433/db"
   export REDIS_URL="redis://localhost:6380/0"
   ```

### Configuration Loading Issues

#### Issue: Configuration File Not Found

**Symptoms:**
```
ConfigurationFileError: Configuration file not found
FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'
```

**Solutions:**

1. **Create configuration file:**
   ```bash
   # Copy example file
   cp config.example.yaml config.yaml
   
   # Or create minimal config
   cat > config.yaml << 'EOF'
   repositories:
     - url: "https://github.com/your-org/your-repo"
       auth_token: "${GITHUB_TOKEN}"
   
   llm:
     anthropic:
       api_key: "${ANTHROPIC_API_KEY}"
   
   database:
     url: "${DATABASE_URL}"
   
   queue:
     url: "${REDIS_URL}"
   EOF
   ```

2. **Set explicit config path:**
   ```bash
   export AGENTIC_CONFIG_PATH="/path/to/your/config.yaml"
   ```

#### Issue: YAML Parsing Errors

**Symptoms:**
```
yaml.scanner.ScannerError: while scanning a simple key
yaml.parser.ParserError: expected <block end>
```

**Solutions:**

1. **Validate YAML syntax:**
   ```bash
   # Test YAML parsing
   python -c "import yaml; yaml.safe_load(open('config.yaml'))"
   
   # Use online YAML validator
   cat config.yaml | python -c "import sys, yaml; yaml.safe_load(sys.stdin)"
   ```

2. **Fix common YAML issues:**
   ```yaml
   # ❌ Wrong indentation
   database:
     url: "postgresql://..."
       pool_size: 10  # Too much indentation
   
   # ✅ Correct indentation
   database:
     url: "postgresql://..."
     pool_size: 10
   
   # ❌ Missing quotes for special characters
   password: p@ssw0rd!
   
   # ✅ Quoted special characters
   password: "p@ssw0rd!"
   ```

### System Resource Issues

#### Issue: Insufficient Memory

**Symptoms:**
```
MemoryError: Unable to allocate memory
OOMKilled: process killed due to memory pressure
```

**Solutions:**

1. **Check system resources:**
   ```bash
   # Check available memory
   free -h
   
   # Check running processes
   ps aux --sort=-%mem | head -10
   ```

2. **Optimize for lower memory:**
   ```yaml
   # config.yaml - reduce resource usage
   database:
     pool_size: 5        # Reduce from default 20
     max_overflow: 10    # Reduce from default 30
   
   workers:
     monitor:
       concurrency: 1    # Reduce concurrent workers
     analyzer:
       concurrency: 1
   ```

#### Issue: Permission Denied

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied
chmod: Operation not permitted
```

**Solutions:**

1. **Fix file permissions:**
   ```bash
   # Fix config file permissions
   chmod 644 config.yaml
   chmod 600 .env  # Sensitive environment file
   
   # Fix directory permissions
   chmod 755 logs/
   mkdir -p logs/  # Ensure logs directory exists
   ```

2. **Check user permissions:**
   ```bash
   # Check current user
   id
   
   # Check file ownership
   ls -la config.yaml .env
   
   # Fix ownership if needed
   sudo chown $USER:$USER config.yaml .env
   ```

### Getting Help

#### Diagnostic Information Collection

When reporting installation issues, include:

```bash
# System information
echo "=== System Information ==="
uname -a
python --version
pip --version
docker --version 2>/dev/null || echo "Docker not installed"

# Environment check
echo -e "\n=== Environment Variables ==="
env | grep -E "(GITHUB|ANTHROPIC|OPENAI|DATABASE|REDIS)" | cut -d= -f1

# Configuration check
echo -e "\n=== Configuration ==="
ls -la config.yaml .env 2>/dev/null || echo "Config files not found"

# Dependencies check
echo -e "\n=== Dependencies ==="
pip list | grep -E "(fastapi|sqlalchemy|anthropic|openai|redis|psycopg2)"

# Services check
echo -e "\n=== Services ==="
pg_isready -h localhost -p 5432 2>/dev/null && echo "PostgreSQL: OK" || echo "PostgreSQL: Not available"
redis-cli ping 2>/dev/null && echo "Redis: OK" || echo "Redis: Not available"
```

#### Support Resources

- **[Configuration Troubleshooting](../config/troubleshooting.md)** - For configuration validation issues
- **[User Troubleshooting Guide](../user-guide/troubleshooting.md)** - For operational issues after installation  
- **[GitHub Issues](https://github.com/feddericovonwernich/agentic-coding-workflow/issues)** - Report installation bugs
- **[Troubleshooting Hub](../troubleshooting-hub.md)** - Find the right troubleshooting guide

#### Installation Success Verification

After resolving issues, verify your installation:

```bash
# Complete verification script
python -c "
import sys
import os

def test_installation():
    print('=== Installation Verification ===')
    
    # 1. Python version
    print(f'✅ Python {sys.version}')
    
    # 2. Import core modules
    try:
        from src.config import load_config
        print('✅ Core modules importable')
    except ImportError as e:
        print(f'❌ Import failed: {e}')
        return False
    
    # 3. Environment variables
    required_vars = ['GITHUB_TOKEN', 'ANTHROPIC_API_KEY']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f'❌ Missing variables: {missing}')
        return False
    print('✅ Required environment variables set')
    
    # 4. Configuration loading
    try:
        config = load_config()
        print('✅ Configuration loads successfully')
    except Exception as e:
        print(f'❌ Configuration error: {e}')
        return False
    
    print('✅ Installation verification successful!')
    return True

if not test_installation():
    sys.exit(1)
"
```

---

**Next**: [First Deployment Guide](first-deployment.md) | **Support**: [Create an issue](https://github.com/feddericovonwernich/agentic-coding-workflow/issues)