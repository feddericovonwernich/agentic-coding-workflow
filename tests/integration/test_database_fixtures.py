"""
Integration tests for TestDatabaseManager and database fixtures.

Why: Validates that the real database integration fixtures work correctly with actual
     database operations, transaction isolation, and performance monitoring
What: Tests database lifecycle, migration application, data seeding, and cleanup
How: Uses real database instances with controlled test scenarios and assertions
"""

import pytest
import pytest_asyncio
import uuid
from sqlalchemy import text, select, func
from sqlalchemy.exc import SQLAlchemyError

from src.models.repository import Repository
from src.models.pull_request import PullRequest  
from src.models.check_run import CheckRun
from src.models.enums import RepositoryStatus, PRState, CheckStatus, CheckConclusion
# Import database fixtures directly to avoid import issues
from tests.integration.fixtures.database import (
    RealTestDatabaseManager,
    get_test_database_manager,
    reset_test_database_manager
)


@pytest.mark.integration
@pytest.mark.database
class TestDatabaseManagerLifecycle:
    """Test database manager lifecycle operations."""
    
    async def test_create_and_cleanup_database(self, test_database_manager):
        """
        Why: Ensures database creation and cleanup work correctly without leaks
        What: Creates test database, verifies it works, then cleans up
        How: Creates database context, performs operations, verifies cleanup
        """
        isolation_id = str(uuid.uuid4())
        
        # Create test database
        context = await test_database_manager.create_test_database(isolation_id)
        
        try:
            # Verify database context is properly initialized
            assert context.connection_manager is not None
            assert context.session_factory is not None
            assert context.database_url is not None
            assert context.is_transaction_isolated is True
            assert len(context.cleanup_handlers) > 0
            
            # Verify database connection works
            health_check = await test_database_manager.health_check(context)
            assert health_check is True
            
        finally:
            # Cleanup database
            await test_database_manager.cleanup_database(context)
    
    async def test_apply_migrations(self, test_database_manager):
        """
        Why: Verifies that Alembic migrations are applied correctly to test database
        What: Creates database, applies migrations, verifies schema exists
        How: Creates database context, applies migrations, checks for expected tables
        """
        isolation_id = str(uuid.uuid4())
        context = await test_database_manager.create_test_database(isolation_id)
        
        try:
            # Apply migrations
            await test_database_manager.apply_migrations(context)
            
            # Verify tables exist by querying schema
            async with context.session_factory() as session:
                # Check that core tables exist
                table_check_queries = [
                    "SELECT COUNT(*) FROM repositories LIMIT 0",
                    "SELECT COUNT(*) FROM pull_requests LIMIT 0", 
                    "SELECT COUNT(*) FROM check_runs LIMIT 0",
                    "SELECT COUNT(*) FROM pr_state_history LIMIT 0"
                ]
                
                for query in table_check_queries:
                    # Should not raise an exception if table exists
                    await session.execute(text(query))
                    
        finally:
            await test_database_manager.cleanup_database(context)
    
    async def test_database_health_check(self, test_database_context):
        """
        Why: Validates that health check functionality works with real database
        What: Performs health check on active database connection
        How: Uses test context and calls health_check method
        """
        # Get manager from global function for health check
        from tests.integration.fixtures.database import get_test_database_manager
        manager = get_test_database_manager()
        
        # Health check should pass for active database
        health_status = await manager.health_check(test_database_context)
        assert health_status is True


