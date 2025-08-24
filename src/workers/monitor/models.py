"""Processing data models for PR discovery and change detection."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.models.enums import CheckConclusion, CheckStatus, PRState


@dataclass
class PRData:
    """Raw GitHub PR data representation."""

    # Basic PR information
    number: int
    title: str
    author: str
    state: str  # GitHub API returns string, we'll convert to PRState later
    draft: bool

    # Branch information
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str

    # URLs and metadata
    url: str
    body: str | None = None

    # GitHub metadata
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    milestone: str | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None
    merged_at: datetime | None = None

    # Additional metadata
    mergeable: bool | None = None
    mergeable_state: str | None = None
    merged: bool = False
    merge_commit_sha: str | None = None

    # Raw GitHub data for extensibility
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_pr_state(self) -> PRState:
        """Convert GitHub state string to PRState enum."""
        state_mapping = {
            "open": PRState.OPENED,
            "closed": PRState.MERGED if self.merged else PRState.CLOSED,
        }
        return state_mapping.get(self.state.lower(), PRState.OPENED)

    def has_changed_since(self, last_updated: datetime) -> bool:
        """Check if PR has been updated since given timestamp."""
        if not self.updated_at:
            return True  # Assume changed if no timestamp
        return self.updated_at > last_updated

    def get_metadata_dict(self) -> dict[str, Any]:
        """Get metadata dictionary for database storage."""
        return {
            "labels": self.labels,
            "assignees": self.assignees,
            "milestone": self.milestone,
            "mergeable": self.mergeable,
            "mergeable_state": self.mergeable_state,
            "merge_commit_sha": self.merge_commit_sha,
            "github_created_at": self.created_at.isoformat()
            if self.created_at
            else None,
            "github_updated_at": self.updated_at.isoformat()
            if self.updated_at
            else None,
            "github_closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "github_merged_at": self.merged_at.isoformat() if self.merged_at else None,
        }


@dataclass
class CheckRunData:
    """Raw GitHub check run data representation."""

    # GitHub check run information
    external_id: str
    check_name: str
    status: str  # GitHub API returns string, we'll convert to CheckStatus later
    check_suite_id: str | None = None
    conclusion: str | None = None  # Convert to CheckConclusion later

    # URLs and output
    details_url: str | None = None
    logs_url: str | None = None
    output_title: str | None = None
    output_summary: str | None = None
    output_text: str | None = None

    # Timing information
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Raw GitHub data
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_check_status(self) -> CheckStatus:
        """Convert GitHub status string to CheckStatus enum."""
        status_mapping = {
            "queued": CheckStatus.QUEUED,
            "in_progress": CheckStatus.IN_PROGRESS,
            "completed": CheckStatus.COMPLETED,
            "cancelled": CheckStatus.CANCELLED,
        }
        return status_mapping.get(self.status.lower(), CheckStatus.QUEUED)

    def to_check_conclusion(self) -> CheckConclusion | None:
        """Convert GitHub conclusion string to CheckConclusion enum."""
        if not self.conclusion:
            return None

        conclusion_mapping = {
            "success": CheckConclusion.SUCCESS,
            "failure": CheckConclusion.FAILURE,
            "neutral": CheckConclusion.NEUTRAL,
            "cancelled": CheckConclusion.CANCELLED,
            "timed_out": CheckConclusion.TIMED_OUT,
            "action_required": CheckConclusion.ACTION_REQUIRED,
        }
        return conclusion_mapping.get(self.conclusion.lower())

    def has_status_changed(self, current_status: CheckStatus) -> bool:
        """Check if status has changed from current database value."""
        return self.to_check_status() != current_status

    def has_conclusion_changed(
        self, current_conclusion: CheckConclusion | None
    ) -> bool:
        """Check if conclusion has changed from current database value."""
        return self.to_check_conclusion() != current_conclusion

    def get_metadata_dict(self) -> dict[str, Any]:
        """Get metadata dictionary for database storage."""
        return {
            "check_suite_id": self.check_suite_id,
            "output_title": self.output_title,
            "github_started_at": self.started_at.isoformat()
            if self.started_at
            else None,
            "github_completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "raw_output": self.raw_data.get("output", {}),
        }


@dataclass
class PRChangeRecord:
    """Record of changes detected for a single PR."""

    pr_data: PRData
    change_type: str  # "new", "updated", "state_changed"
    existing_pr_id: uuid.UUID | None = None

    # Specific changes detected
    title_changed: bool = False
    state_changed: bool = False
    draft_changed: bool = False
    metadata_changed: bool = False
    sha_changed: bool = False

    # Old values for comparison
    old_title: str | None = None
    old_state: PRState | None = None
    old_head_sha: str | None = None


@dataclass
class CheckRunChangeRecord:
    """Record of changes detected for a single check run."""

    check_data: CheckRunData
    pr_id: uuid.UUID
    change_type: str  # "new", "status_changed", "conclusion_changed", "updated"
    existing_check_id: uuid.UUID | None = None

    # Specific changes detected
    status_changed: bool = False
    conclusion_changed: bool = False
    timing_changed: bool = False

    # Old values for comparison
    old_status: CheckStatus | None = None
    old_conclusion: CheckConclusion | None = None


@dataclass
class ChangeSet:
    """Collection of detected changes for a repository."""

    repository_id: uuid.UUID

    # PR changes
    new_prs: list[PRChangeRecord] = field(default_factory=list)
    updated_prs: list[PRChangeRecord] = field(default_factory=list)

    # Check run changes
    new_check_runs: list[CheckRunChangeRecord] = field(default_factory=list)
    updated_check_runs: list[CheckRunChangeRecord] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes to process."""
        return bool(
            self.new_prs
            or self.updated_prs
            or self.new_check_runs
            or self.updated_check_runs
        )

    @property
    def total_changes(self) -> int:
        """Get total number of changes."""
        return (
            len(self.new_prs)
            + len(self.updated_prs)
            + len(self.new_check_runs)
            + len(self.updated_check_runs)
        )

    def get_pr_ids_with_changes(self) -> list[uuid.UUID]:
        """Get list of PR IDs that have changes."""
        pr_ids = set()

        for pr_change in self.updated_prs:
            if pr_change.existing_pr_id:
                pr_ids.add(pr_change.existing_pr_id)

        for check_change in self.new_check_runs:
            pr_ids.add(check_change.pr_id)

        for check_change in self.updated_check_runs:
            pr_ids.add(check_change.pr_id)

        return list(pr_ids)


