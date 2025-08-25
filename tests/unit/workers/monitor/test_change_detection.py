"""Unit tests for the StateChangeDetector implementation.

Tests cover all change detection scenarios including:
- PR creation and state transitions
- Check run creation and status changes
- Change prioritization and significance analysis
- Efficient comparison algorithms
- Error handling and edge cases
"""

import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import Mock, patch

import pytest

from src.models.enums import CheckConclusion, CheckStatus, PRState
from src.workers.monitor.change_detection import StateChangeDetector
from src.workers.monitor.models import (
    ChangeType,
    CheckRunDiscovery,
    DiscoveryResult,
    SeverityLevel,
    StateChangeEvent,
)


class TestStateChangeDetector:
    """Test suite for StateChangeDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a StateChangeDetector instance for testing."""
        return StateChangeDetector(enable_detailed_logging=True)

    @pytest.fixture
    def sample_pr_data(self):
        """Create sample PR data for testing."""
        repo_id = uuid.uuid4()
        return DiscoveryResult(
            repository_id=repo_id,
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
            discovered_at=datetime.utcnow(),
            github_id=456789,
            github_node_id="PR_test123",
        )

    @pytest.fixture
    def sample_check_run_data(self):
        """Create sample check run data for testing."""
        pr_id = uuid.uuid4()
        return CheckRunDiscovery(
            pr_id=pr_id,
            pr_number=123,
            github_check_run_id="check_123",
            check_name="test-check",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
            details_url="https://github.com/test/actions/run/123",
            started_at=datetime.utcnow() - timedelta(minutes=5),
            completed_at=datetime.utcnow(),
            discovered_at=datetime.utcnow(),
        )

    @pytest.mark.asyncio
    async def test_detect_new_pr_creation(self, detector, sample_pr_data):
        """Test detection of new PR creation."""
        changes = await detector.detect_pr_changes(None, sample_pr_data)

        assert len(changes) == 1
        change = changes[0]
        assert change.event_type == ChangeType.PR_CREATED
        assert change.pr_number == sample_pr_data.pr_number
        assert change.old_state is None
        assert change.new_state is not None
        assert "created" in change.changed_fields
        assert change.severity in [SeverityLevel.LOW, SeverityLevel.MEDIUM]

    @pytest.mark.asyncio
    async def test_detect_pr_state_change(self, detector, sample_pr_data):
        """Test detection of PR state transitions."""
        old_pr = sample_pr_data
        new_pr = DiscoveryResult(
            repository_id=old_pr.repository_id,
            repository_name=old_pr.repository_name,
            repository_owner=old_pr.repository_owner,
            pr_number=old_pr.pr_number,
            title=old_pr.title,
            author=old_pr.author,
            state=PRState.MERGED,  # Changed from OPENED to MERGED
            draft=old_pr.draft,
            base_branch=old_pr.base_branch,
            head_branch=old_pr.head_branch,
            base_sha=old_pr.base_sha,
            head_sha=old_pr.head_sha,
            url=old_pr.url,
            body=old_pr.body,
            discovered_at=old_pr.discovered_at,
            github_id=old_pr.github_id,
            github_node_id=old_pr.github_node_id,
        )

        changes = await detector.detect_pr_changes(old_pr, new_pr)

        assert len(changes) == 1
        change = changes[0]
        assert change.event_type == ChangeType.PR_STATE_CHANGED
        assert "state" in change.changed_fields
        assert change.severity == SeverityLevel.HIGH  # State changes are high priority

    @pytest.mark.asyncio
    async def test_detect_pr_title_change(self, detector, sample_pr_data):
        """Test detection of PR metadata changes."""
        old_pr = sample_pr_data
        new_pr = DiscoveryResult(
            repository_id=old_pr.repository_id,
            repository_name=old_pr.repository_name,
            repository_owner=old_pr.repository_owner,
            pr_number=old_pr.pr_number,
            title="Updated Test PR Title",  # Changed title
            author=old_pr.author,
            state=old_pr.state,
            draft=old_pr.draft,
            base_branch=old_pr.base_branch,
            head_branch=old_pr.head_branch,
            base_sha=old_pr.base_sha,
            head_sha=old_pr.head_sha,
            url=old_pr.url,
            body=old_pr.body,
            discovered_at=old_pr.discovered_at,
            github_id=old_pr.github_id,
            github_node_id=old_pr.github_node_id,
        )

        changes = await detector.detect_pr_changes(old_pr, new_pr)

        assert len(changes) == 1
        change = changes[0]
        assert change.event_type == ChangeType.PR_UPDATED
        assert "title" in change.changed_fields
        assert change.severity == SeverityLevel.LOW  # Metadata changes are low priority

    @pytest.mark.asyncio
    async def test_detect_pr_head_sha_change(self, detector, sample_pr_data):
        """Test detection of new commits (head_sha changes)."""
        old_pr = sample_pr_data
        new_pr = DiscoveryResult(
            repository_id=old_pr.repository_id,
            repository_name=old_pr.repository_name,
            repository_owner=old_pr.repository_owner,
            pr_number=old_pr.pr_number,
            title=old_pr.title,
            author=old_pr.author,
            state=old_pr.state,
            draft=old_pr.draft,
            base_branch=old_pr.base_branch,
            head_branch=old_pr.head_branch,
            base_sha=old_pr.base_sha,
            head_sha="xyz789",  # New commit
            url=old_pr.url,
            body=old_pr.body,
            discovered_at=old_pr.discovered_at,
            github_id=old_pr.github_id,
            github_node_id=old_pr.github_node_id,
        )

        changes = await detector.detect_pr_changes(old_pr, new_pr)

        assert len(changes) == 1
        change = changes[0]
        assert change.event_type == ChangeType.PR_UPDATED
        assert "head_sha" in change.changed_fields
        assert (
            change.severity == SeverityLevel.MEDIUM
        )  # New commits are medium priority

    @pytest.mark.asyncio
    async def test_detect_no_pr_changes(self, detector, sample_pr_data):
        """Test that identical PR states produce no changes."""
        changes = await detector.detect_pr_changes(sample_pr_data, sample_pr_data)
        assert len(changes) == 0

    @pytest.mark.asyncio
    async def test_detect_new_check_run_creation(self, detector, sample_check_run_data):
        """Test detection of new check run creation."""
        pr_id = uuid.uuid4()
        pr_number = 123

        changes = await detector.detect_check_run_changes(
            [], [sample_check_run_data], pr_id, pr_number
        )

        assert len(changes) == 1
        change = changes[0]
        assert change.event_type == ChangeType.CHECK_RUN_CREATED
        assert change.check_run_name == sample_check_run_data.check_name
        assert change.old_state is None
        assert change.new_state is not None

    @pytest.mark.asyncio
    async def test_detect_check_run_status_change(
        self, detector, sample_check_run_data
    ):
        """Test detection of check run status transitions."""
        old_check = sample_check_run_data
        new_check = CheckRunDiscovery(
            pr_id=old_check.pr_id,
            pr_number=old_check.pr_number,
            github_check_run_id=old_check.github_check_run_id,
            check_name=old_check.check_name,
            status=CheckStatus.COMPLETED,  # Same status
            conclusion=CheckConclusion.FAILURE,  # Changed conclusion
            details_url=old_check.details_url,
            started_at=old_check.started_at,
            completed_at=old_check.completed_at,
            discovered_at=old_check.discovered_at,
        )

        pr_id = uuid.uuid4()
        pr_number = 123

        changes = await detector.detect_check_run_changes(
            [old_check], [new_check], pr_id, pr_number
        )

        assert len(changes) == 1
        change = changes[0]
        assert change.event_type == ChangeType.CHECK_RUN_STATUS_CHANGED
        assert "conclusion" in change.changed_fields
        assert change.severity == SeverityLevel.HIGH  # Failures are high priority

    @pytest.mark.asyncio
    async def test_detect_check_run_completion(self, detector):
        """Test detection of check run completion."""
        pr_id = uuid.uuid4()
        old_check = CheckRunDiscovery(
            pr_id=pr_id,
            pr_number=123,
            github_check_run_id="check_123",
            check_name="test-check",
            status=CheckStatus.IN_PROGRESS,
            conclusion=None,
            discovered_at=datetime.utcnow(),
        )

        new_check = CheckRunDiscovery(
            pr_id=pr_id,
            pr_number=123,
            github_check_run_id="check_123",
            check_name="test-check",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
            completed_at=datetime.utcnow(),
            discovered_at=datetime.utcnow(),
        )

        changes = await detector.detect_check_run_changes(
            [old_check], [new_check], pr_id, 123
        )

        assert len(changes) == 1
        change = changes[0]
        assert change.event_type == ChangeType.CHECK_RUN_STATUS_CHANGED
        assert "status" in change.changed_fields
        assert "conclusion" in change.changed_fields
        assert (
            change.severity == SeverityLevel.MEDIUM
        )  # Completions are medium priority

    @pytest.mark.asyncio
    async def test_detect_multiple_check_run_changes(self, detector):
        """Test detection of changes across multiple check runs."""
        pr_id = uuid.uuid4()

        old_checks = [
            CheckRunDiscovery(
                pr_id=pr_id,
                pr_number=123,
                github_check_run_id="check_1",
                check_name="lint",
                status=CheckStatus.IN_PROGRESS,
                discovered_at=datetime.utcnow(),
            ),
            CheckRunDiscovery(
                pr_id=pr_id,
                pr_number=123,
                github_check_run_id="check_2",
                check_name="test",
                status=CheckStatus.COMPLETED,
                conclusion=CheckConclusion.SUCCESS,
                discovered_at=datetime.utcnow(),
            ),
        ]

        new_checks = [
            CheckRunDiscovery(
                pr_id=pr_id,
                pr_number=123,
                github_check_run_id="check_1",
                check_name="lint",
                status=CheckStatus.COMPLETED,
                conclusion=CheckConclusion.FAILURE,  # Failed
                discovered_at=datetime.utcnow(),
            ),
            CheckRunDiscovery(
                pr_id=pr_id,
                pr_number=123,
                github_check_run_id="check_2",
                check_name="test",
                status=CheckStatus.COMPLETED,
                conclusion=CheckConclusion.SUCCESS,  # No change
                discovered_at=datetime.utcnow(),
            ),
            CheckRunDiscovery(
                pr_id=pr_id,
                pr_number=123,
                github_check_run_id="check_3",  # New check
                check_name="build",
                status=CheckStatus.QUEUED,
                discovered_at=datetime.utcnow(),
            ),
        ]

        changes = await detector.detect_check_run_changes(
            old_checks, new_checks, pr_id, 123
        )

        # Should detect: 1 status change (lint failed), 1 new check (build)
        assert len(changes) == 2

        # Find the specific changes
        status_changes = [
            c for c in changes if c.event_type == ChangeType.CHECK_RUN_STATUS_CHANGED
        ]
        creation_changes = [
            c for c in changes if c.event_type == ChangeType.CHECK_RUN_CREATED
        ]

        assert len(status_changes) == 1
        assert len(creation_changes) == 1

        assert status_changes[0].check_run_name == "lint"
        assert creation_changes[0].check_run_name == "build"

    @pytest.mark.asyncio
    async def test_analyze_significance_high_priority(self, detector):
        """Test significance analysis for high priority changes."""
        changes = [
            StateChangeEvent(
                event_type=ChangeType.PR_STATE_CHANGED,
                pr_number=123,
                changed_fields=["state"],
                severity=SeverityLevel.MEDIUM,  # Will be upgraded
                new_state={"state": "merged"},
            ),
        ]

        analyzed = await detector.analyze_significance(changes)

        assert len(analyzed) == 1
        assert analyzed[0].severity == SeverityLevel.HIGH

    @pytest.mark.asyncio
    async def test_analyze_significance_check_run_failure(self, detector):
        """Test significance analysis for check run failures."""
        changes = [
            StateChangeEvent(
                event_type=ChangeType.CHECK_RUN_STATUS_CHANGED,
                pr_number=123,
                changed_fields=["conclusion"],
                severity=SeverityLevel.MEDIUM,
                new_state={"conclusion": "failure"},
                check_run_name="test-check",
            ),
        ]

        analyzed = await detector.analyze_significance(changes)

        assert len(analyzed) == 1
        assert analyzed[0].severity == SeverityLevel.HIGH

    @pytest.mark.asyncio
    async def test_filter_actionable_changes(self, detector):
        """Test filtering of actionable changes."""
        changes = [
            StateChangeEvent(
                event_type=ChangeType.PR_UPDATED,
                pr_number=123,
                changed_fields=["title"],
                severity=SeverityLevel.LOW,  # Not actionable
            ),
            StateChangeEvent(
                event_type=ChangeType.CHECK_RUN_STATUS_CHANGED,
                pr_number=124,
                changed_fields=["conclusion"],
                severity=SeverityLevel.HIGH,  # Actionable due to severity
            ),
            StateChangeEvent(
                event_type=ChangeType.PR_CREATED,
                pr_number=125,
                changed_fields=["created"],
                severity=SeverityLevel.MEDIUM,
                new_state={"draft": False},  # Actionable - non-draft PR
            ),
        ]

        actionable = await detector.filter_actionable_changes(changes)

        assert len(actionable) == 2
        assert actionable[0].pr_number == 124  # High severity
        assert actionable[1].pr_number == 125  # Non-draft PR creation

    @pytest.mark.asyncio
    async def test_filter_actionable_check_run_failure(self, detector):
        """Test filtering actionable check run failures."""
        changes = [
            StateChangeEvent(
                event_type=ChangeType.CHECK_RUN_STATUS_CHANGED,
                pr_number=123,
                changed_fields=["conclusion"],
                severity=SeverityLevel.MEDIUM,
                new_state={"conclusion": "failure"},  # Actionable - failure
            ),
        ]

        actionable = await detector.filter_actionable_changes(changes)

        assert len(actionable) == 1
        assert actionable[0].pr_number == 123

    def test_compare_pr_states_multiple_changes(self, detector, sample_pr_data):
        """Test comparison of PR states with multiple field changes."""
        old_pr = sample_pr_data
        new_pr = DiscoveryResult(
            repository_id=old_pr.repository_id,
            repository_name=old_pr.repository_name,
            repository_owner=old_pr.repository_owner,
            pr_number=old_pr.pr_number,
            title="Updated Title",  # Changed
            author=old_pr.author,
            state=PRState.MERGED,  # Changed
            draft=True,  # Changed
            base_branch=old_pr.base_branch,
            head_branch=old_pr.head_branch,
            base_sha=old_pr.base_sha,
            head_sha="new_sha",  # Changed
            url=old_pr.url,
            body=old_pr.body,
            discovered_at=old_pr.discovered_at,
            github_id=old_pr.github_id,
            github_node_id=old_pr.github_node_id,
        )

        changed_fields, old_dict, new_dict = detector._compare_pr_states(old_pr, new_pr)

        expected_changes = {"title", "state", "draft", "head_sha"}
        assert set(changed_fields) == expected_changes

    def test_compare_check_run_states_output_changes(self, detector):
        """Test comparison of check run states with output changes."""
        pr_id = uuid.uuid4()
        old_check = CheckRunDiscovery(
            pr_id=pr_id,
            pr_number=123,
            github_check_run_id="check_123",
            check_name="test-check",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
            output_summary="Tests passed",
            discovered_at=datetime.utcnow(),
        )

        new_check = CheckRunDiscovery(
            pr_id=pr_id,
            pr_number=123,
            github_check_run_id="check_123",
            check_name="test-check",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
            output_summary="All 15 tests passed successfully",  # Changed
            output_text="Detailed test results...",  # New field
            discovered_at=datetime.utcnow(),
        )

        changes = detector._compare_check_run_states(old_check, new_check)

        assert "output_summary" in changes
        assert "output_text" in changes
        assert len(changes) == 2

    def test_priority_calculation_pr_merge(self, detector):
        """Test priority calculation for PR merge events."""
        change = StateChangeEvent(
            event_type=ChangeType.PR_STATE_CHANGED,
            pr_number=123,
            changed_fields=["state"],
            new_state={"state": "merged"},
            severity=SeverityLevel.LOW,  # Will be recalculated
        )

        priority = detector._calculate_change_priority(change)
        assert priority == SeverityLevel.HIGH

    def test_priority_calculation_check_failure(self, detector):
        """Test priority calculation for check run failures."""
        change = StateChangeEvent(
            event_type=ChangeType.CHECK_RUN_STATUS_CHANGED,
            pr_number=123,
            changed_fields=["conclusion"],
            new_state={"conclusion": "failure"},
            severity=SeverityLevel.LOW,  # Will be recalculated
        )

        priority = detector._calculate_change_priority(change)
        assert priority == SeverityLevel.HIGH

    def test_priority_calculation_new_commits(self, detector):
        """Test priority calculation for new commits."""
        change = StateChangeEvent(
            event_type=ChangeType.PR_UPDATED,
            pr_number=123,
            changed_fields=["head_sha"],
            severity=SeverityLevel.LOW,  # Will be recalculated
        )

        priority = detector._calculate_change_priority(change)
        assert priority == SeverityLevel.MEDIUM

    def test_get_statistics(self, detector):
        """Test getting detector statistics."""
        stats = detector.get_statistics()

        required_keys = [
            "pr_comparisons",
            "check_run_comparisons",
            "changes_detected",
            "cache_hits",
            "cache_size",
        ]
        assert all(key in stats for key in required_keys)
        assert all(isinstance(stats[key], int) for key in required_keys)

    def test_clear_cache(self, detector):
        """Test clearing the detector cache."""
        # Add something to cache first
        detector._comparison_cache["test"] = "data"
        assert len(detector._comparison_cache) > 0

        detector.clear_cache()
        assert len(detector._comparison_cache) == 0

    @pytest.mark.asyncio
    async def test_error_handling_in_pr_detection(self, detector):
        """Test error handling during PR change detection."""
        # Create invalid PR data that might cause errors
        invalid_pr = Mock()
        invalid_pr.to_dict.side_effect = Exception("Test error")

        changes = await detector.detect_pr_changes(invalid_pr, invalid_pr)
        # Should handle error gracefully and return empty list
        assert changes == []

    @pytest.mark.asyncio
    async def test_error_handling_in_check_run_detection(self, detector):
        """Test error handling during check run change detection."""
        # Create invalid check run data
        invalid_check = Mock()
        invalid_check.github_check_run_id = "test"
        invalid_check.to_dict.side_effect = Exception("Test error")

        pr_id = uuid.uuid4()
        changes = await detector.detect_check_run_changes(
            [invalid_check], [invalid_check], pr_id, 123
        )
        # Should handle error gracefully and return empty list
        assert changes == []

    @pytest.mark.asyncio
    async def test_performance_with_large_datasets(self, detector):
        """Test performance with large numbers of check runs."""
        pr_id = uuid.uuid4()

        # Create large dataset
        old_checks = []
        new_checks = []

        for i in range(1000):  # 1000 check runs
            check = CheckRunDiscovery(
                pr_id=pr_id,
                pr_number=123,
                github_check_run_id=f"check_{i}",
                check_name=f"test-{i}",
                status=CheckStatus.COMPLETED,
                conclusion=CheckConclusion.SUCCESS,
                discovered_at=datetime.utcnow(),
            )
            old_checks.append(check)
            new_checks.append(check)  # No changes

        # Should complete quickly with no changes detected
        changes = await detector.detect_check_run_changes(
            old_checks, new_checks, pr_id, 123
        )
        assert len(changes) == 0

    def test_state_change_event_validation_integration(self, detector):
        """Test that generated events pass validation."""
        event = detector._generate_change_event(
            event_type=ChangeType.PR_CREATED,
            pr_id=uuid.uuid4(),
            pr_number=123,
            repository_id=uuid.uuid4(),
            old_state=None,
            new_state={"state": "opened"},
            changed_fields=["created"],
        )

        # Should not raise validation error
        assert event.validate()

    def test_actionable_change_detection_edge_cases(self, detector):
        """Test edge cases in actionable change detection."""
        # Test change with empty new_state
        change_empty_state = StateChangeEvent(
            event_type=ChangeType.PR_STATE_CHANGED,
            pr_number=123,
            changed_fields=["state"],
            severity=SeverityLevel.MEDIUM,
            new_state=None,  # Empty state
        )

        assert not detector._is_actionable_change(change_empty_state)

        # Test high severity change (always actionable)
        change_high_severity = StateChangeEvent(
            event_type=ChangeType.PR_UPDATED,
            pr_number=123,
            changed_fields=["title"],
            severity=SeverityLevel.HIGH,
        )

        assert detector._is_actionable_change(change_high_severity)

    @pytest.mark.asyncio
    async def test_significance_analysis_error_handling(self, detector):
        """Test error handling in significance analysis."""
        # Create change that might cause issues
        problematic_change = StateChangeEvent(
            event_type=ChangeType.PR_UPDATED,
            pr_number=0,  # Invalid PR number
            changed_fields=[],
            severity=SeverityLevel.MEDIUM,
        )

        with patch.object(
            detector, "_calculate_change_priority", side_effect=Exception("Test error")
        ):
            analyzed = await detector.analyze_significance([problematic_change])
            # Should return original change when analysis fails
            assert len(analyzed) == 1
            assert analyzed[0] == problematic_change
