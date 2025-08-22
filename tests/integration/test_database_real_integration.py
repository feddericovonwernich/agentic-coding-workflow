"""
Integration tests for database infrastructure using testcontainers.

These tests spin up a PostgreSQL database in a Docker container
and perform database operations to validate the infrastructure.

Requirements:
- Docker must be installed and running
- testcontainers-python package (installed via requirements.txt)
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any, Optional

import pytest
import pytest_asyncio
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

from src.database.config import DatabaseConfig, reset_database_config
from src.database.connection import (
    DatabaseConnectionManager,
    reset_connection_manager,
)
from src.database.health import (
    DatabaseHealthChecker,
    HealthStatus,
    reset_health_checker,
)


@pytest.fixture(scope="module")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """
    Spin up a PostgreSQL database in a Docker container.

    This fixture has module scope, so the container is reused across all tests
    in this module for efficiency.
    """
    with PostgresContainer(
        image="postgres:15-alpine",
        username="test_user",
        password="test_password",
        dbname="test_agentic_workflow",
        # Don't specify driver - let testcontainers use default psycopg2
    ) as postgres:
        # Wait for container to be ready
        postgres.get_connection_url()
        yield postgres


@pytest.fixture
def database_config(postgres_container: PostgresContainer) -> DatabaseConfig:
    """
    Create a DatabaseConfig that points to the real test database.

    This fixture provides actual database configuration using the
    testcontainer's connection details.
    """
    # Reset any cached configuration
    reset_database_config()
    reset_connection_manager()
    reset_health_checker()

    # Get connection URL from container
    connection_url = postgres_container.get_connection_url()

    # Convert psycopg2 URL to asyncpg URL
    async_url = connection_url.replace("postgresql+psycopg2", "postgresql+asyncpg")

    # Create pool config properly
    from src.database.config import DatabasePoolConfig

    pool_config = DatabasePoolConfig(
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
    )

    # Create config with database URL
    config = DatabaseConfig(
        database_url=async_url,
        pool=pool_config,  # Use proper pool config object
    )

    return config


@pytest_asyncio.fixture
async def connection_manager(
    database_config: DatabaseConfig,
) -> AsyncGenerator[DatabaseConnectionManager, None]:
    """
    Create a DatabaseConnectionManager connected to the real test database.

    This fixture provides a connection manager that actually connects to
    the PostgreSQL container.
    """
    manager = DatabaseConnectionManager(database_config)
    yield manager
    # Cleanup
    await manager.close()


@pytest.mark.integration
class TestDatabaseConnection:
    """Test actual database connectivity with a PostgreSQL instance."""

    @pytest.mark.asyncio
    async def test_database_connection(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify we can actually connect to a PostgreSQL database
        What: Tests basic connectivity by executing a simple query
        How: Uses connection_manager to connect to PostgreSQL container
             and executes SELECT 1 to verify the connection works
        """
        async with connection_manager.get_session() as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            assert value == 1

    @pytest.mark.asyncio
    async def test_database_version_check(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify we can query database metadata from PostgreSQL
        What: Tests ability to retrieve PostgreSQL version information
        How: Executes SELECT version() against the database container
             and validates we get a proper PostgreSQL version string
        """
        async with connection_manager.get_session() as session:
            result = await session.execute(text("SELECT version()"))
            version = result.scalar()
            assert version is not None
            assert "PostgreSQL" in version
            assert "15" in version  # We're using postgres:15-alpine

    @pytest.mark.asyncio
    async def test_database_table_operations(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify we can perform DDL and DML operations on database
        What: Tests CREATE TABLE, INSERT, SELECT, and DROP operations
        How: Creates a temporary table in the database, performs CRUD
             operations, and validates data integrity
        """
        async with connection_manager.get_session() as session:
            # Create table
            await session.execute(
                text("""
                CREATE TABLE IF NOT EXISTS test_table (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    value INTEGER
                )
            """)
            )

            # Insert data
            await session.execute(
                text("""
                INSERT INTO test_table (name, value)
                VALUES (:name, :value)
            """),
                {"name": "test_item", "value": 42},
            )

            # Select data
            result = await session.execute(
                text("""
                SELECT name, value FROM test_table
                WHERE name = :name
            """),
                {"name": "test_item"},
            )

            row = result.fetchone()
            assert row is not None
            assert row[0] == "test_item"
            assert row[1] == 42

            # Clean up
            await session.execute(text("DROP TABLE test_table"))
            await session.commit()

    @pytest.mark.asyncio
    async def test_database_transaction_rollback(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify transaction rollback works correctly with database
        What: Tests that rolled back transactions don't persist data
        How: Creates a table, inserts data, rolls back, and verifies
             the data was not persisted in the database
        """
        # First transaction - create table and rollback insert
        async with connection_manager.get_session() as session:
            await session.execute(
                text("""
                CREATE TABLE IF NOT EXISTS rollback_test (
                    id SERIAL PRIMARY KEY,
                    data VARCHAR(100)
                )
            """)
            )
            await session.commit()

        # Second transaction - insert and rollback
        try:
            async with connection_manager.get_session() as session:
                await session.execute(
                    text("""
                    INSERT INTO rollback_test (data) VALUES ('should_not_exist')
                """)
                )
                # Force an error to trigger rollback
                raise ValueError("Intentional error for rollback test")
        except ValueError:
            pass  # Expected

        # Third transaction - verify rollback worked
        async with connection_manager.get_session() as session:
            result = await session.execute(
                text("""
                SELECT COUNT(*) FROM rollback_test
            """)
            )
            count = result.scalar()
            assert count == 0  # No rows should exist due to rollback

            # Clean up
            await session.execute(text("DROP TABLE IF EXISTS rollback_test"))
            await session.commit()

    @pytest.mark.asyncio
    async def test_database_concurrent_sessions(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify connection pooling works with database connections
        What: Tests multiple concurrent database sessions
        How: Creates multiple async tasks that each use a database session
             concurrently, validating the connection pool handles them properly
        """

        async def execute_query(session_id: int) -> int:
            async with connection_manager.get_session() as session:
                result = await session.execute(
                    text(
                        "SELECT CAST(:id AS INTEGER) as session_id, NOW() as timestamp"
                    ),
                    {"id": session_id},
                )
                row = result.fetchone()
                return int(row[0]) if row else 0  # Return session_id

        # Run 10 concurrent queries
        tasks = [execute_query(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # Verify all queries completed successfully
        assert len(results) == 10
        assert set(results) == set(range(10))


@pytest.mark.integration
class TestDatabaseHealth:
    """Test health monitoring with a PostgreSQL instance."""

    @pytest.mark.asyncio
    async def test_health_check_connectivity(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify health checks work against database
        What: Tests connectivity health check returns HEALTHY
        How: Creates DatabaseHealthChecker with connection manager
             and validates connectivity check succeeds
        """
        health_checker = DatabaseHealthChecker(connection_manager)
        result = await health_checker.check_connectivity()

        assert result.status == HealthStatus.HEALTHY
        assert result.error is None
        assert result.duration_ms > 0
        assert result.details is not None
        assert "Connected successfully" in result.details["response"]

    @pytest.mark.asyncio
    async def test_health_check_write_permissions(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify write permission checks work with database
        What: Tests ability to create, write, and drop tables
        How: Runs write permission health check which creates a temp table,
             inserts data, and drops it in the database
        """
        health_checker = DatabaseHealthChecker(connection_manager)
        result = await health_checker.check_write_permissions()

        assert result.status == HealthStatus.HEALTHY
        assert result.error is None
        assert result.details is not None
        assert "create" in result.details["operations"]
        assert "insert" in result.details["operations"]
        assert "drop" in result.details["operations"]

    @pytest.mark.asyncio
    async def test_health_check_response_time(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify response time checks work with database latency
        What: Tests database response time measurement
        How: Runs response time health check against database
             and validates it completes within acceptable time
        """
        health_checker = DatabaseHealthChecker(connection_manager)
        result = await health_checker.check_response_time(query_timeout=5.0)

        assert result.status == HealthStatus.HEALTHY
        assert result.duration_ms < 5000  # Should be well under 5 seconds
        assert result.details is not None
        assert "table_count" in result.details

    @pytest.mark.asyncio
    async def test_comprehensive_health_check(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify all health checks work together against database
        What: Tests comprehensive health check suite
        How: Runs all health checks (connectivity, pool, version, permissions,
             response time) against the PostgreSQL container
        """
        health_checker = DatabaseHealthChecker(connection_manager)
        report = await health_checker.run_comprehensive_health_check(
            include_performance=True, query_timeout=2.0
        )

        assert report.overall_status == HealthStatus.HEALTHY
        assert report.is_healthy
        assert len(report.checks) >= 4  # At least 4 health checks
        assert len(report.failed_checks) == 0
        assert report.total_duration_ms > 0

        # Verify specific checks
        check_names = {check.name for check in report.checks}
        assert "connectivity" in check_names
        assert "connection_pool" in check_names
        assert "database_version" in check_names
        assert "write_permissions" in check_names


@pytest.mark.integration
class TestDatabasePooling:
    """Test connection pooling behavior with database."""

    @pytest.mark.asyncio
    async def test_connection_pool_limits(
        self, database_config: DatabaseConfig
    ) -> None:
        """
        Why: Verify connection pool can handle multiple concurrent connections
        What: Tests that multiple concurrent connections work properly
        How: Creates a manager with small pool size, opens multiple
             concurrent connections, and validates they all work
        """
        # Create manager with small pool for testing
        config = database_config
        config.pool.pool_size = 2
        config.pool.max_overflow = 1

        manager = DatabaseConnectionManager(config)

        try:
            # Test concurrent database operations
            async def test_query(query_id: int) -> int:
                async with manager.get_session() as session:
                    result = await session.execute(
                        text("SELECT CAST(:id AS INTEGER) as test_id"), {"id": query_id}
                    )
                    return result.scalar() or 0

            # Run multiple concurrent queries
            tasks = [test_query(i) for i in range(5)]
            results = await asyncio.gather(*tasks)

            # Verify all queries completed successfully
            assert results == list(range(5))

        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_connection_pool_config(
        self, database_config: DatabaseConfig
    ) -> None:
        """
        Why: Verify connection pool configuration is applied correctly
        What: Tests that pool configuration settings are respected
        How: Creates manager with custom pool config and validates
             basic connection functionality works as expected
        """
        # Create manager with custom pool config
        config = database_config
        config.pool.pool_size = 3
        config.pool.max_overflow = 2
        config.pool.pool_timeout = 10

        manager = DatabaseConnectionManager(config)

        try:
            # Test basic connection functionality
            async with manager.get_session() as session:
                result = await session.execute(text("SELECT 1 as test"))
                value = result.scalar()
                assert value == 1

            # Test multiple sequential connections
            for i in range(5):
                async with manager.get_session() as session:
                    result = await session.execute(
                        text("SELECT CAST(:num AS INTEGER) as result"), {"num": i}
                    )
                    value = result.scalar()
                    assert value == i

        finally:
            await manager.close()


@pytest.mark.integration
@pytest.mark.slow
class TestDatabaseStress:
    """Stress tests with database to validate stability."""

    @pytest.mark.asyncio
    async def test_database_many_operations(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify system handles many sequential operations reliably
        What: Tests executing many database operations in sequence
        How: Performs 100 sequential database queries and validates
             all complete successfully without connection issues
        """
        for i in range(100):
            async with connection_manager.get_session() as session:
                result = await session.execute(
                    text("SELECT CAST(:num AS INTEGER) * 2 as result"), {"num": i}
                )
                value = result.scalar()
                assert value == i * 2

    @pytest.mark.asyncio
    async def test_database_concurrent_stress(
        self, connection_manager: DatabaseConnectionManager
    ) -> None:
        """
        Why: Verify system handles high concurrency with database
        What: Tests many concurrent database operations
        How: Executes 50 concurrent database queries simultaneously
             and validates all complete successfully
        """

        async def stress_query(query_id: int) -> tuple[int, int]:
            async with connection_manager.get_session() as session:
                result = await session.execute(
                    text("""
                    SELECT
                        CAST(:id AS INTEGER) as query_id,
                        COUNT(*) as table_count
                    FROM information_schema.tables
                """),
                    {"id": query_id},
                )
                row = result.fetchone()
                return (int(row[0]), int(row[1])) if row else (0, 0)

        # Run 50 concurrent queries
        tasks = [stress_query(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        # Verify all completed
        assert len(results) == 50
        query_ids = [r[0] for r in results]
        assert set(query_ids) == set(range(50))

        # All should have gotten the same table count
        table_counts = [r[1] for r in results]
        assert len(set(table_counts)) == 1  # All counts should be identical