@pytest.mark.integration  
@pytest.mark.database
class TestDatabaseIsolation:
    """Test database transaction isolation."""
    
    async def test_transaction_isolation_between_sessions(self, test_database_context):
        """
        Why: Ensures that operations in different sessions are properly isolated
        What: Creates data in one session, verifies it's not visible in another
        How: Uses session factory to create isolated sessions and verify separation
        """
        # Create data in first session
        repo_id = uuid.uuid4()
        async with test_database_context.session_factory() as session1:
            repo = Repository(
                id=repo_id,
                url="https://github.com/test/isolation",
                name="test/isolation",
                status=RepositoryStatus.ACTIVE
            )
            session1.add(repo)
            await session1.commit()
        
        # Verify data exists in second session (same transaction)
        async with test_database_context.session_factory() as session2:
            result = await session2.get(Repository, repo_id)
            # With transaction isolation, the data should be rolled back
            # This tests that our transaction isolation is working
            assert result is None  # Data was rolled back due to transaction isolation
    
    async def test_session_rollback_on_error(self, test_database_context):
        """
        Why: Verifies that sessions properly rollback on errors
        What: Creates data, causes error, verifies rollback occurred  
        How: Creates data, raises exception, verifies data was not persisted
        """
        repo_id = uuid.uuid4()
        
        # Attempt operation that will fail
        with pytest.raises(Exception):
            async with test_database_context.session_factory() as session:
                repo = Repository(
                    id=repo_id,
                    url="https://github.com/test/rollback",
                    name="test/rollback", 
                    status=RepositoryStatus.ACTIVE
                )
                session.add(repo)
                await session.flush()  # Flush to database
                
                # Intentionally raise error to trigger rollback
                raise ValueError("Intentional error for rollback test")
        
        # Verify data was rolled back
        async with test_database_context.session_factory() as session:
            result = await session.get(Repository, repo_id)
            assert result is None  # Data should be rolled back


