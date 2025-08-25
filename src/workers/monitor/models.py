"""Data models and interfaces for the PR Monitor Worker.

This module defines data classes and abstract interfaces for PR discovery,
processing, and synchronization operations. These models provide type safety
and clear contracts between components in the monitoring system.

All data models are designed to integrate seamlessly with existing SQLAlchemy
models and provide comprehensive validation and debugging capabilities.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ...models.enums import CheckConclusion, CheckStatus, PRState, TriggerEvent


class OperationStatus(str, Enum):
    """Status of database operations."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ChangeType(str, Enum):
    """Types of state changes that can be detected."""

    PR_CREATED = "pr_created"
    PR_UPDATED = "pr_updated"
    PR_STATE_CHANGED = "pr_state_changed"
    CHECK_RUN_CREATED = "check_run_created"
    CHECK_RUN_UPDATED = "check_run_updated"
    CHECK_RUN_STATUS_CHANGED = "check_run_status_changed"


class SeverityLevel(str, Enum):
    """Severity levels for errors and events."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ProcessingMetrics:
    """Performance metrics for PR monitoring operations.

    Tracks API usage, processing times, and success/failure rates
    to enable performance monitoring and optimization.
    """

    # API Usage metrics
    github_api_calls_made: int = 0
    github_api_calls_remaining: int = 0
    github_rate_limit_reset_time: datetime | None = None

    # Processing time metrics (in seconds)
    discovery_duration: float = 0.0
    check_run_discovery_duration: float = 0.0
    state_detection_duration: float = 0.0
    synchronization_duration: float = 0.0
    total_processing_duration: float = 0.0

    # Success/failure tracking
    prs_discovered: int = 0
    prs_processed_successfully: int = 0
    prs_failed_processing: int = 0
    check_runs_discovered: int = 0
    check_runs_processed_successfully: int = 0
    check_runs_failed_processing: int = 0

    # Error tracking
    errors_encountered: list[str] = field(default_factory=list)
    warnings_issued: list[str] = field(default_factory=list)

    # Resource usage
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0

    def __str__(self) -> str:
        """Return human-readable string representation."""
        success_rate = (
            (self.prs_processed_successfully / max(self.prs_discovered, 1)) * 100
            if self.prs_discovered > 0
            else 0.0
        )
        return (
            f"ProcessingMetrics(prs_discovered={self.prs_discovered}, "
            f"success_rate={success_rate:.1f}%, "
            f"total_duration={self.total_processing_duration:.2f}s, "
            f"api_calls={self.github_api_calls_made})"
        )

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"ProcessingMetrics("
            f"prs_discovered={self.prs_discovered}, "
            f"prs_successful={self.prs_processed_successfully}, "
            f"prs_failed={self.prs_failed_processing}, "
            f"check_runs_discovered={self.check_runs_discovered}, "
            f"total_duration={self.total_processing_duration:.2f}s, "
            f"api_calls={self.github_api_calls_made}, "
            f"errors={len(self.errors_encountered)})"
        )

    @property
    def success_rate(self) -> float:
        """Calculate PR processing success rate as percentage."""
        if self.prs_discovered == 0:
            return 0.0
        return (self.prs_processed_successfully / self.prs_discovered) * 100

    @property
    def check_run_success_rate(self) -> float:
        """Calculate check run processing success rate as percentage."""
        if self.check_runs_discovered == 0:
            return 0.0
        return (
            self.check_runs_processed_successfully / self.check_runs_discovered
        ) * 100

    @property
    def has_errors(self) -> bool:
        """Check if any errors were encountered during processing."""
        return len(self.errors_encountered) > 0 or self.prs_failed_processing > 0

    @property
    def is_rate_limited(self) -> bool:
        """Check if GitHub API rate limiting is active."""
        return (
            self.github_api_calls_remaining is not None
            and self.github_api_calls_remaining <= 100
        )

    def validate(self) -> bool:
        """Validate metric data integrity.

        Returns:
            bool: True if all metrics are valid

        Raises:
            ValueError: If any metrics are invalid
        """
        if self.prs_discovered < 0:
            raise ValueError("PRs discovered cannot be negative")

        if self.prs_processed_successfully > self.prs_discovered:
            raise ValueError("Successful PRs cannot exceed total discovered")

        if self.total_processing_duration < 0:
            raise ValueError("Processing duration cannot be negative")

        if self.github_api_calls_made < 0:
            raise ValueError("API calls made cannot be negative")

        return True


@dataclass(frozen=True)
class DiscoveryResult:
    """Result of PR discovery from GitHub API.

    Encapsulates pull request data with metadata about the discovery
    operation, including pagination info and filtering results.
    """

    # Repository information
    repository_id: uuid.UUID
    repository_name: str
    repository_owner: str

    # PR data from GitHub API
    pr_number: int
    title: str
    author: str
    state: PRState
    draft: bool

    # Branch information
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str

    # URLs and metadata
    url: str
    body: str | None = None
    pr_metadata: dict[str, Any] | None = None

    # Discovery metadata
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    last_updated_at: datetime | None = None
    etag: str | None = None

    # GitHub API metadata
    github_id: int = 0
    github_node_id: str = ""

    def __str__(self) -> str:
        """Return human-readable string representation."""
        return (
            f"DiscoveryResult(#{self.pr_number}: {self.title[:50]}... "
            f"by {self.author}, state={self.state}, draft={self.draft})"
        )

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"DiscoveryResult("
            f"repo={self.repository_owner}/{self.repository_name}, "
            f"pr_number={self.pr_number}, "
            f"title='{self.title[:30]}...', "
            f"author={self.author}, "
            f"state={self.state}, "
            f"draft={self.draft}, "
            f"base={self.base_branch}, "
            f"head={self.head_branch})"
        )

    @property
    def is_active(self) -> bool:
        """Check if PR is in an active state for monitoring."""
        return self.state == PRState.OPENED and not self.draft

    @property
    def repository_full_name(self) -> str:
        """Get full repository name in owner/repo format."""
        return f"{self.repository_owner}/{self.repository_name}"

    @property
    def is_mergeable_state(self) -> bool:
        """Check if PR is in a state that allows merging."""
        return self.state == PRState.OPENED and not self.draft

    def validate(self) -> bool:
        """Validate PR data integrity.

        Returns:
            bool: True if all data is valid

        Raises:
            ValueError: If any data is invalid
        """
        if not self.repository_name or not self.repository_owner:
            raise ValueError("Repository name and owner are required")

        if self.pr_number <= 0:
            raise ValueError("PR number must be positive")

        if not self.title.strip():
            raise ValueError("PR title cannot be empty")

        if not self.author.strip():
            raise ValueError("PR author cannot be empty")

        if not self.base_branch or not self.head_branch:
            raise ValueError("Base and head branches are required")

        if not self.base_sha or not self.head_sha:
            raise ValueError("Base and head SHAs are required")

        if not self.url:
            raise ValueError("PR URL is required")

        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "repository_id": str(self.repository_id),
            "repository_name": self.repository_name,
            "repository_owner": self.repository_owner,
            "pr_number": self.pr_number,
            "title": self.title,
            "author": self.author,
            "state": self.state.value,
            "draft": self.draft,
            "base_branch": self.base_branch,
            "head_branch": self.head_branch,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "url": self.url,
            "body": self.body,
            "pr_metadata": self.pr_metadata,
            "discovered_at": self.discovered_at.isoformat(),
            "last_updated_at": (
                self.last_updated_at.isoformat() if self.last_updated_at else None
            ),
            "etag": self.etag,
            "github_id": self.github_id,
            "github_node_id": self.github_node_id,
        }


@dataclass(frozen=True)
class CheckRunDiscovery:
    """Result of check run discovery from GitHub API.

    Encapsulates check run data with metadata about status tracking
    and failure analysis capabilities.
    """

    # Associated PR information
    pr_id: uuid.UUID
    pr_number: int

    # GitHub check run information
    github_check_run_id: str
    check_name: str
    check_suite_id: str | None = None
    status: CheckStatus = CheckStatus.QUEUED
    conclusion: CheckConclusion | None = None

    # URLs and output
    details_url: str | None = None
    logs_url: str | None = None
    output_summary: str | None = None
    output_text: str | None = None

    # Timing information
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Discovery metadata
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    check_metadata: dict[str, Any] | None = None

    def __str__(self) -> str:
        """Return human-readable string representation."""
        status_display = f"{self.status}"
        if self.conclusion:
            status_display = f"{self.status}:{self.conclusion}"

        return (
            f"CheckRunDiscovery({self.check_name} for PR #{self.pr_number}, "
            f"status={status_display})"
        )

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"CheckRunDiscovery("
            f"pr_number={self.pr_number}, "
            f"check_name='{self.check_name}', "
            f"github_id={self.github_check_run_id}, "
            f"status={self.status}, "
            f"conclusion={self.conclusion}, "
            f"started_at={self.started_at}, "
            f"completed_at={self.completed_at})"
        )

    @property
    def is_completed(self) -> bool:
        """Check if check run is completed."""
        return self.status == CheckStatus.COMPLETED

    @property
    def is_successful(self) -> bool:
        """Check if check run completed successfully."""
        return (
            self.status == CheckStatus.COMPLETED
            and self.conclusion == CheckConclusion.SUCCESS
        )

    @property
    def is_failed(self) -> bool:
        """Check if check run failed."""
        return (
            self.status == CheckStatus.COMPLETED
            and self.conclusion == CheckConclusion.FAILURE
        )

    @property
    def is_in_progress(self) -> bool:
        """Check if check run is currently running."""
        return self.status in (CheckStatus.QUEUED, CheckStatus.IN_PROGRESS)

    @property
    def duration(self) -> float | None:
        """Get duration of check run in seconds."""
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def is_actionable_failure(self) -> bool:
        """Check if this is a failure that can be automatically fixed."""
        if not self.is_failed:
            return False

        # Define patterns that indicate actionable failures
        actionable_patterns = ["lint", "format", "style", "test", "build", "compile"]
        check_name_lower = self.check_name.lower()
        return any(pattern in check_name_lower for pattern in actionable_patterns)

    def get_failure_category(self) -> str | None:
        """Categorize the type of failure for routing to appropriate handlers."""
        if not self.is_failed:
            return None

        check_name_lower = self.check_name.lower()

        # Categorize based on check name patterns
        if any(
            word in check_name_lower for word in ["lint", "eslint", "flake8", "ruff"]
        ):
            return "lint"
        elif any(word in check_name_lower for word in ["format", "prettier", "black"]):
            return "format"
        elif any(word in check_name_lower for word in ["test", "pytest", "jest"]):
            return "test"
        elif any(word in check_name_lower for word in ["build", "compile", "webpack"]):
            return "build"
        elif any(word in check_name_lower for word in ["type", "mypy", "typescript"]):
            return "type"
        elif any(word in check_name_lower for word in ["security", "audit"]):
            return "security"
        else:
            return "other"

    def validate(self) -> bool:
        """Validate check run data integrity.

        Returns:
            bool: True if all data is valid

        Raises:
            ValueError: If any data is invalid
        """
        if not self.github_check_run_id:
            raise ValueError("GitHub check run ID is required")

        if not self.check_name.strip():
            raise ValueError("Check name cannot be empty")

        if self.pr_number <= 0:
            raise ValueError("PR number must be positive")

        if self.status == CheckStatus.COMPLETED and self.conclusion is None:
            raise ValueError("Completed check runs must have a conclusion")

        if (
            self.started_at
            and self.completed_at
            and self.started_at > self.completed_at
        ):
            raise ValueError("Started time cannot be after completed time")

        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pr_id": str(self.pr_id),
            "pr_number": self.pr_number,
            "github_check_run_id": self.github_check_run_id,
            "check_name": self.check_name,
            "check_suite_id": self.check_suite_id,
            "status": self.status.value,
            "conclusion": self.conclusion.value if self.conclusion else None,
            "details_url": self.details_url,
            "logs_url": self.logs_url,
            "output_summary": self.output_summary,
            "output_text": self.output_text,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "discovered_at": self.discovered_at.isoformat(),
            "check_metadata": self.check_metadata,
        }


@dataclass(frozen=True)
class StateChangeEvent:
    """Represents a detected change in PR or check run state.

    Captures both the previous and new states with metadata about
    what changed and when the change was detected.
    """

    # Event identification
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: ChangeType = ChangeType.PR_UPDATED
    detected_at: datetime = field(default_factory=datetime.utcnow)

    # Object identification
    pr_id: uuid.UUID = field(default_factory=uuid.uuid4)
    pr_number: int = 0
    repository_id: uuid.UUID = field(default_factory=uuid.uuid4)

    # State comparison
    old_state: dict[str, Any] | None = None
    new_state: dict[str, Any] | None = None
    changed_fields: list[str] = field(default_factory=list)

    # Additional context
    trigger_event: TriggerEvent | None = None
    severity: SeverityLevel = SeverityLevel.MEDIUM
    metadata: dict[str, Any] | None = None

    # Check run specific (when applicable)
    check_run_id: uuid.UUID | None = None
    check_run_name: str | None = None

    def __str__(self) -> str:
        """Return human-readable string representation."""
        if self.check_run_name:
            return (
                f"StateChangeEvent({self.event_type} in PR #{self.pr_number}, "
                f"check: {self.check_run_name}, severity={self.severity})"
            )
        return (
            f"StateChangeEvent({self.event_type} in PR #{self.pr_number}, "
            f"fields={self.changed_fields}, severity={self.severity})"
        )

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"StateChangeEvent("
            f"event_id={self.event_id}, "
            f"event_type={self.event_type}, "
            f"pr_number={self.pr_number}, "
            f"changed_fields={self.changed_fields}, "
            f"severity={self.severity}, "
            f"detected_at={self.detected_at}, "
            f"check_run_name={self.check_run_name})"
        )

    @property
    def is_significant_change(self) -> bool:
        """Check if this change requires immediate action."""
        significant_fields = {"state", "status", "conclusion", "head_sha", "base_sha"}
        return self.severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL) or any(
            field in significant_fields for field in self.changed_fields
        )

    @property
    def is_check_run_event(self) -> bool:
        """Check if this event is related to check runs."""
        return self.event_type in (
            ChangeType.CHECK_RUN_CREATED,
            ChangeType.CHECK_RUN_UPDATED,
            ChangeType.CHECK_RUN_STATUS_CHANGED,
        )

    @property
    def is_pr_event(self) -> bool:
        """Check if this event is related to PR state."""
        return self.event_type in (
            ChangeType.PR_CREATED,
            ChangeType.PR_UPDATED,
            ChangeType.PR_STATE_CHANGED,
        )

    def get_change_summary(self) -> str:
        """Get a human-readable summary of what changed."""
        if not self.changed_fields:
            return f"{self.event_type.value} detected"

        changes = []
        for field_name in self.changed_fields:
            old_val = self.old_state.get(field_name) if self.old_state else None
            new_val = self.new_state.get(field_name) if self.new_state else None
            if old_val != new_val:
                changes.append(f"{field_name}: {old_val} → {new_val}")

        return "; ".join(changes) if changes else "No specific changes detected"

    def validate(self) -> bool:
        """Validate event data integrity.

        Returns:
            bool: True if all data is valid

        Raises:
            ValueError: If any data is invalid
        """
        if not self.event_id:
            raise ValueError("Event ID is required")

        if self.pr_number <= 0:
            raise ValueError("PR number must be positive")

        if self.is_check_run_event and not self.check_run_name:
            raise ValueError("Check run events must have a check run name")

        if self.old_state and self.new_state and self.old_state == self.new_state:
            raise ValueError("Old and new states cannot be identical")

        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "detected_at": self.detected_at.isoformat(),
            "pr_id": str(self.pr_id),
            "pr_number": self.pr_number,
            "repository_id": str(self.repository_id),
            "old_state": self.old_state,
            "new_state": self.new_state,
            "changed_fields": self.changed_fields,
            "trigger_event": self.trigger_event.value if self.trigger_event else None,
            "severity": self.severity.value,
            "metadata": self.metadata,
            "check_run_id": str(self.check_run_id) if self.check_run_id else None,
            "check_run_name": self.check_run_name,
        }


@dataclass(frozen=True)
class SyncOperation:
    """Represents a database synchronization operation.

    Defines database operations with rollback capabilities and
    comprehensive error handling for data consistency.
    """

    # Operation identification
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operation_type: str = "sync"
    status: OperationStatus = OperationStatus.PENDING

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Data to sync
    pull_requests_to_create: list[DiscoveryResult] = field(default_factory=list)
    pull_requests_to_update: list[DiscoveryResult] = field(default_factory=list)
    check_runs_to_create: list[CheckRunDiscovery] = field(default_factory=list)
    check_runs_to_update: list[CheckRunDiscovery] = field(default_factory=list)

    # State changes to record
    state_changes: list[StateChangeEvent] = field(default_factory=list)

    # Rollback information
    rollback_data: dict[str, Any] | None = None
    can_rollback: bool = True

    # Error handling
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Metadata
    metadata: dict[str, Any] | None = None

    def __str__(self) -> str:
        """Return human-readable string representation."""
        total_operations = (
            len(self.pull_requests_to_create)
            + len(self.pull_requests_to_update)
            + len(self.check_runs_to_create)
            + len(self.check_runs_to_update)
        )
        return (
            f"SyncOperation(id={self.operation_id[:8]}..., "
            f"status={self.status}, operations={total_operations})"
        )

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"SyncOperation("
            f"operation_id={self.operation_id}, "
            f"operation_type={self.operation_type}, "
            f"status={self.status}, "
            f"prs_create={len(self.pull_requests_to_create)}, "
            f"prs_update={len(self.pull_requests_to_update)}, "
            f"checks_create={len(self.check_runs_to_create)}, "
            f"checks_update={len(self.check_runs_to_update)}, "
            f"state_changes={len(self.state_changes)}, "
            f"errors={len(self.errors)})"
        )

    @property
    def is_completed(self) -> bool:
        """Check if operation is completed (successfully or failed)."""
        return self.status in (OperationStatus.COMPLETED, OperationStatus.FAILED)

    @property
    def is_successful(self) -> bool:
        """Check if operation completed successfully."""
        return self.status == OperationStatus.COMPLETED and len(self.errors) == 0

    @property
    def has_errors(self) -> bool:
        """Check if operation has encountered errors."""
        return len(self.errors) > 0 or self.status == OperationStatus.FAILED

    @property
    def duration(self) -> float | None:
        """Get operation duration in seconds."""
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def total_operations(self) -> int:
        """Get total number of database operations."""
        return (
            len(self.pull_requests_to_create)
            + len(self.pull_requests_to_update)
            + len(self.check_runs_to_create)
            + len(self.check_runs_to_update)
        )

    @property
    def is_empty(self) -> bool:
        """Check if operation has no work to do."""
        return self.total_operations == 0 and len(self.state_changes) == 0

    def add_error(self, error_message: str) -> None:
        """Add an error message to the operation.

        Note: This method creates a new instance due to frozen dataclass.
        Use with caution or consider making this mutable if needed.
        """
        # This would require the dataclass not to be frozen
        # or using a different approach for error collection
        pass

    def add_warning(self, warning_message: str) -> None:
        """Add a warning message to the operation.

        Note: This method creates a new instance due to frozen dataclass.
        Use with caution or consider making this mutable if needed.
        """
        # This would require the dataclass not to be frozen
        # or using a different approach for warning collection
        pass

    def validate(self) -> bool:
        """Validate operation data integrity.

        Returns:
            bool: True if all data is valid

        Raises:
            ValueError: If any data is invalid
        """
        if not self.operation_id:
            raise ValueError("Operation ID is required")

        if not self.operation_type:
            raise ValueError("Operation type is required")

        # Validate all PRs in the operation
        for pr in self.pull_requests_to_create + self.pull_requests_to_update:
            pr.validate()

        # Validate all check runs in the operation
        for check_run in self.check_runs_to_create + self.check_runs_to_update:
            check_run.validate()

        # Validate all state changes
        for change in self.state_changes:
            change.validate()

        if (
            self.started_at
            and self.completed_at
            and self.started_at > self.completed_at
        ):
            raise ValueError("Started time cannot be after completed time")

        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "pull_requests_to_create": [
                pr.to_dict() for pr in self.pull_requests_to_create
            ],
            "pull_requests_to_update": [
                pr.to_dict() for pr in self.pull_requests_to_update
            ],
            "check_runs_to_create": [cr.to_dict() for cr in self.check_runs_to_create],
            "check_runs_to_update": [cr.to_dict() for cr in self.check_runs_to_update],
            "state_changes": [sc.to_dict() for sc in self.state_changes],
            "rollback_data": self.rollback_data,
            "can_rollback": self.can_rollback,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


# Abstract Interfaces


class PRDiscoveryInterface(ABC):
    """Abstract interface for PR discovery implementations.

    Defines the contract for discovering and fetching pull requests
    from GitHub repositories with support for filtering and pagination.
    """

    @abstractmethod
    async def discover_pull_requests(
        self,
        repository_id: uuid.UUID,
        repository_owner: str,
        repository_name: str,
        since: datetime | None = None,
        state_filter: PRState | None = None,
        include_drafts: bool = False,
    ) -> list[DiscoveryResult]:
        """Discover pull requests from a GitHub repository.

        Args:
            repository_id: UUID of the repository in our database
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            since: Only return PRs modified since this datetime
            state_filter: Filter by PR state (opened, closed, merged)
            include_drafts: Whether to include draft PRs

        Returns:
            List of discovered pull request results

        Raises:
            GitHubError: For GitHub API related errors
            ValidationError: For invalid parameters
        """
        pass

    @abstractmethod
    async def get_pull_request_details(
        self,
        repository_owner: str,
        repository_name: str,
        pr_number: int,
    ) -> DiscoveryResult:
        """Get detailed information for a specific pull request.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            pr_number: Pull request number

        Returns:
            Detailed pull request information

        Raises:
            GitHubNotFoundError: If PR doesn't exist
            GitHubError: For other GitHub API errors
        """
        pass

    @abstractmethod
    async def check_pr_exists(
        self,
        repository_owner: str,
        repository_name: str,
        pr_number: int,
    ) -> bool:
        """Check if a pull request exists without fetching full details.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            pr_number: Pull request number

        Returns:
            True if PR exists, False otherwise
        """
        pass


class CheckRunDiscoveryInterface(ABC):
    """Abstract interface for check run discovery implementations.

    Defines the contract for discovering and monitoring GitHub check runs
    associated with pull requests.
    """

    @abstractmethod
    async def discover_check_runs(
        self,
        repository_owner: str,
        repository_name: str,
        pr_number: int,
        ref: str,
    ) -> list[CheckRunDiscovery]:
        """Discover check runs for a pull request.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            pr_number: Pull request number
            ref: Git reference (SHA, branch, tag)

        Returns:
            List of discovered check run results

        Raises:
            GitHubError: For GitHub API related errors
        """
        pass

    @abstractmethod
    async def get_check_run_details(
        self,
        repository_owner: str,
        repository_name: str,
        check_run_id: str,
    ) -> CheckRunDiscovery:
        """Get detailed information for a specific check run.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            check_run_id: GitHub check run ID

        Returns:
            Detailed check run information

        Raises:
            GitHubNotFoundError: If check run doesn't exist
            GitHubError: For other GitHub API errors
        """
        pass

    @abstractmethod
    async def get_failed_check_runs(
        self,
        repository_owner: str,
        repository_name: str,
        pr_number: int,
        ref: str,
    ) -> list[CheckRunDiscovery]:
        """Get only failed check runs for a pull request.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            pr_number: Pull request number
            ref: Git reference (SHA, branch, tag)

        Returns:
            List of failed check run results
        """
        pass


class StateDetectorInterface(ABC):
    """Abstract interface for state change detection implementations.

    Defines the contract for detecting and analyzing changes in PR
    and check run states between monitoring cycles.
    """

    @abstractmethod
    async def detect_pr_changes(
        self,
        old_pr_data: DiscoveryResult | None,
        new_pr_data: DiscoveryResult,
    ) -> list[StateChangeEvent]:
        """Detect changes in pull request state.

        Args:
            old_pr_data: Previous PR state (None for new PRs)
            new_pr_data: Current PR state from discovery

        Returns:
            List of detected state change events
        """
        pass

    @abstractmethod
    async def detect_check_run_changes(
        self,
        old_check_runs: list[CheckRunDiscovery],
        new_check_runs: list[CheckRunDiscovery],
        pr_id: uuid.UUID,
        pr_number: int,
    ) -> list[StateChangeEvent]:
        """Detect changes in check run states.

        Args:
            old_check_runs: Previous check run states
            new_check_runs: Current check run states from discovery
            pr_id: Associated PR UUID
            pr_number: Associated PR number

        Returns:
            List of detected state change events
        """
        pass

    @abstractmethod
    async def analyze_significance(
        self,
        changes: list[StateChangeEvent],
    ) -> list[StateChangeEvent]:
        """Analyze and prioritize state changes by significance.

        Args:
            changes: List of detected changes to analyze

        Returns:
            List of changes with updated severity levels
        """
        pass

    @abstractmethod
    async def filter_actionable_changes(
        self,
        changes: list[StateChangeEvent],
    ) -> list[StateChangeEvent]:
        """Filter changes that require immediate action.

        Args:
            changes: List of all detected changes

        Returns:
            List of changes requiring immediate action
        """
        pass


class DataSynchronizerInterface(ABC):
    """Abstract interface for database synchronization implementations.

    Defines the contract for synchronizing discovered data with the
    local database with transaction support and rollback capabilities.
    """

    @abstractmethod
    async def create_sync_operation(
        self,
        pull_requests_to_create: list[DiscoveryResult] | None = None,
        pull_requests_to_update: list[DiscoveryResult] | None = None,
        check_runs_to_create: list[CheckRunDiscovery] | None = None,
        check_runs_to_update: list[CheckRunDiscovery] | None = None,
        state_changes: list[StateChangeEvent] | None = None,
    ) -> SyncOperation:
        """Create a new synchronization operation.

        Args:
            pull_requests_to_create: PRs to create in database
            pull_requests_to_update: PRs to update in database
            check_runs_to_create: Check runs to create in database
            check_runs_to_update: Check runs to update in database
            state_changes: State changes to record

        Returns:
            Configured sync operation ready for execution
        """
        pass

    @abstractmethod
    async def execute_sync_operation(
        self,
        operation: SyncOperation,
    ) -> SyncOperation:
        """Execute a synchronization operation with transaction support.

        Args:
            operation: Sync operation to execute

        Returns:
            Updated operation with results and status

        Raises:
            DatabaseError: For database-related errors
            ValidationError: For data validation errors
        """
        pass

    @abstractmethod
    async def rollback_sync_operation(
        self,
        operation: SyncOperation,
    ) -> SyncOperation:
        """Rollback a failed synchronization operation.

        Args:
            operation: Failed sync operation to rollback

        Returns:
            Updated operation with rollback status

        Raises:
            DatabaseError: If rollback fails
        """
        pass

    @abstractmethod
    async def get_operation_status(
        self,
        operation_id: str,
    ) -> SyncOperation | None:
        """Get the current status of a sync operation.

        Args:
            operation_id: Unique operation identifier

        Returns:
            Current operation status or None if not found
        """
        pass

    @abstractmethod
    async def cleanup_completed_operations(
        self,
        older_than: datetime | None = None,
    ) -> int:
        """Clean up completed sync operations to free resources.

        Args:
            older_than: Remove operations completed before this datetime

        Returns:
            Number of operations cleaned up
        """
        pass
