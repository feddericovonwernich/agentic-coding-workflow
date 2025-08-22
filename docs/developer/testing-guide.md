# Developer Testing Guide

> **📚 Authoritative Reference**: For comprehensive testing standards, detailed patterns, and complete testing methodology, see **[TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md)** - the authoritative source for all testing standards (856 lines).

## Purpose

This guide serves as the **developer entry point** to our testing ecosystem. It provides practical guidance for daily testing tasks and clear navigation to detailed testing resources. For comprehensive testing methodology and authoritative standards, always refer to the main testing guidelines.

## Table of Contents

- [Quick Start](#quick-start)
- [Testing Philosophy](#testing-philosophy)
- [Test Structure Overview](#test-structure-overview)
- [Testing Requirements](#testing-requirements)
- [Test Types](#test-types)
- [Testing Tools](#testing-tools)
- [Best Practices](#best-practices)
- [Advanced Topics](#advanced-topics)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Running Tests

```bash
# Run all tests
pytest

# Run only unit tests (fast, uses mocks)
pytest -m unit

# Run integration tests (uses testcontainers for real databases)
pytest -m integration

# Run with coverage reporting
pytest --cov=src --cov-report=html
```

### Essential Testing Commands

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run linting and type checking
ruff check .
mypy src/

# Generate coverage report
pytest --cov=src --cov-report=term-missing

# Run tests in parallel (faster)
pytest -n auto
```

**New to testing?** Start with our [**TESTING_GUIDELINES.md**](../../TESTING_GUIDELINES.md) - the authoritative testing standards and comprehensive patterns (856 lines).

## Testing Philosophy

Our testing approach follows the comprehensive standards outlined in [TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md).

**Key Principles:**
- **Human Readability First**: Self-documenting tests with clear Why/What/How documentation
- **Strong Interface Testing**: Focus on public interfaces and behavior, not implementation details  
- **Comprehensive Coverage**: High coverage across critical paths including database, APIs, and error handling

**For complete testing philosophy and detailed guidelines, see [TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md).**

## Test Structure Overview

```
tests/
├── conftest.py              # Pytest configuration and shared fixtures
├── unit/                    # Unit tests (fast, isolated, use mocks)
│   ├── database/           # Database configuration and connection tests
│   ├── github/             # GitHub client unit tests
│   └── models/             # SQLAlchemy model tests
├── integration/            # Integration tests (real services via testcontainers)
│   ├── test_database_*.py  # Database integration tests
│   ├── test_github_*.py    # GitHub API integration tests
│   └── test_migration_*.py # Database migration tests
└── __init__.py
```

### Current Test Coverage
- **170+ test methods** across 32 test classes
- **5,000+ lines** of test code
- **90%+ coverage** on critical database and API layers

## Testing Requirements

**All testing requirements and standards are defined in [TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md).**

**Key Requirements Summary:**
- **Mandatory Why/What/How documentation** for every test
- **Clear, descriptive test naming** conventions
- **Type hints and code quality** standards
- **Test isolation and independence** requirements

**Complete documentation requirements and examples: [TESTING_GUIDELINES.md - Documentation Requirements](../../TESTING_GUIDELINES.md#documentation-requirements)**

## Test Types

### Unit Tests (`pytest -m unit`)

**Purpose**: Test individual components in isolation
**Speed**: Very fast (< 1 second per test)
**Dependencies**: Uses mocks for external services

```python
# Example unit test
@pytest.mark.unit
def test_database_config_validation():
    """
    Why: Ensure configuration validation catches invalid database URLs
    What: Tests DatabaseConfig.validate() rejects malformed URLs
    How: Provides invalid URLs and checks ValidationError is raised
    """
    with pytest.raises(ValidationError):
        DatabaseConfig(url="invalid://url")
```

**Best for**: Configuration validation, data models, utility functions

### Integration Tests (`pytest -m integration`)

**Purpose**: Test components working together with real services
**Speed**: Slower (5-30 seconds per test)
**Dependencies**: Uses testcontainers for real PostgreSQL/Redis

```python
# Example integration test
@pytest.mark.integration
async def test_database_connection_lifecycle():
    """
    Why: Verify database connections work correctly in production-like environment
    What: Tests full connection lifecycle with real PostgreSQL
    How: Creates real database, connects, performs operations, cleans up
    """
    # Test with real database via testcontainers
```

**Best for**: Database operations, API integrations, end-to-end workflows

## Testing Tools

### Core Testing Stack

- **[pytest](https://pytest.org/)** - Primary testing framework
- **[testcontainers](https://testcontainers-python.readthedocs.io/)** - Real service integration
- **[pytest-asyncio](https://pytest-asyncio.readthedocs.io/)** - Async test support
- **[pytest-cov](https://pytest-cov.readthedocs.io/)** - Coverage reporting
- **[factory-boy](https://factoryboy.readthedocs.io/)** - Test data generation

### Specialized Tools

- **[Mock GitHub Server](../reference/testing/mock-github-server.md)** - GitHub API testing without tokens
- **[Database Testing Utilities](../testing/database-testing.md)** - Database-specific testing patterns
- **[Async Testing Patterns](../testing/methodology.md)** - Async/await testing best practices

### Coverage and Quality

- **[Coverage Analysis](../testing/coverage.md)** - Understanding and improving test coverage
- **[Quality Metrics](../testing/quality-metrics.md)** - Measuring test effectiveness
- **[Performance Testing](../testing/methodology.md#performance-testing)** - Load and performance validation

## Best Practices

### 📚 **Authoritative Testing Standards**
**Complete best practices and standards: [TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md)**

### 🚀 **Quick Reference**
- Use descriptive test names: `test_should_reject_invalid_url_format()`
- Mandatory Why/What/How documentation for every test
- Mock external dependencies in unit tests, use real services for integration
- Follow test organization and naming conventions from TESTING_GUIDELINES.md

### 🔧 **Specialized Testing Guides**
- **[Database Testing](../testing/database-testing.md)** - Database-specific patterns and considerations
- **[Testing Best Practices](../testing/best-practices.md)** - Additional patterns complementing TESTING_GUIDELINES.md

## Advanced Topics

### Mock GitHub Server
Test GitHub integrations without requiring real tokens or hitting rate limits:
- **[Mock GitHub Server Setup](../reference/testing/mock-github-server.md)** - Complete setup and usage guide
- **[GitHub Client Testing Patterns](../testing/best-practices.md#github-testing)** - Best practices for GitHub API tests

### Performance Testing
- **[Load Testing](../testing/methodology.md#load-testing)** - Testing system performance under load
- **[Database Performance](../testing/database-testing.md#performance)** - Database-specific performance testing

### Test Data Management
- **[Factory Patterns](../testing/best-practices.md#test-data)** - Generating realistic test data
- **[Fixture Design](../testing/methodology.md#fixtures)** - Designing reusable test fixtures

## Troubleshooting

### Common Issues

**Tests fail with database connection errors**
→ See [Database Testing Troubleshooting](../testing/database-testing.md#troubleshooting)

**Integration tests are slow**
→ See [Performance Optimization](../testing/troubleshooting.md#performance)

**Mock server setup issues**
→ See [Mock GitHub Server Troubleshooting](../reference/testing/mock-github-server.md#troubleshooting)

**Coverage reports missing files**
→ See [Coverage Troubleshooting](../testing/coverage.md#troubleshooting)

### Getting Help

1. **[Testing Troubleshooting Guide](../testing/troubleshooting.md)** - Comprehensive problem resolution
2. **[Testing Best Practices](../testing/best-practices.md)** - Avoid common pitfalls
3. **[GitHub Issues](https://github.com/feddericovonwernich/agentic-coding-workflow/issues)** - Report testing-related bugs

## Testing Documentation Navigation

### 📚 **Authoritative Standards**
- **[TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md)** - Complete testing methodology and standards (856 lines)

### 🚀 **Quick Access for Daily Testing**
- **[Testing Best Practices](../testing/best-practices.md)** - Practical testing patterns
- **[Database Testing](../testing/database-testing.md)** - Database-specific guidance
- **[Mock GitHub Server](../reference/testing/mock-github-server.md)** - GitHub API testing

### 📖 **Detailed Reference Documentation**
- **[Testing Methodology](../testing/methodology.md)** - Our testing philosophy and approach
- **[Coverage Analysis](../testing/coverage.md)** - Understanding test coverage
- **[Quality Metrics](../testing/quality-metrics.md)** - Measuring test effectiveness
- **[Testing Troubleshooting](../testing/troubleshooting.md)** - Common issues and solutions

### 🎯 **Testing Journey Map**

**New to the project?**
1. **Start**: Read [TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md) for comprehensive understanding
2. **Practice**: Follow this guide for daily testing tasks
3. **Specialize**: Use detailed reference docs for specific scenarios

**Daily Development Testing:**
- Use this guide for quick reference and common tasks
- Refer to [Testing Best Practices](../testing/best-practices.md) for patterns
- Consult [TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md) for standards

---

**Ready to start testing?** 
- 📚 **Understanding our approach**: Read [TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md)
- 🚀 **Daily testing tasks**: Use this guide and [Testing Best Practices](../testing/best-practices.md)
- 🔧 **Database testing**: See [Database Testing Guide](../testing/database-testing.md)  
- 🐙 **GitHub integration**: Check out the [Mock GitHub Server](../reference/testing/mock-github-server.md)
- 📊 **Coverage analysis**: Read [Coverage Analysis Guide](../testing/coverage.md)