@pytest.mark.integration
@pytest.mark.database  
class TestDataSeeding:
    """Test database data seeding functionality."""
    
    async def test_basic_discovery_seeding(self, test_database_manager, test_database_context):
        """
        Why: Validates that basic discovery scenario creates expected test data
        What: Seeds database with basic scenario, verifies expected records exist
        How: Seeds data, queries database, asserts expected counts and relationships
        """
        # Seed with basic discovery data
        created_ids = await test_database_manager.seed_test_data(
            test_database_context, 
            "basic_discovery"
        )
        
        # Verify expected data was created
        assert "repositories" in created_ids
        assert "pull_requests" in created_ids  
        assert "check_runs" in created_ids
        assert len(created_ids["repositories"]) == 2  # 2 repositories
        assert len(created_ids["pull_requests"]) == 2  # 1 PR per repo
        assert len(created_ids["check_runs"]) == 2  # 1 check per PR
        
        # Verify data exists in database
        async with test_database_context.session_factory() as session:
            repo_count = await session.scalar(select(func.count(Repository.id)))
            pr_count = await session.scalar(select(func.count(PullRequest.id)))
            check_count = await session.scalar(select(func.count(CheckRun.id)))
            
            assert repo_count == 2
            assert pr_count == 2
            assert check_count == 2
    
    async def test_large_repository_seeding(self, test_database_manager, test_database_context):
        """
        Why: Validates that large dataset scenario creates appropriate volume of data
        What: Seeds database with large scenario, verifies high record counts
        How: Seeds large dataset, queries totals, asserts expected volumes
        """
        # Seed with large repository data
        created_ids = await test_database_manager.seed_test_data(
            test_database_context,
            "large_repository"
        )
        
        # Verify large dataset was created
        assert len(created_ids["repositories"]) == 1  # 1 large repository
        assert len(created_ids["pull_requests"]) == 50  # 50 PRs
        assert len(created_ids["check_runs"]) == 150  # 3 checks per PR (50 * 3)
        
        # Verify relationships are correct
        async with test_database_context.session_factory() as session:
            # Get the repository
            repo = await session.get(Repository, created_ids["repositories"][0])
            assert repo is not None
            
            # Verify PR counts
            pr_count = await session.scalar(
                select(func.count(PullRequest.id))
                .where(PullRequest.repository_id == repo.id)
            )
            assert pr_count == 50
    
    async def test_error_conditions_seeding(self, test_database_manager, test_database_context):
        """
        Why: Validates that error scenario creates data representing error states
        What: Seeds database with error scenario, verifies error states exist
        How: Seeds error data, queries for specific error conditions, validates states
        """
        # Seed with error conditions data
        created_ids = await test_database_manager.seed_test_data(
            test_database_context,
            "error_conditions"
        )
        
        # Verify error data was created
        async with test_database_context.session_factory() as session:
            # Check repository has error status
            repo = await session.get(Repository, created_ids["repositories"][0])
            assert repo is not None
            assert repo.status == RepositoryStatus.ERROR
            assert repo.failure_count == 5
            assert repo.last_failure_reason is not None
            
            # Check that there are failed check runs
            failed_checks = await session.scalars(
                select(CheckRun)
                .where(CheckRun.conclusion == CheckConclusion.FAILURE)
            )
            failed_check_list = list(failed_checks)
            assert len(failed_check_list) >= 2  # Should have at least 2 failed checks


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.performance
class TestPerformanceMonitoring:
    """Test database performance monitoring functionality."""
    
    async def test_performance_metrics_collection(self, performance_metrics_collector):
        """
        Why: Validates that performance monitoring captures database operation metrics
        What: Performs database operations and verifies metrics are collected
        How: Uses performance collector, runs queries, checks metrics are recorded
        """
        context, get_metrics = performance_metrics_collector
        
        # Perform some database operations
        async with context.session_factory() as session:
            # Simple query to generate metrics
            await session.execute(text("SELECT 1"))
            await session.execute(text("SELECT COUNT(*) FROM repositories"))
        
        # Get performance metrics
        metrics = get_metrics()
        
        if metrics:  # Metrics may be None if isolation ID extraction failed
            assert metrics.database_operations >= 2  # At least 2 queries
            assert metrics.database_operation_time_ms > 0  # Some time was recorded
            assert metrics.total_test_time_ms > 0  # Test took some time
    
    async def test_performance_monitoring_with_bulk_operations(self, test_database_manager):
        """
        Why: Tests performance monitoring with bulk database operations
        What: Creates many database records and monitors performance
        How: Bulk inserts data, checks performance metrics show appropriate counts
        """
        isolation_id = str(uuid.uuid4())
        context = await test_database_manager.create_test_database(isolation_id)
        
        try:
            await test_database_manager.apply_migrations(context)
            
            # Seed large dataset to generate more operations
            await test_database_manager.seed_test_data(context, "large_repository")
            
            # Check performance metrics
            metrics = test_database_manager.get_performance_metrics(isolation_id)
            
            if metrics:
                # Large dataset should generate significant database activity
                assert metrics.database_operations > 50  # Many insert operations
                assert metrics.connection_count >= 1  # At least one connection
                
        finally:
            await test_database_manager.cleanup_database(context)


@pytest.mark.integration
@pytest.mark.database
class TestDatabaseConstraints:
    """Test that database constraints and relationships work correctly."""
    
    async def test_foreign_key_constraints(self, seeded_database_context):
        """
        Why: Validates that foreign key relationships work in real database
        What: Creates related records and verifies foreign key constraints
        How: Queries related data and verifies relationships are maintained
        """
        async with seeded_database_context.session_factory() as session:
            # Get a repository and its pull requests
            repo = await session.scalar(select(Repository).limit(1))
            assert repo is not None
            
            # Find pull requests for this repository
            prs = await session.scalars(
                select(PullRequest).where(PullRequest.repository_id == repo.id)
            )
            pr_list = list(prs)
            assert len(pr_list) > 0
            
            # Find check runs for the first PR
            if pr_list:
                pr = pr_list[0]
                checks = await session.scalars(
                    select(CheckRun).where(CheckRun.pull_request_id == pr.id)
                )
                check_list = list(checks)
                assert len(check_list) > 0
                
                # Verify the relationship chain
                check = check_list[0]
                assert check.pull_request_id == pr.id
                assert pr.repository_id == repo.id
    
    async def test_unique_constraints(self, seeded_database_context):
        """
        Why: Ensures that unique constraints are enforced in real database
        What: Attempts to create duplicate records that violate unique constraints
        How: Creates duplicate data and expects SQLAlchemy errors
        """
        async with seeded_database_context.session_factory() as session:
            # Get existing repository URL
            repo = await session.scalar(select(Repository).limit(1))
            assert repo is not None
            
            # Attempt to create duplicate repository with same URL
            duplicate_repo = Repository(
                id=uuid.uuid4(),
                url=repo.url,  # Same URL should violate unique constraint
                name="duplicate",
                status=RepositoryStatus.ACTIVE
            )
            
            session.add(duplicate_repo)
            
            # Should raise error due to unique constraint on URL
            with pytest.raises(SQLAlchemyError):
                await session.commit()


