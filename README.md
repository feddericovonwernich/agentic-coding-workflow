# Agentic Coding Workflow

An automated system for monitoring, analyzing, and fixing failed GitHub pull request checks using LLM-powered analysis and the Claude Code SDK.

## 🚀 Quick Start

**Ready to get started?** Choose your path:

### 👥 **For Users** (DevOps, Teams, Admins)
- **🏃‍♂️ [Quick Start Guide](docs/getting-started/README.md)** - Get running in 15 minutes
- **📖 [User Guide](docs/user-guide/README.md)** - Configuration, monitoring, and troubleshooting
- **🔧 [Installation Guide](docs/getting-started/installation.md)** - Production deployment setup

### 👨‍💻 **For Developers** (Contributors)
- **🛠️ [Development Guidelines](DEVELOPMENT_GUIDELINES.md)** - Comprehensive development setup and standards
- **🧪 [Testing Guidelines](TESTING_GUIDELINES.md)** - Testing patterns and best practices
- **📝 [Contributing Guide](CONTRIBUTING.md)** - How to contribute to the project

---

## System Overview

This system orchestrates multiple workers to handle PR monitoring, failure analysis, automated fixing, and multi-agent code reviews. It provides intelligent automation for common CI/CD failures while escalating complex issues to human developers.

### Key Features

- **Automated PR Monitoring**: Continuously monitors GitHub repositories for PR check failures
- **Intelligent Failure Analysis**: Uses LLMs to categorize and understand check failures
- **Automated Fixes**: Applies automated fixes for common issues (linting, formatting, simple test failures)
- **Multi-Agent Reviews**: Orchestrates multiple AI agents for comprehensive code reviews
- **Smart Escalation**: Routes complex issues to human developers via Telegram/Slack

### Architecture

See [DIAGRAMS.md](DIAGRAMS.md) for detailed system architecture and workflow diagrams.

## Installation

For detailed installation instructions, see our user-focused guides:

- **[Quick Start Guide](docs/getting-started/README.md)** - Get running in 15 minutes with minimal setup
- **[Installation Guide](docs/getting-started/installation.md)** - Comprehensive installation for all environments
- **[First Deployment Guide](docs/getting-started/first-deployment.md)** - Production deployment walkthrough

### Quick Installation

```bash
# Clone and install
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your GitHub token and LLM API keys

# Setup database and start
alembic upgrade head
python -m src.workers.monitor
```

**Need help?** Check the [Troubleshooting Guide](docs/user-guide/troubleshooting.md) for common issues.

## Testing

```bash
# Run all tests
pytest

# Run only unit tests (fast, uses mocks)
pytest -m unit

# Run integration tests (uses testcontainers for real databases)
pytest -m integration

# Run with coverage
pytest --cov=src --cov-report=html
```

**Complete Testing Standards:** [TESTING_GUIDELINES.md](TESTING_GUIDELINES.md) - Authoritative testing guidelines and comprehensive patterns.

**Testing Navigation:** [Developer Testing Guide](docs/developer/testing-guide.md) - Overview of testing tools, structure, and specialized guides.

## Development

**For Contributors:** This section is for developers contributing to the project.

### Quick Development Setup

```bash
# Start development services
docker-compose up postgres

# Install development dependencies
pip install -r requirements-dev.txt

# Run database migrations
alembic upgrade head

# Code quality checks
ruff format .
ruff check . --fix
mypy src/
```

**Complete Developer Guide:** [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md) - Comprehensive development setup, coding standards, and best practices.

## Configuration

### For Users

**Complete User Configuration Guide:** [Configuration Guide](docs/user-guide/configuration.md) - Repository setup, notifications, team configuration, and performance tuning.

**Quick Start:** Copy `.env.example` to `.env` and configure your GitHub token and LLM API keys.

### For Developers

**Technical Configuration:** See [docs/config/README.md](docs/config/README.md) for programmatic configuration management and development setup.

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

### 👥 **For Users** (DevOps, Teams, System Administrators)

**Getting Started**
- **[Quick Start Guide](docs/getting-started/README.md)** - Get running in 15 minutes
- **[Installation Guide](docs/getting-started/installation.md)** - Comprehensive setup instructions
- **[First Deployment](docs/getting-started/first-deployment.md)** - Production deployment walkthrough

**Operations & Management**
- **[User Guide](docs/user-guide/README.md)** - Complete user navigation and workflows
- **[Configuration Guide](docs/user-guide/configuration.md)** - Repository setup, notifications, and tuning
- **[Monitoring Guide](docs/user-guide/monitoring.md)** - Dashboards, alerts, and observability
- **[Troubleshooting Guide](docs/user-guide/troubleshooting.md)** - Common issues and solutions

### 👨‍💻 **For Developers** (Contributors)

**Development Guides**
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute to the project
- **[Development Guidelines](DEVELOPMENT_GUIDELINES.md)** - Comprehensive development setup and coding standards
- **[Testing Guidelines](TESTING_GUIDELINES.md)** - Authoritative testing standards and comprehensive patterns
- **[Testing Guide](docs/developer/testing-guide.md)** - Testing tools, structure, and specialized guides
- **[Documentation Guidelines](DOCUMENTATION_GUIDELINES.md)** - Documentation standards for maintainers

**API Integration**
- **[API Documentation](docs/api/README.md)** - Complete API reference with examples
- **[GitHub Client API](docs/api/github-client.md)** - GitHub integration patterns and best practices
- **[Database API](docs/api/database-api.md)** - Models, repositories, and database operations
- **[Configuration API](docs/api/configuration-api.md)** - Configuration management and hot reload
- **[Worker Interfaces](docs/api/worker-interfaces.md)** - Custom worker implementation guide
- **[Webhook API](docs/api/webhooks.md)** - GitHub webhooks and event processing

**Technical Reference**
- **[System Architecture](DIAGRAMS.md)** - Detailed system diagrams and workflows
- **[API Documentation](docs/api/README.md)** - Comprehensive API reference and integration guides
- **[Configuration API](docs/config/README.md)** - Programmatic configuration management
- **[Testing Reference](docs/testing/README.md)** - Detailed testing guides and specialized techniques
- **[Security Policy](SECURITY.md)** - Security policies and vulnerability reporting
- **[Changelog](CHANGELOG.md)** - Version history and release notes

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