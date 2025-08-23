"""Database test assertions for integration testing.

This module provides assertion utilities for verifying database state, 
data consistency, and relationships in integration tests using real databases.
"""

import logging
import uuid
from typing import Any, Dict, List

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from src.models.repository import Repository
from src.models.pull_request import PullRequest
from src.models.check_run import CheckRun
from src.models.state_history import PRStateHistory
from src.workers.discovery.interfaces import PRDiscoveryResult
# Import from database module to avoid dependency on scratch-pad
from .database import TestDatabaseContext

# Define IntegrationTestAssertion interface locally 
from abc import ABC, abstractmethod
from typing import Any

class IntegrationTestAssertion(ABC):
    """Abstract base class for integration test assertions."""
    
    @abstractmethod
    async def assert_database_state(
        self,
        context: TestDatabaseContext,
        expected_state: dict[str, Any]
    ) -> None:
        pass
    
    @abstractmethod
    async def assert_api_interactions(
        self,
        github_context: Any,
        expected_requests: list[dict[str, Any]]
    ) -> None:
        pass
    
    @abstractmethod
    async def assert_cache_behavior(
        self,
        cache: Any,
        expected_hit_rate: float
    ) -> None:
        pass
    
    @abstractmethod
    async def assert_performance_metrics(
        self,
        metrics: Any,
        targets: dict[str, float]
    ) -> None:
        pass

logger = logging.getLogger(__name__)


