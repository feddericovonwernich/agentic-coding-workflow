# Local Development Setup

This guide provides comprehensive instructions for setting up and working with the Agentic Coding Workflow project in your local development environment.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Development Services](#development-services)
- [Development Workflows](#development-workflows)
- [IDE Configuration](#ide-configuration)
- [Debugging Setup](#debugging-setup)
- [Common Development Tasks](#common-development-tasks)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Python 3.9+** with pip and venv
- **Docker** and Docker Compose for local services
- **Git** with your GitHub credentials configured
- **Node.js 16+** (if working with frontend components)
- **PostgreSQL client tools** (optional, for database debugging)

### Tool Installation

#### macOS (using Homebrew)
```bash
# Install system dependencies
brew install python@3.9 docker git postgresql node

# Install Docker Desktop from https://docker.com/products/docker-desktop
```

#### Ubuntu/Debian
```bash
# Install system dependencies
sudo apt update
sudo apt install python3.9 python3.9-venv python3-pip docker.io docker-compose git postgresql-client nodejs npm

# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect
```

#### Windows (using WSL2)
```bash
# Install WSL2 and Ubuntu, then follow Ubuntu instructions
# Install Docker Desktop for Windows with WSL2 backend
```

### API Keys and Accounts

You'll need accounts and API keys for:

1. **GitHub**: [Personal Access Token](https://github.com/settings/tokens) with `repo` and `read:org` scopes
2. **Anthropic**: [API Key](https://console.anthropic.com/) for Claude integration
3. **OpenAI**: [API Key](https://platform.openai.com/api-keys) (optional, for comparative testing)

## Environment Setup

### 1. Repository Clone and Setup

```bash
# Clone the repository
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow

# Create and activate virtual environment
python3.9 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Verify installation
python --version  # Should show Python 3.9+
pip list | grep -E "(fastapi|sqlalchemy|anthropic)"
```

### 2. Environment Variables

Create a `.env` file in the project root:

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your actual values
# Use your preferred editor (nano, vim, code, etc.)
nano .env
```

Required environment variables:

```bash
# GitHub Integration
GITHUB_TOKEN=ghp_your_github_personal_access_token_here

# Database Configuration
DATABASE_URL=postgresql://agentic_user:agentic_password@localhost:5432/agentic_workflow
DATABASE_URL_TEST=postgresql://agentic_user:agentic_password@localhost:5432/agentic_workflow_test

# Queue Configuration
REDIS_URL=redis://localhost:6379/0

# LLM Provider APIs
ANTHROPIC_API_KEY=sk-ant-your_anthropic_api_key_here
OPENAI_API_KEY=sk-your_openai_api_key_here  # Optional

# Notification Services (Optional for development)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Development Settings
LOG_LEVEL=DEBUG
ENVIRONMENT=development

# Claude Code SDK (if using)
CLAUDE_CODE_API_KEY=your_claude_code_api_key
```

### 3. Development Tools Setup

```bash
# Install and configure pre-commit hooks
pre-commit install

# Verify pre-commit setup
pre-commit run --all-files

# Install additional development tools
pip install ipython jupyter  # For interactive development
```

## Development Services

### 1. Docker Services

Start the required infrastructure services:

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Verify services are running
docker-compose ps

# Check service logs if needed
docker-compose logs postgres
docker-compose logs redis
```

#### Service Configuration

**PostgreSQL**:
- Host: `localhost`
- Port: `5432`
- Database: `agentic_workflow`
- Username: `agentic_user`
- Password: `agentic_password`

**Redis**:
- Host: `localhost`
- Port: `6379`
- Database: `0` (default)

### 2. Database Setup

```bash
# Wait for PostgreSQL to be ready
docker-compose exec postgres pg_isready -U agentic_user

# Run database migrations
alembic upgrade head

# Create test database
docker-compose exec postgres createdb -U agentic_user agentic_workflow_test

# Verify database setup
python -c "
from src.database import get_session
import asyncio
async def test():
    session = get_session()
    await session.execute('SELECT 1')
    print('✓ Database connection successful')
asyncio.run(test())
"
```

### 3. Service Health Checks

```bash
# Check all services
python -c "
import asyncio
from src.services.health import check_all_services

async def main():
    health = await check_all_services()
    for service, status in health.items():
        print(f'{service}: {\"✓\" if status else \"✗\"}')

asyncio.run(main())
"
```

## Development Workflows

### 1. Starting Development Environment

Create a development startup script (`scripts/dev-start.sh`):

```bash
#!/bin/bash
set -e

echo "Starting Agentic Coding Workflow development environment..."

# Activate virtual environment
source venv/bin/activate

# Start infrastructure services
docker-compose up -d postgres redis

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 5

# Run migrations
alembic upgrade head

# Run health checks
python -c "
import asyncio
from src.services.health import check_all_services
asyncio.run(check_all_services())
"

echo "✓ Development environment ready!"
echo ""
echo "Available commands:"
echo "  python -m workers.monitor     # Start PR monitor worker"
echo "  python -m workers.analyzer    # Start check analyzer worker"
echo "  python -m workers.fixer       # Start fix applicator worker"
echo "  python -m workers.reviewer    # Start review orchestrator worker"
echo "  python -m api.server          # Start API server (if available)"
echo ""
echo "Testing:"
echo "  pytest tests/ -v              # Run all tests"
echo "  pytest tests/unit/ -v         # Run unit tests"
echo "  pytest tests/integration/ -v  # Run integration tests"
```

Make it executable and use it:

```bash
chmod +x scripts/dev-start.sh
./scripts/dev-start.sh
```

### 2. Worker Development

#### Running Individual Workers

```bash
# Terminal 1: Monitor worker
python -m workers.monitor

# Terminal 2: Analyzer worker  
python -m workers.analyzer

# Terminal 3: Fixer worker
python -m workers.fixer

# Terminal 4: Reviewer worker
python -m workers.reviewer
```

#### Worker Configuration

Edit `config/development.yaml` for local development:

```yaml
system:
  polling_interval: 60  # Faster polling for development
  max_workers: 2        # Fewer workers for local testing
  log_level: "DEBUG"

repositories:
  - url: "https://github.com/your-username/test-repo"
    auth_token: "${GITHUB_TOKEN}"
    skip_patterns:
      pr_labels: ["skip-ci", "wip"]
    failure_threshold: 1  # Process failures immediately

llm_providers:
  default: "anthropic"
  providers:
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-haiku"  # Faster/cheaper model for development
      temperature: 0.1

database:
  url: "${DATABASE_URL}"
  echo: true  # Log SQL queries in development
```

### 3. Testing Workflow

#### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test types
pytest tests/unit/ -v                    # Unit tests
pytest tests/integration/ -v             # Integration tests
pytest tests/workers/ -v                 # Worker-specific tests

# Run tests with coverage
pytest tests/ --cov=src --cov-report=html --cov-report=term

# Run specific test file
pytest tests/unit/test_github_client.py -v

# Run specific test function
pytest tests/unit/test_github_client.py::test_get_pull_request -v

# Run tests matching pattern
pytest -k "test_analyze" -v
```

#### Test Database Management

```bash
# Reset test database
docker-compose exec postgres dropdb -U agentic_user agentic_workflow_test --if-exists
docker-compose exec postgres createdb -U agentic_user agentic_workflow_test

# Run migrations on test database
DATABASE_URL=postgresql://agentic_user:agentic_password@localhost:5432/agentic_workflow_test alembic upgrade head
```

### 4. Code Quality Workflow

```bash
# Format code
ruff format .

# Fix linting issues
ruff check . --fix

# Type checking
mypy src/

# Security scanning
bandit -r src/

# Check dependencies for vulnerabilities
safety check

# Run all pre-commit hooks
pre-commit run --all-files

# Commit with pre-commit validation
git add .
git commit -m "feat: add new feature"  # Pre-commit hooks run automatically
```

## IDE Configuration

### VS Code Setup

#### Recommended Extensions

Create `.vscode/extensions.json`:
```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.pylance",
    "charliermarsh.ruff",
    "ms-python.mypy-type-checker",
    "ms-vscode.vscode-json",
    "redhat.vscode-yaml",
    "ms-vscode.vscode-postgres",
    "bradlc.vscode-tailwindcss"
  ]
}
```

#### VS Code Settings

Create `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "python.terminal.activateEnvironment": true,
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests/"],
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "ruff",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true,
    "source.fixAll.ruff": true
  },
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    ".pytest_cache": true,
    ".coverage": true,
    "htmlcov": true
  }
}
```

#### Launch Configuration

Create `.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Monitor Worker",
      "type": "python",
      "request": "launch",
      "module": "workers.monitor",
      "console": "integratedTerminal",
      "cwd": "${workspaceFolder}",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "Analyzer Worker", 
      "type": "python",
      "request": "launch",
      "module": "workers.analyzer",
      "console": "integratedTerminal",
      "cwd": "${workspaceFolder}",
      "envFile": "${workspaceFolder}/.env"
    },
    {
      "name": "Run Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["tests/", "-v"],
      "console": "integratedTerminal",
      "cwd": "${workspaceFolder}",
      "envFile": "${workspaceFolder}/.env"
    }
  ]
}
```

### PyCharm Setup

#### Project Configuration

1. **Interpreter**: Set to `./venv/bin/python`
2. **Project Structure**: Mark `src/` as Sources Root
3. **Code Style**: Import settings from `.editorconfig`
4. **External Tools**: Configure ruff, mypy, bandit

#### External Tools Configuration

```xml
<!-- File > Settings > Tools > External Tools -->
<tool name="Ruff Format" 
      program="$ProjectFileDir$/venv/bin/ruff"
      arguments="format $FileDir$"
      workingDir="$ProjectFileDir$" />

