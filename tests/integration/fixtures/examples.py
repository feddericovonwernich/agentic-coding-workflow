"""Example integration tests demonstrating TestDatabaseManager usage.

This module provides comprehensive examples showing how to use the TestDatabaseManager
for real integration testing scenarios, following the architectural patterns.
"""

import pytest
import pytest_asyncio
import uuid
from typing import List

from sqlalchemy import select
from src.models.repository import Repository
from src.models.pull_request import PullRequest
from src.models.check_run import CheckRun
from src.models.enums import RepositoryStatus, PRState

# Import fixtures individually to avoid circular imports
try:
    from tests.integration.fixtures.database import (
        RealTestDatabaseManager,
        get_test_database_manager,
        reset_test_database_manager,
        TestDatabaseContext
    )
    # Define fixture-like functions for testing
    test_database_manager = None  # Will be used as fixture
    test_database_context = None  # Will be used as fixture  
    seeded_database_context = None  # Will be used as fixture
    performance_metrics_collector = None  # Will be used as fixture
except ImportError:
    # Fallback definitions
    pass
from tests.integration.fixtures.assertions import DatabaseTestAssertions


@pytest.mark.integration
@pytest.mark.database
class ExampleDatabaseIntegrationTests:
    """Example integration tests showing TestDatabaseManager usage patterns."""
    
    async def test_complete_workflow_example(self, test_database_manager):
        """
        Why: Demonstrates complete workflow from database creation to cleanup
        What: Shows full lifecycle of database testing with real operations
        How: Creates database, applies migrations, seeds data, performs operations, cleanup
        """
        # Step 1: Create isolated test database
        isolation_id = str(uuid.uuid4())
        context = await test_database_manager.create_test_database(isolation_id)
        
        try:
            # Step 2: Apply database migrations
            await test_database_manager.apply_migrations(context)
            
            # Step 3: Seed with test data
            created_ids = await test_database_manager.seed_test_data(
                context, "basic_discovery"
            )
            
            # Step 4: Perform integration test operations
            async with context.session_factory() as session:
                # Query repositories
                repos = await session.scalars(select(Repository))
                repo_list = list(repos)
                assert len(repo_list) == 2
                
                # Create additional test data
                new_repo = Repository(
                    id=uuid.uuid4(),
                    url="https://github.com/test/new-repo",
                    name="test/new-repo",
                    status=RepositoryStatus.ACTIVE
                )
                session.add(new_repo)
                await session.commit()
                
                # Verify new data exists
                all_repos = await session.scalars(select(Repository))
                all_repo_list = list(all_repos)
                assert len(all_repo_list) == 3  # 2 seeded + 1 new
            
            # Step 5: Get performance metrics
            metrics = test_database_manager.get_performance_metrics(isolation_id)
            if metrics:
                assert metrics.database_operations > 0
                
        finally:
            # Step 6: Cleanup database
            await test_database_manager.cleanup_database(context)
    
    async def test_using_fixtures_example(self, seeded_database_context):
        """
        Why: Shows how to use pre-configured fixtures for simpler test setup
        What: Demonstrates using seeded_database_context fixture
        How: Uses fixture, performs queries, validates expected seeded data
        """
        # Context is already created, migrated, and seeded with basic data
        async with seeded_database_context.session_factory() as session:
            # Query seeded repositories
            repos = await session.scalars(
                select(Repository).where(Repository.status == RepositoryStatus.ACTIVE)
            )
            active_repos = list(repos)
            assert len(active_repos) == 2  # Basic discovery seeds 2 active repos
            
            # Query seeded pull requests  
            prs = await session.scalars(select(PullRequest))
            pr_list = list(prs)
            assert len(pr_list) == 2  # 1 PR per repository
            
            # Verify relationships
            for pr in pr_list:
                repo = await session.get(Repository, pr.repository_id)
                assert repo is not None
                assert pr.repository_id == repo.id
    
    async def test_performance_monitoring_example(self, performance_metrics_collector):
        """
        Why: Demonstrates how to use performance monitoring in integration tests
        What: Shows performance metrics collection during database operations  
        How: Uses performance collector, runs operations, analyzes metrics
        """
        context, get_metrics = performance_metrics_collector
        
        # Perform database operations that will be monitored
        async with context.session_factory() as session:
            # Create multiple repositories to generate more database activity
            repos_to_create = []
            for i in range(10):
                repo = Repository(
                    id=uuid.uuid4(),
                    url=f"https://github.com/test/perf-repo-{i}",
                    name=f"test/perf-repo-{i}",
                    status=RepositoryStatus.ACTIVE
                )
                repos_to_create.append(repo)
            
            # Bulk add repositories
            session.add_all(repos_to_create)
            await session.commit()
            
            # Perform queries
            for _ in range(5):
                repos = await session.scalars(select(Repository).limit(5))
                list(repos)  # Consume the result
        
        # Analyze performance metrics
        metrics = get_metrics()
        if metrics:
            # Verify significant database activity was recorded
            assert metrics.database_operations >= 10  # Inserts + queries
            assert metrics.database_operation_time_ms > 0
            assert metrics.total_test_time_ms > 0
            
            # Log performance for analysis
            print(f"Database operations: {metrics.database_operations}")
            print(f"Database time: {metrics.database_operation_time_ms}ms")
            print(f"Operations per second: {metrics.database_ops_per_second}")
    
    async def test_error_handling_example(self, test_database_context):
        """
        Why: Shows how to test error conditions and recovery with real database
        What: Demonstrates error handling patterns in integration tests
        How: Creates error conditions, verifies proper error handling and recovery
        """
        # Test transaction rollback on error
        original_count = 0
        async with test_database_context.session_factory() as session:
            result = await session.scalars(select(Repository))
            original_count = len(list(result))
        
        # Attempt operation that will fail
        try:
            async with test_database_context.session_factory() as session:
                # Add a repository
                repo = Repository(
                    id=uuid.uuid4(),
                    url="https://github.com/test/error-test",
                    name="test/error-test",
                    status=RepositoryStatus.ACTIVE
                )
                session.add(repo)
                await session.flush()  # Flush to database but don't commit
                
                # Simulate error condition
                raise RuntimeError("Simulated error for testing")
                
        except RuntimeError:
            # Expected error occurred
            pass
        
        # Verify transaction was rolled back
        async with test_database_context.session_factory() as session:
            result = await session.scalars(select(Repository))
            final_count = len(list(result))
            assert final_count == original_count  # No change due to rollback
    
    async def test_data_assertions_example(self, seeded_database_context):
        """
        Why: Demonstrates using database test assertions for validation
        What: Shows how to use DatabaseTestAssertions for comprehensive validation
        How: Uses assertion utilities to validate database state and relationships
        """
        assertions = DatabaseTestAssertions()
        
        # Assert overall database state
        expected_state = {
            "repository_count": 2,
            "pull_request_count": 2, 
            "check_run_count": 2,
            "active_repositories": 2,
            "failed_check_runs": 0  # Basic discovery creates successful checks
        }
        
        await assertions.assert_database_state(seeded_database_context, expected_state)
        
        # Verify specific relationships
        async with seeded_database_context.session_factory() as session:
            # Get repository and PR data for relationship testing
            repos = await session.scalars(select(Repository))
            repo_list = list(repos)
            
            expected_relationships = {}
            for repo in repo_list:
                expected_relationships[repo.id] = 1  # Each repo should have 1 PR
            
            await assertions._assert_pr_repository_relationships(
                session, expected_relationships
            )
    
    async def test_complex_scenario_example(self, test_database_manager):
        """
        Why: Shows complex integration testing scenario with multiple phases
        What: Demonstrates multi-phase testing with different data scenarios
        How: Creates multiple contexts, seeds different scenarios, compares results
        """
        # Phase 1: Test with basic scenario
        basic_context = await test_database_manager.create_test_database("basic_test")
        try:
            await test_database_manager.apply_migrations(basic_context)
            await test_database_manager.seed_test_data(basic_context, "basic_discovery")
            
            # Collect basic metrics
            async with basic_context.session_factory() as session:
                basic_repo_count = len(list(await session.scalars(select(Repository))))
                basic_pr_count = len(list(await session.scalars(select(PullRequest))))
            
        finally:
            await test_database_manager.cleanup_database(basic_context)
        
        # Phase 2: Test with error conditions scenario
        error_context = await test_database_manager.create_test_database("error_test")
        try:
            await test_database_manager.apply_migrations(error_context)
            await test_database_manager.seed_test_data(error_context, "error_conditions")
            
            # Collect error scenario metrics
            async with error_context.session_factory() as session:
                error_repos = await session.scalars(
                    select(Repository).where(Repository.status == RepositoryStatus.ERROR)
                )
                error_repo_count = len(list(error_repos))
                
                failed_checks = await session.scalars(
                    select(CheckRun).where(CheckRun.conclusion == "failure")
                )
                failed_check_count = len(list(failed_checks))
            
        finally:
            await test_database_manager.cleanup_database(error_context)
        
        # Phase 3: Compare results
        assert basic_repo_count == 2  # Basic scenario
        assert basic_pr_count == 2
        assert error_repo_count >= 1  # Error scenario should have error repositories
        assert failed_check_count >= 1  # Error scenario should have failed checks
        
        # Verify scenarios are truly isolated
        assert basic_repo_count != error_repo_count or basic_pr_count != failed_check_count


