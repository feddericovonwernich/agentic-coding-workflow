# Agentic Coding Workflow

An automated system for monitoring, analyzing, and fixing failed GitHub pull request checks using LLM-powered analysis and the Claude Code SDK.

## 🚀 Quick Start

**Ready to get started?** Choose your path:

### 👥 **For Users** (DevOps, Teams, Admins)
- **🏃‍♂️ [Quick Start Guide](docs/getting-started/README.md)** - Get running in 15 minutes
- **📖 [User Guide](docs/user-guide/README.md)** - Configuration, monitoring, and troubleshooting
- **🔧 [Installation Guide](docs/getting-started/installation.md)** - Production deployment setup

### 👨‍💻 **For Developers** (Contributors)
- **📖 [Developer Guide](docs/developer/README.md)** - Complete development documentation hub
- **🚀 [Onboarding Guide](docs/developer/onboarding.md)** - New developer 30-day onboarding plan
- **🛠️ [Development Guidelines](DEVELOPMENT_GUIDELINES.md)** - Comprehensive coding standards reference
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

**Need help?** Visit the [**Troubleshooting Hub**](docs/troubleshooting-hub.md) to find the right troubleshooting guide for your specific issue, or jump directly to [Operational Troubleshooting](docs/user-guide/troubleshooting.md) for common running issues.

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

**Complete Developer Documentation:** [Developer Guide Hub](docs/developer/README.md) - Comprehensive development documentation including onboarding, architecture, best practices, and workflows.

**Reference:** [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md) - Detailed coding standards and technical patterns.

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
│   ├── cache/              # Cache infrastructure
│   │   ├── cache_manager.py # Cache management and strategies
│   │   ├── memory_cache.py # In-memory cache implementation
│   │   └── redis_cache.py  # Redis cache implementation
│   ├── config/             # Configuration management
│   │   ├── loader.py       # Configuration loading and validation
│   │   ├── manager.py      # Configuration management
│   │   └── models.py       # Configuration data models
│   ├── database/           # Database infrastructure
│   │   ├── config.py       # Database configuration
│   │   ├── connection.py   # Connection and session management
│   │   ├── health.py       # Database health monitoring
│   │   └── transactions.py # Transaction management
│   ├── github/             # GitHub API integration
│   │   ├── client.py       # GitHub API client
│   │   ├── auth.py         # Authentication handling
│   │   ├── pagination.py   # Pagination support
│   │   └── rate_limiting.py# Rate limiting implementation
│   ├── models/             # SQLAlchemy data models
│   │   ├── base.py         # Base model classes
│   │   ├── pull_request.py # Pull request models
│   │   ├── check_run.py    # Check run models
│   │   ├── repository.py   # Repository models
│   │   └── enums.py        # Enumeration types
│   ├── repositories/       # Repository pattern implementation
│   │   ├── base.py         # Base repository class
│   │   ├── pull_request.py # PR repository operations
│   │   └── check_run.py    # Check run repository operations
│   ├── workers/            # Worker implementations
│   │   └── monitor/        # PR Monitor Worker (Issue #48)
│   │       ├── models.py   # Data models and interfaces
│   │       ├── discovery.py# PR and check run discovery engines
│   │       ├── change_detection.py # State change detection
│   │       ├── synchronization.py  # Database synchronization
│   │       └── processor.py# Main orchestration processor
│   └── performance/        # Performance optimization
│       ├── monitoring.py   # Performance monitoring
│       └── optimizations.py# Query and connection optimizations
├── tests/
│   ├── unit/              # Unit tests with mocks
│   │   ├── workers/       # Worker unit tests
│   │   │   └── monitor/   # Monitor worker tests
│   │   ├── config/        # Configuration tests
│   │   ├── database/      # Database tests
│   │   └── github/        # GitHub integration tests
│   ├── integration/       # Integration tests
│   │   ├── github/        # GitHub API integration tests
│   │   └── test_database_real_integration.py
│   └── conftest.py        # Test fixtures and configuration
├── alembic/               # Database migrations
├── docs/                  # Comprehensive documentation
│   ├── api/               # API documentation
│   ├── developer/         # Developer guides
│   ├── user-guide/        # User documentation
│   └── getting-started/   # Installation and setup guides
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

