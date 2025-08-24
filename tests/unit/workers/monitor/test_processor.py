"""Unit tests for PR processor orchestration.

This module tests the core PRProcessor class that orchestrates the entire
processing flow for discovering and processing pull requests from GitHub repositories.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.enums import RepositoryStatus
from src.models.repository import Repository
from src.workers.monitor.models import (
    BatchProcessingResult,
    ChangeSet,
    PRChangeRecord,
    PRData,
    ProcessingResult,
)
from src.workers.monitor.processor import DefaultPRProcessor


class TestDefaultPRProcessor:
    """Tests for DefaultPRProcessor class."""

    @pytest.fixture
    def mock_discovery_service(self):
        """
        Why: Need isolated testing of processor logic without external dependencies
        What: Creates mock PR discovery service for testing
        How: Uses AsyncMock to simulate service interface
        """
        mock = AsyncMock()
        mock.discover_prs_and_checks.return_value = (5, 12)  # 5 PRs, 12 check runs
        return mock

    @pytest.fixture
    def mock_change_detection_service(self):
        """
        Why: Need isolated testing of change detection coordination
        What: Creates mock change detection service for testing
        How: Uses AsyncMock with default empty changeset
        """
        mock = AsyncMock()
        changeset = ChangeSet(repository_id=uuid.uuid4())
        mock.detect_changes.return_value = changeset
        return mock

    @pytest.fixture
    def mock_synchronization_service(self):
        """
        Why: Need isolated testing of synchronization coordination
        What: Creates mock synchronization service for testing
        How: Uses AsyncMock returning successful synchronization count
        """
        mock = AsyncMock()
        mock.synchronize_changes.return_value = 3  # 3 changes synchronized
        return mock

    @pytest.fixture
    def processor(
        self,
        mock_discovery_service,
        mock_change_detection_service,
        mock_synchronization_service,
    ):
        """
        Why: Need configured processor instance for testing
        What: Creates DefaultPRProcessor with all mocked dependencies
        How: Injects all mock services into processor constructor
        """
        return DefaultPRProcessor(
            discovery_service=mock_discovery_service,
            change_detection_service=mock_change_detection_service,
            synchronization_service=mock_synchronization_service,
            max_concurrent_repos=5,
        )

    @pytest.fixture
    def sample_repository(self):
        """
        Why: Need consistent repository model for testing
        What: Creates sample Repository instance with required fields
        How: Uses Repository model with test data
        """
        repo = Repository()
        repo.id = uuid.uuid4()
        repo.url = "https://github.com/test/repo"
        repo.name = "test-repo"
        repo.status = RepositoryStatus.ACTIVE
        repo.failure_count = 0
        return repo

    @pytest.fixture
    def sample_changeset_with_changes(self, sample_repository):
        """
        Why: Need changeset with actual changes for testing synchronization
        What: Creates ChangeSet with sample PR changes
        How: Populates changeset with mock PRChangeRecord data
        """
        changeset = ChangeSet(repository_id=sample_repository.id)

        # Add sample PR changes
        pr_data = PRData(
            number=1,
            title="Test PR",
            author="test-user",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature",
            base_sha="abc123",
            head_sha="def456",
            url="https://github.com/test/repo/pull/1",
        )

        changeset.new_prs.append(PRChangeRecord(pr_data=pr_data, change_type="new"))
        changeset.updated_prs.append(
            PRChangeRecord(
                pr_data=pr_data, change_type="updated", existing_pr_id=uuid.uuid4()
            )
        )

        return changeset

    async def test_process_repository_success(
        self,
        processor,
        sample_repository,
        mock_change_detection_service,
        sample_changeset_with_changes,
    ):
        """
        Why: Verify successful repository processing flow and metrics collection
        What: Tests complete processing workflow with all phases successful
        How: Mocks all services to succeed and verifies result metrics
        """
        # Setup change detection to return changeset with changes
        mock_change_detection_service.detect_changes.return_value = (
            sample_changeset_with_changes
        )

        result = await processor.process_repository(sample_repository)

        # Verify successful completion
        assert result.success is True
        assert result.repository_id == sample_repository.id
        assert result.repository_url == sample_repository.url
        assert result.completed_at is not None
        assert result.processing_time > 0

        # Verify metrics
        assert result.prs_discovered == 5
        assert result.check_runs_discovered == 12
        assert result.changes_detected == 2  # 1 new + 1 updated PR
        assert result.changes_synchronized == 3
        assert result.new_prs == 1
        assert result.updated_prs == 1

        # Verify no errors
        assert len(result.errors) == 0
        assert result.has_errors is False

        # Verify service calls
        processor.discovery_service.discover_prs_and_checks.assert_called_once_with(
            sample_repository
        )
        processor.change_detection_service.detect_changes.assert_called_once_with(
            sample_repository
        )
        processor.synchronization_service.synchronize_changes.assert_called_once_with(
            sample_changeset_with_changes
        )

    async def test_process_repository_discovery_failure(
        self, processor, sample_repository
    ):
        """
        Why: Ensure discovery failures are properly handled and don't stop processing
        What: Tests behavior when discovery service raises exception
        How: Mocks discovery service to raise exception, verifies error handling
        """
        # Setup discovery to fail
        processor.discovery_service.discover_prs_and_checks.side_effect = Exception(
            "GitHub API error"
        )

        result = await processor.process_repository(sample_repository)

        # Verify failure is recorded
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "discovery_failure"
        assert "GitHub API error" in result.errors[0].message
        assert result.completed_at is not None

        # Verify metrics show zero discoveries due to failure
        assert result.prs_discovered == 0
        assert result.check_runs_discovered == 0

        # Verify other phases still execute
        processor.change_detection_service.detect_changes.assert_called_once_with(
            sample_repository
        )

    async def test_process_repository_change_detection_failure(
        self, processor, sample_repository
    ):
        """
        Why: Ensure change detection failures are properly handled
        What: Tests behavior when change detection service raises exception
        How: Mocks change detection to fail, verifies error handling and continuation
        """
        # Setup change detection to fail
        processor.change_detection_service.detect_changes.side_effect = Exception(
            "Database connection error"
        )

        result = await processor.process_repository(sample_repository)

        # Verify failure is recorded
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "change_detection_failure"
        assert "Database connection error" in result.errors[0].message

        # Verify discovery still succeeded
        assert result.prs_discovered == 5
        assert result.check_runs_discovered == 12

        # Verify synchronization is not called when there are no changes (optimization)
        processor.synchronization_service.synchronize_changes.assert_not_called()

    async def test_process_repository_synchronization_failure(
        self,
        processor,
        sample_repository,
        sample_changeset_with_changes,
        mock_change_detection_service,
    ):
        """
        Why: Ensure synchronization failures are properly handled and recorded
        What: Tests behavior when synchronization service raises exception
        How: Mocks synchronization to fail, verifies error handling
        """
        # Setup services
        mock_change_detection_service.detect_changes.return_value = (
            sample_changeset_with_changes
        )
        processor.synchronization_service.synchronize_changes.side_effect = Exception(
            "Database write error"
        )

        result = await processor.process_repository(sample_repository)

        # Verify failure is recorded
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "synchronization_failure"
        assert "Database write error" in result.errors[0].message

        # Verify earlier phases succeeded
        assert result.prs_discovered == 5
        assert result.check_runs_discovered == 12
        assert result.changes_detected == 2

        # Verify synchronization count is not updated due to failure
        assert result.changes_synchronized == 0

    async def test_process_repository_no_changes(
        self, processor, sample_repository, mock_change_detection_service
    ):
        """
        Why: Verify efficient handling when no changes are detected
        What: Tests behavior when changeset has no changes to synchronize
        How: Returns empty changeset and verifies synchronization optimization
        """
        # Setup empty changeset
        empty_changeset = ChangeSet(repository_id=sample_repository.id)
        mock_change_detection_service.detect_changes.return_value = empty_changeset

        result = await processor.process_repository(sample_repository)

        # Verify successful completion with no changes
        assert result.success is True
        assert result.changes_detected == 0
        assert result.changes_synchronized == 0
        assert result.new_prs == 0
        assert result.updated_prs == 0

        # Verify synchronization was optimized away (not called with no changes)
        processor.synchronization_service.synchronize_changes.assert_not_called()

    @patch("src.workers.monitor.processor.logger")
    async def test_process_repository_logging(
        self,
        mock_logger,
        processor,
        sample_repository,
        sample_changeset_with_changes,
        mock_change_detection_service,
    ):
        """
        Why: Verify comprehensive logging throughout processing workflow
        What: Tests that appropriate log messages are generated at each phase
        How: Mocks logger and verifies log calls with correct data
        """
        mock_change_detection_service.detect_changes.return_value = (
            sample_changeset_with_changes
        )

        await processor.process_repository(sample_repository)

        # Verify logging calls
        mock_logger.info.assert_any_call(
            "Starting repository processing",
            extra={
                "repository_id": str(sample_repository.id),
                "repository_url": sample_repository.url,
                "repository_name": sample_repository.name,
            },
        )

        mock_logger.info.assert_any_call(
            "Repository processing completed",
            extra={
                "repository_id": str(sample_repository.id),
                "success": True,
                "processing_time": pytest.approx(
                    0.0, abs=1.0
                ),  # Allow some processing time
                "changes_synchronized": 3,
                "error_count": 0,
            },
        )

    async def test_process_repositories_success(
        self, processor, sample_changeset_with_changes
    ):
        """
        Why: Verify successful batch processing of multiple repositories
        What: Tests concurrent processing of repository list
        How: Creates multiple repositories and verifies batch results aggregation
        """
        # Create test repositories
        repositories = []
        for i in range(3):
            repo = Repository()
            repo.id = uuid.uuid4()
            repo.url = f"https://github.com/test/repo-{i}"
            repo.name = f"test-repo-{i}"
            repo.status = RepositoryStatus.ACTIVE
            repositories.append(repo)

        # Mock change detection service to return changesets with changes for each repo
        def create_changeset_for_repo(repository):
            changeset = ChangeSet(repository_id=repository.id)
            pr_data = PRData(
                number=1,
                title="Test PR",
                author="test-user",
                state="open",
                draft=False,
                base_branch="main",
                head_branch="feature",
                base_sha="abc123",
                head_sha="def456",
                url=f"{repository.url}/pull/1",
            )
            changeset.new_prs.append(PRChangeRecord(pr_data=pr_data, change_type="new"))
            return changeset

        processor.change_detection_service.detect_changes.side_effect = (
            create_changeset_for_repo
        )

        batch_result = await processor.process_repositories(repositories)

        # Verify batch completion
        assert batch_result.repositories_processed == 3
        assert batch_result.completed_at is not None
        assert batch_result.processing_time > 0

        # Verify aggregated metrics
        assert batch_result.total_prs_discovered == 15  # 5 per repo * 3 repos
        assert batch_result.total_check_runs_discovered == 36  # 12 per repo * 3 repos
        assert batch_result.total_changes_synchronized == 9  # 3 per repo * 3 repos

        # Verify success rate
        assert batch_result.success_rate == 100.0
        assert batch_result.total_errors == 0

        # Verify individual results
        assert len(batch_result.results) == 3
        for result in batch_result.results:
            assert result.success is True

    async def test_process_repositories_partial_failures(self, processor):
        """
        Why: Verify error isolation - failures in some repos don't affect others
        What: Tests batch processing with some repositories failing
        How: Mocks service to fail for specific repository, verifies isolation
        """
        # Create test repositories
        repositories = []
        for i in range(3):
            repo = Repository()
            repo.id = uuid.uuid4()
            repo.url = f"https://github.com/test/repo-{i}"
            repo.name = f"test-repo-{i}"
            repo.status = RepositoryStatus.ACTIVE
            repositories.append(repo)

        # Make discovery fail for second repository
        async def failing_discover(repository):
            if "repo-1" in repository.url:
                raise Exception("API rate limit exceeded")
            return (5, 12)

        processor.discovery_service.discover_prs_and_checks.side_effect = (
            failing_discover
        )

        batch_result = await processor.process_repositories(repositories)

        # Verify batch completion with partial failures
        assert batch_result.repositories_processed == 3
        assert batch_result.success_rate == pytest.approx(
            66.67, rel=0.1
        )  # 2/3 successful
        assert batch_result.total_errors == 1

        # Verify individual results
        assert len(batch_result.results) == 3
        successful_results = [r for r in batch_result.results if r.success]
        failed_results = [r for r in batch_result.results if not r.success]

        assert len(successful_results) == 2
        assert len(failed_results) == 1
        assert "API rate limit exceeded" in str(failed_results[0].errors[0])

    async def test_process_repositories_empty_list(self, processor):
        """
        Why: Verify graceful handling of empty repository lists
        What: Tests batch processing with no repositories provided
        How: Calls process_repositories with empty list, verifies clean completion
        """
        batch_result = await processor.process_repositories([])

        # Verify clean completion
        assert batch_result.repositories_processed == 0
        assert batch_result.completed_at is not None
        assert len(batch_result.results) == 0
        assert batch_result.success_rate == 0.0
        assert batch_result.total_errors == 0

    async def test_process_repositories_concurrency_limiting(self, processor):
        """
        Why: Verify semaphore-based concurrency limiting works correctly
        What: Tests that concurrent processing respects max_concurrent_repos limit
        How: Creates more repos than limit, monitors semaphore usage
        """
        # Create more repositories than the concurrency limit
        repositories = []
        for i in range(10):  # More than max_concurrent_repos=5
            repo = Repository()
            repo.id = uuid.uuid4()
            repo.url = f"https://github.com/test/repo-{i}"
            repo.name = f"test-repo-{i}"
            repo.status = RepositoryStatus.ACTIVE
            repositories.append(repo)

        # Track concurrent calls using a counter
        concurrent_calls = 0
        max_concurrent_seen = 0

        async def track_concurrency(*args, **kwargs):
            nonlocal concurrent_calls, max_concurrent_seen
            concurrent_calls += 1
            max_concurrent_seen = max(max_concurrent_seen, concurrent_calls)

            # Simulate some processing time
            await asyncio.sleep(0.01)

            concurrent_calls -= 1
            return (5, 12)

        processor.discovery_service.discover_prs_and_checks.side_effect = (
            track_concurrency
        )

        batch_result = await processor.process_repositories(repositories)

        # Verify concurrency was limited
        assert max_concurrent_seen <= processor.max_concurrent_repos
        assert batch_result.repositories_processed == 10

    async def test_process_repository_updates_tracking_success(
        self, processor, sample_repository
    ):
        """
        Why: Verify repository tracking is updated correctly on successful processing
        What: Tests that success resets failure count and updates last polled time
        How: Processes repository successfully and verifies tracking updates
        """
        # Set initial failure state
        sample_repository.failure_count = 3
        sample_repository.last_failure_at = datetime.now(timezone.utc)

        # Mock repository methods
        sample_repository.reset_failure_count = MagicMock()
        sample_repository.update_last_polled = MagicMock()

        result = await processor.process_repository(sample_repository)

        # Verify successful processing
        assert result.success is True

        # Verify tracking updates
        sample_repository.reset_failure_count.assert_called_once()
        sample_repository.update_last_polled.assert_called_once()

    async def test_process_repository_updates_tracking_failure(
        self, processor, sample_repository
    ):
        """
        Why: Verify repository tracking is updated correctly on processing failure
        What: Tests that failure increments failure count with error details
        How: Forces processing failure and verifies tracking updates
        """
        # Force discovery failure
        processor.discovery_service.discover_prs_and_checks.side_effect = Exception(
            "API error"
        )

        # Mock repository methods
        sample_repository.increment_failure_count = MagicMock()
        sample_repository.reset_failure_count = MagicMock()

        result = await processor.process_repository(sample_repository)

        # Verify failed processing
        assert result.success is False

        # Verify tracking updates
        sample_repository.increment_failure_count.assert_called_once()
        sample_repository.reset_failure_count.assert_not_called()

        # Verify failure reason contains error info
        call_args = sample_repository.increment_failure_count.call_args
        assert "discovery_failure" in call_args[0][0]

    async def test_concurrent_processing_exception_handling(self, processor):
        """
        Why: Verify robust exception handling during concurrent processing
        What: Tests that exceptions in asyncio.gather are properly handled
        How: Mocks task to raise exception, verifies it's converted to error result
        """
        # Create test repository
        repo = Repository()
        repo.id = uuid.uuid4()
        repo.url = "https://github.com/test/repo"
        repo.name = "test-repo"
        repo.status = RepositoryStatus.ACTIVE

        # Force exception during processing
        with patch.object(
            processor, "process_repository", side_effect=Exception("Task failure")
        ):
            batch_result = await processor.process_repositories([repo])

        # Verify exception is handled gracefully
        assert batch_result.repositories_processed == 1
        assert len(batch_result.results) == 1

        error_result = batch_result.results[0]
        assert error_result.success is False
        assert len(error_result.errors) == 1
        assert error_result.errors[0].error_type == "batch_processing_failure"
        assert "Task failure" in error_result.errors[0].message

    async def test_processing_metrics_accuracy(
        self,
        processor,
        sample_repository,
        sample_changeset_with_changes,
        mock_change_detection_service,
    ):
        """
        Why: Verify all processing metrics are calculated and reported accurately
        What: Tests comprehensive metric collection throughout processing workflow
        How: Provides known inputs and verifies all output metrics match expectations
        """
        # Setup known changeset metrics
        mock_change_detection_service.detect_changes.return_value = (
            sample_changeset_with_changes
        )

        result = await processor.process_repository(sample_repository)

        # Verify discovery metrics
        assert result.prs_discovered == 5
        assert result.check_runs_discovered == 12

        # Verify change detection metrics
        assert result.changes_detected == 2  # From sample_changeset_with_changes
        assert result.new_prs == 1
        assert result.updated_prs == 1
        assert result.new_check_runs == 0
        assert result.updated_check_runs == 0

        # Verify synchronization metrics
        assert result.changes_synchronized == 3

        # Verify timing metrics
        assert result.processing_time > 0
        assert result.started_at < result.completed_at

        # Verify error metrics
        assert result.has_errors is False
        assert len(result.errors) == 0

    @patch("src.workers.monitor.processor.logger")
    async def test_error_logging_detail(
        self, mock_logger, processor, sample_repository
    ):
        """
        Why: Verify detailed error information is logged for troubleshooting
        What: Tests that errors include context, exception types, and repository info
        How: Forces various error types and verifies log content
        """
        # Force discovery failure with specific exception
        test_exception = ConnectionError("GitHub API unreachable")
        processor.discovery_service.discover_prs_and_checks.side_effect = test_exception

        await processor.process_repository(sample_repository)

        # Verify error logging
        mock_logger.error.assert_called_with(
            "Discovery phase failed",
            extra={
                "repository_id": str(sample_repository.id),
                "error": str(test_exception),
            },
        )

    def test_processor_initialization(self):
        """
        Why: Verify processor is properly initialized with all required dependencies
        What: Tests constructor parameter handling and default values
        How: Creates processor with various configurations and verifies setup
        """
        mock_discovery = AsyncMock()
        mock_change_detection = AsyncMock()
        mock_synchronization = AsyncMock()

        # Test default concurrency
        processor = DefaultPRProcessor(
            discovery_service=mock_discovery,
            change_detection_service=mock_change_detection,
            synchronization_service=mock_synchronization,
        )
        assert processor.max_concurrent_repos == 10

        # Test custom concurrency
        processor = DefaultPRProcessor(
            discovery_service=mock_discovery,
            change_detection_service=mock_change_detection,
            synchronization_service=mock_synchronization,
            max_concurrent_repos=3,
        )
        assert processor.max_concurrent_repos == 3
        assert processor._semaphore._value == 3
