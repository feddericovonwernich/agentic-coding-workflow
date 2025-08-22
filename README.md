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

```bash
# Run all tests
pytest

# Run only unit tests (fast)
pytest -m unit

# Run integration tests (requires Docker)
pytest -m integration

# Run with coverage
pytest --cov=src --cov-report=html
```

For detailed testing guidelines, see [TESTING_GUIDELINES.md](TESTING_GUIDELINES.md).

## Development

```bash
# Start development database
docker-compose up postgres

# Run database migrations
alembic upgrade head

# Format and lint code
ruff format .
ruff check . --fix

# Type checking
mypy src/
```

For comprehensive development guidelines, see [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md).

## Configuration

The system uses environment variables for configuration. See `.env.example` for all available options.

Key configuration areas:
- Database connection and pooling
- GitHub API authentication
- LLM provider settings
- Notification channels

For detailed configuration documentation, see the configuration section in [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md).

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

## Documentation

### 📚 Complete Documentation
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution guidelines and development workflow
- **[DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md)** - Comprehensive development best practices and coding standards
- **[TESTING_GUIDELINES.md](TESTING_GUIDELINES.md)** - Testing guidelines and patterns for reliable code
- **[DOCUMENTATION_GUIDELINES.md](DOCUMENTATION_GUIDELINES.md)** - Documentation standards and best practices for maintainers
- **[SECURITY.md](SECURITY.md)** - Security policies and vulnerability reporting
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and release notes

### 🚀 Quick Links
- **[System Architecture](DIAGRAMS.md)** - Detailed system diagrams and workflows
- **[API Documentation](docs/api/)** - GitHub client and configuration APIs *(coming soon)*
- **[Deployment Guide](docs/deployment/)** - Production deployment instructions *(coming soon)*
- **[User Guide](docs/user-guide/)** - End-user documentation *(coming soon)*

## Contributing

We welcome contributions! Please read our [Contributing Guidelines](CONTRIBUTING.md) for details on:

- Setting up your development environment
- Code style and standards ([DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md))
- Testing requirements ([TESTING_GUIDELINES.md](TESTING_GUIDELINES.md))
- Pull request process
- Community guidelines

### Quick Start for Contributors

1. Fork the repository
2. Follow the [development setup guide](CONTRIBUTING.md#getting-started)
3. Read the [development best practices](DEVELOPMENT_GUIDELINES.md)
4. Ensure your tests follow our [testing guidelines](TESTING_GUIDELINES.md)
5. Submit a pull request

## Security

Security is important to us. Please see our [Security Policy](SECURITY.md) for information on:
- Reporting vulnerabilities
- Security best practices
- Supported versions

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with SQLAlchemy, Pydantic V2, and pytest
- Uses testcontainers for integration testing
- Powered by Claude Code SDK for automated fixes