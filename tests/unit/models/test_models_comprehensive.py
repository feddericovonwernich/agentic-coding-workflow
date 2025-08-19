"""
Comprehensive unit tests for SQLAlchemy models.

Why: Ensure all models have correct field definitions, relationships,
     and business logic methods without requiring database persistence
What: Tests model structure, field types, business logic, and enum handling
How: Creates model instances and tests their behavior in isolation
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.models.analysis_result import AnalysisResult
from src.models.base import BaseModel
from src.models.check_run import CheckRun
from src.models.enums import (
    CheckConclusion,
    CheckStatus,
    PRState,
    RepositoryStatus,
    TriggerEvent,
)
from src.models.fix_attempt import FixAttempt
from src.models.pull_request import PullRequest
from src.models.repository import Repository
from src.models.review import Review
from src.models.state_history import PRStateHistory


class TestBaseModel:
    """Test BaseModel functionality."""

    def test_base_model_has_required_fields(self) -> None:
        """
        Why: Verify BaseModel defines core fields all models need
        What: Tests that BaseModel has id, created_at, and updated_at fields
        How: Inspects model class attributes
        """
        # Check that the class has the required mapped columns
        assert hasattr(BaseModel, "id")
        assert hasattr(BaseModel, "created_at")
        assert hasattr(BaseModel, "updated_at")

    def test_to_dict_method_exists(self) -> None:
        """
        Why: Verify BaseModel provides serialization method
        What: Tests that to_dict method is available
        How: Checks method existence on BaseModel
        """
        assert hasattr(BaseModel, "to_dict")
        assert callable(BaseModel.to_dict)

    def test_repr_method_exists(self) -> None:
        """
        Why: Verify BaseModel provides string representation
        What: Tests that __repr__ method is available
        How: Checks method existence on BaseModel
        """
        assert hasattr(BaseModel, "__repr__")
        assert callable(BaseModel.__repr__)


class TestEnumIntegrity:
    """Test enum definitions and values."""

    def test_pr_state_enum_values(self) -> None:
        """
        Why: Ensure PR state values are correct for GitHub integration
        What: Tests all PRState enum values
        How: Checks each enum member has expected value
        """
        assert PRState.OPENED.value == "opened"
        assert PRState.CLOSED.value == "closed"
        assert PRState.MERGED.value == "merged"

        # Test enum completeness
        assert len(PRState) == 3

    def test_check_status_enum_values(self) -> None:
        """
        Why: Ensure check status values match GitHub API
        What: Tests all CheckStatus enum values
        How: Checks each enum member has expected value
        """
        assert CheckStatus.QUEUED.value == "queued"
        assert CheckStatus.IN_PROGRESS.value == "in_progress"
        assert CheckStatus.COMPLETED.value == "completed"
        assert CheckStatus.CANCELLED.value == "cancelled"

        assert len(CheckStatus) == 4

    def test_check_conclusion_enum_values(self) -> None:
        """
        Why: Ensure check conclusion values match GitHub API
        What: Tests all CheckConclusion enum values
        How: Checks each enum member has expected value
        """
        expected_values = {
            "success",
            "failure",
            "neutral",
            "cancelled",
            "timed_out",
            "action_required",
            "stale",
            "skipped",
        }
        actual_values = {conclusion.value for conclusion in CheckConclusion}

        assert actual_values == expected_values
        assert len(CheckConclusion) == 8

    def test_repository_status_enum_values(self) -> None:
        """
        Why: Ensure repository status values are correct
        What: Tests all RepositoryStatus enum values
        How: Checks each enum member has expected value
        """
        assert RepositoryStatus.ACTIVE.value == "active"
        assert RepositoryStatus.SUSPENDED.value == "suspended"
        assert RepositoryStatus.ERROR.value == "error"

        assert len(RepositoryStatus) == 3

    def test_trigger_event_enum_values(self) -> None:
        """
        Why: Ensure trigger event values are correct
        What: Tests all TriggerEvent enum values
        How: Checks each enum member has expected value
        """
        expected_values = {
            "opened",
            "synchronize",
            "closed",
            "reopened",
            "edited",
            "manual_check",
        }
        actual_values = {event.value for event in TriggerEvent}

        assert actual_values == expected_values
        assert len(TriggerEvent) == 6


class TestModelCreation:
    """Test model creation with required fields."""

    def test_repository_creation(self) -> None:
        """
        Why: Verify Repository model can be created with required fields
        What: Tests Repository creation and field assignment
        How: Creates instance and checks field values
        """
        repo = Repository(
            url="https://github.com/test/repo",
            name="repo",
            full_name="test/repo",
            status=RepositoryStatus.ACTIVE,
            polling_interval_minutes=15,
            failure_count=0,
        )

        assert repo.url == "https://github.com/test/repo"
        assert repo.name == "repo"
        assert repo.full_name == "test/repo"
        assert repo.status == RepositoryStatus.ACTIVE
        assert repo.polling_interval_minutes == 15
        assert repo.failure_count == 0

    def test_pull_request_creation(self) -> None:
        """
        Why: Verify PullRequest model can be created with required fields
        What: Tests PullRequest creation and field assignment
        How: Creates instance and checks field values
        """
        repository_id = uuid.uuid4()

        pr = PullRequest(
            repository_id=repository_id,
            pr_number=123,
            title="Test PR",
            author="testuser",
            state=PRState.OPENED,
            draft=False,
        )

        assert pr.repository_id == repository_id
        assert pr.pr_number == 123
        assert pr.title == "Test PR"
        assert pr.author == "testuser"
        assert pr.state == PRState.OPENED
        assert pr.draft is False

    def test_check_run_creation(self) -> None:
        """
        Why: Verify CheckRun model can be created with required fields
        What: Tests CheckRun creation and field assignment
        How: Creates instance and checks field values
        """
        pr_id = uuid.uuid4()

        check = CheckRun(
            pr_id=pr_id,
            external_id="12345",
            check_name="test-check",
            status=CheckStatus.QUEUED,
        )

        assert check.pr_id == pr_id
        assert check.external_id == "12345"
        assert check.check_name == "test-check"
        assert check.status == CheckStatus.QUEUED

    def test_analysis_result_creation(self) -> None:
        """
        Why: Verify AnalysisResult model can be created with required fields
        What: Tests AnalysisResult creation and field assignment
        How: Creates instance and checks field values
        """
        check_run_id = uuid.uuid4()

        analysis = AnalysisResult(
            check_run_id=check_run_id, category="lint", confidence_score=0.95
        )

        assert analysis.check_run_id == check_run_id
        assert analysis.category == "lint"
        assert analysis.confidence_score == 0.95

    def test_fix_attempt_creation(self) -> None:
        """
        Why: Verify FixAttempt model can be created with required fields
        What: Tests FixAttempt creation and field assignment
        How: Creates instance and checks field values
        """
        analysis_result_id = uuid.uuid4()

        fix = FixAttempt(
            analysis_result_id=analysis_result_id,
            fix_strategy="auto-lint",
            status="pending",
        )

        assert fix.analysis_result_id == analysis_result_id
        assert fix.fix_strategy == "auto-lint"
        assert fix.status == "pending"

    def test_pr_state_history_creation(self) -> None:
        """
        Why: Verify PRStateHistory model can be created with required fields
        What: Tests PRStateHistory creation and field assignment
        How: Creates instance and checks field values
        """
        pr_id = uuid.uuid4()

        history = PRStateHistory(
            pr_id=pr_id,
            old_state=PRState.OPENED,
            new_state=PRState.CLOSED,
            trigger_event=TriggerEvent.CLOSED,
        )

        assert history.pr_id == pr_id
        assert history.old_state == PRState.OPENED
        assert history.new_state == PRState.CLOSED
        assert history.trigger_event == TriggerEvent.CLOSED

    def test_review_creation(self) -> None:
        """
        Why: Verify Review model can be created with required fields
        What: Tests Review creation and field assignment
        How: Creates instance and checks field values
        """
        pr_id = uuid.uuid4()

        review = Review(pr_id=pr_id, reviewer_type="human", status="pending")

        assert review.pr_id == pr_id
        assert review.reviewer_type == "human"
        assert review.status == "pending"


class TestBusinessLogic:
    """Test business logic methods on models."""

    def test_repository_needs_polling_logic(self) -> None:
        """
        Why: Verify repository polling logic works correctly
        What: Tests needs_polling() method behavior
        How: Creates repo and tests different polling scenarios
        """
        repo = Repository(
            url="https://github.com/test/repo",
            name="repo",
            full_name="test/repo",
            status=RepositoryStatus.ACTIVE,
            polling_interval_minutes=15,
        )

        # Never polled should need polling
        assert repo.last_polled_at is None
        assert repo.needs_polling is True

    def test_pull_request_state_transitions(self) -> None:
        """
        Why: Verify PR state transition validation works
        What: Tests can_transition_to() method
        How: Creates PR and tests valid/invalid transitions
        """
        repository_id = uuid.uuid4()

        pr = PullRequest(
            repository_id=repository_id,
            pr_number=1,
            title="Test PR",
            author="user",
            state=PRState.OPENED,
        )

        # Valid transitions from OPENED
        assert pr.can_transition_to(PRState.CLOSED) is True
        assert pr.can_transition_to(PRState.MERGED) is True

        # Test merged PR cannot transition
        pr.state = PRState.MERGED
        assert pr.can_transition_to(PRState.OPENED) is False
        assert pr.can_transition_to(PRState.CLOSED) is False

    def test_check_run_status_properties(self) -> None:
        """
        Why: Verify check run status property logic
        What: Tests is_completed, is_successful, is_failed properties
        How: Creates checks with different statuses and tests properties
        """
        pr_id = uuid.uuid4()

        # Completed successful check
        success_check = CheckRun(
            pr_id=pr_id,
            external_id="1",
            check_name="test",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
        )

        assert success_check.is_completed is True
        assert success_check.is_successful is True
        assert success_check.is_failed is False

        # Completed failed check
        failed_check = CheckRun(
            pr_id=pr_id,
            external_id="2",
            check_name="test",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.FAILURE,
        )

        assert failed_check.is_completed is True
        assert failed_check.is_successful is False
        assert failed_check.is_failed is True

    def test_check_run_failure_categorization(self) -> None:
        """
        Why: Verify automatic failure categorization for routing
        What: Tests get_failure_category() method
        How: Creates failed checks with different names and tests categories
        """
        pr_id = uuid.uuid4()

        # Lint failure
        lint_check = CheckRun(
            pr_id=pr_id,
            external_id="1",
            check_name="eslint-check",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.FAILURE,
        )

        assert lint_check.get_failure_category() == "lint"

        # Test failure
        test_check = CheckRun(
            pr_id=pr_id,
            external_id="2",
            check_name="unit-tests",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.FAILURE,
        )

        assert test_check.get_failure_category() == "test"

    def test_pr_state_history_properties(self) -> None:
        """
        Why: Verify PR state history provides correct metadata
        What: Tests is_initial_state, is_reopening, etc. properties
        How: Creates history entries and tests property values
        """
        pr_id = uuid.uuid4()

        # Initial state (no old state)
        initial_history = PRStateHistory(
            pr_id=pr_id,
            old_state=None,
            new_state=PRState.OPENED,
            trigger_event=TriggerEvent.OPENED,
        )

        assert initial_history.is_initial_state is True
        assert initial_history.is_reopening is False

        # Reopening event
        reopen_history = PRStateHistory(
            pr_id=pr_id,
            old_state=PRState.CLOSED,
            new_state=PRState.OPENED,
            trigger_event=TriggerEvent.REOPENED,
        )

        assert reopen_history.is_initial_state is False
        assert reopen_history.is_reopening is True


class TestFieldConstraints:
    """Test field constraints and validation."""

    def test_repository_config_overrides_dict_field(self) -> None:
        """
        Why: Verify config_overrides field accepts dict data
        What: Tests that config_overrides can store complex data
        How: Creates repo with config data and verifies storage
        """
        config = {
            "max_retries": 5,
            "timeout": 30,
            "custom_settings": {"feature_flag": True},
        }

        repo = Repository(
            url="https://github.com/test/repo",
            name="repo",
            full_name="test/repo",
            config_override=config,
        )

        assert repo.config_override == config
        assert repo.config_override["max_retries"] == 5
        assert repo.config_override["custom_settings"]["feature_flag"] is True

    def test_pull_request_metadata_field(self) -> None:
        """
        Why: Verify pr_metadata field accepts dict data
        What: Tests that pr_metadata can store complex data
        How: Creates PR with metadata and verifies storage
        """
        metadata = {
            "labels": ["bug", "urgent"],
            "reviewers": ["user1", "user2"],
            "ci_info": {"build_id": "12345"},
        }

        repository_id = uuid.uuid4()
        pr = PullRequest(
            repository_id=repository_id,
            pr_number=1,
            title="Test PR",
            author="user",
            pr_metadata=metadata,
        )

        assert pr.pr_metadata == metadata
        assert pr.pr_metadata["labels"] == ["bug", "urgent"]
        assert pr.pr_metadata["ci_info"]["build_id"] == "12345"

    def test_check_run_metadata_field(self) -> None:
        """
        Why: Verify check_metadata field accepts dict data
        What: Tests that check_metadata can store complex data
        How: Creates check with metadata and verifies storage
        """
        metadata = {
            "error_details": {"line": 42, "file": "test.py"},
            "suggestions": ["Fix import", "Add type hint"],
        }

        pr_id = uuid.uuid4()
        check = CheckRun(
            pr_id=pr_id,
            external_id="1",
            check_name="test",
            status=CheckStatus.COMPLETED,
            check_metadata=metadata,
        )

        assert check.check_metadata == metadata
        assert check.check_metadata["error_details"]["line"] == 42

    def test_string_field_lengths(self) -> None:
        """
        Why: Verify string fields accept reasonable lengths
        What: Tests that string fields can store expected data sizes
        How: Creates models with various string field lengths
        """
        # Test reasonable field lengths
        long_title = "A" * 500  # Should be acceptable
        long_description = "B" * 2000  # Should be acceptable

        repository_id = uuid.uuid4()
        pr = PullRequest(
            repository_id=repository_id,
            pr_number=1,
            title=long_title,
            body=long_description,
            author="user",
        )

        assert pr.title == long_title
        assert pr.body == long_description


class TestModelRelationshipFields:
    """Test relationship field definitions."""

    def test_models_have_relationship_fields(self) -> None:
        """
        Why: Verify models define relationship fields for ORM
        What: Tests that relationship fields are defined on models
        How: Checks for relationship attributes on model classes
        """
        # Repository should have pull_requests relationship
        assert hasattr(Repository, "pull_requests")

        # PullRequest should have relationships
        assert hasattr(PullRequest, "repository")
        assert hasattr(PullRequest, "check_runs")
        assert hasattr(PullRequest, "state_history")
        assert hasattr(PullRequest, "reviews")

        # CheckRun should have relationships
        assert hasattr(CheckRun, "pull_request")
        assert hasattr(CheckRun, "analysis_results")

        # AnalysisResult should have relationships
        assert hasattr(AnalysisResult, "check_run")
        assert hasattr(AnalysisResult, "fix_attempts")

        # FixAttempt should have relationship
        assert hasattr(FixAttempt, "analysis_result")

        # PRStateHistory should have relationship
        assert hasattr(PRStateHistory, "pull_request")

        # Review should have relationship
        assert hasattr(Review, "pull_request")
