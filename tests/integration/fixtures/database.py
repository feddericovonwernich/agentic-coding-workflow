"""Real database fixtures for integration testing.

This module provides TestDatabaseManager for real database integration in tests,
supporting both SQLite for CI/CD and PostgreSQL for local development with 
transaction-based isolation and performance monitoring.
"""

import asyncio
import logging
import os
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import alembic.config
import alembic.command
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError  
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from src.database.config import DatabaseConfig, DatabasePoolConfig
from src.database.connection import DatabaseConnectionManager
from src.models.repository import Repository
from src.models.pull_request import PullRequest
from src.models.check_run import CheckRun
from src.models.enums import RepositoryStatus, PRState, CheckStatus, CheckConclusion
import sys
from pathlib import Path

# Add scratch-pad to path for interface imports
scratch_pad_path = Path(__file__).parents[3] / "scratch-pad"
if str(scratch_pad_path) not in sys.path:
    sys.path.append(str(scratch_pad_path))

try:
    from interfaces.integration_testing_interfaces import (
        TestDatabaseContext,
        TestDatabaseManager,
        PerformanceMetrics
    )
except ImportError:
    # Fallback definitions if scratch-pad interfaces not available
    from dataclasses import dataclass
    from typing import Any, AsyncContextManager, Awaitable, Callable
    from abc import ABC, abstractmethod
    from contextlib import asynccontextmanager
    
    @dataclass
    class TestDatabaseContext:
        connection_manager: Any
        session_factory: Callable[[], AsyncContextManager[Any]]
        cleanup_handlers: list[Callable[[], Awaitable[None]]]
        test_data_ids: dict[str, list[Any]]
        database_url: str
        is_transaction_isolated: bool = True
    
    @dataclass  
    class PerformanceMetrics:
        test_name: str
        database_operations: int
        database_operation_time_ms: float
        api_requests: int
        api_request_time_ms: float
        cache_hits: int
        cache_misses: int
        memory_usage_mb: float
        total_test_time_ms: float
        
        @property
        def database_ops_per_second(self) -> float:
            if self.database_operation_time_ms == 0:
                return 0.0
            return (self.database_operations / self.database_operation_time_ms) * 1000
    
    class TestDatabaseManager(ABC):
        @abstractmethod
        async def create_test_database(self, isolation_id: str) -> TestDatabaseContext:
            pass
        
        @abstractmethod
        async def apply_migrations(self, context: TestDatabaseContext) -> None:
            pass
        
        @abstractmethod
        async def seed_test_data(self, context: TestDatabaseContext, scenario: str) -> dict[str, list[Any]]:
            pass
        
        @abstractmethod
        async def cleanup_database(self, context: TestDatabaseContext) -> None:
            pass
        
        @abstractmethod
        @asynccontextmanager
        async def get_transaction_context(self, context: TestDatabaseContext) -> AsyncContextManager[Any]:
            pass

logger = logging.getLogger(__name__)


@dataclass
class DatabasePerformanceMonitor:
    """Monitors database performance metrics during integration tests."""
    
    test_name: str
    query_count: int = 0
    query_time_ms: float = 0.0
    connection_count: int = 0
    start_time: float = field(default_factory=time.time)
    
    def record_query(self, duration_ms: float) -> None:
        """Record database query execution time."""
        self.query_count += 1
        self.query_time_ms += duration_ms
    
    def record_connection(self) -> None:
        """Record new database connection."""
        self.connection_count += 1
    
    def get_metrics(self) -> PerformanceMetrics:
        """Get performance metrics for test."""
        total_time = (time.time() - self.start_time) * 1000
        return PerformanceMetrics(
            test_name=self.test_name,
            database_operations=self.query_count,
            database_operation_time_ms=self.query_time_ms,
            api_requests=0,
            api_request_time_ms=0.0,
            cache_hits=0,
            cache_misses=0,
            memory_usage_mb=0.0,
            total_test_time_ms=total_time
        )


