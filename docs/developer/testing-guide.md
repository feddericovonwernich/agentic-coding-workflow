# Comprehensive Testing Guide

Welcome to the complete testing guide for the Agentic Coding Workflow project. This guide serves as your single entry point for understanding our testing philosophy, practices, and tools.

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

**New to testing?** Start with our [Testing Best Practices Guide](../testing/best-practices.md).

## Testing Philosophy

Our testing approach is built on three core principles:

### 1. **Human Readability First**
Tests should be self-documenting and easy to understand. Every test includes clear documentation explaining why it exists, what it tests, and how it works.

### 2. **Strong Interface Testing**
We focus on testing public interfaces and behavior rather than internal implementation details. This makes tests more maintainable and less brittle.

### 3. **Comprehensive Coverage**
We maintain high test coverage across all critical paths, with particular attention to:
- Database operations and data integrity
- External API integrations (GitHub, LLM providers)
- Configuration management and validation
- Error handling and edge cases

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

### Mandatory Documentation

Every test must include a comment block explaining:

```python
def test_example_functionality():
    """
    Why: Explain the business reason this test exists
    
    What: Describe what specific functionality is being tested
    
    How: Outline the approach used to test the functionality
    """
    # Test implementation
```

**Example:**
```python
def test_analyzer_categorizes_lint_failures():
    """
    Why: Ensure the analyzer correctly identifies lint failures to route them
         for automatic fixing rather than human escalation
    
    What: Tests that CheckAnalyzer.analyze() returns category='lint' for
          eslint failure logs
    
    How: Provides sample eslint failure logs and verifies the returned
         analysis has the correct category and confidence score
    """
    # Test implementation
```

### Code Quality Standards

- **Type hints**: All test functions and fixtures must have type hints
- **Clear naming**: Test names should describe the expected behavior
- **Isolated tests**: Each test should be independent and idempotent
- **Proper fixtures**: Use pytest fixtures for setup and teardown

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

### 🚀 **Quick Reference**
- Use descriptive test names: `test_should_reject_invalid_url_format()`
- One assertion per test (when possible)
- Use fixtures for common setup/teardown
- Mock external dependencies in unit tests
- Use real services in integration tests

### 📚 **Comprehensive Guide**
For detailed best practices including naming conventions, fixture usage, and testing patterns, see our [Testing Best Practices Guide](../testing/best-practices.md).

### 🔧 **Database Testing**
Database testing requires special considerations for transactions, isolation, and performance. See our [Database Testing Guide](../testing/database-testing.md).

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

## Documentation Navigation

### Quick Access
- **[Testing Best Practices](../testing/best-practices.md)** - Start here for testing standards
- **[Database Testing](../testing/database-testing.md)** - Database-specific guidance
- **[Mock GitHub Server](../reference/testing/mock-github-server.md)** - GitHub API testing

### Complete Reference
- **[Testing Methodology](../testing/methodology.md)** - Our testing philosophy and approach
- **[Coverage Analysis](../testing/coverage.md)** - Understanding test coverage
- **[Quality Metrics](../testing/quality-metrics.md)** - Measuring test effectiveness
- **[Testing Troubleshooting](../testing/troubleshooting.md)** - Common issues and solutions

---

**Ready to start testing?** 
- 🚀 **New to the project**: Start with [Testing Best Practices](../testing/best-practices.md)
- 🔧 **Working with databases**: See [Database Testing Guide](../testing/database-testing.md)  
- 🐙 **Testing GitHub integration**: Check out the [Mock GitHub Server](../reference/testing/mock-github-server.md)
- 📊 **Improving coverage**: Read [Coverage Analysis Guide](../testing/coverage.md)