@pytest.mark.integration
@pytest.mark.database
@pytest.mark.slow
class ExamplePerformanceIntegrationTests:
    """Examples of performance-focused integration tests."""
    
    async def test_large_dataset_performance_example(self, test_database_manager):
        """
        Why: Demonstrates performance testing with large datasets
        What: Tests database performance with bulk operations and large record counts
        How: Creates large dataset, measures operations, validates performance targets
        """
        isolation_id = str(uuid.uuid4())
        context = await test_database_manager.create_test_database(isolation_id)
        
        try:
            await test_database_manager.apply_migrations(context)
            
            # Seed large dataset
            await test_database_manager.seed_test_data(context, "large_repository")
            
            # Perform performance test operations
            async with context.session_factory() as session:
                # Test bulk query performance
                all_prs = await session.scalars(select(PullRequest))
                pr_list = list(all_prs)
                assert len(pr_list) == 50  # Large dataset has 50 PRs
                
                # Test filtered query performance  
                active_repos = await session.scalars(
                    select(Repository).where(Repository.status == RepositoryStatus.ACTIVE)
                )
                active_repo_list = list(active_repos)
                assert len(active_repo_list) == 1  # Large dataset has 1 active repo
            
            # Validate performance metrics
            metrics = test_database_manager.get_performance_metrics(isolation_id)
            if metrics:
                # Performance targets for large dataset
                performance_targets = {
                    "max_test_time_ms": 30000,  # 30 seconds max
                    "db_ops_per_second": 10,    # At least 10 ops/second
                }
                
                assertions = DatabaseTestAssertions()
                await assertions.assert_performance_metrics(metrics, performance_targets)
                
        finally:
            await test_database_manager.cleanup_database(context)
    
    async def test_concurrent_access_example(self, test_database_manager):
        """
        Why: Shows how to test concurrent database access scenarios
        What: Tests multiple concurrent database operations for race conditions
        How: Creates multiple sessions, performs concurrent operations, validates results
        """
        isolation_id = str(uuid.uuid4())
        context = await test_database_manager.create_test_database(isolation_id)
        
        try:
            await test_database_manager.apply_migrations(context)
            await test_database_manager.seed_test_data(context, "basic_discovery")
            
            # Simulate concurrent database operations
            import asyncio
            
            async def concurrent_operation(repo_suffix: str):
                async with context.session_factory() as session:
                    # Each concurrent operation creates a repository
                    repo = Repository(
                        id=uuid.uuid4(),
                        url=f"https://github.com/test/concurrent-{repo_suffix}",
                        name=f"test/concurrent-{repo_suffix}",
                        status=RepositoryStatus.ACTIVE
                    )
                    session.add(repo)
                    await session.commit()
                    return repo.id
            
            # Run 5 concurrent operations
            tasks = [
                concurrent_operation(f"repo-{i}") 
                for i in range(5)
            ]
            repo_ids = await asyncio.gather(*tasks)
            
            # Verify all operations completed successfully
            assert len(repo_ids) == 5
            assert len(set(repo_ids)) == 5  # All IDs should be unique
            
            # Verify all repositories exist in database
            async with context.session_factory() as session:
                total_repos = await session.scalars(select(Repository))
                total_count = len(list(total_repos))
                assert total_count == 7  # 2 seeded + 5 concurrent
                
        finally:
            await test_database_manager.cleanup_database(context)


# Export example classes
__all__ = [
    "ExampleDatabaseIntegrationTests",
    "ExamplePerformanceIntegrationTests"
]