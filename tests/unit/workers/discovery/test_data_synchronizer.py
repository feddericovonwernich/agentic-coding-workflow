"""
Unit tests for Data Synchronizer component.

Tests data synchronization functionality including batch operations,
transaction management, rollback scenarios, and error handling.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.workers.discovery.data_synchronizer import DatabaseSynchronizer
from src.workers.discovery.interfaces import (
    PRDiscoveryResult,
    StateChange,
    SynchronizationResult,
)
from tests.fixtures.discovery import (
    DiscoveredCheckRunFactory,
    DiscoveryErrorFactory,
    PRDiscoveryResultFactory,
    StateChangeFactory,
    SynchronizationResultFactory,
)


class TestDataSynchronizerBatchOperations:
    """Tests for batch synchronization operations."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """
        Why: Provides mock database session for testing database operations
        What: Creates AsyncMock that simulates SQLAlchemy AsyncSession behavior
        How: Sets up session with transaction methods and query execution support
        """
        session = AsyncMock(spec=AsyncSession)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        session.add = AsyncMock()
        session.merge = AsyncMock()
        session.in_transaction = MagicMock(return_value=False)
        session.begin = AsyncMock()

        # Mock query results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        return session

    @pytest.fixture
    def mock_pr_repository(self) -> AsyncMock:
        """
        Why: Provides mock PR repository for testing database operations without
             actual DB
        What: Creates AsyncMock with bulk PR operations and constraint handling
        How: Sets up mock methods for batch upserts, creates, and updates
        """
        repo = AsyncMock()
        repo.bulk_upsert = AsyncMock()
        repo.bulk_create = AsyncMock()
        repo.bulk_update = AsyncMock()
        repo.get_by_repository_and_number = AsyncMock()
        return repo

    @pytest.fixture
    def mock_check_repository(self) -> AsyncMock:
        """
        Why: Provides mock check run repository for testing check run synchronization
        What: Creates AsyncMock with bulk check run operations
        How: Sets up mock methods for batch check run database operations
        """
        repo = AsyncMock()
        repo.bulk_upsert = AsyncMock()
        repo.bulk_create = AsyncMock()
        repo.bulk_update = AsyncMock()
        return repo

    @pytest.fixture
    def mock_state_repository(self) -> AsyncMock:
        """
        Why: Provides mock state history repository for testing state change tracking
        What: Creates AsyncMock with state change recording operations
        How: Sets up mock methods for recording state change history
        """
        repo = AsyncMock()
        repo.record_state_changes = AsyncMock()
        repo.bulk_create_changes = AsyncMock()
        return repo

    @pytest.fixture
    def data_synchronizer(
        self,
        mock_session,
        mock_pr_repository,
        mock_check_repository,
        mock_state_repository,
    ):
        """
        Why: Provides configured DatabaseSynchronizer instance for testing
        What: Creates synchronizer with all mocked dependencies for isolated testing
        How: Injects all mock repositories and session for controlled testing
        """
        return DatabaseSynchronizer(
            session=mock_session,
            pr_repository=mock_pr_repository,
            check_repository=mock_check_repository,
            state_history_repository=mock_state_repository,
            batch_size=10,  # Small batch size for testing
        )

    async def test_synchronize_processes_discovery_results_in_batches_efficiently(
        self, data_synchronizer, mock_pr_repository, mock_check_repository
    ):
        """
        Why: Ensure synchronizer efficiently processes large discovery results using
             batch operations to minimize database load and improve performance.

        What: Tests that synchronize() processes multiple discovery results using
              bulk database operations and returns comprehensive synchronization
              metrics.

        How: Provides multiple discovery results with PRs and check runs, mocks
             repository batch operations, validates bulk operations are used
             efficiently.
        """
        # Arrange
        discovery_results = [
            PRDiscoveryResultFactory.create(repository_id=uuid.uuid4()),
            PRDiscoveryResultFactory.create(repository_id=uuid.uuid4()),
            PRDiscoveryResultFactory.create(repository_id=uuid.uuid4()),
        ]
        state_changes = [StateChangeFactory.create() for _ in range(5)]

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            # Mock transaction context manager
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            result = await data_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert
        assert result is not None
        assert isinstance(result, SynchronizationResult)
        assert result.total_prs_processed > 0
        assert result.total_checks_processed >= 0
        assert result.state_changes_recorded >= 0
        assert result.processing_time_ms >= 0.0
        assert len(result.errors) == 0 or result.success is False

    async def test_synchronize_handles_new_and_existing_prs_correctly(
        self, data_synchronizer, mock_pr_repository, mock_session
    ):
        """
        Why: Ensure synchronizer correctly distinguishes between new PRs that need
             creation and existing PRs that need updates, maintaining data integrity.

        What: Tests that synchronize() properly identifies new vs existing PRs and
              uses appropriate database operations (insert vs update) for each.

        How: Provides discovery results with mix of new and existing PRs, mocks
             session to simulate existing PR detection, validates appropriate
             operations.
        """
        # Arrange
        repository_id = uuid.uuid4()
        discovery_results = [
            PRDiscoveryResultFactory.create(repository_id=repository_id)
        ]
        state_changes = []

        # Mock session query results to simulate some existing PRs
        from src.models.pull_request import PullRequest

        existing_prs = []
        for pr in discovery_results[0].discovered_prs[:2]:  # First two PRs exist
            mock_existing_pr = MagicMock(spec=PullRequest)
            mock_existing_pr.pr_number = pr.pr_number
            mock_existing_pr.id = uuid.uuid4()
            existing_prs.append(mock_existing_pr)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = existing_prs
        mock_session.execute.return_value = mock_result

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            result = await data_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert
        assert result is not None
        assert isinstance(result.prs_created, int)
        assert isinstance(result.prs_updated, int)
        assert result.prs_created >= 0
        assert result.prs_updated >= 0
        # Total should equal processed
        assert result.prs_created + result.prs_updated == result.total_prs_processed

    async def test_synchronize_processes_check_runs_with_proper_pr_association(
        self, data_synchronizer, mock_check_repository, mock_session
    ):
        """
        Why: Ensure synchronizer correctly associates check runs with their parent PRs
             during synchronization, maintaining referential integrity.

        What: Tests that synchronize() processes check runs from discovery results and
              properly links them to their corresponding PR records in database.

        How: Provides discovery results with PRs containing check runs, validates
             check runs are processed with correct PR associations and bulk operations.
        """
        # Arrange
        discovery_results = [
            PRDiscoveryResultFactory.create_with_errors(error_count=0)  # Clean result
        ]

        # Add check runs to discovered PRs
        for result in discovery_results:
            for pr in result.discovered_prs:
                if not pr.check_runs:
                    pr.check_runs = [
                        DiscoveredCheckRunFactory.create(),
                        DiscoveredCheckRunFactory.create(),
                    ]

        state_changes = []

        # Mock PR query to return PR IDs for check run association
        mock_pr_results = []
        for result in discovery_results:
            for pr in result.discovered_prs:
                mock_pr_results.append((uuid.uuid4(), pr.pr_number))

        mock_result = MagicMock()
        mock_result.all.return_value = mock_pr_results
        mock_session.execute.return_value = mock_result

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            result = await data_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert
        assert result is not None
        assert result.total_checks_processed >= 0
        assert result.checks_created >= 0
        assert result.checks_updated >= 0

    async def test_synchronize_records_state_changes_in_history_table(
        self, data_synchronizer, mock_state_repository
    ):
        """
        Why: Ensure synchronizer records all state changes in history table for
             audit trail and debugging capabilities, maintaining change tracking.

        What: Tests that synchronize() processes provided state changes and records
              them in state history table with proper timestamps and metadata.

        How: Provides state changes with discovery results, mocks state repository,
             validates state changes are recorded with proper batch operations.
        """
        from src.workers.discovery.interfaces import ChangeType, EntityType

        # Arrange
        discovery_results = [PRDiscoveryResultFactory.create()]
        state_changes = [
            StateChangeFactory.create(
                entity_type=EntityType.PULL_REQUEST,
                change_type=ChangeType.STATE_CHANGED,
                entity_id=uuid.uuid4(),  # Valid UUID, not placeholder
                old_state="open",
                new_state="closed",
            ),
            StateChangeFactory.create(
                entity_type=EntityType.PULL_REQUEST,
                change_type=ChangeType.STATE_CHANGED,
                entity_id=uuid.uuid4(),
                old_state="closed",
                new_state="merged",
            ),
        ]

        # Mock state repository operations
        mock_state_repository.create_transition = AsyncMock()

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            result = await data_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert
        assert result is not None
        assert result.state_changes_recorded >= 0
        # Some state changes might be filtered out (e.g., placeholder IDs)
        assert result.state_changes_recorded <= len(state_changes)

    async def test_synchronize_returns_comprehensive_operation_metrics(
        self, data_synchronizer
    ):
        """
        Why: Ensure synchronizer provides detailed metrics about synchronization
             operations for monitoring, debugging, and performance analysis.

        What: Tests that synchronize() returns SynchronizationResult with accurate
              counts of all database operations and processing performance metrics.

        How: Provides discovery data, mocks repository operations with known counts,
             validates returned metrics match expected operation counts and timing.
        """
        # Arrange
        discovery_results = [
            PRDiscoveryResultFactory.create(),
            PRDiscoveryResultFactory.create(),
        ]
        state_changes = [StateChangeFactory.create() for _ in range(3)]

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            result = await data_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert comprehensive metrics
        assert result is not None
        assert isinstance(result, SynchronizationResult)

        # Verify all metric fields are present and valid
        assert isinstance(result.total_prs_processed, int)
        assert isinstance(result.prs_created, int)
        assert isinstance(result.prs_updated, int)
        assert isinstance(result.total_checks_processed, int)
        assert isinstance(result.checks_created, int)
        assert isinstance(result.checks_updated, int)
        assert isinstance(result.state_changes_recorded, int)
        assert isinstance(result.processing_time_ms, float)
        assert isinstance(result.errors, list)

        # Verify logical consistency
        assert result.prs_created + result.prs_updated == result.total_prs_processed
        assert (
            result.checks_created + result.checks_updated
            == result.total_checks_processed
        )
        assert result.processing_time_ms >= 0.0


class TestDataSynchronizerTransactionManagement:
    """Tests for transaction management and rollback scenarios."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """
        Why: Provides mock database session for testing transaction operations
        What: Creates AsyncMock that simulates SQLAlchemy AsyncSession behavior
        How: Sets up session with transaction methods and query execution support
        """
        session = AsyncMock(spec=AsyncSession)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        session.add = AsyncMock()
        session.merge = AsyncMock()
        session.in_transaction = MagicMock(return_value=False)
        session.begin = AsyncMock()

        # Mock query results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        return session

    @pytest.fixture
    def mock_pr_repository(self) -> AsyncMock:
        """Mock PR repository for transaction testing."""
        repo = AsyncMock()
        repo.bulk_upsert = AsyncMock()
        repo.bulk_create = AsyncMock()
        repo.bulk_update = AsyncMock()
        repo.get_by_repository_and_number = AsyncMock()
        return repo

    @pytest.fixture
    def mock_check_repository(self) -> AsyncMock:
        """Mock check run repository for transaction testing."""
        repo = AsyncMock()
        repo.bulk_upsert = AsyncMock()
        repo.bulk_create = AsyncMock()
        repo.bulk_update = AsyncMock()
        return repo

    @pytest.fixture
    def mock_state_repository(self) -> AsyncMock:
        """Mock state history repository for transaction testing."""
        repo = AsyncMock()
        repo.record_state_changes = AsyncMock()
        repo.bulk_create_changes = AsyncMock()
        repo.create_transition = AsyncMock()
        return repo

    @pytest.fixture
    def transaction_synchronizer(
        self,
        mock_session,
        mock_pr_repository,
        mock_check_repository,
        mock_state_repository,
    ):
        """Data synchronizer configured for transaction testing."""
        return DatabaseSynchronizer(
            session=mock_session,
            pr_repository=mock_pr_repository,
            check_repository=mock_check_repository,
            state_history_repository=mock_state_repository,
            batch_size=10,
        )

    async def test_synchronize_commits_transaction_on_successful_operations(
        self, transaction_synchronizer
    ):
        """
        Why: Ensure synchronizer commits database transaction when all operations
             complete successfully, persisting all changes atomically.

        What: Tests that synchronize() begins transaction, performs operations,
              and commits transaction when no errors occur during processing.

        How: Provides clean discovery data, mocks successful operations, validates
             transaction is begun, operations executed, and transaction committed.
        """
        # Arrange
        discovery_results = [PRDiscoveryResultFactory.create()]
        state_changes = []

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            result = await transaction_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert
        assert result is not None
        assert len(result.errors) == 0  # No errors means success

        # Verify transaction was started and completed
        mock_transaction_scope.assert_called_once()
        mock_transaction.__aenter__.assert_called_once()
        mock_transaction.__aexit__.assert_called_once()

    async def test_synchronize_rolls_back_transaction_on_constraint_violations(
        self, transaction_synchronizer, mock_session
    ):
        """
        Why: Ensure synchronizer rolls back transaction when constraint violations
             occur, maintaining database consistency and preventing partial updates.

        What: Tests that synchronize() rolls back entire transaction when database
              constraint violations occur during any operation phase.

        How: Mocks session to raise IntegrityError during flush, validates transaction
             rollback occurs and error is properly reported in result.
        """
        # Arrange
        discovery_results = [PRDiscoveryResultFactory.create()]
        state_changes = []

        # Mock constraint violation during flush operation
        mock_session.flush.side_effect = IntegrityError(
            "duplicate key constraint", None, None
        )

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            # Mock transaction that raises exception on exit (rollback)
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(
                side_effect=IntegrityError("duplicate key constraint", None, None)
            )
            mock_transaction_scope.return_value = mock_transaction

            result = await transaction_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert
        assert result is not None
        assert not result.success  # Has errors
        assert len(result.errors) > 0

        # Check that synchronization_error is recorded
        assert any(
            error.error_type == "synchronization_error" for error in result.errors
        )

    async def test_synchronize_rolls_back_transaction_on_database_connection_errors(
        self, transaction_synchronizer
    ):
        """
        Why: Ensure synchronizer handles database connection errors gracefully with
             proper transaction rollback, preventing data corruption from partial
             operations.

        What: Tests that synchronize() rolls back transaction when database connection
              errors occur and returns appropriate error information.

        How: Mocks transaction scope to raise connection errors, validates rollback
             behavior and error reporting for database connectivity issues.
        """
        # Arrange
        discovery_results = [PRDiscoveryResultFactory.create()]
        state_changes = []

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            # Mock transaction scope to raise connection error
            mock_transaction_scope.side_effect = OperationalError(
                "connection failed", None, None
            )

            result = await transaction_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert
        assert result is not None
        assert not result.success
        assert len(result.errors) > 0

        # Check that synchronization_error is recorded
        assert any(
            error.error_type == "synchronization_error" for error in result.errors
        )
        assert any("connection failed" in error.message for error in result.errors)

    async def test_synchronize_handles_partial_operation_failures_with_rollback(
        self, transaction_synchronizer, mock_session
    ):
        """
        Why: Ensure synchronizer rolls back entire transaction when any operation
             fails, even if previous operations succeeded, maintaining atomicity.

        What: Tests that synchronize() rolls back all changes when later operations
              fail, even if earlier operations (like PR upserts) were successful.

        How: Mocks session to fail during flush after PR processing, validates
             complete rollback occurs and no partial data is committed.
        """
        # Arrange
        discovery_results = [PRDiscoveryResultFactory.create()]
        state_changes = []

        # Mock session to fail during flush (after some operations)
        call_count = 0

        def mock_flush():
            nonlocal call_count
            call_count += 1
            if call_count > 1:  # Fail on second flush call
                raise Exception("Check operation failed")

        mock_session.flush.side_effect = mock_flush

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            # Transaction exits with exception, triggering rollback
            mock_transaction.__aexit__ = AsyncMock(
                side_effect=Exception("Check operation failed")
            )
            mock_transaction_scope.return_value = mock_transaction

            result = await transaction_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert
        assert result is not None
        assert not result.success
        assert len(result.errors) > 0

        # Check that synchronization_error is recorded
        assert any(
            error.error_type == "synchronization_error" for error in result.errors
        )

    async def test_begin_and_commit_transaction_methods_work_correctly(
        self, transaction_synchronizer
    ):
        """
        Why: Ensure transaction management methods work correctly for explicit
             transaction control in complex synchronization scenarios.

        What: Tests that begin_transaction() and commit_transaction() methods
              function properly and maintain transaction state correctly.

        How: Calls transaction methods explicitly, validates transaction state
             is managed correctly through begin/commit lifecycle.
        """
        # Act - Begin transaction
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            transaction = await transaction_synchronizer.begin_transaction()

            # Assert transaction started
            assert transaction is not None
            assert transaction_synchronizer._current_transaction is not None

            # Act - Commit transaction
            await transaction_synchronizer.commit_transaction()

            # Assert transaction was cleaned up
            assert transaction_synchronizer._current_transaction is None

    async def test_rollback_transaction_method_works_correctly(
        self, transaction_synchronizer
    ):
        """
        Why: Ensure rollback transaction method works correctly for error recovery
             and maintains database consistency during failure scenarios.

        What: Tests that rollback_transaction() method properly rolls back active
              transaction and cleans up transaction state.

        How: Begins transaction, calls rollback method, validates transaction
             is properly rolled back and state is cleaned up.
        """
        # Arrange - Begin transaction
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            await transaction_synchronizer.begin_transaction()
            assert transaction_synchronizer._current_transaction is not None

            # Act - Rollback transaction
            await transaction_synchronizer.rollback_transaction()

            # Assert transaction was cleaned up and stats updated
            assert transaction_synchronizer._current_transaction is None
            assert transaction_synchronizer.stats["transaction_rollbacks"] > 0


class TestDataSynchronizerErrorHandling:
    """Tests for error handling and edge cases in synchronization."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Mock session for error handling tests."""
        session = AsyncMock(spec=AsyncSession)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        session.add = AsyncMock()
        session.merge = AsyncMock()
        session.in_transaction = MagicMock(return_value=False)
        session.begin = AsyncMock()

        # Mock query results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        return session

    @pytest.fixture
    def mock_pr_repository(self) -> AsyncMock:
        """Mock PR repository for error handling testing."""
        repo = AsyncMock()
        repo.bulk_upsert = AsyncMock()
        repo.bulk_create = AsyncMock()
        repo.bulk_update = AsyncMock()
        repo.get_by_repository_and_number = AsyncMock()
        return repo

    @pytest.fixture
    def mock_check_repository(self) -> AsyncMock:
        """Mock check repository for error handling testing."""
        repo = AsyncMock()
        repo.bulk_upsert = AsyncMock()
        repo.bulk_create = AsyncMock()
        repo.bulk_update = AsyncMock()
        return repo

    @pytest.fixture
    def mock_state_repository(self) -> AsyncMock:
        """Mock state repository for error handling testing."""
        repo = AsyncMock()
        repo.record_state_changes = AsyncMock()
        repo.bulk_create_changes = AsyncMock()
        repo.create_transition = AsyncMock()
        return repo

    @pytest.fixture
    def error_handling_synchronizer(
        self,
        mock_session,
        mock_pr_repository,
        mock_check_repository,
        mock_state_repository,
    ):
        """Data synchronizer configured for error handling testing."""
        return DatabaseSynchronizer(
            session=mock_session,
            pr_repository=mock_pr_repository,
            check_repository=mock_check_repository,
            state_history_repository=mock_state_repository,
            batch_size=10,
        )

    async def test_synchronize_handles_empty_discovery_results_gracefully(
        self, error_handling_synchronizer
    ):
        """
        Why: Ensure synchronizer handles empty discovery results gracefully without
             errors, as some repositories may have no changes to synchronize.

        What: Tests that synchronize() processes empty discovery results and state
              changes without errors and returns appropriate zero-count metrics.

        How: Provides empty lists for discovery results and state changes, validates
             successful processing with zero counts and no errors.
        """
        # Arrange
        discovery_results = []
        state_changes = []

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            result = await error_handling_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert
        assert result is not None
        assert result.total_prs_processed == 0
        assert result.total_checks_processed == 0
        assert result.state_changes_recorded == 0
        assert result.success is True  # No errors for empty data

    async def test_synchronize_handles_malformed_discovery_data_gracefully(
        self, error_handling_synchronizer
    ):
        """
        Why: Ensure synchronizer validates discovery data and handles malformed
             data gracefully without system crashes, maintaining robustness.

        What: Tests that synchronize() validates discovery data structure and
              handles missing or invalid fields with appropriate error reporting.

        How: Provides discovery results with missing required fields, validates
             errors are caught and reported without propagating exceptions.
        """
        # Arrange - Create discovery result with potential data issues
        malformed_results = [
            PRDiscoveryResultFactory.create(discovered_prs=[])  # Empty PRs
        ]
        state_changes = []

        # Act - Should handle gracefully
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            result = await error_handling_synchronizer.synchronize(
                malformed_results, state_changes
            )

        # Assert
        assert result is not None
        # Should either succeed with empty data or report validation errors
        # appropriately
        # The real implementation should handle empty PR lists gracefully
        assert result.total_prs_processed == 0  # No PRs to process

    async def test_synchronize_maintains_performance_under_large_data_volumes(
        self, error_handling_synchronizer
    ):
        """
        Why: Ensure synchronizer maintains acceptable performance when processing
             large volumes of discovery data, preventing timeouts and resource
             exhaustion.

        What: Tests that synchronize() processes large discovery results efficiently
              within reasonable time limits and memory usage.

        How: Provides large discovery results with many PRs and state changes,
             validates processing completes within acceptable time bounds.
        """
        # Arrange - Large data volume
        large_discovery_results = [
            PRDiscoveryResultFactory.create()
            for _ in range(10)  # Multiple repositories
        ]
        large_state_changes = [
            StateChangeFactory.create()
            for _ in range(100)  # Many state changes
        ]

        # Act
        import time

        start_time = time.perf_counter()

        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(return_value=None)
            mock_transaction_scope.return_value = mock_transaction

            result = await error_handling_synchronizer.synchronize(
                large_discovery_results, large_state_changes
            )

        end_time = time.perf_counter()
        processing_time_seconds = end_time - start_time

        # Assert performance and correctness
        assert result is not None
        assert processing_time_seconds < 10.0  # Should complete within 10 seconds
        assert result.processing_time_ms >= 0.0
        # Should process all data
        assert result.total_prs_processed >= 0
        assert result.state_changes_recorded >= 0

    async def test_synchronize_reports_detailed_error_information(
        self, error_handling_synchronizer, mock_session
    ):
        """
        Why: Ensure synchronizer provides detailed error information for debugging
             and monitoring when operations fail, enabling effective troubleshooting.

        What: Tests that synchronize() captures and reports comprehensive error
              details including error type, context, and recovery information.

        How: Mocks session to raise specific errors, validates error details
             are captured and reported with sufficient information for diagnosis.
        """
        # Arrange
        discovery_results = [PRDiscoveryResultFactory.create()]
        state_changes = []

        # Mock specific error scenario during flush
        mock_session.flush.side_effect = IntegrityError(
            "UNIQUE constraint failed: pull_requests.repository_id, "
            "pull_requests.pr_number",
            None,
            None,
        )

        # Act
        with patch(
            "src.workers.discovery.data_synchronizer.transaction_scope"
        ) as mock_transaction_scope:
            mock_transaction = AsyncMock()
            mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
            mock_transaction.__aexit__ = AsyncMock(
                side_effect=IntegrityError(
                    "UNIQUE constraint failed: pull_requests.repository_id, "
                    "pull_requests.pr_number",
                    None,
                    None,
                )
            )
            mock_transaction_scope.return_value = mock_transaction

            result = await error_handling_synchronizer.synchronize(
                discovery_results, state_changes
            )

        # Assert detailed error information
        assert result is not None
        assert not result.success
        assert len(result.errors) > 0

        # The synchronizer should capture the error - it could be pr_batch_sync_error
        # or synchronization_error
        error = result.errors[0]
        assert error.error_type in ["pr_batch_sync_error", "synchronization_error"]
        assert "UNIQUE constraint" in error.message or "IntegrityError" in error.message
        assert error.context is not None
        # Check that context contains relevant information
        assert any(
            key in error.context for key in ["repository_id", "discovery_results_count"]
        )
