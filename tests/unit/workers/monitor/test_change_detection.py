"""Unit tests for change detection logic.

This module tests the change detection system that compares GitHub API data
with database state to identify new, updated, and state-changed PRs and check runs.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.enums import CheckConclusion, CheckStatus, PRState
from src.workers.monitor.change_detection import DatabaseChangeDetector
from src.workers.monitor.models import (
    ChangeSet,
    CheckRunChangeRecord,
    CheckRunData,
    PRChangeRecord,
    PRData,
)


class TestDatabaseChangeDetector:
    """Tests for DatabaseChangeDetector class."""

    @pytest.fixture
    def mock_pr_repository(self):
        """
        Why: Need isolated testing of change detection logic without database dependencies
        What: Creates mock PullRequestRepository for testing
        How: Uses AsyncMock to simulate repository interface
        """
        return AsyncMock()

    @pytest.fixture
    def mock_check_run_repository(self):
        """
        Why: Need isolated testing of check run change detection without database dependencies
        What: Creates mock CheckRunRepository for testing
        How: Uses AsyncMock to simulate repository interface
        """
        return AsyncMock()

    @pytest.fixture
    def change_detector(self, mock_pr_repository, mock_check_run_repository):
        """
        Why: Need consistent change detector instance for testing
        What: Creates DatabaseChangeDetector with mocked dependencies
        How: Injects mock repositories into detector
        """
        return DatabaseChangeDetector(mock_pr_repository, mock_check_run_repository)

    @pytest.fixture
    def sample_repository_id(self):
        """
        Why: Need consistent repository ID for testing
        What: Provides a sample UUID for repository identification
        How: Returns fixed UUID4
        """
        return uuid.uuid4()

    @pytest.fixture
    def sample_pr_data(self):
        """
        Why: Need realistic PR data for testing change detection
        What: Provides sample PRData object
        How: Returns PRData with typical GitHub PR structure
        """
        return PRData(
            number=123,
            title="Sample PR Title",
            author="testuser",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/test",
            base_sha="abc123",
            head_sha="def456",
            url="https://github.com/owner/repo/pull/123",
            body="Sample PR body",
            labels=["bug", "enhancement"],
            assignees=["assignee1"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_check_run_data(self):
        """
        Why: Need realistic check run data for testing change detection
        What: Provides sample CheckRunData object
        How: Returns CheckRunData with typical GitHub check structure
        """
        return CheckRunData(
            external_id="12345",
            check_name="CI Tests",
            status="completed",
            conclusion="success",
            details_url="https://github.com/owner/repo/runs/12345",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_existing_pr(self, sample_repository_id):
        """
        Why: Need mock database PR object for comparison testing
        What: Provides mock PR object matching database structure
        How: Creates MagicMock with PR properties
        """
        pr = MagicMock()
        pr.id = uuid.uuid4()
        pr.pr_number = 123
        pr.title = "Sample PR Title"
        pr.author = "testuser"
        pr.state = PRState.OPENED
        pr.draft = False
        pr.head_sha = "def456"
        pr.pr_metadata = {"labels": ["bug", "enhancement"], "assignees": ["assignee1"]}
        return pr

    @pytest.fixture
    def sample_existing_check_run(self):
        """
        Why: Need mock database check run object for comparison testing
        What: Provides mock check run object matching database structure
        How: Creates MagicMock with check run properties
        """
        check = MagicMock()
        check.id = uuid.uuid4()
        check.external_id = "12345"
        check.check_name = "CI Tests"
        check.status = CheckStatus.COMPLETED
        check.conclusion = CheckConclusion.SUCCESS
        check.started_at = datetime.now(timezone.utc)
        check.completed_at = datetime.now(timezone.utc)
        return check


class TestPRChangeDetection(TestDatabaseChangeDetector):
    """Tests for PR change detection functionality."""

    async def test_detect_new_pr_when_not_in_database(
        self, change_detector, sample_repository_id, sample_pr_data, mock_pr_repository
    ):
        """
        Why: Validates detection of completely new PRs not in database
        What: Tests new PR detection when database returns empty results
        How: Mocks empty database response and verifies new PR detection
        """
        # Arrange
        mock_pr_repository.get_recent_prs.return_value = []

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [sample_pr_data]
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].change_type == "new"
        assert changes[0].pr_data == sample_pr_data
        assert changes[0].existing_pr_id is None

    async def test_detect_pr_title_change(
        self,
        change_detector,
        sample_repository_id,
        sample_pr_data,
        sample_existing_pr,
        mock_pr_repository,
    ):
        """
        Why: Validates detection of PR title changes
        What: Tests title change detection by modifying PR data
        How: Sets up existing PR with different title and verifies change detection
        """
        # Arrange
        sample_existing_pr.title = "Old Title"
        mock_pr_repository.get_recent_prs.return_value = [sample_existing_pr]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [sample_pr_data]
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].change_type == "updated"
        assert changes[0].title_changed is True
        assert changes[0].old_title == "Old Title"

    async def test_detect_pr_state_change(
        self,
        change_detector,
        sample_repository_id,
        sample_pr_data,
        sample_existing_pr,
        mock_pr_repository,
    ):
        """
        Why: Validates detection of PR state changes (open -> closed, etc.)
        What: Tests state change detection by modifying PR state
        How: Sets up existing PR with different state and verifies change detection
        """
        # Arrange
        sample_existing_pr.state = PRState.CLOSED
        mock_pr_repository.get_recent_prs.return_value = [sample_existing_pr]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [sample_pr_data]
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].state_changed is True
        assert changes[0].old_state == PRState.CLOSED

    async def test_detect_pr_draft_status_change(
        self,
        change_detector,
        sample_repository_id,
        sample_pr_data,
        sample_existing_pr,
        mock_pr_repository,
    ):
        """
        Why: Validates detection of PR draft status changes
        What: Tests draft status change detection
        How: Sets up existing PR with different draft status and verifies detection
        """
        # Arrange
        sample_existing_pr.draft = True  # Existing is draft
        # sample_pr_data.draft is False by default
        mock_pr_repository.get_recent_prs.return_value = [sample_existing_pr]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [sample_pr_data]
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].draft_changed is True

    async def test_detect_pr_sha_change_new_commits(
        self,
        change_detector,
        sample_repository_id,
        sample_pr_data,
        sample_existing_pr,
        mock_pr_repository,
    ):
        """
        Why: Validates detection of new commits (SHA changes)
        What: Tests SHA change detection when new commits are pushed
        How: Sets up existing PR with different head SHA and verifies detection
        """
        # Arrange
        sample_existing_pr.head_sha = "oldsha123"
        mock_pr_repository.get_recent_prs.return_value = [sample_existing_pr]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [sample_pr_data]
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].sha_changed is True
        assert changes[0].old_head_sha == "oldsha123"

    async def test_detect_pr_metadata_change_labels(
        self,
        change_detector,
        sample_repository_id,
        sample_pr_data,
        sample_existing_pr,
        mock_pr_repository,
    ):
        """
        Why: Validates detection of PR metadata changes (labels, assignees, etc.)
        What: Tests metadata change detection for labels
        How: Sets up existing PR with different labels and verifies detection
        """
        # Arrange
        sample_existing_pr.pr_metadata = {"labels": ["old-label"], "assignees": []}
        mock_pr_repository.get_recent_prs.return_value = [sample_existing_pr]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [sample_pr_data]
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].metadata_changed is True

    async def test_no_changes_when_pr_identical(
        self,
        change_detector,
        sample_repository_id,
        sample_pr_data,
        sample_existing_pr,
        mock_pr_repository,
    ):
        """
        Why: Validates that identical PRs don't generate false positive changes
        What: Tests that no changes are detected when PR data matches database
        How: Sets up identical PR data and database state, verifies no changes
        """
        # Arrange - all fields already match between sample_pr_data and sample_existing_pr
        mock_pr_repository.get_recent_prs.return_value = [sample_existing_pr]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [sample_pr_data]
        )

        # Assert
        assert len(changes) == 0

    async def test_empty_pr_list_returns_empty_changes(
        self, change_detector, sample_repository_id, mock_pr_repository
    ):
        """
        Why: Validates handling of empty input (edge case)
        What: Tests that empty PR list returns empty changes
        How: Passes empty list and verifies empty result
        """
        # Act
        changes = await change_detector.detect_pr_changes(sample_repository_id, [])

        # Assert
        assert changes == []
        # Should not even call the repository
        mock_pr_repository.get_recent_prs.assert_not_called()

    async def test_database_error_handling_fallback_to_empty(
        self, change_detector, sample_repository_id, sample_pr_data, mock_pr_repository
    ):
        """
        Why: Validates graceful handling of database errors
        What: Tests fallback behavior when database queries fail
        How: Mocks repository to raise exception and verifies graceful handling
        """
        # Arrange
        mock_pr_repository.get_recent_prs.side_effect = Exception("Database error")

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [sample_pr_data]
        )

        # Assert - should treat as new PR when database fails
        assert len(changes) == 1
        assert changes[0].change_type == "new"


class TestCheckRunChangeDetection(TestDatabaseChangeDetector):
    """Tests for check run change detection functionality."""

    async def test_detect_new_check_run(
        self,
        change_detector,
        sample_check_run_data,
        mock_check_run_repository,
    ):
        """
        Why: Validates detection of completely new check runs
        What: Tests new check run detection when not in database
        How: Sets up PR changes with existing PR ID and verifies new check detection
        """
        # Arrange
        pr_id = uuid.uuid4()
        pr_change = PRChangeRecord(
            pr_data=MagicMock(),
            change_type="updated",
            existing_pr_id=pr_id,
        )
        pr_change.pr_data.number = 123

        mock_check_run_repository.get_all_for_pr.return_value = []
        check_runs_by_pr = {123: [sample_check_run_data]}

        # Act
        changes = await change_detector.detect_check_run_changes(
            [pr_change], check_runs_by_pr
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].change_type == "new"
        assert changes[0].check_data == sample_check_run_data
        assert changes[0].pr_id == pr_id

    async def test_detect_check_run_status_change(
        self,
        change_detector,
        sample_check_run_data,
        sample_existing_check_run,
        mock_check_run_repository,
    ):
        """
        Why: Validates detection of check run status changes
        What: Tests status change detection (queued -> in_progress -> completed)
        How: Sets up existing check with different status and verifies change detection
        """
        # Arrange
        pr_id = uuid.uuid4()
        pr_change = PRChangeRecord(
            pr_data=MagicMock(),
            change_type="updated",
            existing_pr_id=pr_id,
        )
        pr_change.pr_data.number = 123

        # Existing check is in progress, new data shows completed
        sample_existing_check_run.status = CheckStatus.IN_PROGRESS
        mock_check_run_repository.get_all_for_pr.return_value = [
            sample_existing_check_run
        ]

        check_runs_by_pr = {123: [sample_check_run_data]}

        # Act
        changes = await change_detector.detect_check_run_changes(
            [pr_change], check_runs_by_pr
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].status_changed is True
        assert changes[0].old_status == CheckStatus.IN_PROGRESS

    async def test_detect_check_run_conclusion_change(
        self,
        change_detector,
        sample_check_run_data,
        sample_existing_check_run,
        mock_check_run_repository,
    ):
        """
        Why: Validates detection of check run conclusion changes
        What: Tests conclusion change detection (success -> failure)
        How: Sets up existing check with different conclusion and verifies detection
        """
        # Arrange
        pr_id = uuid.uuid4()
        pr_change = PRChangeRecord(
            pr_data=MagicMock(),
            change_type="updated",
            existing_pr_id=pr_id,
        )
        pr_change.pr_data.number = 123

        # Existing check failed, new data shows success
        sample_existing_check_run.conclusion = CheckConclusion.FAILURE
        mock_check_run_repository.get_all_for_pr.return_value = [
            sample_existing_check_run
        ]

        check_runs_by_pr = {123: [sample_check_run_data]}

        # Act
        changes = await change_detector.detect_check_run_changes(
            [pr_change], check_runs_by_pr
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].conclusion_changed is True
        assert changes[0].old_conclusion == CheckConclusion.FAILURE

    async def test_detect_check_run_timing_change(
        self,
        change_detector,
        sample_check_run_data,
        sample_existing_check_run,
        mock_check_run_repository,
    ):
        """
        Why: Validates detection of check run timing changes
        What: Tests timing change detection (started_at, completed_at)
        How: Sets up existing check with different timing and verifies detection
        """
        # Arrange
        pr_id = uuid.uuid4()
        pr_change = PRChangeRecord(
            pr_data=MagicMock(),
            change_type="updated",
            existing_pr_id=pr_id,
        )
        pr_change.pr_data.number = 123

        # Existing check has no completion time, new data has completion time
        sample_existing_check_run.completed_at = None
        mock_check_run_repository.get_all_for_pr.return_value = [
            sample_existing_check_run
        ]

        check_runs_by_pr = {123: [sample_check_run_data]}

        # Act
        changes = await change_detector.detect_check_run_changes(
            [pr_change], check_runs_by_pr
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].timing_changed is True

    async def test_no_changes_when_check_run_identical(
        self,
        change_detector,
        sample_check_run_data,
        sample_existing_check_run,
        mock_check_run_repository,
    ):
        """
        Why: Validates that identical check runs don't generate false positive changes
        What: Tests that no changes are detected when check run data matches database
        How: Sets up identical check run data and database state, verifies no changes
        """
        # Arrange
        pr_id = uuid.uuid4()
        pr_change = PRChangeRecord(
            pr_data=MagicMock(),
            change_type="updated",
            existing_pr_id=pr_id,
        )
        pr_change.pr_data.number = 123

        # Make sure the existing check run has identical values to sample_check_run_data
        sample_existing_check_run.started_at = sample_check_run_data.started_at
        sample_existing_check_run.completed_at = sample_check_run_data.completed_at

        mock_check_run_repository.get_all_for_pr.return_value = [
            sample_existing_check_run
        ]
        check_runs_by_pr = {123: [sample_check_run_data]}

        # Act
        changes = await change_detector.detect_check_run_changes(
            [pr_change], check_runs_by_pr
        )

        # Assert
        assert len(changes) == 0

    async def test_empty_check_runs_returns_empty_changes(
        self, change_detector, mock_check_run_repository
    ):
        """
        Why: Validates handling of empty input (edge case)
        What: Tests that empty check runs dict returns empty changes
        How: Passes empty dict and verifies empty result
        """
        # Act
        changes = await change_detector.detect_check_run_changes([], {})

        # Assert
        assert changes == []

    async def test_skip_check_runs_for_new_prs_without_ids(
        self, change_detector, sample_check_run_data
    ):
        """
        Why: Validates handling of new PRs that don't have database IDs yet
        What: Tests that check runs for new PRs are skipped
        How: Provides PR change without existing_pr_id and verifies skip
        """
        # Arrange
        pr_change = PRChangeRecord(
            pr_data=MagicMock(),
            change_type="new",
            existing_pr_id=None,  # New PR without database ID
        )
        pr_change.pr_data.number = 123
        check_runs_by_pr = {123: [sample_check_run_data]}

        # Act
        changes = await change_detector.detect_check_run_changes(
            [pr_change], check_runs_by_pr
        )

        # Assert
        assert changes == []


class TestChangesetCreation(TestDatabaseChangeDetector):
    """Tests for changeset creation functionality."""

    def test_create_changeset_organizes_changes_by_type(
        self, change_detector, sample_repository_id
    ):
        """
        Why: Validates proper organization of changes into changeset structure
        What: Tests changeset creation with mixed new and updated changes
        How: Creates various change records and verifies proper categorization
        """
        # Arrange
        new_pr_change = PRChangeRecord(
            pr_data=MagicMock(), change_type="new", existing_pr_id=None
        )
        updated_pr_change = PRChangeRecord(
            pr_data=MagicMock(), change_type="updated", existing_pr_id=uuid.uuid4()
        )
        new_check_change = CheckRunChangeRecord(
            check_data=MagicMock(),
            pr_id=uuid.uuid4(),
            change_type="new",
            existing_check_id=None,
        )
        updated_check_change = CheckRunChangeRecord(
            check_data=MagicMock(),
            pr_id=uuid.uuid4(),
            change_type="updated",
            existing_check_id=uuid.uuid4(),
        )

        pr_changes = [new_pr_change, updated_pr_change]
        check_changes = [new_check_change, updated_check_change]

        # Act
        changeset = change_detector.create_changeset(
            sample_repository_id, pr_changes, check_changes
        )

        # Assert
        assert changeset.repository_id == sample_repository_id
        assert len(changeset.new_prs) == 1
        assert len(changeset.updated_prs) == 1
        assert len(changeset.new_check_runs) == 1
        assert len(changeset.updated_check_runs) == 1

    def test_create_empty_changeset(self, change_detector, sample_repository_id):
        """
        Why: Validates handling of empty changes (edge case)
        What: Tests changeset creation with no changes
        How: Creates changeset with empty lists and verifies structure
        """
        # Act
        changeset = change_detector.create_changeset(sample_repository_id, [], [])

        # Assert
        assert changeset.repository_id == sample_repository_id
        assert len(changeset.new_prs) == 0
        assert len(changeset.updated_prs) == 0
        assert len(changeset.new_check_runs) == 0
        assert len(changeset.updated_check_runs) == 0
        assert not changeset.has_changes
        assert changeset.total_changes == 0

    def test_changeset_properties_calculate_correctly(
        self, change_detector, sample_repository_id
    ):
        """
        Why: Validates changeset property calculations for metrics
        What: Tests has_changes and total_changes properties
        How: Creates changeset with known number of changes and verifies calculations
        """
        # Arrange
        pr_changes = [
            PRChangeRecord(
                pr_data=MagicMock(), change_type="new", existing_pr_id=None
            ),
            PRChangeRecord(
                pr_data=MagicMock(), change_type="updated", existing_pr_id=uuid.uuid4()
            ),
        ]
        check_changes = [
            CheckRunChangeRecord(
                check_data=MagicMock(),
                pr_id=uuid.uuid4(),
                change_type="new",
                existing_check_id=None,
            )
        ]

        # Act
        changeset = change_detector.create_changeset(
            sample_repository_id, pr_changes, check_changes
        )

        # Assert
        assert changeset.has_changes is True
        assert changeset.total_changes == 3
        pr_ids = changeset.get_pr_ids_with_changes()
        assert len(pr_ids) >= 1  # At least the updated PR and check run PR


class TestEdgeCasesAndErrorHandling(TestDatabaseChangeDetector):
    """Tests for edge cases and error handling scenarios."""

    async def test_multiple_prs_mixed_changes_and_new(
        self, change_detector, sample_repository_id, mock_pr_repository
    ):
        """
        Why: Validates handling of mixed scenarios with multiple PRs
        What: Tests processing multiple PRs with some new, some changed, some unchanged
        How: Sets up complex scenario and verifies correct categorization
        """
        # Arrange - create multiple PR data objects
        pr_data_new = PRData(
            number=100,
            title="New PR",
            author="user1",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/new",
            base_sha="abc123",
            head_sha="new456",
            url="https://github.com/owner/repo/pull/100",
        )
        
        pr_data_changed = PRData(
            number=200,
            title="Changed Title",
            author="user2",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/changed",
            base_sha="abc123",
            head_sha="changed789",
            url="https://github.com/owner/repo/pull/200",
        )
        
        pr_data_unchanged = PRData(
            number=300,
            title="Unchanged PR",
            author="user3",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/unchanged",
            base_sha="abc123",
            head_sha="unchanged999",
            url="https://github.com/owner/repo/pull/300",
        )

        # Create corresponding existing PRs
        existing_pr_changed = MagicMock()
        existing_pr_changed.id = uuid.uuid4()
        existing_pr_changed.pr_number = 200
        existing_pr_changed.title = "Old Title"  # Different from pr_data_changed
        existing_pr_changed.author = "user2"
        existing_pr_changed.state = PRState.OPENED
        existing_pr_changed.draft = False
        existing_pr_changed.head_sha = "changed789"
        existing_pr_changed.pr_metadata = {
            "labels": [],  # Same as pr_data_changed.labels (empty by default)
            "assignees": [],  # Same as pr_data_changed.assignees (empty by default)  
            "milestone": None,  # Same as pr_data_changed.milestone (None by default)
        }

        existing_pr_unchanged = MagicMock()
        existing_pr_unchanged.id = uuid.uuid4()
        existing_pr_unchanged.pr_number = 300
        existing_pr_unchanged.title = "Unchanged PR"  # Same as pr_data_unchanged
        existing_pr_unchanged.author = "user3"
        existing_pr_unchanged.state = PRState.OPENED
        existing_pr_unchanged.draft = False
        existing_pr_unchanged.head_sha = "unchanged999"
        existing_pr_unchanged.pr_metadata = {
            "labels": [],  # Same as pr_data_unchanged.labels (empty by default)
            "assignees": [],  # Same as pr_data_unchanged.assignees (empty by default)
            "milestone": None,  # Same as pr_data_unchanged.milestone (None by default)
        }

        mock_pr_repository.get_recent_prs.return_value = [
            existing_pr_changed,
            existing_pr_unchanged,
        ]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [pr_data_new, pr_data_changed, pr_data_unchanged]
        )

        # Assert
        assert len(changes) == 2  # Only new and changed PRs
        change_types = {change.change_type for change in changes}
        assert "new" in change_types
        assert "updated" in change_types
        
        # Verify specific changes
        new_changes = [c for c in changes if c.change_type == "new"]
        updated_changes = [c for c in changes if c.change_type == "updated"]
        
        assert len(new_changes) == 1
        assert new_changes[0].pr_data.number == 100
        
        assert len(updated_changes) == 1
        assert updated_changes[0].pr_data.number == 200
        assert updated_changes[0].title_changed is True

    async def test_check_run_database_query_failure_handling(
        self, change_detector, mock_check_run_repository, sample_check_run_data
    ):
        """
        Why: Validates graceful handling of database errors during check run queries
        What: Tests error handling when check run repository queries fail
        How: Mocks repository to raise exception and verifies graceful handling
        """
        # Arrange
        pr_id = uuid.uuid4()
        pr_change = PRChangeRecord(
            pr_data=MagicMock(),
            change_type="updated",
            existing_pr_id=pr_id,
        )
        pr_change.pr_data.number = 123
        
        # Make the repository call fail
        mock_check_run_repository.get_all_for_pr.side_effect = Exception("Database connection error")
        check_runs_by_pr = {123: [sample_check_run_data]}

        # Act
        changes = await change_detector.detect_check_run_changes(
            [pr_change], check_runs_by_pr
        )

        # Assert - should treat as new check run when database fails
        assert len(changes) == 1
        assert changes[0].change_type == "new"

    async def test_concurrent_pr_processing_with_overlapping_numbers(
        self, change_detector, sample_repository_id, mock_pr_repository
    ):
        """
        Why: Validates handling of PRs with overlapping numbers (edge case)
        What: Tests processing when PR numbers might overlap in complex scenarios
        How: Creates PRs with similar patterns and verifies correct matching
        """
        # Arrange - create PRs with numbers that could cause confusion
        pr_data_12 = PRData(
            number=12,
            title="PR 12",
            author="user1",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/12",
            base_sha="abc123",
            head_sha="sha12",
            url="https://github.com/owner/repo/pull/12",
        )
        
        pr_data_123 = PRData(
            number=123,
            title="PR 123",
            author="user2",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/123",
            base_sha="abc123",
            head_sha="sha123",
            url="https://github.com/owner/repo/pull/123",
        )

        existing_pr_12 = MagicMock()
        existing_pr_12.id = uuid.uuid4()
        existing_pr_12.pr_number = 12
        existing_pr_12.title = "PR 12 Modified"  # Different title
        existing_pr_12.author = "user1"
        existing_pr_12.state = PRState.OPENED
        existing_pr_12.draft = False
        existing_pr_12.head_sha = "sha12"
        existing_pr_12.pr_metadata = {
            "labels": [],  # Same as pr_data_12.labels (empty by default)
            "assignees": [],  # Same as pr_data_12.assignees (empty by default)  
            "milestone": None,  # Same as pr_data_12.milestone (None by default)
        }

        mock_pr_repository.get_recent_prs.return_value = [existing_pr_12]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [pr_data_12, pr_data_123]
        )

        # Assert
        assert len(changes) == 2
        
        # PR 12 should be updated (title changed)
        pr_12_changes = [c for c in changes if c.pr_data.number == 12]
        assert len(pr_12_changes) == 1
        assert pr_12_changes[0].change_type == "updated"
        assert pr_12_changes[0].title_changed is True
        
        # PR 123 should be new
        pr_123_changes = [c for c in changes if c.pr_data.number == 123]
        assert len(pr_123_changes) == 1
        assert pr_123_changes[0].change_type == "new"

    async def test_check_run_with_null_conclusion_handling(
        self, change_detector, mock_check_run_repository
    ):
        """
        Why: Validates handling of check runs with null/missing conclusion
        What: Tests processing check runs that are still in progress (no conclusion)
        How: Creates check run data with None conclusion and verifies handling
        """
        # Arrange
        check_data_no_conclusion = CheckRunData(
            external_id="pending123",
            check_name="Pending Check",
            status="in_progress",
            conclusion=None,  # Still running
            details_url="https://github.com/owner/repo/runs/pending123",
            started_at=datetime.now(timezone.utc),
            completed_at=None,
        )
        
        existing_check = MagicMock()
        existing_check.id = uuid.uuid4()
        existing_check.external_id = "pending123"
        existing_check.check_name = "Pending Check"
        existing_check.status = CheckStatus.QUEUED  # Was queued, now in progress
        existing_check.conclusion = None
        existing_check.started_at = None
        existing_check.completed_at = None

        pr_id = uuid.uuid4()
        pr_change = PRChangeRecord(
            pr_data=MagicMock(),
            change_type="updated",
            existing_pr_id=pr_id,
        )
        pr_change.pr_data.number = 123

        mock_check_run_repository.get_all_for_pr.return_value = [existing_check]
        check_runs_by_pr = {123: [check_data_no_conclusion]}

        # Act
        changes = await change_detector.detect_check_run_changes(
            [pr_change], check_runs_by_pr
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].status_changed is True  # Queued -> In Progress
        assert changes[0].conclusion_changed is False  # Both None
        assert changes[0].timing_changed is True  # Started time added

    async def test_timezone_handling_in_timestamps(
        self, change_detector, sample_repository_id, mock_pr_repository
    ):
        """
        Why: Validates proper handling of timezone differences in timestamps
        What: Tests timestamp comparison with different timezone representations
        How: Creates PR data with timezone-aware timestamps and verifies handling
        """
        # Arrange - create PR with timezone-aware timestamps
        utc_time = datetime.now(timezone.utc)
        
        pr_data_with_tz = PRData(
            number=456,
            title="Timezone Test PR",
            author="user_tz",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/timezone",
            base_sha="abc123",
            head_sha="tz789",
            url="https://github.com/owner/repo/pull/456",
            created_at=utc_time,
            updated_at=utc_time,
        )

        existing_pr_tz = MagicMock()
        existing_pr_tz.id = uuid.uuid4()
        existing_pr_tz.pr_number = 456
        existing_pr_tz.title = "Timezone Test PR"
        existing_pr_tz.author = "user_tz"
        existing_pr_tz.state = PRState.OPENED
        existing_pr_tz.draft = False
        existing_pr_tz.head_sha = "tz789"
        existing_pr_tz.pr_metadata = {
            "labels": [],  # Same as pr_data_with_tz.labels
            "assignees": [],  # Same as pr_data_with_tz.assignees
            "milestone": None,  # Same as pr_data_with_tz.milestone
            "github_created_at": utc_time.isoformat(),
            "github_updated_at": utc_time.isoformat(),
        }

        mock_pr_repository.get_recent_prs.return_value = [existing_pr_tz]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [pr_data_with_tz]
        )

        # Assert - should not detect changes for identical timestamps
        assert len(changes) == 0

    async def test_large_metadata_comparison_performance(
        self, change_detector, sample_repository_id, mock_pr_repository
    ):
        """
        Why: Validates performance with large metadata objects
        What: Tests metadata comparison with large label/assignee lists
        How: Creates PR with many labels and assignees, verifies efficient processing
        """
        # Arrange - create PR with extensive metadata
        many_labels = [f"label-{i}" for i in range(100)]
        many_assignees = [f"user-{i}" for i in range(50)]
        
        pr_data_large_meta = PRData(
            number=789,
            title="Large Metadata PR",
            author="power_user",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/large-meta",
            base_sha="abc123",
            head_sha="meta456",
            url="https://github.com/owner/repo/pull/789",
            labels=many_labels,
            assignees=many_assignees,
        )

        existing_pr_large = MagicMock()
        existing_pr_large.id = uuid.uuid4()
        existing_pr_large.pr_number = 789
        existing_pr_large.title = "Large Metadata PR"
        existing_pr_large.author = "power_user"
        existing_pr_large.state = PRState.OPENED
        existing_pr_large.draft = False
        existing_pr_large.head_sha = "meta456"
        existing_pr_large.pr_metadata = {
            "labels": many_labels[:-1],  # Missing one label
            "assignees": many_assignees,
        }

        mock_pr_repository.get_recent_prs.return_value = [existing_pr_large]

        # Act
        changes = await change_detector.detect_pr_changes(
            sample_repository_id, [pr_data_large_meta]
        )

        # Assert
        assert len(changes) == 1
        assert changes[0].metadata_changed is True

    def test_changeset_pr_ids_with_complex_changes(
        self, change_detector, sample_repository_id
    ):
        """
        Why: Validates PR ID collection from complex changeset scenarios
        What: Tests get_pr_ids_with_changes with various change combinations
        How: Creates complex changeset and verifies PR ID extraction
        """
        # Arrange
        pr_id_1 = uuid.uuid4()
        pr_id_2 = uuid.uuid4()
        pr_id_3 = uuid.uuid4()

        # New PR (won't have existing_pr_id)
        new_pr_change = PRChangeRecord(
            pr_data=MagicMock(), change_type="new", existing_pr_id=None
        )
        
        # Updated PR
        updated_pr_change = PRChangeRecord(
            pr_data=MagicMock(), change_type="updated", existing_pr_id=pr_id_1
        )
        
        # New check run
        new_check_change = CheckRunChangeRecord(
            check_data=MagicMock(),
            pr_id=pr_id_2,
            change_type="new",
            existing_check_id=None,
        )
        
        # Updated check run
        updated_check_change = CheckRunChangeRecord(
            check_data=MagicMock(),
            pr_id=pr_id_3,
            change_type="updated",
            existing_check_id=uuid.uuid4(),
        )

        pr_changes = [new_pr_change, updated_pr_change]
        check_changes = [new_check_change, updated_check_change]

        # Act
        changeset = change_detector.create_changeset(
            sample_repository_id, pr_changes, check_changes
        )
        pr_ids = changeset.get_pr_ids_with_changes()

        # Assert
        # Should include: pr_id_1 (updated PR), pr_id_2 (new check), pr_id_3 (updated check)
        # Should NOT include the new PR (no existing ID)
        expected_ids = {pr_id_1, pr_id_2, pr_id_3}
        actual_ids = set(pr_ids)
        assert actual_ids == expected_ids