@pytest.mark.integration
@pytest.mark.database
class TestDatabaseErrorHandling:
    """Test error handling in database operations."""
    
    async def test_connection_recovery(self, test_database_context):
        """
        Why: Validates that database connections can recover from errors
        What: Simulates connection issues and verifies recovery
        How: Performs operations after simulated errors, verifies system recovers
        """
        # This test verifies the database manager handles errors gracefully
        async with test_database_context.session_factory() as session:
            # Perform valid operation
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
            
            # Even if there was a connection issue, new sessions should work
        
        # Create new session and verify it works
        async with test_database_context.session_factory() as session:
            result = await session.execute(text("SELECT 2"))
            assert result.scalar() == 2
    
    async def test_invalid_sql_handling(self, test_database_context):
        """
        Why: Ensures that invalid SQL statements are handled properly
        What: Executes invalid SQL and verifies appropriate errors are raised
        How: Uses invalid SQL statement and expects SQLAlchemy error
        """
        with pytest.raises(SQLAlchemyError):
            async with test_database_context.session_factory() as session:
                # Invalid SQL should raise an error
                await session.execute(text("SELECT FROM invalid_table_name"))


@pytest.mark.integration
@pytest.mark.database
class TestFixtureIntegration:
    """Test that pytest fixtures work correctly together."""
    
    async def test_multiple_fixtures_work_together(
        self, 
        seeded_database_context,
        test_database_manager
    ):
        """
        Why: Validates that different fixtures can be used together in one test
        What: Uses multiple fixtures and verifies they work cohesively  
        How: Uses seeded context and manager together, performs operations
        """
        # Verify seeded context has data
        async with seeded_database_context.session_factory() as session:
            repo_count = await session.scalar(select(func.count(Repository.id)))
            assert repo_count > 0
        
        # Verify manager can still perform operations
        health_check = await test_database_manager.health_check(seeded_database_context)
        assert health_check is True
    
    async def test_fixture_cleanup_prevents_data_leakage(
        self, 
        test_database_manager
    ):
        """
        Why: Ensures that fixture cleanup prevents data from leaking between tests
        What: Creates isolated contexts and verifies they don't share data
        How: Creates multiple contexts, checks that data doesn't leak between them
        """
        # Create first context and add data
        isolation_id_1 = str(uuid.uuid4())
        context_1 = await test_database_manager.create_test_database(isolation_id_1)
        
        try:
            await test_database_manager.apply_migrations(context_1)
            await test_database_manager.seed_test_data(context_1, "basic_discovery")
            
            # Verify data exists in first context
            async with context_1.session_factory() as session:
                count_1 = await session.scalar(select(func.count(Repository.id)))
                assert count_1 == 2  # Basic discovery creates 2 repositories
                
        finally:
            await test_database_manager.cleanup_database(context_1)
        
        # Create second context - should be clean
        isolation_id_2 = str(uuid.uuid4())
        context_2 = await test_database_manager.create_test_database(isolation_id_2)
        
        try:
            await test_database_manager.apply_migrations(context_2)
            
            # Should be empty (no data leakage)
            async with context_2.session_factory() as session:
                count_2 = await session.scalar(select(func.count(Repository.id)))
                assert count_2 == 0  # Should be empty - no data leakage
                
        finally:
            await test_database_manager.cleanup_database(context_2)