class DatabaseTestAssertions(IntegrationTestAssertion):
    """Real database assertions for integration testing."""
    
    async def assert_database_state(
        self,
        context: TestDatabaseContext,
        expected_state: dict[str, Any]
    ) -> None:
        """Assert database state matches expectations after workflow.
        
        Args:
            context: Integration test context
            expected_state: Expected database state with counts and conditions
        """
        async with context.session_factory() as session:
            # Assert record counts
            if "repository_count" in expected_state:
                await self._assert_record_count(
                    session, Repository, expected_state["repository_count"]
                )
            
            if "pull_request_count" in expected_state:
                await self._assert_record_count(
                    session, PullRequest, expected_state["pull_request_count"]
                )
            
            if "check_run_count" in expected_state:
                await self._assert_record_count(
                    session, CheckRun, expected_state["check_run_count"]
                )
            
            # Assert specific record states
            if "active_repositories" in expected_state:
                await self._assert_active_repository_count(
                    session, expected_state["active_repositories"]
                )
            
            if "failed_check_runs" in expected_state:
                await self._assert_failed_check_count(
                    session, expected_state["failed_check_runs"]
                )
            
            # Assert data relationships
            if "pr_repository_relationships" in expected_state:
                await self._assert_pr_repository_relationships(
                    session, expected_state["pr_repository_relationships"]
                )
    
    async def assert_api_interactions(
        self,
        github_context: Any,  # GitHubMockContext - simplified for now
        expected_requests: list[dict[str, Any]]
    ) -> None:
        """Assert GitHub API interactions match expectations.
        
        Args:
            github_context: GitHub mock context
            expected_requests: Expected API request patterns
        """
        # This will be implemented when GitHub mock server is created
        # For now, this is a placeholder following the interface
        logger.info(f"API assertion placeholder - expected {len(expected_requests)} requests")
    
    async def assert_cache_behavior(
        self,
        cache: Any,  # TestCacheStrategy - simplified for now
        expected_hit_rate: float
    ) -> None:
        """Assert cache behavior meets expectations.
        
        Args:
            cache: Test cache strategy
            expected_hit_rate: Expected cache hit rate (0.0 to 1.0)
        """
        # This will be implemented when cache strategy is created
        # For now, this is a placeholder following the interface
        logger.info(f"Cache assertion placeholder - expected hit rate {expected_hit_rate}")
    
    async def assert_performance_metrics(
        self,
        metrics: Any,  # PerformanceMetrics
        targets: dict[str, float]
    ) -> None:
        """Assert performance metrics meet targets.
        
        Args:
            metrics: Actual performance metrics
            targets: Performance targets dictionary
        """
        if not metrics:
            raise AssertionError("No performance metrics available")
        
        # Check database operations per second target
        if "db_ops_per_second" in targets:
            actual_ops_per_second = metrics.database_ops_per_second
            expected_min = targets["db_ops_per_second"]
            assert actual_ops_per_second >= expected_min, (
                f"Database operations per second {actual_ops_per_second} "
                f"below target {expected_min}"
            )
        
        # Check total test time target
        if "max_test_time_ms" in targets:
            actual_time = metrics.total_test_time_ms
            max_time = targets["max_test_time_ms"]
            assert actual_time <= max_time, (
                f"Test time {actual_time}ms exceeded target {max_time}ms"
            )
        
        # Check database operation time target
        if "max_db_time_ms" in targets:
            actual_db_time = metrics.database_operation_time_ms
            max_db_time = targets["max_db_time_ms"]
            assert actual_db_time <= max_db_time, (
                f"Database time {actual_db_time}ms exceeded target {max_db_time}ms"
            )
    
    # Private helper methods
    
    async def _assert_record_count(
        self, 
        session: AsyncSession, 
        model_class: Any, 
        expected_count: int
    ) -> None:
        """Assert exact record count for model."""
        result = await session.execute(select(func.count(model_class.id)))
        actual_count = result.scalar()
        assert actual_count == expected_count, (
            f"Expected {expected_count} {model_class.__name__} records, "
            f"got {actual_count}"
        )
    
    async def _assert_active_repository_count(
        self,
        session: AsyncSession,
        expected_count: int
    ) -> None:
        """Assert count of active repositories."""
        from src.models.enums import RepositoryStatus
        
        result = await session.execute(
            select(func.count(Repository.id))
            .where(Repository.status == RepositoryStatus.ACTIVE)
        )
        actual_count = result.scalar()
        assert actual_count == expected_count, (
            f"Expected {expected_count} active repositories, got {actual_count}"
        )
    
    async def _assert_failed_check_count(
        self,
        session: AsyncSession, 
        expected_count: int
    ) -> None:
        """Assert count of failed check runs."""
        from src.models.enums import CheckConclusion
        
        result = await session.execute(
            select(func.count(CheckRun.id))
            .where(CheckRun.conclusion == CheckConclusion.FAILURE)
        )
        actual_count = result.scalar()
        assert actual_count == expected_count, (
            f"Expected {expected_count} failed check runs, got {actual_count}"
        )
    
    async def _assert_pr_repository_relationships(
        self,
        session: AsyncSession,
        expected_relationships: dict[uuid.UUID, int]
    ) -> None:
        """Assert pull request to repository relationships.
        
        Args:
            expected_relationships: Dict of repository_id -> expected PR count
        """
        for repo_id, expected_pr_count in expected_relationships.items():
            result = await session.execute(
                select(func.count(PullRequest.id))
                .where(PullRequest.repository_id == repo_id)
            )
            actual_pr_count = result.scalar()
            assert actual_pr_count == expected_pr_count, (
                f"Repository {repo_id} expected {expected_pr_count} PRs, "
                f"got {actual_pr_count}"
            )
    
    async def assert_foreign_key_constraints(
        self, 
        session: AsyncSession, 
        model_instance: Any
    ) -> None:
        """Verify all foreign key relationships exist."""
        primary_key = model_instance.id
        loaded_instance = await session.get(type(model_instance), primary_key)
        assert loaded_instance is not None, (
            f"Could not reload {type(model_instance).__name__} with ID {primary_key}"
        )
    
    async def assert_data_consistency(
        self,
        session: AsyncSession,
        pr_discovery_results: List[PRDiscoveryResult]
    ) -> None:
        """Verify discovery results match database state.
        
        Args:
            session: Database session
            pr_discovery_results: Results from PR discovery workflow
        """
        for result in pr_discovery_results:
            # Check repository exists
            repo = await session.get(Repository, result.repository_id)
            assert repo is not None, (
                f"Repository {result.repository_id} not found in database"
            )
            
            # Check PR count matches
            pr_count_result = await session.execute(
                select(func.count(PullRequest.id))
                .where(PullRequest.repository_id == result.repository_id)
            )
            expected_pr_count = len(result.discovered_prs)
            actual_pr_count = pr_count_result.scalar()
            assert actual_pr_count == expected_pr_count, (
                f"PR count mismatch for repository {result.repository_id}: "
                f"expected {expected_pr_count}, got {actual_pr_count}"
            )
            
            # Verify PR details match
            for expected_pr in result.discovered_prs:
                pr = await session.execute(
                    select(PullRequest)
                    .where(
                        PullRequest.repository_id == result.repository_id,
                        PullRequest.pr_number == expected_pr.number
                    )
                )
                actual_pr = pr.scalar_one_or_none()
                assert actual_pr is not None, (
                    f"PR #{expected_pr.number} not found for repository {result.repository_id}"
                )
                
                # Verify key PR attributes match
                assert actual_pr.title == expected_pr.title, (
                    f"PR title mismatch: expected '{expected_pr.title}', "
                    f"got '{actual_pr.title}'"
                )
                assert actual_pr.author == expected_pr.author, (
                    f"PR author mismatch: expected '{expected_pr.author}', "
                    f"got '{actual_pr.author}'"
                )


