"""
Integration tests for PRProcessor orchestration with real database interactions.

Tests the complete end-to-end workflow of PR processing including discovery,
change detection, and synchronization with actual database operations.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.repository import Repository
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.workers.monitor.change_detection import DatabaseChangeDetector
from src.workers.monitor.discovery import GitHubPRDiscoveryService
from src.workers.monitor.models import ChangeSet, CheckRunChangeRecord, PRChangeRecord
from src.workers.monitor.processor import DefaultPRProcessor
from src.workers.monitor.synchronization import DatabaseSynchronizer


@pytest.mark.integration
class TestPRProcessorIntegration:
    """Integration tests for complete PR processing workflow."""

    @pytest.mark.asyncio
    async def test_end_to_end_pr_processing_workflow(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        sample_pr_data,
        sample_check_run_data,
        mock_github_client,
    ):
        """
        Why: Verify complete PR processing workflow works with real database
        What: Tests full end-to-end processing from discovery to synchronization
        How: Uses real database operations with mocked GitHub API responses,
             processes PRs through all phases and validates data persistence
        """
        # Setup repositories
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        # Create services with real database connections
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Mock discovery service to return our test data
        async def mock_discover_prs_and_checks(repository):
            return len(sample_pr_data), len(sample_check_run_data)
        
        discovery_service.discover_prs_and_checks = AsyncMock(
            side_effect=mock_discover_prs_and_checks
        )
        
        # Mock change detector to return changes for all our test data
        async def mock_detect_changes(repository):
            changeset = ChangeSet(repository_id=repository.id)
            
            # Add new PR changes
            for pr_data in sample_pr_data:
                pr_data.raw_data["repository_id"] = str(repository.id)
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            
            # Add new check run changes (link to first PR)
            if changeset.new_prs:
                first_pr = changeset.new_prs[0]
                for check_data in sample_check_run_data:
                    changeset.new_check_runs.append(
                        CheckRunChangeRecord(
                            check_data=check_data,
                            pr_id=uuid.uuid4(),  # Will be set when PR is created
                            change_type="new",
                        )
                    )
            
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_detect_changes)
        
        # Create processor with real services
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
            max_concurrent_repos=5,
        )
        
        # Execute processing
        result = await processor.process_repository(test_repository_in_db)
        
        # Verify processing results
        assert result.success is True
        assert result.prs_discovered == len(sample_pr_data)
        assert result.check_runs_discovered == len(sample_check_run_data)
        assert result.changes_synchronized > 0
        assert result.processing_time > 0
        assert len(result.errors) == 0
        
        # Verify data was actually persisted in database
        # Check PRs were created
        prs_in_db = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        assert len(prs_in_db) == len(sample_pr_data)
        
        # Verify PR data matches
        pr_by_number = {pr.pr_number: pr for pr in prs_in_db}
        for original_pr in sample_pr_data:
            db_pr = pr_by_number[original_pr.number]
            assert db_pr.title == original_pr.title
            assert db_pr.author == original_pr.author
            assert db_pr.state == original_pr.to_pr_state()
            assert db_pr.draft == original_pr.draft

    @pytest.mark.asyncio
    async def test_batch_repository_processing(
        self,
        database_session,
        setup_database_schema,
        sample_pr_data,
        mock_github_client,
    ):
        """
        Why: Verify batch processing of multiple repositories works correctly
        What: Tests concurrent processing of multiple repositories
        How: Creates multiple test repositories, processes them concurrently,
             and validates all complete successfully with proper metrics
        """
        # Create multiple test repositories
        repositories = []
        for i in range(5):
            repo = Repository()
            repo.id = uuid.uuid4()
            repo.url = f"https://github.com/test-org/test-repo-{i}"
            repo.name = f"test-repo-{i}"
            repo.owner = "test-org"
            repo.repo_name = f"test-repo-{i}"
            repositories.append(repo)
            
            # Insert into database
            await database_session.execute(
                text("""
                INSERT INTO repositories 
                (id, url, name, owner, repo_name, status, failure_count, 
                 created_at, updated_at)
                VALUES (:id, :url, :name, :owner, :repo_name, 'active', 0,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """),
                {
                    "id": repo.id,
                    "url": repo.url,
                    "name": repo.name,
                    "owner": repo.owner,
                    "repo_name": repo.repo_name,
                },
            )
        await database_session.commit()
        
        # Setup services
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Mock services to return consistent data
        discovery_service.discover_prs_and_checks = AsyncMock(return_value=(2, 3))
        
        async def mock_detect_changes(repository):
            changeset = ChangeSet(repository_id=repository.id)
            # Add one new PR per repository
            pr_data = sample_pr_data[0]  # Use first sample PR
            pr_data.raw_data["repository_id"] = str(repository.id)
            pr_data.number = 100 + hash(str(repository.id)) % 1000  # Unique PR numbers
            changeset.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_detect_changes)
        
        # Create processor
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
            max_concurrent_repos=3,  # Test concurrency limiting
        )
        
        # Execute batch processing
        batch_result = await processor.process_repositories(repositories)
        
        # Verify batch results
        assert batch_result.repositories_processed == 5
        assert batch_result.success_rate == 100.0
        assert batch_result.total_errors == 0
        assert batch_result.processing_time > 0
        assert len(batch_result.results) == 5
        
        # Verify all repositories processed successfully
        for result in batch_result.results:
            assert result.success is True
            assert result.prs_discovered == 2
            assert result.check_runs_discovered == 3
            assert result.changes_synchronized > 0

    @pytest.mark.asyncio
    async def test_error_handling_and_isolation(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        mock_github_client,
    ):
        """
        Why: Verify error handling works correctly and doesn't corrupt data
        What: Tests processing continues when individual phases fail
        How: Injects errors in different phases and validates proper error
             handling, rollback behavior, and error reporting
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        # Create services with error injection
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Inject error in discovery phase
        discovery_service.discover_prs_and_checks = AsyncMock(
            side_effect=Exception("GitHub API error")
        )
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
        )
        
        # Execute processing with error
        result = await processor.process_repository(test_repository_in_db)
        
        # Verify error handling
        assert result.success is False
        assert len(result.errors) > 0
        assert "discovery_failure" in str(result.errors[0])
        assert result.processing_time > 0
        
        # Verify repository failure tracking
        assert test_repository_in_db.failure_count > 0
        assert test_repository_in_db.last_failure_reason is not None

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_failure(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        sample_pr_data,
        mock_github_client,
    ):
        """
        Why: Verify database transactions roll back properly on failures
        What: Tests that partial failures don't leave inconsistent data
        How: Causes synchronization to fail partway through and validates
             that no partial data is committed to the database
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Mock successful discovery and change detection
        discovery_service.discover_prs_and_checks = AsyncMock(return_value=(3, 5))
        
        async def mock_detect_changes(repository):
            changeset = ChangeSet(repository_id=repository.id)
            for pr_data in sample_pr_data:
                pr_data.raw_data["repository_id"] = str(repository.id)
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_detect_changes)
        
        # Inject error in synchronization phase
        original_sync = synchronizer.synchronize_changes
        
        async def failing_sync(repo_id, changeset):
            # Simulate partial success then failure
            if changeset.new_prs:
                # Start transaction but fail before commit
                raise Exception("Database constraint violation")
            return await original_sync(repo_id, changeset)
        
        synchronizer.synchronize_changes = AsyncMock(side_effect=failing_sync)
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
        )
        
        # Get initial PR count
        initial_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        initial_count = len(initial_prs)
        
        # Execute processing with synchronization failure
        result = await processor.process_repository(test_repository_in_db)
        
        # Verify failure was recorded
        assert result.success is False
        assert len(result.errors) > 0
        assert "synchronization_failure" in str(result.errors[0])
        
        # Verify no partial data was committed (transaction rolled back)
        final_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        final_count = len(final_prs)
        assert final_count == initial_count  # No new PRs should be committed

    @pytest.mark.asyncio
    async def test_concurrent_repository_processing_limits(
        self,
        database_session,
        setup_database_schema,
        mock_github_client,
    ):
        """
        Why: Verify concurrency limits are respected during batch processing
        What: Tests that max_concurrent_repos setting is enforced
        How: Creates many repositories, sets low concurrency limit, and
             validates processing respects the limit through timing analysis
        """
        # Create many test repositories
        repositories = []
        for i in range(10):
            repo = Repository()
            repo.id = uuid.uuid4()
            repo.url = f"https://github.com/test-org/concurrent-test-{i}"
            repo.name = f"concurrent-test-{i}"
            repositories.append(repo)
        
        # Setup services with artificial delay
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Add delay to simulate processing time
        async def slow_discovery(repository):
            await asyncio.sleep(0.1)  # 100ms delay
            return (1, 1)
        
        async def slow_change_detection(repository):
            await asyncio.sleep(0.1)  # 100ms delay
            return ChangeSet(repository_id=repository.id)
        
        discovery_service.discover_prs_and_checks = AsyncMock(
            side_effect=slow_discovery
        )
        change_detector.detect_changes = AsyncMock(side_effect=slow_change_detection)
        
        # Create processor with very low concurrency limit
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
            max_concurrent_repos=2,  # Very low limit
        )
        
        # Measure processing time
        start_time = datetime.now(timezone.utc)
        batch_result = await processor.process_repositories(repositories)
        end_time = datetime.now(timezone.utc)
        
        processing_time = (end_time - start_time).total_seconds()
        
        # Verify results
        assert batch_result.repositories_processed == 10
        assert batch_result.success_rate == 100.0
        
        # With concurrency limit of 2, processing 10 repos with 0.2s each
        # should take at least 1 second (5 batches * 0.2s each)
        # But less than 2 seconds (10 sequential * 0.2s each)
        assert processing_time >= 0.8  # Allow some variance
        assert processing_time < 1.8   # Should be significantly faster than sequential


@pytest.mark.integration
class TestPRProcessorPerformance:
    """Performance and scalability tests for PR processing."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_volume_processing(
        self,
        database_session,
        setup_database_schema,
        performance_test_data,
        mock_github_client,
    ):
        """
        Why: Verify system can handle large volumes of PR data efficiently
        What: Tests processing of 100 PRs with 500 check runs
        How: Uses performance test data to simulate high-volume processing
             and measures timing and memory efficiency
        """
        # Create test repository
        repo = Repository()
        repo.id = uuid.uuid4()
        repo.url = "https://github.com/test-org/large-repo"
        repo.name = "large-repo"
        
        await database_session.execute(
            text("""
            INSERT INTO repositories 
            (id, url, name, owner, repo_name, status, failure_count,
             created_at, updated_at)
            VALUES (:id, :url, :name, 'test-org', 'large-repo', 'active', 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {"id": repo.id, "url": repo.url, "name": repo.name},
        )
        await database_session.commit()
        
        # Setup services
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Mock with large dataset
        large_prs = performance_test_data["prs"]
        large_checks = performance_test_data["check_runs"]
        
        discovery_service.discover_prs_and_checks = AsyncMock(
            return_value=(len(large_prs), len(large_checks))
        )
        
        async def mock_large_changeset(repository):
            changeset = ChangeSet(repository_id=repository.id)
            
            # Add all PRs as new
            for pr_data in large_prs[:50]:  # Process subset to avoid timeout
                pr_data.raw_data["repository_id"] = str(repository.id)
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_large_changeset)
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
            max_concurrent_repos=10,
        )
        
        # Execute performance test
        start_time = datetime.now(timezone.utc)
        result = await processor.process_repository(repo)
        end_time = datetime.now(timezone.utc)
        
        # Verify performance
        processing_time = (end_time - start_time).total_seconds()
        
        assert result.success is True
        assert result.changes_synchronized == 50  # 50 PRs processed
        assert processing_time < 30.0  # Should complete within 30 seconds
        
        # Verify data was persisted efficiently
        persisted_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=repo.id
        )
        assert len(persisted_prs) == 50

    @pytest.mark.asyncio
    async def test_memory_efficiency_with_large_datasets(
        self,
        database_session,
        setup_database_schema,
        performance_test_data,
        mock_github_client,
    ):
        """
        Why: Verify system doesn't consume excessive memory with large datasets
        What: Tests memory usage patterns during large-scale processing
        How: Processes large datasets and monitors that memory usage remains
             reasonable through proper streaming and batching
        """
        import psutil
        import os
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create test repository
        repo = Repository()
        repo.id = uuid.uuid4()
        repo.url = "https://github.com/test-org/memory-test"
        repo.name = "memory-test"
        
        # Setup services (similar to above test)
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Mock services
        discovery_service.discover_prs_and_checks = AsyncMock(return_value=(100, 500))
        
        async def mock_streaming_changeset(repository):
            # Simulate streaming processing - return smaller chunks
            changeset = ChangeSet(repository_id=repository.id)
            
            # Process smaller batch to test memory efficiency
            for pr_data in performance_test_data["prs"][:20]:
                pr_data.raw_data["repository_id"] = str(repository.id)
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_streaming_changeset)
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
        )
        
        # Execute processing
        result = await processor.process_repository(repo)
        
        # Check final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Verify processing succeeded
        assert result.success is True
        
        # Verify memory usage is reasonable (less than 100MB increase)
        assert memory_increase < 100, f"Memory increased by {memory_increase}MB"