class RealTestDatabaseManager(TestDatabaseManager):
    """Real database manager for integration testing with transaction isolation."""
    
    def __init__(self, database_type: str = "auto"):
        """Initialize test database manager.
        
        Args:
            database_type: Database type - "sqlite", "postgresql", or "auto" 
        """
        self.database_type = self._determine_database_type(database_type)
        self.temp_files: list[Path] = []
        self.performance_monitors: dict[str, DatabasePerformanceMonitor] = {}
        self._test_database_configs: dict[str, DatabaseConfig] = {}
    
    def _determine_database_type(self, database_type: str) -> str:
        """Determine appropriate database type for testing environment."""
        if database_type == "auto":
            # Use SQLite for CI/CD, PostgreSQL for local development
            if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
                return "sqlite"
            elif os.getenv("DATABASE_URL", "").startswith("postgresql"):
                return "postgresql"
            else:
                return "sqlite"
        return database_type
    
    async def create_test_database(self, isolation_id: str) -> TestDatabaseContext:
        """Create isolated test database instance.
        
        Args:
            isolation_id: Unique identifier for test isolation
            
        Returns:
            Database context with real connection manager
        """
        logger.info(f"Creating test database with isolation_id: {isolation_id}")
        
        # Create database configuration for test
        if self.database_type == "sqlite":
            database_url = await self._create_sqlite_database(isolation_id)
        else:
            database_url = await self._create_postgresql_database(isolation_id)
        
        # Create test-specific database configuration
        config = DatabaseConfig(
            database_url=database_url,
            pool=DatabasePoolConfig(
                pool_size=2,  # Smaller pool for tests
                max_overflow=5,
                pool_pre_ping=True,
                pool_timeout=10
            ),
            echo_sql=bool(os.getenv("TEST_ECHO_SQL", False))
        )
        
        self._test_database_configs[isolation_id] = config
        
        # Create connection manager with monitoring
        connection_manager = DatabaseConnectionManager(config)
        
        # Add performance monitoring hooks
        performance_monitor = DatabasePerformanceMonitor(isolation_id)
        self.performance_monitors[isolation_id] = performance_monitor
        self._add_performance_monitoring(connection_manager.engine, performance_monitor)
        
        # Create session factory with transaction isolation
        session_factory = self._create_isolated_session_factory(connection_manager)
        
        # Setup cleanup handlers
        cleanup_handlers = [
            lambda: self._cleanup_database_resources(isolation_id, connection_manager)
        ]
        
        context = TestDatabaseContext(
            connection_manager=connection_manager,
            session_factory=session_factory,
            cleanup_handlers=cleanup_handlers,
            test_data_ids={},
            database_url=database_url,
            is_transaction_isolated=True
        )
        
        logger.info(f"Test database created successfully: {isolation_id}")
        return context
    
    async def _create_sqlite_database(self, isolation_id: str) -> str:
        """Create SQLite test database."""
        if os.getenv("TEST_USE_MEMORY_DB", "true").lower() == "true":
            # Use in-memory database for fastest tests
            return f"sqlite+aiosqlite:///:memory:?cache=shared&uri=true&isolation_id={isolation_id}"
        else:
            # Use temporary file database
            temp_file = Path(tempfile.mktemp(suffix=f"_{isolation_id}.db"))
            self.temp_files.append(temp_file)
            return f"sqlite+aiosqlite:///{temp_file}?isolation_id={isolation_id}"
    
    async def _create_postgresql_database(self, isolation_id: str) -> str:
        """Create PostgreSQL test database with unique schema."""
        base_config = DatabaseConfig()
        base_url = base_config.get_sqlalchemy_url()
        
        # Use unique schema per test for isolation
        schema_name = f"test_{isolation_id}".replace("-", "_")
        
        # PostgreSQL doesn't support schemas in URL, so we'll use the main database
        # but apply migrations to a unique schema (handled in apply_migrations)
        return f"{base_url}?options=-csearch_path={schema_name}"
    
    def _add_performance_monitoring(
        self, 
        engine: AsyncEngine, 
        monitor: DatabasePerformanceMonitor
    ) -> None:
        """Add performance monitoring event handlers to database engine."""
        
        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()
        
        @event.listens_for(engine.sync_engine, "after_cursor_execute") 
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if hasattr(context, '_query_start_time'):
                duration_ms = (time.time() - context._query_start_time) * 1000
                monitor.record_query(duration_ms)
        
        @event.listens_for(engine.sync_engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            monitor.record_connection()
    
    def _create_isolated_session_factory(
        self, 
        connection_manager: DatabaseConnectionManager
    ) -> Callable[[], AsyncGenerator[AsyncSession, None]]:
        """Create session factory with transaction-based isolation."""
        
        @asynccontextmanager
        async def isolated_session() -> AsyncGenerator[AsyncSession, None]:
            """Create isolated database session within transaction."""
            async with connection_manager.get_session() as session:
                # Start transaction for test isolation
                transaction = await session.begin()
                try:
                    yield session
                    # Don't commit - rollback for isolation
                    await transaction.rollback()
                except Exception:
                    await transaction.rollback()
                    raise
        
        return isolated_session
    
    async def apply_migrations(self, context: TestDatabaseContext) -> None:
        """Apply database migrations to test database.
        
        Args:
            context: Database context to apply migrations to
        """
        logger.info("Applying database migrations to test database")
        
        try:
            # Create Alembic configuration
            alembic_cfg = self._create_alembic_config(context.database_url)
            
            if self.database_type == "sqlite":
                # SQLite migrations run synchronously
                await self._apply_migrations_sync(alembic_cfg)
            else:
                # PostgreSQL migrations can run asynchronously
                await self._apply_migrations_async(alembic_cfg, context.connection_manager)
                
            logger.info("Database migrations applied successfully")
            
        except Exception as e:
            logger.error(f"Failed to apply migrations: {e}")
            raise RuntimeError(f"Migration failed: {e}") from e
    
    def _create_alembic_config(self, database_url: str) -> alembic.config.Config:
        """Create Alembic configuration for test database."""
        # Find alembic.ini in project root
        project_root = Path(__file__).parents[3]  # Navigate up from tests/integration/fixtures/
        alembic_ini = project_root / "alembic.ini"
        
        if not alembic_ini.exists():
            raise RuntimeError(f"Alembic configuration not found at {alembic_ini}")
        
        # Create Alembic config
        alembic_cfg = alembic.config.Config(str(alembic_ini))
        
        # Set database URL (convert to sync URL for Alembic)
        sync_url = database_url.replace("+aiosqlite", "").replace("+asyncpg", "")
        alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
        
        # Set script location
        script_location = project_root / "alembic"
        alembic_cfg.set_main_option("script_location", str(script_location))
        
        return alembic_cfg
    
    async def _apply_migrations_sync(self, alembic_cfg: alembic.config.Config) -> None:
        """Apply migrations synchronously for SQLite."""
        def run_migrations():
            alembic.command.upgrade(alembic_cfg, "head")
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_migrations)
    
    async def _apply_migrations_async(
        self, 
        alembic_cfg: alembic.config.Config, 
        connection_manager: DatabaseConnectionManager
    ) -> None:
        """Apply migrations asynchronously for PostgreSQL."""
        def run_migrations():
            alembic.command.upgrade(alembic_cfg, "head")
        
        # Run in executor
        loop = asyncio.get_event_loop() 
        await loop.run_in_executor(None, run_migrations)
    
    async def seed_test_data(
        self, 
        context: TestDatabaseContext, 
        scenario: str
    ) -> dict[str, list[uuid.UUID]]:
        """Seed database with test data for specific scenario.
        
        Args:
            context: Database context to seed
            scenario: Test scenario name for appropriate data
            
        Returns:
            Dictionary mapping data types to created record IDs
        """
        logger.info(f"Seeding test data for scenario: {scenario}")
        
        # Define scenario data factories
        scenario_factories = {
            "basic_discovery": self._seed_basic_discovery_data,
            "large_repository": self._seed_large_repository_data, 
            "error_conditions": self._seed_error_condition_data,
            "performance_test": self._seed_performance_test_data,
            "empty": self._seed_empty_data
        }
        
        factory = scenario_factories.get(scenario, self._seed_basic_discovery_data)
        created_ids = await factory(context)
        
        # Track created IDs for cleanup
        context.test_data_ids.update(created_ids)
        
        logger.info(f"Test data seeded successfully: {len(sum(created_ids.values(), []))} records")
        return created_ids
    
    async def _seed_basic_discovery_data(
        self, 
        context: TestDatabaseContext
    ) -> dict[str, list[uuid.UUID]]:
        """Seed basic discovery test data."""
        repository_ids = []
        pr_ids = []
        check_ids = []
        
        async with context.session_factory() as session:
            # Create test repositories
            repos = [
                Repository(
                    id=uuid.uuid4(),
                    url="https://github.com/test/repo1",
                    name="test/repo1",
                    full_name="test/repo1",
                    status=RepositoryStatus.ACTIVE
                ),
                Repository(
                    id=uuid.uuid4(),
                    url="https://github.com/test/repo2", 
                    name="test/repo2",
                    full_name="test/repo2",
                    status=RepositoryStatus.ACTIVE
                )
            ]
            
            for repo in repos:
                session.add(repo)
                repository_ids.append(repo.id)
            
            await session.flush()
            
            # Create test pull requests
            for repo in repos:
                pr = PullRequest(
                    id=uuid.uuid4(),
                    repository_id=repo.id,
                    pr_number=1,
                    title="Test PR",
                    author="testuser",
                    state=PRState.OPENED,
                    base_branch="main",
                    head_branch="feature/test",
                    base_sha="abc123",
                    head_sha="def456",
                    url=f"{repo.url}/pull/1"
                )
                session.add(pr)
                pr_ids.append(pr.id)
                
                # Add check run to PR
                check = CheckRun(
                    id=uuid.uuid4(),
                    pull_request_id=pr.id,
                    external_id="123456",
                    check_name="CI Tests",
                    status=CheckStatus.COMPLETED,
                    conclusion=CheckConclusion.SUCCESS
                )
                session.add(check)
                check_ids.append(check.id)
            
            await session.commit()
        
        return {
            "repositories": repository_ids,
            "pull_requests": pr_ids,
            "check_runs": check_ids
        }
    
    async def _seed_large_repository_data(
        self, 
        context: TestDatabaseContext
    ) -> dict[str, list[uuid.UUID]]:
        """Seed large repository test data for performance testing."""
        repository_ids = []
        pr_ids = []
        check_ids = []
        
        async with context.session_factory() as session:
            # Create large repository
            repo = Repository(
                id=uuid.uuid4(),
                url="https://github.com/test/large-repo",
                name="test/large-repo",
                full_name="test/large-repo",
                status=RepositoryStatus.ACTIVE
            )
            session.add(repo)
            repository_ids.append(repo.id)
            await session.flush()
            
            # Create many pull requests (50 for performance testing)
            for i in range(50):
                pr = PullRequest(
                    id=uuid.uuid4(),
                    repository_id=repo.id,
                    pr_number=i + 1,
                    title=f"Test PR {i + 1}",
                    author=f"testuser{i % 5}",  # 5 different users
                    state=PRState.OPENED,
                    base_branch="main",
                    head_branch=f"feature/test-{i}",
                    base_sha=f"abc{i:03d}",
                    head_sha=f"def{i:03d}",
                    url=f"{repo.url}/pull/{i + 1}"
                )
                session.add(pr)
                pr_ids.append(pr.id)
                
                # Add multiple check runs per PR
                for j in range(3):  # 3 checks per PR
                    check = CheckRun(
                        id=uuid.uuid4(),
                        pull_request_id=pr.id,
                        external_id=f"{i}-{j}-{int(time.time())}",
                        check_name=f"Check {j + 1}",
                        status=CheckStatus.COMPLETED,
                        conclusion=CheckConclusion.SUCCESS if j < 2 else CheckConclusion.FAILURE
                    )
                    session.add(check)
                    check_ids.append(check.id)
            
            await session.commit()
        
        return {
            "repositories": repository_ids,
            "pull_requests": pr_ids,
            "check_runs": check_ids
        }
    
    async def _seed_error_condition_data(
        self, 
        context: TestDatabaseContext
    ) -> dict[str, list[uuid.UUID]]:
        """Seed data that simulates error conditions."""
        repository_ids = []
        pr_ids = []
        check_ids = []
        
        async with context.session_factory() as session:
            # Create repository with error status
            repo = Repository(
                id=uuid.uuid4(),
                url="https://github.com/test/error-repo",
                name="test/error-repo", 
                full_name="test/error-repo",
                status=RepositoryStatus.ERROR,
                failure_count=5,
                last_failure_reason="API rate limit exceeded"
            )
            session.add(repo)
            repository_ids.append(repo.id)
            await session.flush()
            
            # Create PR with failed checks
            pr = PullRequest(
                id=uuid.uuid4(),
                repository_id=repo.id,
                pr_number=1,
                title="Failing PR",
                author="testuser",
                state=PRState.OPENED,
                base_branch="main",
                head_branch="feature/failing",
                base_sha="abc123",
                head_sha="def456",
                url=f"{repo.url}/pull/1"
            )
            session.add(pr)
            pr_ids.append(pr.id)
            
            # Add failed check runs
            failed_checks = [
                ("Build", CheckConclusion.FAILURE),
                ("Tests", CheckConclusion.FAILURE), 
                ("Lint", CheckConclusion.SUCCESS)
            ]
            
            for check_name, conclusion in failed_checks:
                check = CheckRun(
                    id=uuid.uuid4(),
                    pull_request_id=pr.id,
                    external_id=f"fail-{check_name.lower()}-123",
                    check_name=check_name,
                    status=CheckStatus.COMPLETED,
                    conclusion=conclusion
                )
                session.add(check)
                check_ids.append(check.id)
            
            await session.commit()
        
        return {
            "repositories": repository_ids,
            "pull_requests": pr_ids,
            "check_runs": check_ids
        }
    
    async def _seed_performance_test_data(
        self,
        context: TestDatabaseContext
    ) -> dict[str, list[uuid.UUID]]:
        """Seed data optimized for performance testing."""
        # Use large repository data but with more controlled dataset
        return await self._seed_large_repository_data(context)
    
    async def _seed_empty_data(
        self,
        context: TestDatabaseContext
    ) -> dict[str, list[uuid.UUID]]:
        """Seed empty data (no test data created)."""
        return {
            "repositories": [],
            "pull_requests": [],
            "check_runs": []
        }
    
    async def cleanup_database(self, context: TestDatabaseContext) -> None:
        """Clean up test database and close connections.
        
        Args:
            context: Database context to clean up
        """
        logger.info("Cleaning up test database")
        
        try:
            # Execute all cleanup handlers
            for cleanup_handler in reversed(context.cleanup_handlers):
                await cleanup_handler()
                
        except Exception as e:
            logger.error(f"Error during database cleanup: {e}")
        finally:
            # Ensure connection manager is closed
            if context.connection_manager:
                try:
                    await context.connection_manager.close()
                except Exception as e:
                    logger.warning(f"Error closing connection manager: {e}")
        
        logger.info("Database cleanup completed")
    
    async def _cleanup_database_resources(
        self, 
        isolation_id: str, 
        connection_manager: DatabaseConnectionManager
    ) -> None:
        """Clean up database resources for specific isolation ID."""
        try:
            # Close connection manager
            await connection_manager.close()
            
            # Clean up temporary files
            await self._cleanup_temp_files()
            
            # Remove config and monitor
            self._test_database_configs.pop(isolation_id, None)
            self.performance_monitors.pop(isolation_id, None)
            
        except Exception as e:
            logger.warning(f"Error cleaning up resources for {isolation_id}: {e}")
    
    async def _cleanup_temp_files(self) -> None:
        """Clean up temporary database files."""
        for temp_file in self.temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception as e:
                logger.warning(f"Could not delete temporary file {temp_file}: {e}")
        
        self.temp_files.clear()
    
    @asynccontextmanager
    async def get_transaction_context(
        self, 
        context: TestDatabaseContext
    ) -> AsyncGenerator[AsyncSession, None]:
        """Get transactional database session for test isolation.
        
        Args:
            context: Database context for transaction
            
        Returns:
            Async context manager providing isolated database session
        """
        async with context.session_factory() as session:
            # Session is already transaction-isolated in our implementation
            yield session
    
    def get_performance_metrics(self, isolation_id: str) -> PerformanceMetrics | None:
        """Get performance metrics for specific test."""
        monitor = self.performance_monitors.get(isolation_id)
        return monitor.get_metrics() if monitor else None
    
    async def health_check(self, context: TestDatabaseContext) -> bool:
        """Check if test database is healthy and responsive."""
        try:
            async with context.session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global instance for integration tests
_test_database_manager: RealTestDatabaseManager | None = None


def get_test_database_manager() -> RealTestDatabaseManager:
    """Get global test database manager instance."""
    global _test_database_manager
    
    if _test_database_manager is None:
        _test_database_manager = RealTestDatabaseManager()
    
    return _test_database_manager


def reset_test_database_manager() -> None:
    """Reset global test database manager (useful for test cleanup)."""
    global _test_database_manager
    _test_database_manager = None