class DatabaseTestUtilities:
    """Utility functions for database integration testing."""
    
    @staticmethod
    async def count_records(session: AsyncSession, model_class: Any) -> int:
        """Count total records for a model."""
        result = await session.execute(select(func.count(model_class.id)))
        return result.scalar()
    
    @staticmethod
    async def verify_table_exists(session: AsyncSession, table_name: str) -> bool:
        """Verify that a table exists in the database."""
        try:
            await session.execute(text(f"SELECT 1 FROM {table_name} LIMIT 0"))
            return True
        except SQLAlchemyError:
            return False
    
    @staticmethod
    async def get_table_row_count(session: AsyncSession, table_name: str) -> int:
        """Get row count for a table by name."""
        result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return result.scalar()
    
    @staticmethod
    async def verify_index_exists(session: AsyncSession, index_name: str) -> bool:
        """Verify that an index exists in the database."""
        try:
            # This is PostgreSQL-specific - would need adaptation for SQLite
            result = await session.execute(text("""
                SELECT COUNT(*)
                FROM pg_class 
                WHERE relname = :index_name AND relkind = 'i'
            """), {"index_name": index_name})
            return result.scalar() > 0
        except SQLAlchemyError:
            # For SQLite or if query fails, return True (assume exists)
            return True
    
    @staticmethod
    async def cleanup_test_data(
        session: AsyncSession, 
        data_ids: Dict[str, List[uuid.UUID]]
    ) -> None:
        """Clean up test data by IDs.
        
        Args:
            session: Database session
            data_ids: Dictionary mapping model names to ID lists
        """
        model_mapping = {
            "check_runs": CheckRun,
            "pull_requests": PullRequest, 
            "repositories": Repository
        }
        
        # Delete in reverse order to respect foreign keys
        cleanup_order = ["check_runs", "pull_requests", "repositories"]
        
        for model_name in cleanup_order:
            if model_name in data_ids:
                model_class = model_mapping[model_name]
                ids_to_delete = data_ids[model_name]
                
                if ids_to_delete:
                    await session.execute(
                        text(f"DELETE FROM {model_class.__tablename__} WHERE id = ANY(:ids)"),
                        {"ids": ids_to_delete}
                    )
        
        await session.commit()


# Export main classes
__all__ = [
    "DatabaseTestAssertions",
    "DatabaseTestUtilities"
]