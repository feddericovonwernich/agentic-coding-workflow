# Developer Guide

> **📋 Document Purpose**: This is the **navigation hub** for all developer documentation. It provides comprehensive resources, journey maps, and clear paths to all development guidance.

## Welcome to Development

Welcome to the Agentic Coding Workflow project! This guide serves as your **central navigation point** for all developer resources, from onboarding to advanced development workflows.

## Quick Navigation

### Getting Started
- **[New Developer Onboarding](onboarding.md)** - Complete onboarding checklist for new contributors
- **[Local Development Setup](local-development.md)** - Environment setup and development workflows
- **[Testing Guide](testing-guide.md)** - Testing overview and entry point

### Understanding the System
- **[System Architecture](architecture.md)** - System design, components, and data flow
- **[Development Best Practices](best-practices.md)** - Consolidated coding standards and practices

### Development Workflows
- **[Code Review Guidelines](code-review.md)** - Review process and standards
- **[Debugging & Troubleshooting](debugging.md)** - Common issues and debugging techniques

### External References
- **[API Documentation](../api/README.md)** - Comprehensive API reference
- **[Testing Documentation](../testing/README.md)** - Detailed testing guides
- **[User Guide](../user-guide/README.md)** - End-user documentation

## Developer Journey Map

### 🌱 New Contributor (First Week)
**Goal**: Get oriented and make your first contribution

1. **Day 1**: Complete [onboarding checklist](onboarding.md#prerequisites-checklist)
2. **Day 2-3**: Set up [local development environment](local-development.md)
3. **Day 4-5**: Read [architecture overview](architecture.md) and understand system design
4. **Day 6-7**: Complete first small contribution following [best practices](best-practices.md)

### 🌿 Regular Contributor (Ongoing)
**Goal**: Develop features and contribute to system improvement

- **Feature Development**: Follow [development workflow](best-practices.md#development-workflow)
- **Code Reviews**: Use [review guidelines](code-review.md) for giving and receiving feedback
- **Testing**: Apply [testing standards](testing-guide.md) for all contributions
- **Debugging**: Use [troubleshooting guide](debugging.md) for issues

### 🌳 Maintainer (Advanced)
**Goal**: Guide project direction and mentor other developers

- **Architecture Decisions**: Contribute to [architectural documentation](architecture.md)
- **Process Improvement**: Update [best practices](best-practices.md) and workflows
- **Mentoring**: Help new developers through onboarding process
- **Quality Assurance**: Ensure adherence to standards and practices

## Development Environment Overview

This project uses:
- **Language**: Python with async/await patterns
- **Database**: PostgreSQL with SQLAlchemy
- **Queue System**: Redis for worker coordination
- **External APIs**: GitHub API, Anthropic Claude, OpenAI
- **Testing**: pytest with async support
- **Code Quality**: ruff, mypy, pre-commit hooks

## Common Development Tasks

### Quick Start Commands
```bash
# Setup development environment
pip install -r requirements.txt
pre-commit install

# Run tests
pytest tests/ -v

# Code quality checks
ruff format .
ruff check . --fix
mypy src/

# Start local development
docker-compose up  # All services
python -m workers.monitor  # Individual worker
```

### Daily Development Workflow
1. **Start**: Pull latest changes, run tests
2. **Develop**: Make changes following [best practices](best-practices.md)
3. **Test**: Write tests using [testing standards](testing-guide.md)
4. **Review**: Self-review using [code review checklist](code-review.md#review-checklist)
5. **Submit**: Create PR following [contribution guidelines](best-practices.md#development-workflow)

## Project-Specific Patterns

### Key Design Patterns
- **Provider Pattern**: All external integrations (LLMs, notifications)
- **Worker Pattern**: Separate workers for each workflow step
- **Repository Pattern**: Database access abstraction
- **Strategy Pattern**: Different fix strategies based on failure types

### Code Organization
```
src/
├── workers/          # Worker implementations
├── services/         # Shared services (GitHub, LLM, notifications)
├── repositories/     # Database access patterns
├── models/          # Data models and schemas
└── config/          # Configuration management
```

## Documentation Standards

All documentation follows these principles:
- **Progressive Disclosure**: Start simple, link to detailed guides
- **Task-Oriented**: Organized around what developers need to accomplish
- **Context-Aware**: Provides background and rationale, not just steps
- **Maintainable**: Easy to update as the system evolves

## Getting Help

### Internal Resources
- **Architecture Questions**: See [architecture.md](architecture.md)
- **Setup Issues**: Check [local-development.md](local-development.md)
- **Testing Problems**: Consult [testing-guide.md](testing-guide.md)
- **Code Review**: Reference [code-review.md](code-review.md)

### Development Standards
- **Code Quality**: Follow [best practices](best-practices.md)
- **Error Handling**: Use patterns from [DEVELOPMENT_GUIDELINES.md](../../DEVELOPMENT_GUIDELINES.md)
- **Testing**: Apply standards from [testing documentation](../testing/README.md)

### External Resources
- **GitHub API**: [Official GitHub API Documentation](https://docs.github.com/en/rest)
- **Anthropic Claude**: [Claude API Documentation](https://docs.anthropic.com/)
- **SQLAlchemy**: [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

---

**Note**: This documentation is actively maintained. If you find gaps or outdated information, please update the relevant sections as part of your contributions.