# Agentic Coding Workflow

An automated system for monitoring, analyzing, and fixing failed GitHub pull request checks using LLM-powered analysis and the Claude Code SDK.

## Overview

This system orchestrates multiple workers to handle PR monitoring, failure analysis, automated fixing, and multi-agent code reviews. It provides intelligent automation for common CI/CD failures while escalating complex issues to human developers.

## Features

- **Automated PR Monitoring**: Continuously monitors GitHub repositories for PR check failures
- **Intelligent Failure Analysis**: Uses LLMs to categorize and understand check failures
- **Automated Fixes**: Applies automated fixes for common issues (linting, formatting, simple test failures)
- **Multi-Agent Reviews**: Orchestrates multiple AI agents for comprehensive code reviews
- **Smart Escalation**: Routes complex issues to human developers via Telegram/Slack

## Architecture

See [DIAGRAMS.md](DIAGRAMS.md) for detailed system architecture and workflow diagrams.

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL 12+
- Docker (for running tests with testcontainers)
- Redis (optional, for queue management)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Start the database:
```bash
docker-compose up -d postgres
```

5. Run database migrations:
```bash
alembic upgrade head
```

## Testing

### Test Categories

The project has two levels of testing:

1. **Unit Tests** - Fast, isolated tests with mocked dependencies
2. **Integration Tests** - Tests against actual PostgreSQL database using testcontainers

### Running Tests

```bash
# Run all tests
pytest

# Run only unit tests (fast)
pytest -m unit

# Run integration tests (requires Docker)
pytest -m integration
# Or
pytest -m real_database

# Run with coverage
pytest --cov=src --cov-report=html
```

### Real Integration Tests

The real integration tests use testcontainers to spin up a PostgreSQL database in Docker:

```bash
# Ensure Docker is running
docker info

# Run real database tests
pytest tests/integration/test_database_real_integration.py -v

# Or run all real database tests
pytest -m real_database
```

These tests validate:
- Actual database connectivity
- Transaction management
- Connection pooling
- Health monitoring
- Concurrent operations
- Stress testing with many queries

## Development

### Local Database

Start a local PostgreSQL instance for development:

```bash
# Start development database
docker-compose up postgres

# Start test database (on port 5433)
docker-compose up test-postgres

# Stop all services
docker-compose down
```

### Database Management

```bash
# Create a new migration
alembic revision -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

### Code Quality

```bash
# Format code
black src/ tests/
isort src/ tests/

# Type checking
mypy src/

# Linting
flake8 src/ tests/
```

## Configuration

The system uses a hierarchical configuration approach:

1. Environment variables (highest priority)
2. `.env` file
3. Default values in code

See `.env.example` for all available configuration options.

### Database Configuration

- `DATABASE_URL`: Complete database connection URL (alternative: `DATABASE_DATABASE_URL`)
- `DATABASE_HOST`: Database host (default: localhost)
- `DATABASE_PORT`: Database port (default: 5432)
- `DATABASE_DATABASE`: Database name (default: agentic_workflow)
- `DATABASE_USERNAME`: Database user (default: postgres)
- `DATABASE_PASSWORD`: Database password (required)

### Connection Pool Settings

- `DATABASE_POOL_SIZE`: Base pool size (default: 20)
- `DATABASE_POOL_MAX_OVERFLOW`: Additional connections when pool exhausted (default: 30)
- `DATABASE_POOL_TIMEOUT`: Timeout to get connection from pool (default: 30s)
- `DATABASE_POOL_RECYCLE`: Connection recycle time (default: 3600s)
- `DATABASE_POOL_PRE_PING`: Enable connection health checks (default: true)

## Project Structure

```
agentic-coding-workflow/
├── src/
│   ├── database/           # Database infrastructure
│   │   ├── config.py       # Configuration management
│   │   ├── connection.py   # Connection and session management
│   │   └── health.py       # Health monitoring
│   ├── models/             # SQLAlchemy models (future)
│   ├── workers/            # Worker implementations (future)
│   └── services/           # Shared services (future)
├── tests/
│   ├── unit/              # Unit tests with mocks
│   ├── integration/       # Integration tests
│   └── conftest.py        # Test fixtures
├── alembic/               # Database migrations
├── docs/                  # Documentation
└── docker-compose.yml     # Local development services
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Recent Updates

### Pydantic V2 Migration
The database infrastructure has been upgraded to Pydantic V2 for improved performance and features:
- Updated configuration validation and environment variable handling
- Enhanced type safety and error reporting  
- Improved async compatibility

**Breaking Change**: Environment variable `DATABASE_NAME` is now `DATABASE_DATABASE` to align with Pydantic V2 field naming conventions.

## Acknowledgments

- Built with SQLAlchemy, Pydantic V2, and pytest
- Uses testcontainers for integration testing
- Powered by Claude Code SDK for automated fixes