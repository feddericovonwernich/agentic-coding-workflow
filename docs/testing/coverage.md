# Test Coverage Analysis and Reporting

This guide covers test coverage analysis, measurement, and reporting for the database testing infrastructure.

## Table of Contents

- [Coverage Overview](#coverage-overview)
- [Running Coverage Analysis](#running-coverage-analysis)
- [Coverage Reports](#coverage-reports)
- [Coverage Goals and Metrics](#coverage-goals-and-metrics)
- [Coverage Configuration](#coverage-configuration)
- [Interpreting Coverage Results](#interpreting-coverage-results)
- [Improving Coverage](#improving-coverage)
- [CI Integration](#ci-integration)

## Coverage Overview

### Current Coverage Status

Based on our comprehensive test suite:
- **170 test methods** across 32 test classes
- **5,182 lines** of test code
- **Comprehensive unit tests**: Models, repositories, database operations
- **Integration tests**: Real database testing with testcontainers

### Coverage Tools

We use **pytest-cov** (coverage.py) for code coverage analysis:

```bash
# Install coverage tools
pip install pytest-cov coverage[toml]
```

## Running Coverage Analysis

### Basic Coverage Commands

```bash
# Run tests with coverage
pytest tests/ --cov=src

# Generate HTML report
pytest tests/ --cov=src --cov-report=html

# Generate XML report (for CI)
pytest tests/ --cov=src --cov-report=xml

# Terminal report with missing lines
pytest tests/ --cov=src --cov-report=term-missing

# Multiple report formats
pytest tests/ --cov=src --cov-report=html --cov-report=xml --cov-report=term-missing
```

### Coverage by Component

```bash
# Database layer coverage
pytest tests/ --cov=src/database --cov-report=html

# Models coverage
pytest tests/ --cov=src/models --cov-report=html

# Repositories coverage  
pytest tests/ --cov=src/repositories --cov-report=html

# Cache layer coverage
pytest tests/ --cov=src/cache --cov-report=html

# Performance monitoring coverage
pytest tests/ --cov=src/performance --cov-report=html
```

### Targeted Coverage Analysis

```bash
# Coverage for specific test type
pytest tests/unit/ --cov=src --cov-report=html
pytest tests/integration/ --cov=src --cov-report=html

# Coverage with test filtering
pytest tests/ -k "test_repository" --cov=src --cov-report=html

# Coverage excluding specific modules
pytest tests/ --cov=src --cov-report=html --cov-omit="src/cache/*"
```

## Coverage Reports

### HTML Report

The HTML report provides the most detailed coverage information:

```bash
# Generate HTML report
pytest tests/ --cov=src --cov-report=html

# Open the report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

**HTML Report Features:**
- Overall coverage percentage
- File-by-file coverage breakdown
- Line-by-line coverage highlighting
- Missing line identification
- Branch coverage analysis

### Terminal Report

Quick coverage summary in terminal:

```bash
# Basic terminal report
pytest tests/ --cov=src --cov-report=term

# Terminal report with missing lines
pytest tests/ --cov=src --cov-report=term-missing
```

Example terminal output:
```
Name                                    Stmts   Miss  Cover   Missing
---------------------------------------------------------------------
src/__init__.py                             1      0   100%
src/database/__init__.py                    0      0   100%
src/database/config.py                    127      5    96%   89, 134, 167, 203, 241
src/database/connection.py                 98      3    97%   45, 78, 112
src/models/__init__.py                     28      0   100%
src/models/base.py                         69      2    97%   34, 67
src/repositories/base.py                  127      1    99%   156
---------------------------------------------------------------------
TOTAL                                    1834     23    99%
```

### XML Report

For CI/CD integration:

```bash
# Generate XML report
pytest tests/ --cov=src --cov-report=xml

# The report is saved as coverage.xml
```

## Coverage Goals and Metrics

### Target Coverage Levels

| Component | Target Coverage | Current Status |
|-----------|----------------|----------------|
| **Database Layer** | ≥ 95% | ✅ Achieved |
| **Models** | ≥ 95% | ✅ Achieved |
| **Repositories** | ≥ 95% | ✅ Achieved |
| **Cache Layer** | ≥ 90% | ✅ Achieved |
| **Performance** | ≥ 85% | ✅ Achieved |
| **Overall** | ≥ 90% | ✅ Achieved |

### Critical Coverage Areas

**Must Have 100% Coverage:**
- Model validation methods
- Repository CRUD operations
- Database connection handling
- Error handling paths
- State transition logic

**Must Have ≥95% Coverage:**
- All public repository methods
- Model business logic
- Database configuration
- Cache operations

**Acceptable ≥85% Coverage:**
- Performance monitoring utilities
- Complex query optimization logic
- Advanced caching strategies

### Coverage Quality Metrics

Beyond line coverage, we track:
- **Branch coverage**: Decision point testing
- **Function coverage**: All functions called
- **Class coverage**: All classes instantiated
- **Error path coverage**: Exception scenarios tested

## Coverage Configuration

### pytest.ini Configuration

```ini
[tool:pytest]
testpaths = tests
addopts = 
    --strict-markers
    --cov=src
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-fail-under=90
```

### pyproject.toml Configuration

```toml
[tool.coverage.run]
source = ["src"]
branch = true
omit = [
    "*/migrations/*",
    "*/tests/*",
    "*/__pycache__/*",
    "*/venv/*",
    "setup.py"
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
show_missing = true
skip_covered = false
precision = 2

[tool.coverage.html]
directory = "htmlcov"
```

### .coveragerc Configuration

```ini
[run]
source = src
branch = True
omit = 
    */migrations/*
    */tests/*
    */__pycache__/*
    */venv/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:

show_missing = True
precision = 2
fail_under = 90

[html]
directory = htmlcov
```

## Interpreting Coverage Results

### Understanding Coverage Metrics

**Line Coverage**: Percentage of code lines executed by tests
- **90%+ = Excellent**: Comprehensive test coverage
- **80-89% = Good**: Adequate coverage with some gaps
- **70-79% = Fair**: Needs improvement
- **<70% = Poor**: Significant testing gaps

**Branch Coverage**: Percentage of decision branches tested
- Critical for testing conditional logic
- Should be close to line coverage percentage
- Gaps indicate untested edge cases

### Identifying Coverage Gaps

1. **Missing Lines**: Code never executed by tests
2. **Partial Branches**: Conditional statements with untested paths
3. **Uncovered Functions**: Functions never called in tests
4. **Error Paths**: Exception handling not tested

### Coverage Analysis Workflow

```bash
# 1. Generate coverage report
pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# 2. Review terminal output for quick overview
# Look for files with <90% coverage

# 3. Open HTML report for detailed analysis
open htmlcov/index.html

# 4. Click on files with low coverage
# Identify specific missing lines

# 5. Write tests for missing coverage
# Focus on critical paths first

# 6. Re-run coverage to verify improvement
pytest tests/ --cov=src --cov-report=term-missing
```

## Improving Coverage

### Strategies for Increasing Coverage

#### 1. Target Missing Lines

```bash
# Identify specific missing lines
pytest tests/ --cov=src --cov-report=term-missing

# Focus on high-impact areas first
# - Error handling paths
# - Edge case conditions
# - Complex business logic
```

#### 2. Add Error Path Testing

```python
# Cover exception handling
def test_repository_handles_database_error():
    """Test repository error handling for database failures."""
    mock_session.execute.side_effect = SQLAlchemyError("Database error")
    
    with pytest.raises(SQLAlchemyError):
        await repository.get_by_id(uuid.uuid4())
```

#### 3. Test Edge Cases

```python
# Cover boundary conditions
def test_bulk_update_empty_list():
    """Test bulk update with empty list."""
    result = await repository.bulk_update_last_checked([])
    assert result == 0

def test_pagination_beyond_results():
    """Test pagination when offset exceeds available results."""
    results = await repository.list_all(limit=10, offset=1000)
    assert len(results) == 0
```

#### 4. Test Configuration Paths

```python
# Cover different configuration scenarios
def test_database_config_with_ssl():
    """Test database configuration with SSL enabled."""
    config = DatabaseConfig(
        host="localhost",
        database="test_db",
        ssl_mode="require"
    )
    assert config.ssl_mode == "require"
```

### Coverage Improvement Process

1. **Analyze Current Coverage**
   ```bash
   pytest tests/ --cov=src --cov-report=html --cov-report=term-missing
   ```

2. **Identify Priority Areas**
   - Critical business logic with <95% coverage
   - Error handling paths
   - Public API methods

3. **Write Targeted Tests**
   - Focus on missing lines
   - Test edge cases and error conditions
   - Ensure realistic scenarios

4. **Verify Improvement**
   ```bash
   pytest tests/ --cov=src --cov-report=term
   ```

5. **Maintain Coverage**
   - Add tests for new code
   - Update tests when code changes
   - Monitor coverage in CI

## CI Integration

### GitHub Actions Coverage

```yaml
name: Tests and Coverage

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest-cov
    
    - name: Run tests with coverage
      run: |
        pytest tests/ --cov=src --cov-report=xml --cov-report=term-missing --cov-fail-under=90
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: true
```

### Coverage Enforcement

```bash
# Fail build if coverage below threshold
pytest tests/ --cov=src --cov-fail-under=90

# Generate coverage badge
coverage-badge -o coverage.svg
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest-coverage
        name: pytest-coverage
        entry: pytest tests/ --cov=src --cov-fail-under=90
        language: system
        pass_filenames: false
        always_run: true
```

## Coverage Monitoring

### Regular Coverage Checks

```bash
# Weekly coverage analysis
pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# Generate coverage trend report
coverage report --show-missing > coverage-$(date +%Y-%m-%d).txt
```

### Coverage Regression Detection

```bash
# Compare with baseline
coverage report --compare baseline-coverage.json

# Set new baseline after improvements
coverage json -o baseline-coverage.json
```

### Coverage Metrics Dashboard

Track coverage trends over time:
- Line coverage percentage
- Branch coverage percentage
- Files with <90% coverage
- Critical paths coverage
- New code coverage

## Best Practices

### Coverage Best Practices

1. **Focus on Quality, Not Just Quantity**
   - 95% meaningful coverage > 100% superficial coverage
   - Test critical paths thoroughly
   - Include error scenarios

2. **Use Coverage to Find Gaps, Not Prove Quality**
   - Coverage shows what's NOT tested
   - Low coverage indicates missing tests
   - High coverage doesn't guarantee good tests

3. **Maintain Coverage Over Time**
   - Set coverage requirements in CI
   - Review coverage in code reviews
   - Update tests when refactoring

4. **Combine with Other Quality Metrics**
   - Mutation testing
   - Code review
   - Static analysis
   - Integration testing

### Common Coverage Pitfalls

❌ **Don't:**
- Write tests just to increase coverage numbers
- Ignore error handling paths
- Test implementation details instead of behavior
- Exclude important code from coverage analysis

✅ **Do:**
- Write meaningful tests that verify behavior
- Test both success and failure scenarios
- Focus on critical business logic
- Use coverage to guide testing efforts

## Summary

Effective test coverage analysis:
- **Measures test completeness** across the codebase
- **Identifies testing gaps** in critical functionality  
- **Guides testing efforts** toward high-impact areas
- **Maintains quality standards** through CI integration
- **Tracks improvement trends** over time

Current coverage achievements:
- ✅ **>95% coverage** for database layer
- ✅ **170 test methods** with comprehensive scenarios
- ✅ **5,182 lines** of quality test code
- ✅ **Real database testing** with testcontainers
- ✅ **CI integration** with coverage enforcement

For detailed testing guidance, see [Testing Best Practices](./best-practices.md).