<tool name="Ruff Check"
      program="$ProjectFileDir$/venv/bin/ruff" 
      arguments="check $FileDir$ --fix"
      workingDir="$ProjectFileDir$" />

<tool name="MyPy"
      program="$ProjectFileDir$/venv/bin/mypy"
      arguments="$FileDir$"
      workingDir="$ProjectFileDir$" />
```

## Debugging Setup

### 1. Python Debugging

#### Debug Configuration

```python
# src/debug_config.py
import logging
import structlog

def setup_debug_logging():
    """Configure debug logging for development."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Configure structlog for development
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# Use in your development code
if __name__ == "__main__":
    setup_debug_logging()
    # Your worker or application code
```

#### Interactive Debugging

```python
# Add breakpoints in your code
import pdb; pdb.set_trace()  # Standard debugger

# Or use ipdb for enhanced debugging
import ipdb; ipdb.set_trace()  # Enhanced debugger

# Or use built-in breakpoint() (Python 3.7+)
breakpoint()  # Uses pdb by default, configurable via PYTHONBREAKPOINT
```

### 2. Database Debugging

#### pgAdmin Setup (Optional)

```bash
# Start pgAdmin (if you want a GUI)
docker run -d \
  --name pgadmin \
  -p 8080:80 \
  -e PGADMIN_DEFAULT_EMAIL=admin@example.com \
  -e PGADMIN_DEFAULT_PASSWORD=admin \
  dpage/pgadmin4

# Access at http://localhost:8080
# Server: postgres container IP or localhost
# Database: agentic_workflow
# Username: agentic_user
# Password: agentic_password
```

#### SQL Query Debugging

```python
# Enable SQL query logging in development
from sqlalchemy import create_engine

engine = create_engine(
    DATABASE_URL,
    echo=True,  # Log all SQL queries
    echo_pool=True  # Log connection pool events
)
```

### 3. Redis Debugging

```bash
# Connect to Redis CLI
docker-compose exec redis redis-cli

# Monitor all Redis commands
MONITOR

# Check queue contents
LLEN queue_name
LRANGE queue_name 0 -1

# Check key patterns
KEYS *
```

## Common Development Tasks

### 1. Adding a New Worker

```bash
# Create worker file
mkdir -p src/workers
touch src/workers/my_new_worker.py

# Implement worker following the pattern
cat > src/workers/my_new_worker.py << 'EOF'
"""My new worker implementation."""

import asyncio
from typing import Any, Dict

from src.workers.base import BaseWorker, WorkerMessage


class MyNewWorker(BaseWorker):
    """Worker that does something specific."""
    
    async def process_message(self, message: WorkerMessage) -> None:
        """Process a single message."""
        # Implementation here
        pass


async def main() -> None:
    """Main entry point for the worker."""
    worker = MyNewWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
EOF

# Add tests
mkdir -p tests/workers
touch tests/workers/test_my_new_worker.py

# Run the worker
python -m workers.my_new_worker
```

### 2. Database Migrations

```bash
# Create a new migration
alembic revision -m "Add new table for feature X"

# Edit the generated migration file
# migrations/versions/xxx_add_new_table_for_feature_x.py

# Apply the migration
alembic upgrade head

# Downgrade if needed
alembic downgrade -1

# Check migration status
alembic current
alembic history
```

### 3. Adding New Dependencies

```bash
# Add to requirements.txt or pyproject.toml
pip install new-package

# Update requirements file
pip freeze > requirements.txt

# Or use pip-tools for better dependency management
pip install pip-tools
pip-compile requirements.in  # Generate requirements.txt from requirements.in
```

### 4. Environment Switching

```bash
# Development environment
export ENVIRONMENT=development
python -m workers.monitor

# Testing environment
export ENVIRONMENT=testing
DATABASE_URL=$DATABASE_URL_TEST pytest tests/

# Staging environment (if available)
export ENVIRONMENT=staging
# Use staging configuration
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Issues

```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check PostgreSQL logs
docker-compose logs postgres

# Test connection manually
psql postgresql://agentic_user:agentic_password@localhost:5432/agentic_workflow

# Reset database if corrupted
docker-compose down
docker volume rm agentic-coding-workflow_postgres_data
docker-compose up -d postgres
# Wait, then run migrations
alembic upgrade head
```

#### 2. Redis Connection Issues

```bash
# Check if Redis is running
docker-compose ps redis

# Test Redis connection
redis-cli -h localhost -p 6379 ping

# Check Redis logs
docker-compose logs redis

# Clear Redis data if needed
redis-cli FLUSHALL
```

#### 3. Import Errors

```bash
# Make sure you're in the virtual environment
which python  # Should point to venv/bin/python

# Install project in development mode
pip install -e .

# Check PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

#### 4. API Key Issues

```bash
# Verify environment variables are loaded
python -c "import os; print('GITHUB_TOKEN' in os.environ)"
python -c "import os; print('ANTHROPIC_API_KEY' in os.environ)"

# Test API keys
python -c "
import os
from src.services.github import GitHubClient
import asyncio

async def test():
    client = GitHubClient(token=os.getenv('GITHUB_TOKEN'))
    user = await client.get_user()
    print(f'GitHub user: {user[\"login\"]}')

asyncio.run(test())
"
```

#### 5. Port Conflicts

```bash
# Check what's using ports
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis
lsof -i :8000  # API server

# Use different ports in docker-compose.yml if needed
# Edit docker-compose.yml and change port mappings
```

### Getting Help

#### Log Analysis

```bash
# Check application logs
tail -f logs/application.log

# Check worker-specific logs
tail -f logs/monitor.log
tail -f logs/analyzer.log

# Filter logs by level
grep "ERROR" logs/application.log
grep "WARNING" logs/application.log
```

#### Performance Debugging

```bash
# Run with profiling
python -m cProfile -o profile.stats -m workers.monitor

# Analyze profile
python -c "
import pstats
stats = pstats.Stats('profile.stats')
stats.sort_stats('cumulative').print_stats(20)
"

# Memory usage monitoring
pip install memory-profiler
python -m memory_profiler workers/monitor.py
```

#### Debug Mode

```bash
# Run with extra debugging
export LOG_LEVEL=DEBUG
export SQLALCHEMY_ECHO=1
python -m workers.monitor
```

---

This local development setup provides everything you need to effectively develop, test, and debug the Agentic Coding Workflow system. For additional help, see the [troubleshooting guide](debugging.md) or consult the team documentation.