**Troubleshooting & Support**
- **[🛠️ Troubleshooting Hub](docs/troubleshooting-hub.md)** - **Navigation center** - find the right guide for your issue type
- **[Operational Issues](docs/user-guide/troubleshooting.md)** - PR processing, notifications, performance problems  
- **[Installation Issues](docs/getting-started/installation.md#troubleshooting)** - Environment setup and service startup problems
- **[Configuration Issues](docs/config/troubleshooting.md)** - Technical configuration validation and debugging

### 👨‍💻 **For Developers** (Contributors)

**Development Guides**
- **[Developer Guide Hub](docs/developer/README.md)** - Complete development documentation navigation
- **[New Developer Onboarding](docs/developer/onboarding.md)** - Structured 30-day onboarding with milestones
- **[System Architecture](docs/developer/architecture.md)** - System design, components, and design decisions
- **[Development Best Practices](docs/developer/best-practices.md)** - Consolidated coding standards and practices
- **[Local Development Setup](docs/developer/local-development.md)** - Environment setup and development workflows
- **[Testing Guide](docs/developer/testing-guide.md)** - Testing overview and entry point
- **[Debugging Guide](docs/developer/debugging.md)** - Debugging techniques and troubleshooting
- **[Code Review Guidelines](docs/developer/code-review.md)** - Review process and standards

**Development Troubleshooting**
- **[🛠️ Troubleshooting Hub](docs/troubleshooting-hub.md)** - **Navigation center** - find the right guide for your issue type
- **[Development Debugging](docs/developer/debugging.md)** - IDE setup, debugging tools, local development issues
- **[Testing Issues](docs/testing/troubleshooting.md)** - Test execution, database testing, CI/CD problems

**Reference Documentation**
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute to the project
- **[Development Guidelines](DEVELOPMENT_GUIDELINES.md)** - Comprehensive coding standards reference
- **[Testing Guidelines](TESTING_GUIDELINES.md)** - Authoritative testing standards and comprehensive patterns
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

## 🧭 Navigation by Scenario

**Need help finding the right documentation?** Use these common scenarios to navigate directly to what you need:

### 📥 **"I want to install and run this system"**
1. **[Quick Start Guide](docs/getting-started/README.md)** → Get running in 15 minutes
2. **[Installation Guide](docs/getting-started/installation.md)** → Comprehensive setup
3. **[Configuration Guide](docs/user-guide/configuration.md)** → Repository and notification setup
4. **[Troubleshooting Hub](docs/troubleshooting-hub.md)** → If you encounter issues

### 🔧 **"I want to configure this for my team"**
1. **[Configuration Guide](docs/user-guide/configuration.md)** → User scenarios and templates
2. **[Configuration API](docs/config/README.md)** → Technical configuration management  
3. **[Configuration Troubleshooting](docs/config/troubleshooting.md)** → If configuration isn't working

### 🚨 **"Something isn't working"**
1. **[🛠️ Troubleshooting Hub](docs/troubleshooting-hub.md)** → **Start here** - finds the right guide for your issue
2. **[Installation Issues](docs/getting-started/installation.md#troubleshooting)** → System won't start/run
3. **[Operational Issues](docs/user-guide/troubleshooting.md)** → PRs not processing, notifications broken
4. **[Development Issues](docs/developer/debugging.md)** → Local development problems

### 💻 **"I want to contribute to this project"**
1. **[Developer Guide Hub](docs/developer/README.md)** → Complete development navigation
2. **[New Developer Onboarding](docs/developer/onboarding.md)** → Structured 30-day onboarding
3. **[Contributing Guidelines](CONTRIBUTING.md)** → How to contribute
4. **[Development Guidelines](DEVELOPMENT_GUIDELINES.md)** → Coding standards reference

### 🧪 **"I need to understand testing"**
1. **[Testing Guide](docs/developer/testing-guide.md)** → Testing overview and entry point
2. **[Testing Guidelines](TESTING_GUIDELINES.md)** → Authoritative testing standards
3. **[Testing Troubleshooting](docs/testing/troubleshooting.md)** → If tests are failing

### 🔗 **"I want to integrate with APIs"**
1. **[API Documentation](docs/api/README.md)** → Complete API reference
2. **[GitHub Client API](docs/api/github-client.md)** → GitHub integration patterns
3. **[Configuration API](docs/api/configuration-api.md)** → Programmatic configuration
4. **[Worker Interfaces](docs/api/worker-interfaces.md)** → Custom worker implementation

### 🏗️ **"I want to understand the architecture"**
1. **[System Architecture](docs/developer/architecture.md)** → System design and components
2. **[System Diagrams](DIAGRAMS.md)** → Detailed architecture diagrams
3. **[Developer Guide](docs/developer/README.md)** → Development patterns and workflows

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