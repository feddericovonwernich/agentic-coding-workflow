"""
Test configuration and fixtures for database infrastructure tests.

Provides pytest fixtures, test databases, and common testing utilities
for both unit and integration tests.
"""

import asyncio
import os
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Test database configuration
TEST_DATABASE_URL = (
    "postgresql+asyncpg://postgres:test@localhost:5432/test_agentic_workflow"
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create an event loop for the entire test session.

    Why: Ensures all async tests run in the same event loop for consistency
    What: Provides a session-scoped event loop for async testing
    How: Creates a new event loop and ensures it's properly closed
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_database_config():
    """
    Mock database configuration for unit tests.

    Why: Isolates unit tests from real database dependencies
    What: Provides a mock DatabaseConfig instance with test values
    How: Creates a MagicMock with realistic configuration properties
    """
    mock_config = MagicMock()
    mock_config.host = "localhost"
    mock_config.port = 5432
    mock_config.database = "test_db"
    mock_config.username = "test_user"
    mock_config.password = "test_password"
    mock_config.database_url = TEST_DATABASE_URL
    mock_config.get_sqlalchemy_url.return_value = TEST_DATABASE_URL
    mock_config.get_alembic_url.return_value = (
        "postgresql://postgres:test@localhost:5432/test_agentic_workflow"
    )

    # Mock pool configuration
    mock_config.pool = MagicMock()
    mock_config.pool.pool_size = 20
    mock_config.pool.max_overflow = 30
    mock_config.pool.pool_timeout = 30
    mock_config.pool.pool_recycle = 3600
    mock_config.pool.pool_pre_ping = True

    return mock_config


@pytest.fixture
def mock_async_session():
    """
    Mock async database session for unit tests.

    Why: Allows testing database operations without real database connections
    What: Provides a mock AsyncSession with common database methods
    How: Creates AsyncMock with execute, commit, rollback, and close methods
    """
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.scalar = AsyncMock()

    return session


@pytest.fixture
def mock_connection_manager(mock_async_session):
    """
    Mock database connection manager for unit tests.

    Why: Tests connection management logic without actual database connections
    What: Provides a mock DatabaseConnectionManager with session handling
    How: Creates AsyncMock with get_session context manager and health checks
    """
    manager = AsyncMock()
    manager.get_session.return_value.__aenter__ = AsyncMock(
        return_value=mock_async_session
    )
    manager.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    manager.engine = MagicMock()
    manager.session_factory = MagicMock(return_value=mock_async_session)

    # Mock engine pool for health checks
    pool = MagicMock()
    pool.size.return_value = 5
    pool.checkedout.return_value = 2
    pool.overflow.return_value = 0
    pool.checkedin.return_value = 3
    manager.engine.pool = pool

    return manager


@pytest.fixture
def test_env_vars():
    """
    Set up test environment variables.

    Why: Ensures tests run with predictable configuration values
    What: Sets DATABASE_URL and other required environment variables
    How: Uses monkeypatch to temporarily set environment variables
    """
    env_vars = {
        "DATABASE_URL": TEST_DATABASE_URL,
        "DATABASE_HOST": "localhost",
        "DATABASE_PORT": "5432",
        "DATABASE_NAME": "test_agentic_workflow",
        "DATABASE_USERNAME": "postgres",
        "DATABASE_PASSWORD": "test_password",
    }

    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest_asyncio.fixture
async def mock_database_engine():
    """
    Mock async database engine for integration tests.

    Why: Provides a mock engine for testing database operations
    What: Creates a mock async engine with connection capabilities
    How: Uses AsyncMock with connect, dispose, and pool attributes
    """
    engine = AsyncMock()
    engine.connect = AsyncMock()
    engine.dispose = AsyncMock()

    # Mock connection context manager
    connection = AsyncMock()
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=None)
    engine.connect.return_value = connection

    # Mock pool
    pool = MagicMock()
    pool.size.return_value = 5
    pool.checkedout.return_value = 1
    pool.overflow.return_value = 0
    pool.checkedin.return_value = 4
    engine.pool = pool

    return engine


@pytest.fixture
def sample_health_check_results():
    """
    Sample health check results for testing.

    Why: Provides consistent test data for health monitoring tests
    What: Returns various HealthCheckResult instances for different scenarios
    How: Creates a dictionary of sample results for healthy, degraded,
         and unhealthy states
    """
    from src.database.health import HealthCheckResult, HealthStatus

    return {
        "healthy_connectivity": HealthCheckResult(
            name="connectivity",
            status=HealthStatus.HEALTHY,
            duration_ms=50.0,
            details={"response": "Connected successfully"},
        ),
        "unhealthy_connectivity": HealthCheckResult(
            name="connectivity",
            status=HealthStatus.UNHEALTHY,
            duration_ms=1000.0,
            error="Connection timeout",
        ),
        "degraded_pool": HealthCheckResult(
            name="connection_pool",
            status=HealthStatus.DEGRADED,
            duration_ms=25.0,
            details={
                "pool_size": 5,
                "checked_out": 4,
                "utilization_percent": 80.0,
                "warning": "Connection pool utilization high",
            },
        ),
        "healthy_response_time": HealthCheckResult(
            name="response_time",
            status=HealthStatus.HEALTHY,
            duration_ms=100.0,
            details={"query_duration_ms": 100.0, "timeout_ms": 1000.0},
        ),
    }


class AsyncContextManager:
    """
    Helper class for testing async context managers.

    Why: Provides a reusable async context manager for testing
    What: Implements __aenter__ and __aexit__ methods for async context management
    How: Uses provided enter and exit callables or default behavior
    """

    def __init__(self, enter_result=None, exit_result=None):
        self.enter_result = enter_result
        self.exit_result = exit_result

    async def __aenter__(self):
        return self.enter_result

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.exit_result


@pytest.fixture
def async_context_manager_factory():
    """
    Factory for creating async context managers in tests.

    Why: Simplifies creation of mock async context managers
    What: Returns a factory function for creating AsyncContextManager instances
    How: Uses the AsyncContextManager helper class
    """
    return AsyncContextManager
