#!/usr/bin/env python3
"""
Database Operations Examples

This module demonstrates comprehensive usage of the database API,
including models, repositories, transactions, and connection management.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from src.database.connection import DatabaseManager
from src.database.config import DatabaseConfig
from src.database.transactions import TransactionManager
from src.models import (
    PullRequest, Repository, CheckRun, PRStateHistory,
    PRState, CheckStatus, CheckConclusion, RepositoryStatus, TriggerEvent
)
from src.repositories import (
    PullRequestRepository, RepositoryRepository, CheckRunRepository,
    PRStateHistoryRepository
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseExamples:
    """Examples of database operations and patterns."""
    
    def __init__(self, database_url: str = "sqlite:///./example.db"):
        """Initialize database examples."""
        self.config = DatabaseConfig(
            url=database_url,
            pool_size=5,
            echo=True  # Enable SQL logging for examples
        )
        self.manager = DatabaseManager(self.config)
    
    async def setup_database(self):
        """Setup database and create tables."""
        logger.info("=== Database Setup ===")
        
        try:
            await self.manager.initialize()
            logger.info("Database initialized successfully")
            
            # Create tables if they don't exist
            from src.models.base import Base
            async with self.manager.get_engine().begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Database tables created")
            
        except Exception as e:
            logger.error(f"Database setup failed: {e}")
            raise
    
    async def example_basic_crud_operations(self):
        """Example: Basic CRUD operations with repositories."""
        logger.info("=== Basic CRUD Operations ===")
        
        async with self.manager.get_session() as session:
            try:
                # Create repository instance
                repo_repository = RepositoryRepository(session)
                
                # CREATE: Create a new repository
                repository = await repo_repository.create(
                    name="example-repo",
                    full_name="owner/example-repo",
                    owner="owner",
                    github_id=123456,
                    url="https://github.com/owner/example-repo",
                    status=RepositoryStatus.ACTIVE,
                    repo_metadata={
                        "description": "Example repository for testing",
                        "language": "Python",
                        "stars": 42
                    }
                )
                
                logger.info(f"Created repository: {repository.full_name} (ID: {repository.id})")
                
                # READ: Get repository by ID
                found_repo = await repo_repository.get_by_id(repository.id)
                logger.info(f"Found repository: {found_repo.name}")
                
                # UPDATE: Update repository metadata
                updated_repo = await repo_repository.update(
                    repository,
                    repo_metadata={
                        "description": "Updated description",
                        "language": "Python",
                        "stars": 100
                    }
                )
                logger.info(f"Updated repository stars: {updated_repo.repo_metadata['stars']}")
                
                # LIST: Get all repositories
                all_repos = await repo_repository.list_all(limit=10)
                logger.info(f"Total repositories: {len(all_repos)}")
                
                # DELETE: Delete repository
                deleted = await repo_repository.delete_by_id(repository.id)
                logger.info(f"Repository deleted: {deleted}")
                
                # Commit changes
                await session.commit()
                
            except Exception as e:
                logger.error(f"CRUD operations failed: {e}")
                await session.rollback()
                raise
    
    async def example_pull_request_lifecycle(self):
        """Example: Complete pull request lifecycle."""
        logger.info("=== Pull Request Lifecycle ===")
        
        async with self.manager.get_session() as session:
            try:
                # Create repositories
                repo_repo = RepositoryRepository(session)
                pr_repo = PullRequestRepository(session)
                history_repo = PRStateHistoryRepository(session)
                
                # Create a repository first
                repository = await repo_repo.create(
                    name="test-repo",
                    full_name="owner/test-repo",
                    owner="owner",
                    github_id=789012,
                    url="https://github.com/owner/test-repo",
                    status=RepositoryStatus.ACTIVE
                )
                
                # CREATE: Create a pull request
                pr = await pr_repo.create(
                    repository_id=repository.id,
                    github_id=101,
                    number=1,
                    title="Add new feature",
                    description="This PR adds a new feature to the application",
                    author="developer",
                    state=PRState.OPENED,
                    head_sha="abc123def456",
                    base_sha="def456abc123",
                    pr_metadata={
                        "labels": ["feature", "enhancement"],
                        "reviewers": ["reviewer1", "reviewer2"],
                        "milestone": "v1.0"
                    }
                )
                
                logger.info(f"Created PR #{pr.number}: {pr.title}")
                
                # Create state history for PR opening
                await history_repo.create_transition(
                    pr_id=pr.id,
                    old_state=None,
                    new_state=PRState.OPENED,
                    trigger_event=TriggerEvent.OPENED,
                    triggered_by="developer",
                    metadata={"action": "opened", "initial": True}
                )
                
                # UPDATE: Simulate PR updates
                updated_pr = await pr_repo.update(
                    pr,
                    head_sha="new123sha456",
                    pr_metadata={
                        **pr.pr_metadata,
                        "updated_by": "developer",
                        "last_update_reason": "new commits"
                    }
                )
                
                logger.info(f"Updated PR head SHA: {updated_pr.head_sha}")
                
                # Create state transition for update
                await history_repo.create_transition(
                    pr_id=pr.id,
                    old_state=PRState.OPENED,
                    new_state=PRState.OPENED,
                    trigger_event=TriggerEvent.SYNCHRONIZE,
                    triggered_by="developer",
                    metadata={"new_commits": 3}
                )
                
                # SEARCH: Find PRs by repository
                repo_prs = await pr_repo.get_by_repository_id(repository.id)
                logger.info(f"PRs for repository: {len(repo_prs)}")
                
                # CLOSE: Close the PR
                closed_pr = await pr_repo.update_state(
                    pr.id,
                    PRState.CLOSED,
                    TriggerEvent.CLOSED,
                    metadata={"closure_reason": "completed", "merged": False}
                )
                
                logger.info(f"Closed PR: {closed_pr.state}")
                
                # Get state history
                history = await history_repo.get_history_for_pr(pr.id)
                logger.info(f"PR state history entries: {len(history)}")
                
                for entry in history:
                    logger.info(f"  {entry.old_state} -> {entry.new_state} ({entry.trigger_event})")
                
                await session.commit()
                return pr.id
                
            except Exception as e:
                logger.error(f"PR lifecycle failed: {e}")
                await session.rollback()
                raise
    
    async def example_check_runs_management(self):
        """Example: Managing check runs for pull requests."""
        logger.info("=== Check Runs Management ===")
        
        async with self.manager.get_session() as session:
            try:
                # Setup repositories
                repo_repo = RepositoryRepository(session)
                pr_repo = PullRequestRepository(session)
                check_repo = CheckRunRepository(session)
                
                # Create repository and PR
                repository = await repo_repo.create(
                    name="check-repo",
                    full_name="owner/check-repo",
                    owner="owner",
                    github_id=345678,
                    url="https://github.com/owner/check-repo",
                    status=RepositoryStatus.ACTIVE
                )
                
                pr = await pr_repo.create(
                    repository_id=repository.id,
                    github_id=202,
                    number=2,
                    title="Fix bug in authentication",
                    author="developer",
                    state=PRState.OPENED,
                    head_sha="check123sha",
                    base_sha="base456sha"
                )
                
                # Create multiple check runs
                check_configs = [
                    {
                        "name": "CI Tests",
                        "status": CheckStatus.COMPLETED,
                        "conclusion": CheckConclusion.SUCCESS,
                        "external_id": "ci-123"
                    },
                    {
                        "name": "Linting",
                        "status": CheckStatus.COMPLETED,
                        "conclusion": CheckConclusion.FAILURE,
                        "external_id": "lint-456"
                    },
                    {
                        "name": "Security Scan",
                        "status": CheckStatus.IN_PROGRESS,
                        "conclusion": None,
                        "external_id": "security-789"
                    }
                ]
                
                created_checks = []
                for config in check_configs:
                    check_run = await check_repo.create(
                        pull_request_id=pr.id,
                        name=config["name"],
                        status=config["status"],
                        conclusion=config["conclusion"],
                        external_id=config["external_id"],
                        started_at=datetime.utcnow(),
                        completed_at=datetime.utcnow() if config["status"] == CheckStatus.COMPLETED else None,
                        check_metadata={
                            "url": f"https://example.com/checks/{config['external_id']}",
                            "details": f"Check run for {config['name']}"
                        }
                    )
                    created_checks.append(check_run)
                    logger.info(f"Created check: {check_run.name} - {check_run.status}")
                
                # Query check runs
                pr_checks = await check_repo.get_by_pull_request_id(pr.id)
                logger.info(f"Total checks for PR: {len(pr_checks)}")
                
                # Get failed checks
                failed_checks = await check_repo.get_failed_checks(pr.id)
                logger.info(f"Failed checks: {len(failed_checks)}")
                
                for check in failed_checks:
                    logger.info(f"  Failed: {check.name} - {check.conclusion}")
                
                # Update check run (complete security scan)
                security_check = next(c for c in created_checks if c.name == "Security Scan")
                updated_check = await check_repo.update(
                    security_check,
                    status=CheckStatus.COMPLETED,
                    conclusion=CheckConclusion.SUCCESS,
                    completed_at=datetime.utcnow(),
                    check_metadata={
                        **security_check.check_metadata,
                        "vulnerabilities_found": 0,
                        "scan_duration": "45s"
                    }
                )
                logger.info(f"Updated security check: {updated_check.conclusion}")
                
                # Get check run statistics
                stats = await check_repo.get_check_run_statistics(pr.id)
                logger.info(f"Check statistics: {stats}")
                
                await session.commit()
                
            except Exception as e:
                logger.error(f"Check runs management failed: {e}")
                await session.rollback()
                raise
    
    async def example_complex_queries(self):
        """Example: Complex database queries and aggregations."""
        logger.info("=== Complex Queries ===")
        
        async with self.manager.get_session() as session:
            try:
                pr_repo = PullRequestRepository(session)
                history_repo = PRStateHistoryRepository(session)
                
                # Get PR statistics
                total_prs = await pr_repo.count_all()
                logger.info(f"Total PRs in database: {total_prs}")
                
                # Get PRs by state
                for state in PRState:
                    count = await pr_repo.count_by_state(state)
                    logger.info(f"PRs in {state}: {count}")
                
                # Get recent activity
                since = datetime.utcnow() - timedelta(days=7)
                recent_prs = await pr_repo.get_recent_activity(since=since, limit=5)
                logger.info(f"Recent PRs (last 7 days): {len(recent_prs)}")
                
                # Get state transition statistics
                if total_prs > 0:
                    transition_stats = await history_repo.get_transition_statistics(
                        since=since
                    )
                    logger.info("State transition statistics:")
                    for state, count in transition_stats.items():
                        logger.info(f"  {state}: {count}")
                
                # Get PRs with failed checks
                prs_with_failed_checks = await pr_repo.get_prs_with_failed_checks()
                logger.info(f"PRs with failed checks: {len(prs_with_failed_checks)}")
                
            except Exception as e:
                logger.error(f"Complex queries failed: {e}")
                raise
    
    async def example_transaction_management(self):
        """Example: Transaction management and error handling."""
        logger.info("=== Transaction Management ===")
        
        try:
            # Example 1: Successful transaction
            async with self.manager.get_session() as session:
                repo_repo = RepositoryRepository(session)
                pr_repo = PullRequestRepository(session)
                
                # Create repository and PR in same transaction
                repository = await repo_repo.create(
                    name="transaction-repo",
                    full_name="owner/transaction-repo",
                    owner="owner",
                    github_id=999999,
                    url="https://github.com/owner/transaction-repo",
                    status=RepositoryStatus.ACTIVE
                )
                
                pr = await pr_repo.create(
                    repository_id=repository.id,
                    github_id=999,
                    number=999,
                    title="Transaction test PR",
                    author="test-user",
                    state=PRState.OPENED,
                    head_sha="transaction123",
                    base_sha="base123"
                )
                
                # Commit transaction
                await session.commit()
                logger.info("Transaction committed successfully")
            
            # Example 2: Transaction rollback on error
            try:
                async with self.manager.get_session() as session:
                    repo_repo = RepositoryRepository(session)
                    
                    # Create repository
                    repository = await repo_repo.create(
                        name="rollback-repo",
                        full_name="owner/rollback-repo",
                        owner="owner",
                        github_id=888888,
                        url="https://github.com/owner/rollback-repo",
                        status=RepositoryStatus.ACTIVE
                    )
                    
                    # Simulate error
                    raise ValueError("Simulated error for rollback")
                    
            except ValueError:
                logger.info("Transaction rolled back due to error (expected)")
            
            # Verify rollback worked - repository should not exist
            async with self.manager.get_session() as session:
                repo_repo = RepositoryRepository(session)
                repos = await repo_repo.get_by_name("rollback-repo")
                logger.info(f"Repositories with rollback name: {len(repos)}")
            
        except Exception as e:
            logger.error(f"Transaction management failed: {e}")
            raise
    
    async def example_connection_management(self):
        """Example: Connection management and health checks."""
        logger.info("=== Connection Management ===")
        
        try:
            # Check database health
            is_healthy = await self.manager.health_check()
            logger.info(f"Database health: {'OK' if is_healthy else 'FAILED'}")
            
            # Get connection pool info
            pool_info = self.manager.get_pool_info()
            logger.info(f"Connection pool info: {pool_info}")
            
            # Test multiple concurrent connections
            async def test_connection(conn_id: int):
                async with self.manager.get_session() as session:
                    repo_repo = RepositoryRepository(session)
                    count = await repo_repo.count_all()
                    logger.info(f"Connection {conn_id}: found {count} repositories")
                    await asyncio.sleep(0.1)  # Simulate work
            
            # Run concurrent connections
            tasks = [test_connection(i) for i in range(3)]
            await asyncio.gather(*tasks)
            
            logger.info("Concurrent connections test completed")
            
        except Exception as e:
            logger.error(f"Connection management failed: {e}")
            raise
    
    async def example_performance_optimization(self):
        """Example: Performance optimization techniques."""
        logger.info("=== Performance Optimization ===")
        
        async with self.manager.get_session() as session:
            try:
                pr_repo = PullRequestRepository(session)
                
                # Example 1: Batch operations
                batch_data = []
                for i in range(5):
                    batch_data.append({
                        "repository_id": uuid.uuid4(),  # Would be real repo ID
                        "github_id": 1000 + i,
                        "number": 100 + i,
                        "title": f"Batch PR {i}",
                        "author": "batch-user",
                        "state": PRState.OPENED,
                        "head_sha": f"sha{i}",
                        "base_sha": "base"
                    })
                
                # Note: In real implementation, you'd create a batch_create method
                logger.info(f"Prepared {len(batch_data)} items for batch operation")
                
                # Example 2: Pagination for large datasets
                page_size = 10
                page = 0
                
                while True:
                    prs = await pr_repo.list_all(
                        limit=page_size,
                        offset=page * page_size
                    )
                    
                    if not prs:
                        break
                    
                    logger.info(f"Processed page {page + 1} with {len(prs)} PRs")
                    page += 1
                    
                    if page >= 3:  # Limit for example
                        break
                
                # Example 3: Selective field loading (would need custom query)
                logger.info("Performance optimization examples completed")
                
            except Exception as e:
                logger.error(f"Performance optimization failed: {e}")
                raise
    
    async def cleanup_database(self):
        """Clean up database resources."""
        logger.info("=== Database Cleanup ===")
        
        try:
            await self.manager.close()
            logger.info("Database connections closed")
            
        except Exception as e:
            logger.error(f"Database cleanup failed: {e}")


async def comprehensive_database_example():
    """Comprehensive example demonstrating all database patterns."""
    # Use in-memory SQLite for examples
    examples = DatabaseExamples("sqlite:///./database_examples.db")
    
    try:
        await examples.setup_database()
        await examples.example_basic_crud_operations()
        pr_id = await examples.example_pull_request_lifecycle()
        await examples.example_check_runs_management()
        await examples.example_complex_queries()
        await examples.example_transaction_management()
        await examples.example_connection_management()
        await examples.example_performance_optimization()
        
        logger.info("All database examples completed successfully!")
        
    except Exception as e:
        logger.error(f"Database examples failed: {e}")
    
    finally:
        await examples.cleanup_database()


if __name__ == "__main__":
    # Run comprehensive examples
    asyncio.run(comprehensive_database_example())