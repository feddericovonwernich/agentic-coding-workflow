# Testing Troubleshooting Guide

This guide provides solutions for common issues encountered when running database tests in the agentic coding workflow project.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Test Execution Issues](#test-execution-issues)
- [Database Connection Problems](#database-connection-problems)
- [Test Data Issues](#test-data-issues)
- [Performance Problems](#performance-problems)
- [Integration Test Failures](#integration-test-failures)
- [Migration Test Issues](#migration-test-issues)
- [Coverage and Reporting Problems](#coverage-and-reporting-problems)
- [CI/CD Issues](#cicd-issues)
- [Common Error Messages](#common-error-messages)

## Quick Diagnostics

### First Steps for Any Test Issue

```bash
# 1. Check basic test execution
pytest tests/ -v --tb=short

# 2. Run a single test to isolate the issue
pytest tests/unit/repositories/test_pull_request_repository.py::TestPullRequestRepository::test_create_pull_request -v

# 3. Check test environment
python -c "import sys; print(sys.version)"
pip list | grep -E "(pytest|sqlalchemy|asyncpg)"

# 4. Verify database connectivity (for integration tests)
python -c "
import asyncio
from testcontainers.postgres import PostgresContainer

async def test_db():
    postgres = PostgresContainer('postgres:15')
    postgres.start()
    print(f'Database URL: {postgres.get_connection_url()}')
    postgres.stop()

asyncio.run(test_db())
"
```

### Environment Health Check

```bash
# Create a health check script
cat > scripts/test_health_check.py << 'EOF'
#!/usr/bin/env python3
"""Test environment health check."""

import asyncio
import sys
import os
from pathlib import Path

async def main():
    print("=== Test Environment Health Check ===\n")
    
    # 1. Python version
    print(f"Python version: {sys.version}")
    
    # 2. Working directory
    print(f"Working directory: {os.getcwd()}")
    
    # 3. Test files existence
    test_files = [
        "tests/conftest.py",
        "tests/unit/repositories/test_pull_request_repository.py",
        "tests/integration/test_database_real_integration.py"
    ]
    
    print("\nTest files:")
    for file in test_files:
        exists = Path(file).exists()
        status = "✅" if exists else "❌"
        print(f"  {status} {file}")
    
    # 4. Required packages
    try:
        import pytest
        import sqlalchemy
        import asyncpg
        import testcontainers
        print(f"\n✅ All required packages available")
        print(f"   pytest: {pytest.__version__}")
        print(f"   sqlalchemy: {sqlalchemy.__version__}")
    except ImportError as e:
        print(f"\n❌ Missing package: {e}")
        return 1
    
    # 5. Database container test
    try:
        from testcontainers.postgres import PostgresContainer
        postgres = PostgresContainer("postgres:15")
        postgres.start()
        print(f"\n✅ PostgreSQL container: {postgres.get_connection_url()}")
        postgres.stop()
    except Exception as e:
        print(f"\n❌ Container error: {e}")
        return 1
    
    print("\n=== Health check completed successfully ===")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
EOF

python scripts/test_health_check.py
```

## Test Execution Issues

### Issue: Tests Not Found

**Symptoms:**
```
collected 0 items
```

**Causes & Solutions:**

1. **Wrong directory or file naming**
   ```bash
   # Check test discovery
   pytest --collect-only tests/
   
   # Ensure files start with 'test_' or end with '_test.py'
   ls tests/unit/repositories/
   # Should show: test_pull_request_repository.py, etc.
   ```

2. **Python path issues**
   ```bash
   # Add current directory to Python path
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   pytest tests/
   
   # Or use -s flag to see import errors
   pytest tests/ -s
   ```

3. **Import errors preventing test discovery**
   ```bash
   # Check for import issues
   python -m pytest tests/ --tb=long -v
   ```

### Issue: Tests Hang or Timeout

**Symptoms:**
```
tests/integration/test_repository_integration.py::test_pr_lifecycle PASSED [100%]
```
(Test never completes)

**Solutions:**

1. **Database connection issues**
   ```python
   # Add timeout to async operations
   async def test_with_timeout():
       async with asyncio.timeout(30):  # 30 second timeout
           result = await repo.get_by_id(pr_id)
   ```

2. **Unclosed database connections**
   ```python
   # Ensure proper session cleanup
   @pytest.fixture
   async def async_session(async_session_factory):
       async with async_session_factory() as session:
           yield session
           # Session automatically closed by context manager
   ```

3. **Docker container issues**
   ```bash
   # Clean up containers
   docker ps -a | grep postgres | awk '{print $1}' | xargs docker rm -f
   docker system prune -f
   ```

### Issue: Asyncio Event Loop Errors

**Symptoms:**
```
RuntimeError: There is no current event loop in thread
```

**Solutions:**

1. **Missing pytest-asyncio plugin**
   ```bash
   pip install pytest-asyncio
   
   # Add to pytest.ini
   [tool:pytest]
   asyncio_mode = auto
   ```

2. **Incorrect async fixture usage**
   ```python
   # Wrong
   @pytest.fixture
   def async_session():
       return AsyncSession()
   
   # Correct
   @pytest.fixture
   async def async_session(async_session_factory):
       async with async_session_factory() as session:
           yield session
   ```

## Database Connection Problems

### Issue: PostgreSQL Container Fails to Start

**Symptoms:**
```
testcontainers.core.exceptions.ContainerStartupException: Container failed to start
```

**Solutions:**

1. **Docker daemon not running**
   ```bash
   # Check Docker status
   docker info
   
   # Start Docker (varies by OS)
   sudo systemctl start docker  # Linux
   open -a Docker              # macOS
   ```

2. **Port conflicts**
   ```bash
   # Check for port usage
   lsof -i :5432
   
   # Kill conflicting processes if needed
   sudo kill -9 <PID>
   ```

3. **Docker resource limits**
   ```bash
   # Clean up Docker resources
   docker system df
   docker system prune -a
   
   # Increase Docker memory (Docker Desktop)
   # Settings > Resources > Memory > 4GB+
   ```

### Issue: Connection Refused Errors

**Symptoms:**
```
asyncpg.exceptions.ConnectionDoesNotExistError: connection does not exist
```

**Solutions:**

1. **Container not fully ready**
   ```python
   # Add readiness check
   @pytest.fixture(scope="session")
   async def postgres_container():
       postgres = PostgresContainer("postgres:15")
       postgres.start()
       
       # Wait for container to be ready
       import time
       time.sleep(2)
       
       # Test connection
       conn_url = postgres.get_connection_url()
       engine = create_async_engine(conn_url.replace("postgresql://", "postgresql+asyncpg://"))
       
       async with engine.begin() as conn:
           await conn.execute(text("SELECT 1"))
       
       yield postgres
       postgres.stop()
   ```

2. **Incorrect connection string format**
   ```python
   # Ensure correct async format
   sync_url = "postgresql://user:pass@host:port/db"
   async_url = "postgresql+asyncpg://user:pass@host:port/db"
   
   # Debug connection URL
   print(f"Connection URL: {postgres_container.get_connection_url()}")
   ```

### Issue: Database Permission Errors

**Symptoms:**
```
asyncpg.exceptions.InsufficientPrivilegeError: permission denied for table
```

**Solutions:**

1. **Use superuser for tests**
   ```python
   postgres = PostgresContainer(
       "postgres:15",
       username="test_user",
       password="test_password",
       dbname="test_db"
   )
   ```

2. **Grant necessary permissions**
   ```sql
   -- Run in database setup
   GRANT ALL PRIVILEGES ON DATABASE test_db TO test_user;
   GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO test_user;
   ```

## Test Data Issues

### Issue: Foreign Key Constraint Violations

**Symptoms:**
```
asyncpg.exceptions.ForeignKeyViolationError: insert or update on table "pull_requests" violates foreign key constraint
```

**Solutions:**

1. **Create dependencies in correct order**
   ```python
   # Wrong: PR without repository
   pr = await pr_repo.create(
       repository_id=uuid.uuid4(),  # Non-existent repository
       pr_number=123,
       title="Test"
   )
   
   # Correct: Create repository first
   repo = await repo_repo.create(**TestDataFactory.create_repository())
   pr = await pr_repo.create(
       repository_id=repo.id,  # Existing repository
       pr_number=123,
       title="Test"
   )
   await session.commit()
   ```

2. **Use test data factories**
   ```python
   class TestDataFactory:
       @staticmethod
       async def create_complete_pr_scenario(session):
           """Create PR with all dependencies."""
           repo_repo = RepositoryRepository(session)
           pr_repo = PullRequestRepository(session)
           
           # Create repository first
           repo = await repo_repo.create(
               url="https://github.com/test/repo",
               name="repo",
               full_name="test/repo"
           )
           
           # Create PR with valid repository_id
           pr = await pr_repo.create(
               repository_id=repo.id,
               pr_number=123,
               title="Test PR",
               author="user"
           )
           
           await session.commit()
           return repo, pr
   ```

### Issue: Unique Constraint Violations

**Symptoms:**
```
asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint
```

**Solutions:**

1. **Use unique test data**
   ```python
   # Generate unique values
   unique_suffix = uuid.uuid4().hex[:8]
   
   repo = await repo_repo.create(
       url=f"https://github.com/test/repo-{unique_suffix}",
       name=f"repo-{unique_suffix}",
       full_name=f"test/repo-{unique_suffix}"
   )
   ```

2. **Clean up between tests**
   ```python
   @pytest.fixture(autouse=True)
   async def cleanup_database(async_session_factory):
       yield  # Run test
       
       # Clean up after test
       async with async_session_factory() as session:
           await session.execute(text("TRUNCATE TABLE pull_requests CASCADE"))
           await session.execute(text("TRUNCATE TABLE repositories CASCADE"))
           await session.commit()
   ```

### Issue: Test Data Pollution

**Symptoms:**
- Tests pass individually but fail when run together
- Intermittent test failures

**Solutions:**

1. **Ensure complete cleanup**
   ```python
   # Complete cleanup fixture
   @pytest.fixture(autouse=True)
   async def ensure_clean_state(async_session_factory):
       # Clean before test (in case previous test failed)
       async with async_session_factory() as session:
           tables = ["fix_attempts", "analysis_results", "check_runs", 
                    "pr_state_history", "reviews", "pull_requests", "repositories"]
           for table in tables:
               await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
           await session.commit()
       
       yield  # Run test
       
       # Clean after test
       async with async_session_factory() as session:
           for table in tables:
               await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
           await session.commit()
   ```

2. **Use transaction rollback for unit tests**
   ```python
   @pytest.fixture
   async def rollback_session(async_session_factory):
       """Provide session that automatically rolls back."""
       async with async_session_factory() as session:
           trans = await session.begin()
           yield session
           await trans.rollback()
   ```

## Performance Problems

### Issue: Slow Test Execution

**Symptoms:**
- Test suite takes longer than expected (>10 seconds)
- Individual tests are slow

**Solutions:**

1. **Identify slow tests**
   ```bash
   # Show slowest tests
   pytest tests/ --durations=10
   
   # Profile specific test
   pytest tests/integration/test_repository_integration.py::test_complex_query -s --durations=0
   ```

2. **Optimize database operations**
   ```python
   # Batch operations instead of individual queries
   # Slow
   for pr_id in pr_ids:
       await repo.update_last_checked(pr_id, datetime.now())
   
   # Fast
   await repo.bulk_update_last_checked(pr_ids, datetime.now())
   ```

3. **Use connection pooling**
   ```python
   # Configure connection pooling for tests
   @pytest.fixture(scope="session")
   async def async_engine(postgres_container):
       engine = create_async_engine(
           database_url,
           poolclass=StaticPool,
           pool_pre_ping=True,
           pool_recycle=3600
       )
       yield engine
       await engine.dispose()
   ```

### Issue: Memory Usage Problems

**Symptoms:**
- Tests consume excessive memory
- Out of memory errors

**Solutions:**

1. **Monitor memory usage**
   ```python
   import tracemalloc
   
   @pytest.fixture(autouse=True)
   def trace_memory():
       tracemalloc.start()
       yield
       current, peak = tracemalloc.get_traced_memory()
       print(f"Memory usage: current={current / 1024 / 1024:.1f}MB, peak={peak / 1024 / 1024:.1f}MB")
       tracemalloc.stop()
   ```

2. **Proper resource cleanup**
   ```python
   # Ensure all connections are closed
   @pytest.fixture
   async def async_session_factory(async_engine):
       factory = async_sessionmaker(async_engine, class_=AsyncSession)
       yield factory
       
       # Close all connections
       await async_engine.dispose()
   ```

## Integration Test Failures

### Issue: Migration Tests Fail

**Symptoms:**
```
alembic.util.exc.CommandError: Can't locate revision identified by
```

**Solutions:**

1. **Clean migration state**
   ```bash
   # Reset migration state
   rm -rf alembic/versions/
   alembic revision --autogenerate -m "Initial migration"
   ```

2. **Ensure clean database for migration**
   ```python
   async def test_migration_from_scratch():
       """Test migration on completely clean database."""
       # Don't run any setup migrations
       engine = create_async_engine(database_url)
       
       async with engine.begin() as conn:
           # Ensure completely empty database
           await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
           await conn.execute(text("CREATE SCHEMA public"))
       
       # Now run migration
       run_migrations(database_url)
       
       # Verify schema
       async with engine.begin() as conn:
           result = await conn.execute(text("""
               SELECT tablename FROM pg_tables 
               WHERE schemaname = 'public'
           """))
           tables = [row[0] for row in result.fetchall()]
           assert "repositories" in tables
   ```

### Issue: Container Resource Limits

**Symptoms:**
- Tests fail in CI but pass locally
- Container startup timeouts

**Solutions:**

1. **Optimize container configuration**
   ```python
   postgres = PostgresContainer(
       "postgres:15-alpine",  # Smaller image
       username="test",
       password="test",
       dbname="test"
   ).with_env("POSTGRES_INITDB_ARGS", "--auth-host=trust") \
    .with_env("POSTGRES_HOST_AUTH_METHOD", "trust")
   ```

2. **Add retry logic for container startup**
   ```python
   @pytest.fixture(scope="session")
   def postgres_container():
       for attempt in range(3):
           try:
               postgres = PostgresContainer("postgres:15")
               postgres.start()
               
               # Verify container is ready
               import time
               time.sleep(1)
               
               return postgres
           except Exception as e:
               if attempt == 2:
                   raise
               time.sleep(2)
   ```

## Migration Test Issues

### Issue: Schema Mismatch Errors

**Symptoms:**
```
AssertionError: Expected table 'pull_requests' not found in database
```

**Solutions:**

1. **Verify migration execution**
   ```python
   async def test_migration_execution():
       """Verify migration actually runs."""
       # Check migration history
       async with engine.begin() as conn:
           result = await conn.execute(text("""
               SELECT version_num FROM alembic_version
           """))
           version = result.scalar()
           assert version is not None, "No migration version found"
           
           # Check specific table
           result = await conn.execute(text("""
               SELECT EXISTS (
                   SELECT FROM information_schema.tables 
                   WHERE table_schema = 'public' 
                   AND table_name = 'pull_requests'
               )
           """))
           table_exists = result.scalar()
           assert table_exists, "pull_requests table not created"
   ```

2. **Debug migration SQL**
   ```python
   # Enable SQL logging for migrations
   import logging
   logging.getLogger('alembic').setLevel(logging.DEBUG)
   logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
   ```

## Coverage and Reporting Problems

### Issue: Coverage Not Collected

**Symptoms:**
```bash
pytest tests/ --cov=src
# No coverage report shown
```

**Solutions:**

1. **Install coverage dependencies**
   ```bash
   pip install pytest-cov coverage[toml]
   ```

2. **Check coverage configuration**
   ```ini
   # pytest.ini
   [tool:pytest]
   addopts = --cov=src --cov-report=term-missing
   ```

3. **Verify source path**
   ```bash
   # Ensure src directory exists and has Python files
   ls -la src/
   
   # Run with explicit source
   pytest tests/ --cov=./src
   ```

### Issue: Coverage Report Generation Fails

**Symptoms:**
```
coverage html
No data to report.
```

**Solutions:**

1. **Check data file**
   ```bash
   # Look for .coverage file
   ls -la .coverage*
   
   # If missing, run tests with coverage
   pytest tests/ --cov=src --cov-report=xml
   ```

2. **Generate report manually**
   ```bash
   coverage run -m pytest tests/
   coverage report
   coverage html
   ```

## CI/CD Issues

### Issue: Tests Fail Only in CI

**Symptoms:**
- Tests pass locally but fail in GitHub Actions
- Different behavior in CI environment

**Solutions:**

1. **Debug CI environment**
   ```yaml
   # Add debug steps to GitHub Actions
   - name: Debug environment
     run: |
       echo "Python version: $(python --version)"
       echo "Working directory: $(pwd)"
       echo "Available memory: $(free -h)"
       echo "Docker info:"
       docker info
       
       # List installed packages
       pip list
       
       # Check test files
       find tests/ -name "*.py" | head -10
   ```

2. **Match CI environment locally**
   ```bash
   # Use same Python version as CI
   pyenv install 3.12.11
   pyenv local 3.12.11
   
   # Use same dependency versions
   pip install -r requirements.txt --force-reinstall
   ```

3. **Add retry for flaky tests**
   ```yaml
   - name: Run tests with retry
     run: |
       pytest tests/ --maxfail=1 --tb=short || \
       pytest tests/ --maxfail=1 --tb=short || \
       pytest tests/ --maxfail=1 --tb=short
   ```

### Issue: Container Issues in CI

**Symptoms:**
```
Cannot connect to the Docker daemon
```

**Solutions:**

1. **Enable Docker service**
   ```yaml
   # GitHub Actions
   jobs:
     test:
       runs-on: ubuntu-latest
       services:
         docker:
           image: docker:dind
           options: --privileged
   ```

2. **Use matrix testing**
   ```yaml
   strategy:
     matrix:
       python-version: ['3.12']
       postgres-version: ['15']
   
   services:
     postgres:
       image: postgres:${{ matrix.postgres-version }}
       env:
         POSTGRES_PASSWORD: test
       options: >-
         --health-cmd pg_isready
         --health-interval 10s
         --health-timeout 5s
         --health-retries 5
   ```

## Common Error Messages

### `ModuleNotFoundError: No module named 'src'`

**Solution:**
```bash
# Add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Or install in development mode
pip install -e .

# Or use relative imports in tests
# tests/test_example.py
from src.models.pull_request import PullRequest  # Instead of: from models.pull_request import PullRequest
```

### `AttributeError: 'AsyncMock' object has no attribute 'return_value'`

**Solution:**
```python
# Incorrect mock setup
mock_session = AsyncMock()
mock_session.execute.return_value = result  # Wrong for async

# Correct mock setup
mock_session = AsyncMock()
mock_session.execute.return_value = result  # This is actually correct
# Or for more complex scenarios:
mock_session.execute = AsyncMock(return_value=result)
```

### `pytest.PytestUnraisableExceptionWarning`

**Solution:**
```python
# Ensure proper async cleanup
@pytest.fixture
async def async_session(async_session_factory):
    async with async_session_factory() as session:
        yield session
        # Session cleanup handled by context manager
    
# Or suppress warnings if they're not critical
import warnings
warnings.filterwarnings("ignore", category=pytest.PytestUnraisableExceptionWarning)
```

### `ValueError: I/O operation on closed file`

**Solution:**
```python
# Check for proper resource management
async def test_with_proper_cleanup():
    async with async_session_factory() as session:
        # Do operations
        result = await repo.get_by_id(some_id)
        # Session automatically closed here
    
    # Don't use session after context manager
```

## Getting Additional Help

### Enable Debug Logging

```python
# Add to test file or conftest.py
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable SQLAlchemy logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)
```

### Create Minimal Reproduction

```python
# Create minimal test case
async def test_minimal_reproduction():
    """Minimal test case demonstrating the issue."""
    # Simplest possible setup
    session = AsyncMock()
    repo = PullRequestRepository(session)
    
    # Minimal operation
    result = await repo.get_by_id(uuid.uuid4())
    
    # Basic assertion
    assert result is not None
```

### Useful Debug Commands

```bash
# Test environment validation
python -c "import pytest, sqlalchemy, asyncpg, testcontainers; print('All modules available')"

# Database connectivity test
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        result = await conn.execute(text('SELECT 1'))
        print(f'Database test: {result.scalar()}')
    await engine.dispose()

asyncio.run(test())
"

# Container diagnostics
docker ps -a
docker logs <container_id>
docker system df
```

## Summary

Most database testing issues fall into these categories:

1. **Environment Setup**: Missing dependencies, Python path issues
2. **Database Connectivity**: Container startup, connection configuration  
3. **Test Data Management**: Foreign keys, unique constraints, cleanup
4. **Async/Await Issues**: Event loop problems, fixture configuration
5. **Resource Management**: Memory usage, connection leaks

Following the patterns in our [Testing Best Practices](./best-practices.md) and using proper [Testing Methodology](./methodology.md) helps prevent most issues.

When troubleshooting:
1. Start with the simplest possible test case
2. Check environment setup and dependencies
3. Verify database connectivity
4. Enable debug logging
5. Use the provided diagnostic scripts

For complex issues, create a minimal reproduction case and check the related documentation in this testing guide.