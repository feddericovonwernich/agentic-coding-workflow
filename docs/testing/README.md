# Testing Reference Documentation

This directory contains detailed testing reference guides for the Agentic Coding Workflow project.

> **📚 Navigation**: This is the **testing reference hub**. For testing overview and daily workflows, see [Testing Guide](../developer/testing-guide.md). For authoritative testing standards, see [Testing Guidelines](../../TESTING_GUIDELINES.md). For testing issues, see [Testing Troubleshooting](troubleshooting.md).

## Quick Start

1. **Run all tests**: `pytest tests/ -v`
2. **Unit tests only**: `pytest tests/unit/ -v`  
3. **Integration tests**: `pytest tests/integration/ -v`
4. **With coverage**: `pytest tests/ --cov=src --cov-report=html`

## Reference Documentation Contents

- **[Testing Best Practices](./best-practices.md)** - Comprehensive guide to testing standards and requirements
- **[Database Testing Guide](./database-testing.md)** - Specific guidance for database testing patterns
- **[Test Coverage Guide](./coverage.md)** - Coverage analysis and reporting techniques
- **[Testing Methodology](./methodology.md)** - Our testing approach and philosophy  
- **[Quality Metrics](./quality-metrics.md)** - How we measure and track test quality
- **[Troubleshooting Guide](./troubleshooting.md)** - Common testing issues and solutions

## Specialized Testing References

- **[Mock GitHub Server](../reference/testing/mock-github-server.md)** - GitHub API testing without tokens

## Navigation

**New to testing?** Start with the [Complete Testing Guide](../developer/testing-guide.md) for comprehensive guidance.

## Test Structure Overview

```
tests/
├── conftest.py              # Pytest configuration and fixtures
├── unit/                    # Unit tests (fast, isolated)
│   ├── database/           # Database configuration and connection tests
│   ├── models/             # SQLAlchemy model tests
│   └── repositories/       # Repository pattern tests
├── integration/            # Integration tests (real database)
│   ├── test_database_*.py  # Database integration tests
│   └── test_repository_*.py # Repository integration tests
└── __init__.py
```

## Key Testing Components

### Current Test Coverage
- **170 test methods** across 32 test classes
- **5,182 lines** of test code
- **Unit tests**: Models, repositories, database operations
- **Integration tests**: Real database, migrations, end-to-end workflows
- **Real database testing**: PostgreSQL with testcontainers

### Testing Infrastructure
- **Pytest**: Primary testing framework
- **Testcontainers**: Real PostgreSQL for integration tests
- **AsyncMock**: Async operation testing
- **Factory patterns**: Test data generation
- **Comprehensive fixtures**: Database setup, cleanup, and state management

## Running Tests

### Basic Test Execution
```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/unit/repositories/test_pull_request_repository.py -v

# Specific test method
pytest tests/unit/models/test_models_comprehensive.py::TestModelCreation::test_pull_request_creation -v

# Integration tests only
pytest tests/integration/ -v
```

### Advanced Test Options
```bash
# With coverage
pytest tests/ --cov=src --cov-report=html

# Parallel execution
pytest tests/ -n auto

# Stop on first failure
pytest tests/ -x

# Verbose output with print statements
pytest tests/ -v -s

# Run only failed tests from last run
pytest tests/ --lf
```

## Test Development Guidelines

### Writing New Tests
1. Follow the **Why/What/How** documentation pattern in docstrings
2. Use descriptive test names that explain the scenario
3. Keep tests isolated and independent
4. Use appropriate fixtures for setup/teardown
5. Test both success and failure scenarios

### Test Organization
- **Unit tests**: Fast, isolated, mock external dependencies
- **Integration tests**: Real database, test component interactions
- **Test data**: Use factories, avoid hardcoded values
- **Assertions**: Clear, specific, with helpful failure messages

## Performance Considerations

### Current Performance Benchmarks
- **Unit test suite**: < 1 second execution time
- **Integration test suite**: < 10 seconds with testcontainers
- **Individual operations**: Basic performance validation (35ms thresholds)

### Future Performance Testing
See related issues:
- [Performance Testing Infrastructure (#32)](https://github.com/feddericovonwernich/agentic-coding-workflow/issues/32)
- [Advanced Testing Features (#33)](https://github.com/feddericovonwernich/agentic-coding-workflow/issues/33)

## Contributing to Tests

### Before Submitting Changes
1. Run the full test suite: `pytest tests/ -v`
2. Ensure new code has test coverage
3. Update documentation if adding new test patterns
4. Follow existing test naming conventions

### Test Review Checklist
- [ ] Tests follow Why/What/How documentation pattern
- [ ] Tests are properly isolated and independent
- [ ] Both success and failure cases are covered
- [ ] Test names are descriptive and clear
- [ ] Appropriate fixtures are used
- [ ] No hardcoded test data or magic numbers

## Getting Help

**Testing Issues:**
- **[🛠️ Troubleshooting Hub](../troubleshooting-hub.md)** - **Navigation center** - find the right troubleshooting guide for your issue type
- **[Testing Troubleshooting](./troubleshooting.md)** - Test execution, database testing, CI/CD problems
- **[Development Debugging](../developer/debugging.md)** - Local development environment and debugging issues

**Testing Guidance:**
- **[Testing Best Practices](./best-practices.md)** - Detailed testing guidance and patterns
- **[Testing Guide](../developer/testing-guide.md)** - Complete testing overview and workflows
- **[Testing Guidelines](../../TESTING_GUIDELINES.md)** - Authoritative testing standards and methodology

**Additional Resources:**
- Review existing tests for patterns and examples
- For performance testing needs, see issues #32 and #33