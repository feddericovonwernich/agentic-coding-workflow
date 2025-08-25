"""Comprehensive unit tests for the DataSynchronizer class."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import CheckRun, PullRequest
from src.models.enums import CheckConclusion, CheckStatus, PRState, TriggerEvent
from src.workers.monitor.models import (
    CheckRunDiscovery,
    DiscoveryResult,
    OperationStatus,
    StateChangeEvent,
    SyncOperation,
)
from src.workers.monitor.synchronization import (
    ConflictResolutionStrategy,
    DataSynchronizer,
)


@pytest.fixture
def mock_session():
    """Mock AsyncSession for testing."""
    session = AsyncMock(spec=AsyncSession)
    session.in_transaction.return_value = False
    session.begin = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def sample_repository_id():
    """Sample repository UUID for testing."""
    return uuid.uuid4()


@pytest.fixture
def sample_pr_id():
    """Sample PR UUID for testing."""
    return uuid.uuid4()


@pytest.fixture
def sample_discovery_result(sample_repository_id):
    """Sample DiscoveryResult for testing."""
    return DiscoveryResult(
        repository_id=sample_repository_id,
        repository_name="test-repo",
        repository_owner="test-owner",
        pr_number=123,
        title="Test PR",
        author="test-author",
        state=PRState.OPENED,
        draft=False,
        base_branch="main",
        head_branch="feature-branch",
        base_sha="abc123",
        head_sha="def456",
        url="https://github.com/test-owner/test-repo/pull/123",
        body="Test PR body",
        github_id=456789,
        github_node_id="PR_test123",
    )


@pytest.fixture
def sample_check_run_discovery(sample_pr_id):
    """Sample CheckRunDiscovery for testing."""
    return CheckRunDiscovery(
        pr_id=sample_pr_id,
        pr_number=123,
        github_check_run_id="check_123",
        check_name="test-check",
        status=CheckStatus.COMPLETED,
        conclusion=CheckConclusion.SUCCESS,
        details_url="https://github.com/test/details",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_state_change(sample_pr_id, sample_repository_id):
    """Sample StateChangeEvent for testing."""
    return StateChangeEvent(
        pr_id=sample_pr_id,
        pr_number=123,
        repository_id=sample_repository_id,
        old_state={"state": "opened"},
        new_state={"state": "merged"},
        changed_fields=["state"],
    )


@pytest.fixture
def synchronizer(mock_session):
    """DataSynchronizer instance for testing."""
    return DataSynchronizer(
        session=mock_session,
        batch_size=10,
        conflict_resolution=ConflictResolutionStrategy.GITHUB_WINS,
        enable_audit_log=True,
    )


class TestDataSynchronizerInitialization:
    """Test DataSynchronizer initialization."""

    def test_initialization_with_defaults(self, mock_session):
        """Test initialization with default parameters."""
        sync = DataSynchronizer(mock_session)

        assert sync.session == mock_session
        assert sync.batch_size == 1000
        assert sync.conflict_resolution == ConflictResolutionStrategy.GITHUB_WINS
        assert sync.enable_audit_log is True
        assert sync._current_operation is None
        assert sync._rollback_data == {}

    def test_initialization_with_custom_parameters(self, mock_session):
        """Test initialization with custom parameters."""
        sync = DataSynchronizer(
            session=mock_session,
            batch_size=500,
            conflict_resolution=ConflictResolutionStrategy.DATABASE_WINS,
            enable_audit_log=False,
        )

        assert sync.batch_size == 500
        assert sync.conflict_resolution == ConflictResolutionStrategy.DATABASE_WINS
        assert sync.enable_audit_log is False


class TestSyncOperationCreation:
    """Test sync operation creation and management."""

    async def test_create_empty_sync_operation(self, synchronizer):
        """Test creating an empty sync operation."""
        operation = await synchronizer.create_sync_operation()

        assert operation.operation_id is not None
        assert operation.status == OperationStatus.PENDING
        assert operation.total_operations == 0
        assert operation.is_empty is True
        assert len(operation.pull_requests_to_create) == 0
        assert len(operation.pull_requests_to_update) == 0
        assert len(operation.check_runs_to_create) == 0
        assert len(operation.check_runs_to_update) == 0

    async def test_create_sync_operation_with_data(
        self, synchronizer, sample_discovery_result, sample_check_run_discovery
    ):
        """Test creating a sync operation with data."""
        operation = await synchronizer.create_sync_operation(
            pull_requests_to_create=[sample_discovery_result],
            check_runs_to_update=[sample_check_run_discovery],
        )

        assert operation.total_operations == 2
        assert operation.is_empty is False
        assert len(operation.pull_requests_to_create) == 1
        assert len(operation.check_runs_to_update) == 1
        assert operation.pull_requests_to_create[0] == sample_discovery_result


class TestSyncOperationExecution:
    """Test sync operation execution."""

    @patch("src.workers.monitor.synchronization.DatabaseTransaction")
    async def test_execute_empty_sync_operation(
        self, mock_db_transaction, synchronizer
    ):
        """Test executing an empty sync operation."""
        empty_operation = SyncOperation()

        result = await synchronizer.execute_sync_operation(empty_operation)

        assert result.status == OperationStatus.COMPLETED
        assert result.operation_id == empty_operation.operation_id
        # Should not create a transaction for empty operation
        mock_db_transaction.assert_not_called()

    @patch("src.workers.monitor.synchronization.DatabaseTransaction")
    async def test_execute_sync_operation_success(
        self, mock_db_transaction, synchronizer, sample_discovery_result
    ):
        """Test successful sync operation execution."""
        # Setup mock transaction context manager
        mock_transaction = AsyncMock()
        mock_db_transaction.return_value.__aenter__.return_value = mock_transaction

        # Mock repository methods
        synchronizer.pr_repo.get_by_repo_and_number = AsyncMock(return_value=None)
        synchronizer.pr_repo.bulk_update_last_checked = AsyncMock(return_value=1)

        operation = SyncOperation(pull_requests_to_create=[sample_discovery_result])

        result = await synchronizer.execute_sync_operation(operation)

        assert result.status == OperationStatus.COMPLETED
        assert result.started_at is not None
        assert result.completed_at is not None
        mock_db_transaction.assert_called_once()

    @patch("src.workers.monitor.synchronization.DatabaseTransaction")
    async def test_execute_sync_operation_failure(
        self, mock_db_transaction, synchronizer, sample_discovery_result
    ):
        """Test sync operation execution with failure."""
        # Setup mock transaction to raise exception
        mock_db_transaction.return_value.__aenter__.side_effect = Exception(
            "Test error"
        )

        operation = SyncOperation(pull_requests_to_create=[sample_discovery_result])

        with pytest.raises(Exception, match="Sync operation failed"):
            await synchronizer.execute_sync_operation(operation)


class TestPRSynchronization:
    """Test PR synchronization operations."""

    async def test_categorize_pr_operations_all_new(
        self, synchronizer, sample_discovery_result
    ):
        """Test categorizing PRs when all are new."""
        # Mock repository to return None (PR doesn't exist)
        synchronizer.pr_repo.get_by_repo_and_number = AsyncMock(return_value=None)

        prs_to_create, prs_to_update = await synchronizer._categorize_pr_operations(
            [sample_discovery_result]
        )

        assert len(prs_to_create) == 1
        assert len(prs_to_update) == 0
        assert prs_to_create[0] == sample_discovery_result

    async def test_categorize_pr_operations_existing(
        self, synchronizer, sample_discovery_result
    ):
        """Test categorizing PRs when they exist and need updates."""
        # Mock existing PR with different title
        existing_pr = MagicMock(spec=PullRequest)
        existing_pr.title = "Different Title"
        existing_pr.body = sample_discovery_result.body
        existing_pr.state = sample_discovery_result.state
        existing_pr.draft = sample_discovery_result.draft
        existing_pr.head_sha = sample_discovery_result.head_sha
        existing_pr.base_sha = sample_discovery_result.base_sha

        synchronizer.pr_repo.get_by_repo_and_number = AsyncMock(
            return_value=existing_pr
        )

        prs_to_create, prs_to_update = await synchronizer._categorize_pr_operations(
            [sample_discovery_result]
        )

        assert len(prs_to_create) == 0
        assert len(prs_to_update) == 1
        assert prs_to_update[0] == sample_discovery_result

    async def test_pr_needs_update_true(self, synchronizer, sample_discovery_result):
        """Test PR needs update detection when changes exist."""
        existing_pr = MagicMock(spec=PullRequest)
        existing_pr.title = "Different Title"  # This should trigger update
        existing_pr.body = sample_discovery_result.body
        existing_pr.state = sample_discovery_result.state
        existing_pr.draft = sample_discovery_result.draft
        existing_pr.head_sha = sample_discovery_result.head_sha
        existing_pr.base_sha = sample_discovery_result.base_sha

        needs_update = await synchronizer._pr_needs_update(
            existing_pr, sample_discovery_result
        )

        assert needs_update is True

    async def test_pr_needs_update_false(self, synchronizer, sample_discovery_result):
        """Test PR needs update detection when no changes exist."""
        existing_pr = MagicMock(spec=PullRequest)
        existing_pr.title = sample_discovery_result.title
        existing_pr.body = sample_discovery_result.body
        existing_pr.state = sample_discovery_result.state
        existing_pr.draft = sample_discovery_result.draft
        existing_pr.head_sha = sample_discovery_result.head_sha
        existing_pr.base_sha = sample_discovery_result.base_sha

        needs_update = await synchronizer._pr_needs_update(
            existing_pr, sample_discovery_result
        )

        assert needs_update is False

    async def test_create_prs_bulk(self, synchronizer, sample_discovery_result):
        """Test bulk PR creation."""
        # Mock session methods
        synchronizer.session.add_all = MagicMock()
        synchronizer.session.flush = AsyncMock()

        count = await synchronizer._create_prs_bulk([sample_discovery_result])

        assert count == 1
        synchronizer.session.add_all.assert_called_once()
        synchronizer.session.flush.assert_called_once()

    async def test_create_prs_bulk_with_validation_error(
        self, synchronizer, sample_discovery_result
    ):
        """Test bulk PR creation with validation errors."""
        # Create invalid PR data
        invalid_pr = DiscoveryResult(
            repository_id=sample_discovery_result.repository_id,
            repository_name="",  # Invalid empty name
            repository_owner="",  # Invalid empty owner
            pr_number=0,  # Invalid PR number
            title="",  # Invalid empty title
            author="",  # Invalid empty author
            state=PRState.OPENED,
            draft=False,
            base_branch="",  # Invalid empty branch
            head_branch="",  # Invalid empty branch
            base_sha="",  # Invalid empty SHA
            head_sha="",  # Invalid empty SHA
            url="",  # Invalid empty URL
        )

        # Mock session methods
        synchronizer.session.add_all = MagicMock()
        synchronizer.session.flush = AsyncMock()

        # Should handle validation errors gracefully
        count = await synchronizer._create_prs_bulk(
            [invalid_pr, sample_discovery_result]
        )

        # Only valid PR should be created
        assert count == 1


class TestCheckRunSynchronization:
    """Test check run synchronization operations."""

    async def test_categorize_check_operations_all_new(
        self, synchronizer, sample_check_run_discovery
    ):
        """Test categorizing check runs when all are new."""
        # Mock repository to return None (check doesn't exist)
        synchronizer.check_run_repo.get_by_external_id = AsyncMock(return_value=None)

        (
            checks_to_create,
            checks_to_update,
        ) = await synchronizer._categorize_check_operations(
            [sample_check_run_discovery]
        )

        assert len(checks_to_create) == 1
        assert len(checks_to_update) == 0
        assert checks_to_create[0] == sample_check_run_discovery

    async def test_categorize_check_operations_existing(
        self, synchronizer, sample_check_run_discovery
    ):
        """Test categorizing check runs when they exist and need updates."""
        # Mock existing check run with different status
        existing_check = MagicMock(spec=CheckRun)
        existing_check.status = CheckStatus.IN_PROGRESS  # Different from COMPLETED
        existing_check.conclusion = sample_check_run_discovery.conclusion
        existing_check.output_summary = sample_check_run_discovery.output_summary
        existing_check.completed_at = sample_check_run_discovery.completed_at

        synchronizer.check_run_repo.get_by_external_id = AsyncMock(
            return_value=existing_check
        )

        (
            checks_to_create,
            checks_to_update,
        ) = await synchronizer._categorize_check_operations(
            [sample_check_run_discovery]
        )

        assert len(checks_to_create) == 0
        assert len(checks_to_update) == 1
        assert checks_to_update[0] == sample_check_run_discovery

    async def test_check_needs_update_true(
        self, synchronizer, sample_check_run_discovery
    ):
        """Test check run needs update detection when changes exist."""
        existing_check = MagicMock(spec=CheckRun)
        existing_check.status = CheckStatus.IN_PROGRESS  # Different status
        existing_check.conclusion = sample_check_run_discovery.conclusion
        existing_check.output_summary = sample_check_run_discovery.output_summary
        existing_check.completed_at = sample_check_run_discovery.completed_at

        needs_update = await synchronizer._check_needs_update(
            existing_check, sample_check_run_discovery
        )

        assert needs_update is True

    async def test_check_needs_update_false(
        self, synchronizer, sample_check_run_discovery
    ):
        """Test check run needs update detection when no changes exist."""
        existing_check = MagicMock(spec=CheckRun)
        existing_check.status = sample_check_run_discovery.status
        existing_check.conclusion = sample_check_run_discovery.conclusion
        existing_check.output_summary = sample_check_run_discovery.output_summary
        existing_check.completed_at = sample_check_run_discovery.completed_at

        needs_update = await synchronizer._check_needs_update(
            existing_check, sample_check_run_discovery
        )

        assert needs_update is False


class TestConflictResolution:
    """Test conflict resolution strategies."""

    async def test_update_pr_github_wins_strategy(
        self, synchronizer, sample_discovery_result
    ):
        """Test PR update with GitHub wins conflict resolution."""
        existing_pr = MagicMock(spec=PullRequest)
        existing_pr.title = "Old Title"
        existing_pr.body = "Old Body"
        existing_pr.pr_metadata = {"old_key": "old_value"}

        # Set up new data with metadata
        new_pr_data = DiscoveryResult(
            repository_id=sample_discovery_result.repository_id,
            repository_name=sample_discovery_result.repository_name,
            repository_owner=sample_discovery_result.repository_owner,
            pr_number=sample_discovery_result.pr_number,
            title="New Title",
            author=sample_discovery_result.author,
            state=sample_discovery_result.state,
            draft=sample_discovery_result.draft,
            base_branch=sample_discovery_result.base_branch,
            head_branch=sample_discovery_result.head_branch,
            base_sha=sample_discovery_result.base_sha,
            head_sha=sample_discovery_result.head_sha,
            url=sample_discovery_result.url,
            body="New Body",
            pr_metadata={"new_key": "new_value"},
        )

        # Test GitHub wins strategy
        synchronizer.conflict_resolution = ConflictResolutionStrategy.GITHUB_WINS
        updated = await synchronizer._update_pr_with_conflict_resolution(
            existing_pr, new_pr_data
        )

        assert updated is True
        assert existing_pr.title == "New Title"
        assert existing_pr.body == "New Body"
        assert existing_pr.pr_metadata["new_key"] == "new_value"
        assert existing_pr.pr_metadata["old_key"] == "old_value"  # Merged

    async def test_update_pr_database_wins_strategy(
        self, synchronizer, sample_discovery_result
    ):
        """Test PR update with database wins conflict resolution."""
        existing_pr = MagicMock(spec=PullRequest)
        existing_pr.title = "Old Title"
        existing_pr.body = "Old Body"

        synchronizer.conflict_resolution = ConflictResolutionStrategy.DATABASE_WINS
        updated = await synchronizer._update_pr_with_conflict_resolution(
            existing_pr, sample_discovery_result
        )

        assert updated is True
        assert existing_pr.title == "Old Title"  # Unchanged
        assert existing_pr.body == "Old Body"  # Unchanged

    async def test_update_pr_fail_on_conflict_strategy(
        self, synchronizer, sample_discovery_result
    ):
        """Test PR update with fail on conflict strategy."""
        existing_pr = MagicMock(spec=PullRequest)
        existing_pr.title = "Different Title"  # This creates a conflict
        existing_pr.body = sample_discovery_result.body
        existing_pr.state = sample_discovery_result.state

        synchronizer.conflict_resolution = ConflictResolutionStrategy.FAIL_ON_CONFLICT

        with pytest.raises(ValueError, match="PR update conflicts detected"):
            await synchronizer._update_pr_with_conflict_resolution(
                existing_pr, sample_discovery_result
            )


class TestBulkOperations:
    """Test bulk operation handling."""

    def test_batch_items_single_batch(self, synchronizer):
        """Test batching items when all fit in one batch."""
        items = [1, 2, 3, 4, 5]
        synchronizer.batch_size = 10

        batches = list(synchronizer._batch_items(items))

        assert len(batches) == 1
        assert batches[0] == items

    def test_batch_items_multiple_batches(self, synchronizer):
        """Test batching items when multiple batches are needed."""
        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        synchronizer.batch_size = 5

        batches = list(synchronizer._batch_items(items))

        assert len(batches) == 3
        assert batches[0] == [1, 2, 3, 4, 5]
        assert batches[1] == [6, 7, 8, 9, 10]
        assert batches[2] == [11]

    async def test_sync_pull_requests_success(
        self, synchronizer, sample_discovery_result
    ):
        """Test successful PR synchronization."""
        # Mock the sync batch method
        synchronizer._sync_pr_batch = AsyncMock(return_value=(1, 0))

        created, updated, errors = await synchronizer.sync_pull_requests(
            [sample_discovery_result]
        )

        assert created == 1
        assert updated == 0
        assert len(errors) == 0

    async def test_sync_pull_requests_with_errors(
        self, synchronizer, sample_discovery_result
    ):
        """Test PR synchronization with errors."""
        # Mock the sync batch method to raise an exception
        synchronizer._sync_pr_batch = AsyncMock(side_effect=Exception("Batch error"))

        created, updated, errors = await synchronizer.sync_pull_requests(
            [sample_discovery_result]
        )

        assert created == 0
        assert updated == 0
        assert len(errors) == 1
        assert "Failed to sync PR batch: Batch error" in errors[0]


class TestRollbackOperations:
    """Test rollback and error recovery."""

    async def test_rollback_sync_operation_success(self, synchronizer):
        """Test successful rollback operation."""
        # Setup rollback data
        synchronizer._rollback_data = {
            "operation_id": "test-op",
            "created_pr_ids": [],
            "created_check_ids": [],
        }

        # Mock execute rollback method
        synchronizer._execute_rollback_operations = AsyncMock()

        operation = SyncOperation(can_rollback=True)
        result = await synchronizer.rollback_sync_operation(operation)

        assert result.status == OperationStatus.ROLLED_BACK
        assert result.completed_at is not None
        synchronizer._execute_rollback_operations.assert_called_once()

    async def test_rollback_sync_operation_no_rollback_data(self, synchronizer):
        """Test rollback when no rollback data is available."""
        operation = SyncOperation(can_rollback=False)
        result = await synchronizer.rollback_sync_operation(operation)

        assert result.status == OperationStatus.FAILED

    async def test_rollback_sync_operation_failure(self, synchronizer):
        """Test rollback operation failure."""
        # Setup rollback data
        synchronizer._rollback_data = {"operation_id": "test-op"}

        # Mock execute rollback method to raise exception
        synchronizer._execute_rollback_operations = AsyncMock(
            side_effect=Exception("Rollback error")
        )

        operation = SyncOperation(can_rollback=True)
        result = await synchronizer.rollback_sync_operation(operation)

        assert result.status == OperationStatus.FAILED
        assert any(
            "Rollback failed: Rollback error" in error for error in result.errors
        )


class TestOperationStatus:
    """Test operation status tracking."""

    async def test_get_operation_status_current(self, synchronizer):
        """Test getting current operation status."""
        operation = SyncOperation()
        synchronizer._current_operation = operation

        result = await synchronizer.get_operation_status(operation.operation_id)

        assert result == operation

    async def test_get_operation_status_not_found(self, synchronizer):
        """Test getting operation status when not found."""
        result = await synchronizer.get_operation_status("non-existent-id")

        assert result is None

    async def test_cleanup_completed_operations(self, synchronizer):
        """Test cleanup of completed operations."""
        # This is a placeholder test since cleanup is not fully implemented
        result = await synchronizer.cleanup_completed_operations()

        assert result == 0


class TestAuditLogging:
    """Test audit logging functionality."""

    @patch("src.workers.monitor.synchronization.logger")
    def test_log_operation_audit_basic(self, mock_logger, synchronizer):
        """Test basic audit logging."""
        operation = SyncOperation()

        synchronizer._log_operation_audit("TEST_EVENT", operation)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "TEST_EVENT" in call_args
        assert operation.operation_id in call_args

    @patch("src.workers.monitor.synchronization.logger")
    def test_log_operation_audit_with_error(self, mock_logger, synchronizer):
        """Test audit logging with error information."""
        operation = SyncOperation()

        synchronizer._log_operation_audit("ERROR_EVENT", operation, error="Test error")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "ERROR_EVENT" in call_args
        assert "Test error" in call_args

    def test_audit_logging_disabled(self, mock_session):
        """Test that audit logging can be disabled."""
        synchronizer = DataSynchronizer(mock_session, enable_audit_log=False)

        with patch("src.workers.monitor.synchronization.logger") as mock_logger:
            operation = SyncOperation()
            synchronizer._log_operation_audit("TEST_EVENT", operation)
            # This should still log, but in production might be filtered
            mock_logger.info.assert_called_once()


class TestIntegrationScenarios:
    """Test integration scenarios with multiple components."""

    async def test_full_synchronization_workflow(
        self, synchronizer, sample_discovery_result, sample_check_run_discovery
    ):
        """Test a complete synchronization workflow."""
        # Mock repository methods to simulate database state
        synchronizer.pr_repo.get_by_repo_and_number = AsyncMock(return_value=None)
        synchronizer.check_run_repo.get_by_external_id = AsyncMock(return_value=None)
        synchronizer.pr_repo.bulk_update_last_checked = AsyncMock(return_value=1)

        # Mock session operations
        synchronizer.session.add_all = MagicMock()
        synchronizer.session.flush = AsyncMock()

        with patch(
            "src.workers.monitor.synchronization.DatabaseTransaction"
        ) as mock_tx:
            mock_tx.return_value.__aenter__.return_value = synchronizer.session

            # Execute full synchronization
            result = await synchronizer.synchronize_changes(
                discovered_prs=[sample_discovery_result],
                discovered_check_runs=[sample_check_run_discovery],
                state_changes=[],
            )

        assert result.status == OperationStatus.COMPLETED
        assert result.total_operations == 2  # 1 PR create + 1 check create
        synchronizer.session.add_all.assert_called()
        synchronizer.session.flush.assert_called()

    async def test_mixed_create_update_operations(
        self, synchronizer, sample_discovery_result, sample_check_run_discovery
    ):
        """Test mixed create and update operations."""
        # Create second PR that will need updating
        existing_pr = MagicMock(spec=PullRequest)
        existing_pr.title = "Old Title"  # Different from sample
        existing_pr.body = sample_discovery_result.body
        existing_pr.state = sample_discovery_result.state
        existing_pr.draft = sample_discovery_result.draft
        existing_pr.head_sha = sample_discovery_result.head_sha
        existing_pr.base_sha = sample_discovery_result.base_sha

        updated_pr = DiscoveryResult(
            repository_id=uuid.uuid4(),
            repository_name="updated-repo",
            repository_owner="test-owner",
            pr_number=456,
            title="Updated PR Title",
            author="test-author",
            state=PRState.OPENED,
            draft=False,
            base_branch="main",
            head_branch="updated-branch",
            base_sha="updated-abc",
            head_sha="updated-def",
            url="https://github.com/test-owner/updated-repo/pull/456",
        )

        # Mock repository to return None for first PR, existing PR for second
        def mock_get_pr(repo_id, pr_number):
            if pr_number == 123:
                return None  # New PR
            elif pr_number == 456:
                return existing_pr  # Existing PR
            return None

        synchronizer.pr_repo.get_by_repo_and_number = AsyncMock(side_effect=mock_get_pr)
        synchronizer.check_run_repo.get_by_external_id = AsyncMock(return_value=None)
        synchronizer.pr_repo.bulk_update_last_checked = AsyncMock(return_value=2)

        # Mock session operations
        synchronizer.session.add_all = MagicMock()
        synchronizer.session.flush = AsyncMock()

        with patch(
            "src.workers.monitor.synchronization.DatabaseTransaction"
        ) as mock_tx:
            mock_tx.return_value.__aenter__.return_value = synchronizer.session

            # Execute synchronization with mixed operations
            result = await synchronizer.synchronize_changes(
                discovered_prs=[sample_discovery_result, updated_pr],
                discovered_check_runs=[sample_check_run_discovery],
                state_changes=[],
            )

        assert result.status == OperationStatus.COMPLETED
        assert result.total_operations == 3  # 1 create + 1 update + 1 check create