@dataclass
class ProcessingError:
    """Error that occurred during processing."""

    error_type: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    # Optional details for specific error types
    repository_id: uuid.UUID | None = None
    pr_number: int | None = None
    check_run_id: str | None = None

    def __str__(self) -> str:
        """String representation of error."""
        context_str = ""
        if self.repository_id:
            context_str += f" repo={self.repository_id}"
        if self.pr_number:
            context_str += f" pr={self.pr_number}"
        if self.check_run_id:
            context_str += f" check={self.check_run_id}"

        return f"{self.error_type}: {self.message}{context_str}"


@dataclass
class ProcessingResult:
    """Results of processing a single repository."""

    repository_id: uuid.UUID
    repository_url: str

    # Processing metrics
    prs_discovered: int = 0
    check_runs_discovered: int = 0
    changes_detected: int = 0
    changes_synchronized: int = 0

    # Breakdown of changes
    new_prs: int = 0
    updated_prs: int = 0
    new_check_runs: int = 0
    updated_check_runs: int = 0

    # Processing timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    # Error tracking
    errors: list[ProcessingError] = field(default_factory=list)
    success: bool = True

    @property
    def processing_time(self) -> float:
        """Get processing time in seconds."""
        if not self.completed_at:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def has_errors(self) -> bool:
        """Check if processing had any errors."""
        return len(self.errors) > 0

    def add_error(
        self,
        error_type: str,
        message: str,
        context: dict[str, Any] | None = None,
        pr_number: int | None = None,
        check_run_id: str | None = None,
    ) -> None:
        """Add an error to the processing result."""
        error = ProcessingError(
            error_type=error_type,
            message=message,
            context=context or {},
            repository_id=self.repository_id,
            pr_number=pr_number,
            check_run_id=check_run_id,
        )
        self.errors.append(error)

    def mark_completed(self) -> None:
        """Mark processing as completed."""
        self.completed_at = datetime.now()

    def update_from_changeset(self, changeset: ChangeSet) -> None:
        """Update metrics from a processed changeset."""
        self.changes_detected = changeset.total_changes
        self.new_prs = len(changeset.new_prs)
        self.updated_prs = len(changeset.updated_prs)
        self.new_check_runs = len(changeset.new_check_runs)
        self.updated_check_runs = len(changeset.updated_check_runs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "repository_id": str(self.repository_id),
            "repository_url": self.repository_url,
            "prs_discovered": self.prs_discovered,
            "check_runs_discovered": self.check_runs_discovered,
            "changes_detected": self.changes_detected,
            "changes_synchronized": self.changes_synchronized,
            "new_prs": self.new_prs,
            "updated_prs": self.updated_prs,
            "new_check_runs": self.new_check_runs,
            "updated_check_runs": self.updated_check_runs,
            "processing_time": self.processing_time,
            "success": self.success,
            "error_count": len(self.errors),
            "errors": [str(error) for error in self.errors],
        }


@dataclass
class BatchProcessingResult:
    """Results of processing multiple repositories."""

    # Aggregate metrics
    repositories_processed: int = 0
    total_prs_discovered: int = 0
    total_check_runs_discovered: int = 0
    total_changes_synchronized: int = 0

    # Processing timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    # Individual results
    results: list[ProcessingResult] = field(default_factory=list)

    @property
    def processing_time(self) -> float:
        """Get total processing time in seconds."""
        if not self.completed_at:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if not self.results:
            return 0.0
        successful = sum(1 for r in self.results if r.success)
        return (successful / len(self.results)) * 100

    @property
    def total_errors(self) -> int:
        """Get total number of errors across all repositories."""
        return sum(len(r.errors) for r in self.results)

    def add_result(self, result: ProcessingResult) -> None:
        """Add a repository processing result."""
        self.results.append(result)
        self.repositories_processed = len(self.results)
        self.total_prs_discovered += result.prs_discovered
        self.total_check_runs_discovered += result.check_runs_discovered
        self.total_changes_synchronized += result.changes_synchronized

    def mark_completed(self) -> None:
        """Mark batch processing as completed."""
        self.completed_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "repositories_processed": self.repositories_processed,
            "total_prs_discovered": self.total_prs_discovered,
            "total_check_runs_discovered": self.total_check_runs_discovered,
            "total_changes_synchronized": self.total_changes_synchronized,
            "processing_time": self.processing_time,
            "success_rate": self.success_rate,
            "total_errors": self.total_errors,
            "results": [r.to_dict() for r in self.results],
        }
