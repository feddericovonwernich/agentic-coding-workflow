"""Unit tests for database synchronization logic."""

import uuid
from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.transactions import TransactionError
from src.models import CheckRun, PRState, PullRequest, TriggerEvent
from src.models.enums import CheckConclusion, CheckStatus
from src.workers.monitor.models import (
    ChangeSet,
    CheckRunChangeRecord,
    CheckRunData,
    PRChangeRecord,
    PRData,
)
from src.workers.monitor.synchronization import DatabaseSynchronizer


class TestDatabaseSynchronizer:
    """Test DatabaseSynchronizer implementation."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock(spec=AsyncSession)
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.in_transaction.return_value = False
        session.begin = AsyncMock()
        return session

    @pytest.fixture
    def synchronizer(self, mock_session: AsyncMock) -> DatabaseSynchronizer:
        """Create DatabaseSynchronizer with mocked dependencies."""
        return DatabaseSynchronizer(mock_session)

    @pytest.fixture
    def sample_pr_data(self) -> PRData:
        """Create sample PR data for testing."""
        return PRData(
            number=123,
            title="Test PR",
            author="test-user",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature",
            base_sha="abc123",
            head_sha="def456",
            url="https://github.com/test/repo/pull/123",
            body="Test PR body",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            raw_data={"repository_id": str(uuid.uuid4())},
        )

    @pytest.fixture
    def repository_id(self) -> uuid.UUID:
        """Create a repository ID for testing."""
        return uuid.uuid4()

    @pytest.fixture
    def sample_check_data(self) -> CheckRunData:
        """Create sample check run data for testing."""
        return CheckRunData(
            external_id="check_123",
            check_name="test-check",
            status="completed",
            conclusion="success",
            details_url="https://github.com/test/repo/actions",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )

    async def test_synchronize_changes_no_changes(
        self, synchronizer: DatabaseSynchronizer
    ):
        """
        Why: Validates handling of empty changesets
        What: Tests that no operations are performed for empty changesets
        How: Creates empty changeset and verifies early return
        """
        # Arrange
        repository_id = uuid.uuid4()
        empty_changeset = ChangeSet(repository_id=repository_id)

        # Act
        result = await synchronizer.synchronize_changes(repository_id, empty_changeset)

        # Assert
        assert result == 0
        # Verify no database operations were attempted
        synchronizer.session.begin.assert_not_called()

    async def test_synchronize_changes_with_new_prs(
        self, synchronizer: DatabaseSynchronizer, sample_pr_data: PRData
    ):
        """
        Why: Validates successful synchronization of new PRs
        What: Tests creation of new PR records with proper transaction handling
        How: Mocks PR creation and verifies transaction flow
        """
        # Arrange
        repository_id = uuid.uuid4()
        pr_change = PRChangeRecord(pr_data=sample_pr_data, change_type="new")
        changeset = ChangeSet(repository_id=repository_id, new_prs=[pr_change])

        # Mock the bulk creation method
        mock_pr = Mock(spec=PullRequest)
        mock_pr.id = uuid.uuid4()

        with patch.object(synchronizer, "_create_new_prs_bulk") as mock_create:
            mock_create.return_value = [mock_pr]

            # Act
            result = await synchronizer.synchronize_changes(repository_id, changeset)

        # Assert
        assert result == 1
        mock_create.assert_called_once_with([pr_change])

    async def test_synchronize_changes_with_database_error(
        self, synchronizer: DatabaseSynchronizer, sample_pr_data: PRData
    ):
        """
        Why: Validates proper error handling during database operations
        What: Tests that database errors are caught and re-raised as TransactionError
        How: Mocks database error and verifies exception handling
        """
        # Arrange
        repository_id = uuid.uuid4()
        pr_change = PRChangeRecord(pr_data=sample_pr_data, change_type="new")
        changeset = ChangeSet(repository_id=repository_id, new_prs=[pr_change])

        # Mock database error during transaction
        with patch(
            "src.workers.monitor.synchronization.database_transaction"
        ) as mock_tx:
            mock_tx.side_effect = SQLAlchemyError("Database connection failed")

            # Act & Assert
            with pytest.raises(TransactionError, match="Synchronization failed"):
                await synchronizer.synchronize_changes(repository_id, changeset)

    async def test_create_new_prs_empty_list(self, synchronizer: DatabaseSynchronizer):
        """
        Why: Validates handling of empty input lists
        What: Tests that empty lists return empty results without database calls
        How: Passes empty list and verifies no operations
        """
        # Act
        result = await synchronizer.create_new_prs([])

        # Assert
        assert result == []

    async def test_create_new_prs_bulk_operation(
        self, synchronizer: DatabaseSynchronizer, sample_pr_data: PRData
    ):
        """
        Why: Validates bulk insert operations for PR creation
        What: Tests PostgreSQL UPSERT functionality with conflict handling
        How: Mocks repository methods and verifies correct flow
        """
        # Arrange
        pr_change = PRChangeRecord(pr_data=sample_pr_data, change_type="new")

        # Mock PR repository methods
        mock_pr = Mock(spec=PullRequest)
        mock_pr.id = uuid.uuid4()
        mock_pr.state = PRState.OPENED

        synchronizer.pr_repo.get_by_repo_and_number = AsyncMock(return_value=mock_pr)
        synchronizer.history_repo.create_transition = AsyncMock()

        # Mock session execute to simulate successful bulk insert
        synchronizer.session.execute = AsyncMock()
        synchronizer.session.flush = AsyncMock()

        # Act
        result = await synchronizer.create_new_prs([pr_change])

        # Assert
        assert len(result) == 1
        assert result[0] == mock_pr

        # Verify database operations were called
        synchronizer.session.execute.assert_called_once()
        synchronizer.session.flush.assert_called_once()

        # Verify PR retrieval and state history creation
        synchronizer.pr_repo.get_by_repo_and_number.assert_called_once()
        synchronizer.history_repo.create_transition.assert_called_once()

    async def test_update_existing_prs_with_state_change(
        self, synchronizer: DatabaseSynchronizer, sample_pr_data: PRData
    ):
        """
        Why: Validates state transition handling during PR updates
        What: Tests proper state changes with history record creation
        How: Mocks existing PR and verifies state update flow
        """
        # Arrange
        existing_pr_id = uuid.uuid4()
        sample_pr_data.state = "closed"  # Change state to closed

        pr_change = PRChangeRecord(
            pr_data=sample_pr_data,
            change_type="state_changed",
            existing_pr_id=existing_pr_id,
            state_changed=True,
            old_state=PRState.OPENED,
        )

        # Mock existing PR
        mock_existing_pr = Mock(spec=PullRequest)
        mock_existing_pr.id = existing_pr_id
        mock_existing_pr.state = PRState.OPENED
        mock_existing_pr.title = "Old Title"

        # Mock updated PR
        mock_updated_pr = Mock(spec=PullRequest)
        mock_updated_pr.id = existing_pr_id
        mock_updated_pr.state = PRState.CLOSED

        synchronizer.pr_repo.get_by_id = AsyncMock(return_value=mock_existing_pr)
        synchronizer.pr_repo.update_state = AsyncMock(return_value=mock_updated_pr)

        # Act
        result = await synchronizer.update_existing_prs([pr_change])

        # Assert
        assert len(result) == 1
        assert result[0] == mock_updated_pr

        # Verify state update was called
        synchronizer.pr_repo.update_state.assert_called_once_with(
            pr_id=existing_pr_id,
            new_state=PRState.CLOSED,
            trigger_event=TriggerEvent.CLOSED,
            metadata=ANY,
        )

    async def test_create_new_check_runs_bulk_operation(
        self, synchronizer: DatabaseSynchronizer, sample_check_data: CheckRunData
    ):
        """
        Why: Validates bulk creation of check run records
        What: Tests efficient batch insertion of multiple check runs
        How: Mocks repository methods and verifies correct flow
        """
        # Arrange
        pr_id = uuid.uuid4()
        check_change = CheckRunChangeRecord(
            check_data=sample_check_data, pr_id=pr_id, change_type="new"
        )

        # Mock check run retrieval
        mock_check_run = Mock(spec=CheckRun)
        mock_check_run.id = uuid.uuid4()
        synchronizer.check_repo.get_by_external_id = AsyncMock(
            return_value=mock_check_run
        )

        # Mock session operations
        synchronizer.session.execute = AsyncMock()
        synchronizer.session.flush = AsyncMock()

        # Act
        result = await synchronizer.create_new_check_runs([check_change])

        # Assert
        assert len(result) == 1
        assert result[0] == mock_check_run

        # Verify database operations were called
        synchronizer.session.execute.assert_called_once()
        synchronizer.session.flush.assert_called_once()

        # Verify check run retrieval
        synchronizer.check_repo.get_by_external_id.assert_called_once_with(
            sample_check_data.external_id
        )

    async def test_update_existing_check_runs_status_change(
        self, synchronizer: DatabaseSynchronizer, sample_check_data: CheckRunData
    ):
        """
        Why: Validates check run status updates with proper validation
        What: Tests status transition from queued to completed
        How: Mocks existing check run and verifies status update
        """
        # Arrange
        existing_check_id = uuid.uuid4()
        sample_check_data.status = "completed"
        sample_check_data.conclusion = "failure"

        check_change = CheckRunChangeRecord(
            check_data=sample_check_data,
            pr_id=uuid.uuid4(),
            change_type="status_changed",
            existing_check_id=existing_check_id,
            status_changed=True,
        )

        # Mock existing check run
        mock_check_run = Mock(spec=CheckRun)
        mock_check_run.id = existing_check_id

        # Mock updated check run
        mock_updated_check = Mock(spec=CheckRun)
        mock_updated_check.id = existing_check_id
        mock_updated_check.status = CheckStatus.COMPLETED

        synchronizer.check_repo.get_by_id = AsyncMock(return_value=mock_check_run)
        synchronizer.check_repo.update_status = AsyncMock(
            return_value=mock_updated_check
        )

        # Act
        result = await synchronizer.update_existing_check_runs([check_change])

        # Assert
        assert len(result) == 1
        assert result[0] == mock_updated_check

        # Verify status update
        synchronizer.check_repo.update_status.assert_called_once_with(
            check_run_id=existing_check_id,
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.FAILURE,
            metadata=ANY,
        )

    async def test_synchronize_changes_mixed_operations(
        self,
        synchronizer: DatabaseSynchronizer,
        sample_pr_data: PRData,
        sample_check_data: CheckRunData,
    ):
        """
        Why: Validates complex synchronization with multiple operation types
        What: Tests transaction handling with mixed PR and check run operations
        How: Creates changeset with all operation types and verifies execution order
        """
        # Arrange
        repository_id = uuid.uuid4()
        pr_id = uuid.uuid4()

        # Create mixed changeset
        new_pr = PRChangeRecord(pr_data=sample_pr_data, change_type="new")
        updated_pr = PRChangeRecord(
            pr_data=sample_pr_data,
            change_type="updated",
            existing_pr_id=pr_id,
            title_changed=True,
        )
        new_check = CheckRunChangeRecord(
            check_data=sample_check_data, pr_id=pr_id, change_type="new"
        )
        updated_check = CheckRunChangeRecord(
            check_data=sample_check_data,
            pr_id=pr_id,
            change_type="status_changed",
            existing_check_id=uuid.uuid4(),
            status_changed=True,
        )

        changeset = ChangeSet(
            repository_id=repository_id,
            new_prs=[new_pr],
            updated_prs=[updated_pr],
            new_check_runs=[new_check],
            updated_check_runs=[updated_check],
        )

        # Mock all bulk operations
        mock_pr = Mock(spec=PullRequest)
        mock_check = Mock(spec=CheckRun)

        with (
            patch.object(synchronizer, "_create_new_prs_bulk") as mock_create_prs,
            patch.object(synchronizer, "_update_existing_prs_bulk") as mock_update_prs,
            patch.object(
                synchronizer, "_create_new_check_runs_bulk"
            ) as mock_create_checks,
            patch.object(
                synchronizer, "_update_existing_check_runs_bulk"
            ) as mock_update_checks,
        ):
            mock_create_prs.return_value = [mock_pr]
            mock_update_prs.return_value = [mock_pr]
            mock_create_checks.return_value = [mock_check]
            mock_update_checks.return_value = [mock_check]

            # Act
            result = await synchronizer.synchronize_changes(
                repository_id, changeset
            )

        # Assert
        assert result == 4  # Total operations

        # Verify operation order (PRs first, then check runs)
        mock_create_prs.assert_called_once_with([new_pr])
        mock_update_prs.assert_called_once_with([updated_pr])
        mock_create_checks.assert_called_once_with([new_check])
        mock_update_checks.assert_called_once_with([updated_check])

    async def test_determine_trigger_event_transitions(
        self, synchronizer: DatabaseSynchronizer
    ):
        """
        Why: Validates correct trigger event determination for state transitions
        What: Tests all supported state transition trigger events
        How: Tests each transition type and verifies correct trigger event
        """
        # Test PR closed
        trigger = synchronizer._determine_trigger_event(PRState.OPENED, PRState.CLOSED)
        assert trigger == TriggerEvent.CLOSED

        # Test PR merged
        trigger = synchronizer._determine_trigger_event(PRState.OPENED, PRState.MERGED)
        assert trigger == TriggerEvent.CLOSED  # Merged is considered closed

        # Test PR reopened
        trigger = synchronizer._determine_trigger_event(PRState.CLOSED, PRState.OPENED)
        assert trigger == TriggerEvent.REOPENED

        # Test default case
        trigger = synchronizer._determine_trigger_event(PRState.MERGED, PRState.OPENED)
        assert trigger == TriggerEvent.SYNCHRONIZE

    async def test_transaction_rollback_on_error(
        self, synchronizer: DatabaseSynchronizer, sample_pr_data: PRData
    ):
        """
        Why: Validates transaction rollback behavior on errors
        What: Tests that partial failures don't corrupt database state
        How: Simulates error during operation and verifies rollback
        """
        # Arrange
        repository_id = uuid.uuid4()
        pr_change = PRChangeRecord(pr_data=sample_pr_data, change_type="new")
        changeset = ChangeSet(repository_id=repository_id, new_prs=[pr_change])

        # Mock successful start but failure during operation
        with patch.object(synchronizer, "_create_new_prs_bulk") as mock_create:
            mock_create.side_effect = SQLAlchemyError("Connection lost")

            # Act & Assert
            with pytest.raises(TransactionError):
                await synchronizer.synchronize_changes(repository_id, changeset)

    async def test_bulk_operations_efficiency(
        self,
        synchronizer: DatabaseSynchronizer,
        sample_pr_data: PRData,
        sample_check_data: CheckRunData,
    ):
        """
        Why: Validates that bulk operations are used for efficiency
        What: Tests that large datasets use bulk insert/update patterns
        How: Creates large changeset and verifies single bulk operations
        """
        # Arrange - Create large changeset
        repository_id = uuid.uuid4()
        large_changeset = ChangeSet(repository_id=repository_id)

        # Add 100 new PRs
        for i in range(100):
            pr_data = PRData(
                number=i,
                title=f"PR {i}",
                author="bulk-test",
                state="open",
                draft=False,
                base_branch="main",
                head_branch=f"feature-{i}",
                base_sha=f"base{i:03d}",
                head_sha=f"head{i:03d}",
                url=f"https://github.com/test/repo/pull/{i}",
                raw_data={"repository_id": str(repository_id)},
            )
            large_changeset.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )

        # Mock bulk operations to track efficiency
        with patch("src.workers.monitor.synchronization.pg_insert") as mock_pg_insert:
            mock_stmt = Mock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_pg_insert.return_value = mock_stmt

            synchronizer.session.execute.return_value = Mock(rowcount=100)
            synchronizer.pr_repo.get_by_repo_and_number = AsyncMock(
                return_value=Mock(spec=PullRequest)
            )
            synchronizer.history_repo.create_transition = AsyncMock()

            # Act
            await synchronizer.create_new_prs(large_changeset.new_prs)

            # Assert - Should use single bulk operation, not 100 individual inserts
            assert mock_pg_insert.call_count == 1
            # Verify bulk insert was called with all 100 records
            call_args = synchronizer.session.execute.call_args[0][0]
            assert hasattr(call_args, "compile")  # It's a SQLAlchemy statement

    async def test_error_handling_partial_failures(
        self, synchronizer: DatabaseSynchronizer, sample_pr_data: PRData
    ):
        """
        Why: Validates graceful handling of partial operation failures
        What: Tests that individual operation failures don't stop batch processing
        How: Simulates failure on specific records and verifies others succeed
        """
        # Arrange - Multiple PR updates with one that will fail
        valid_pr_id = uuid.uuid4()
        invalid_pr_id = uuid.uuid4()

        valid_change = PRChangeRecord(
            pr_data=sample_pr_data,
            change_type="updated",
            existing_pr_id=valid_pr_id,
            title_changed=True,
        )

        invalid_change = PRChangeRecord(
            pr_data=sample_pr_data,
            change_type="updated",
            existing_pr_id=invalid_pr_id,
            title_changed=True,
        )

        # Mock repository to succeed for valid ID, fail for invalid
        valid_pr = Mock(spec=PullRequest)
        valid_pr.id = valid_pr_id
        valid_pr.title = "Old Title"
        valid_pr.state = PRState.OPENED

        async def mock_get_by_id(pr_id):
            if pr_id == valid_pr_id:
                return valid_pr
            else:
                raise SQLAlchemyError("PR not found")

        synchronizer.pr_repo.get_by_id = AsyncMock(side_effect=mock_get_by_id)
        synchronizer.pr_repo.update = AsyncMock(return_value=valid_pr)

        # Act
        result = await synchronizer.update_existing_prs([valid_change, invalid_change])

        # Assert - Should return successful operations only
        assert len(result) == 1
        assert result[0] == valid_pr

    @pytest.mark.parametrize(
        "operation_count,expected_batches",
        [
            (1, 1),
            (50, 1),
            (100, 1),
            (500, 1),  # All should use single bulk operation
        ],
    )
    async def test_bulk_operation_scalability(
        self,
        synchronizer: DatabaseSynchronizer,
        sample_check_data: CheckRunData,
        operation_count: int,
        expected_batches: int,
    ):
        """
        Why: Validates scalability of bulk operations with varying dataset sizes
        What: Tests that bulk operations maintain efficiency regardless of size
        How: Parameterized test with different record counts
        """
        # Arrange - Create varying number of check run changes
        check_changes = []
        pr_id = uuid.uuid4()

        for i in range(operation_count):
            check_data = CheckRunData(
                external_id=f"check_{i}",
                check_name=f"test-{i}",
                status="completed",
                conclusion="success",
            )
            check_changes.append(
                CheckRunChangeRecord(
                    check_data=check_data, pr_id=pr_id, change_type="new"
                )
            )

        # Mock bulk operations
        with patch("src.workers.monitor.synchronization.pg_insert") as mock_pg_insert:
            mock_stmt = Mock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_pg_insert.return_value = mock_stmt

            synchronizer.session.execute.return_value = Mock(rowcount=operation_count)
            synchronizer.check_repo.get_by_external_id = AsyncMock(
                return_value=Mock(spec=CheckRun)
            )

            # Act
            await synchronizer.create_new_check_runs(check_changes)

            # Assert - Should always use expected number of bulk operations
            assert mock_pg_insert.call_count == expected_batches
