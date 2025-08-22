"""Tests for state change detection."""

import uuid
from datetime import datetime, timezone

import pytest

from src.models import CheckRun, PullRequest
from src.models.enums import CheckConclusion, CheckStatus, PRState
from src.workers.monitor.change_detection import StateChangeDetector
from src.workers.monitor.models import CheckRunData, PRData


class TestStateChangeDetector:
    """
    Why: Ensure state change detection correctly identifies differences between GitHub and database state
    What: Tests PR and check run change detection with various scenarios
    How: Create test data with different states and verify correct change detection
    """
    
    @pytest.fixture
    def detector(self):
        """Create state change detector."""
        return StateChangeDetector()
    
    @pytest.fixture
    def sample_pr_data(self):
        """Create sample PR data from GitHub."""
        return PRData(
            number=123,
            title="Test PR",
            author="test-user",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature",
            base_sha="base123",
            head_sha="head456",
            url="https://github.com/owner/repo/pull/123",
            body="Test PR body",
            metadata={"labels": ["bug"], "assignees": ["user1"]},
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc)
        )
    
    @pytest.fixture
    def existing_pr(self):
        """Create existing PR from database."""
        return PullRequest(
            id=uuid.uuid4(),
            repository_id=uuid.uuid4(),
            pr_number=123,
            title="Test PR",
            author="test-user",
            state=PRState.OPENED,
            draft=False,
            base_branch="main",
            head_branch="feature",
            base_sha="base123",
            head_sha="head456",
            url="https://github.com/owner/repo/pull/123",
            body="Test PR body",
            pr_metadata={"labels": ["bug"], "assignees": ["user1"]}
        )
    
    @pytest.fixture
    def sample_check_data(self):
        """Create sample check run data from GitHub."""
        return CheckRunData(
            id=456,
            name="test-check",
            status="completed",
            conclusion="success",
            started_at=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            completed_at=datetime(2024, 1, 1, 12, 5, tzinfo=timezone.utc),
            details_url="https://example.com/check/456",
            output_title="All tests passed",
            output_summary="Tests completed successfully",
            external_id="ext-456"
        )
    
    @pytest.fixture
    def existing_check(self):
        """Create existing check run from database."""
        return CheckRun(
            id=uuid.uuid4(),
            pr_id=uuid.uuid4(),
            external_check_id="456",
            check_name="test-check",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
            started_at=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            completed_at=datetime(2024, 1, 1, 12, 5, tzinfo=timezone.utc),
            details_url="https://example.com/check/456",
            output_title="All tests passed",
            output_summary="Tests completed successfully"
        )
    
    def test_detect_new_pr(self, detector, sample_pr_data):
        """
        Why: Verify detection of new PRs that don't exist in database
        What: Tests change detection when existing_pr is None
        How: Pass None for existing PR and verify new PR change is detected
        """
        # Act
        updated_pr, changes = detector.detect_pr_changes(sample_pr_data, None)
        
        # Assert
        assert updated_pr is not None
        assert updated_pr.pr_number == 123
        assert updated_pr.title == "Test PR"
        assert updated_pr.state == PRState.OPENED
        
        assert len(changes) == 1
        assert changes[0].change_type == "new_pr"
        assert changes[0].old_value is None
        assert changes[0].new_value == PRState.OPENED
        assert changes[0].metadata["pr_number"] == 123
    
    def test_detect_pr_state_change(self, detector, sample_pr_data, existing_pr):
        """
        Why: Verify detection of PR state changes
        What: Tests detection when PR state changes from open to closed
        How: Modify sample data to closed state and verify change is detected
        """
        # Arrange
        sample_pr_data.state = "closed"
        
        # Act
        updated_pr, changes = detector.detect_pr_changes(sample_pr_data, existing_pr)
        
        # Assert
        assert updated_pr is not None
        assert updated_pr.state == PRState.CLOSED
        
        # Find state change
        state_change = next((c for c in changes if c.change_type == "pr_state"), None)
        assert state_change is not None
        assert state_change.old_value == PRState.OPENED
        assert state_change.new_value == PRState.CLOSED
        assert state_change.metadata["pr_number"] == 123
    
    def test_detect_pr_draft_change(self, detector, sample_pr_data, existing_pr):
        """
        Why: Verify detection of draft status changes
        What: Tests detection when PR draft status changes
        How: Modify draft status and verify change is detected
        """
        # Arrange
        sample_pr_data.draft = True
        
        # Act
        updated_pr, changes = detector.detect_pr_changes(sample_pr_data, existing_pr)
        
        # Assert
        assert updated_pr is not None
        assert updated_pr.draft is True
        
        # Find draft change
        draft_change = next((c for c in changes if c.change_type == "pr_draft"), None)
        assert draft_change is not None
        assert draft_change.old_value is False
        assert draft_change.new_value is True
    
    def test_detect_pr_head_sha_change(self, detector, sample_pr_data, existing_pr):
        """
        Why: Verify detection of new commits (head SHA changes)
        What: Tests detection when head SHA changes indicating new commits
        How: Modify head SHA and verify change is detected
        """
        # Arrange
        sample_pr_data.head_sha = "newhead789"
        
        # Act
        updated_pr, changes = detector.detect_pr_changes(sample_pr_data, existing_pr)
        
        # Assert
        assert updated_pr is not None
        assert updated_pr.head_sha == "newhead789"
        
        # Find SHA change
        sha_change = next((c for c in changes if c.change_type == "pr_head_sha"), None)
        assert sha_change is not None
        assert sha_change.old_value == "head456"
        assert sha_change.new_value == "newhead789"
    
    def test_detect_pr_metadata_change(self, detector, sample_pr_data, existing_pr):
        """
        Why: Verify detection of metadata changes (labels, assignees)
        What: Tests detection when PR labels or assignees change
        How: Modify metadata and verify change is detected
        """
        # Arrange
        sample_pr_data.metadata = {"labels": ["bug", "enhancement"], "assignees": ["user2"]}
        
        # Act
        updated_pr, changes = detector.detect_pr_changes(sample_pr_data, existing_pr)
        
        # Assert
        assert updated_pr is not None
        assert updated_pr.pr_metadata["labels"] == ["bug", "enhancement"]
        assert updated_pr.pr_metadata["assignees"] == ["user2"]
        
        # Find metadata change
        meta_change = next((c for c in changes if c.change_type == "pr_metadata"), None)
        assert meta_change is not None
        assert meta_change.old_value == {"labels": ["bug"], "assignees": ["user1"]}
        assert meta_change.new_value["labels"] == ["bug", "enhancement"]
    
    def test_detect_no_pr_changes(self, detector, sample_pr_data, existing_pr):
        """
        Why: Verify no changes are detected when PR data is identical
        What: Tests that unchanged PRs don't generate spurious change events
        How: Use identical data and verify no updates or changes are detected
        """
        # Act
        updated_pr, changes = detector.detect_pr_changes(sample_pr_data, existing_pr)
        
        # Assert
        assert updated_pr is None  # No updates needed
        assert len(changes) == 0   # No changes detected
    
    def test_detect_new_check_run(self, detector, sample_check_data):
        """
        Why: Verify detection of new check runs that don't exist in database
        What: Tests change detection when existing_check is None
        How: Pass None for existing check and verify new check change is detected
        """
        # Act
        updated_check, changes = detector.detect_check_run_changes(sample_check_data, None)
        
        # Assert
        assert updated_check is not None
        assert updated_check.external_check_id == "456"
        assert updated_check.check_name == "test-check"
        assert updated_check.status == CheckStatus.COMPLETED
        assert updated_check.conclusion == CheckConclusion.SUCCESS
        
        assert len(changes) == 1
        assert changes[0].change_type == "new_check_run"
        assert changes[0].old_value is None
        assert changes[0].new_value == CheckStatus.COMPLETED
        assert changes[0].metadata["check_name"] == "test-check"
        assert changes[0].metadata["external_id"] == 456
    
    def test_detect_check_status_change(self, detector, sample_check_data, existing_check):
        """
        Why: Verify detection of check run status changes
        What: Tests detection when check status changes from in_progress to completed
        How: Modify existing check to in_progress and verify change is detected
        """
        # Arrange
        existing_check.status = CheckStatus.IN_PROGRESS
        
        # Act
        updated_check, changes = detector.detect_check_run_changes(sample_check_data, existing_check)
        
        # Assert
        assert updated_check is not None
        assert updated_check.status == CheckStatus.COMPLETED
        
        # Find status change
        status_change = next((c for c in changes if c.change_type == "check_status"), None)
        assert status_change is not None
        assert status_change.old_value == CheckStatus.IN_PROGRESS
        assert status_change.new_value == CheckStatus.COMPLETED
    
    def test_detect_check_conclusion_change(self, detector, sample_check_data, existing_check):
        """
        Why: Verify detection of check run conclusion changes
        What: Tests detection when check conclusion changes from failure to success
        How: Modify existing check to failure and verify change is detected
        """
        # Arrange
        existing_check.conclusion = CheckConclusion.FAILURE
        sample_check_data.conclusion = "success"
        
        # Act
        updated_check, changes = detector.detect_check_run_changes(sample_check_data, existing_check)
        
        # Assert
        assert updated_check is not None
        assert updated_check.conclusion == CheckConclusion.SUCCESS
        
        # Find conclusion change
        conclusion_change = next((c for c in changes if c.change_type == "check_conclusion"), None)
        assert conclusion_change is not None
        assert conclusion_change.old_value == CheckConclusion.FAILURE
        assert conclusion_change.new_value == CheckConclusion.SUCCESS
    
    def test_detect_no_check_changes(self, detector, sample_check_data, existing_check):
        """
        Why: Verify no changes are detected when check run data is identical
        What: Tests that unchanged check runs don't generate spurious change events
        How: Use identical data and verify no updates or changes are detected
        """
        # Act
        updated_check, changes = detector.detect_check_run_changes(sample_check_data, existing_check)
        
        # Assert
        assert updated_check is None  # No updates needed
        assert len(changes) == 0      # No changes detected
    
    def test_build_change_set(self, detector):
        """
        Why: Verify change set building consolidates updates correctly
        What: Tests that PR and check run updates are properly categorized
        How: Create mixed updates and verify proper categorization in change set
        """
        # Arrange - create mock updates
        new_pr = PullRequest(pr_number=123, state=PRState.OPENED)
        updated_pr = PullRequest(pr_number=124, state=PRState.CLOSED)
        new_check = CheckRun(check_name="new-check", status=CheckStatus.QUEUED)
        updated_check = CheckRun(check_name="updated-check", status=CheckStatus.COMPLETED)
        
        pr_updates = [
            (new_pr, [{"change_type": "new_pr"}]),
            (updated_pr, [{"change_type": "pr_state"}])
        ]
        
        check_updates = [
            (new_check, [{"change_type": "new_check_run"}]),
            (updated_check, [{"change_type": "check_status"}])
        ]
        
        # Act
        change_set = detector.build_change_set(pr_updates, check_updates)
        
        # Assert
        assert len(change_set.new_prs) == 1
        assert len(change_set.updated_prs) == 1
        assert len(change_set.new_check_runs) == 1
        assert len(change_set.updated_check_runs) == 1
        assert change_set.has_changes is True
        assert change_set.total_changes == 4
    
    def test_metadata_changed_detection(self, detector):
        """
        Why: Verify metadata change detection logic
        What: Tests internal method for detecting significant metadata changes
        How: Test various metadata scenarios and verify correct change detection
        """
        # Test no changes
        old_meta = {"labels": ["bug"], "assignees": ["user1"]}
        new_meta = {"labels": ["bug"], "assignees": ["user1"]}
        assert not detector._metadata_changed(old_meta, new_meta)
        
        # Test label changes
        new_meta = {"labels": ["bug", "enhancement"], "assignees": ["user1"]}
        assert detector._metadata_changed(old_meta, new_meta)
        
        # Test assignee changes
        new_meta = {"labels": ["bug"], "assignees": ["user2"]}
        assert detector._metadata_changed(old_meta, new_meta)
        
        # Test milestone changes
        old_meta = {"milestone": "v1.0"}
        new_meta = {"milestone": "v2.0"}
        assert detector._metadata_changed(old_meta, new_meta)