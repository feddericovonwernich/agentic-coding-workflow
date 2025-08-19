"""PullRequest SQLAlchemy model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import CheckRun, PRStateHistory, Repository, Review

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel
from .enums import PRState, TriggerEvent


class PullRequest(BaseModel):
    """Model for pull request tracking."""

    __tablename__ = "pull_requests"

    # Foreign key to repository
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id"), nullable=False
    )

    # Basic PR information
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[PRState] = mapped_column(nullable=False)
    draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Branch information
    base_branch: Mapped[str] = mapped_column(String(200), nullable=False)
    head_branch: Mapped[str] = mapped_column(String(200), nullable=False)
    base_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False)

    # URLs and metadata
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # Tracking fields
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository", back_populates="pull_requests"
    )
    check_runs: Mapped[list["CheckRun"]] = relationship(
        "CheckRun", back_populates="pull_request", cascade="all, delete-orphan"
    )
    state_history: Mapped[list["PRStateHistory"]] = relationship(
        "PRStateHistory", back_populates="pull_request", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(
        "Review", back_populates="pull_request", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("repository_id", "pr_number", name="uq_pr_repo_number"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<PullRequest(id={self.id}, repo_id={self.repository_id}, "
            f"pr_number={self.pr_number}, state={self.state})>"
        )

    @property
    def is_active(self) -> bool:
        """Check if PR is in an active state."""
        return self.state == PRState.OPENED

    @property
    def is_draft_or_closed(self) -> bool:
        """Check if PR is draft or closed."""
        return self.draft or self.state in (PRState.CLOSED, PRState.MERGED)

    def can_transition_to(self, new_state: PRState) -> bool:
        """Check if PR can transition to new state."""
        current = self.state

        # Valid state transitions
        valid_transitions = {
            PRState.OPENED: {PRState.CLOSED, PRState.MERGED},
            PRState.CLOSED: {PRState.OPENED},  # Can reopen
            PRState.MERGED: set(),  # Cannot transition from merged
        }

        return new_state in valid_transitions.get(current, set())

    def update_state(
        self,
        new_state: PRState,
        trigger_event: TriggerEvent,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update PR state with validation."""
        if not self.can_transition_to(new_state):
            raise ValueError(
                f"Invalid state transition from {self.state} to {new_state}"
            )

        self.state = new_state

        # Update metadata if provided
        if metadata:
            if self.pr_metadata is None:
                self.pr_metadata = {}
            self.pr_metadata.update(metadata)

    def get_latest_check_runs(self) -> list["CheckRun"]:
        """Get the most recent check runs for this PR."""
        if not self.check_runs:
            return []

        # Group by check name and get the latest for each
        latest_checks: dict[str, CheckRun] = {}
        for check in self.check_runs:
            check_name = check.check_name
            if (
                check_name not in latest_checks
                or check.created_at > latest_checks[check_name].created_at
            ):
                latest_checks[check_name] = check

        return list(latest_checks.values())

    def has_failed_checks(self) -> bool:
        """Check if PR has any failed check runs."""
        from .enums import CheckConclusion, CheckStatus

        latest_checks = self.get_latest_check_runs()
        return any(
            check.status == CheckStatus.COMPLETED
            and check.conclusion == CheckConclusion.FAILURE
            for check in latest_checks
        )

    def get_failed_checks(self) -> list["CheckRun"]:
        """Get all failed check runs for this PR."""
        from .enums import CheckConclusion, CheckStatus

        latest_checks = self.get_latest_check_runs()
        return [
            check
            for check in latest_checks
            if check.status == CheckStatus.COMPLETED
            and check.conclusion == CheckConclusion.FAILURE
        ]

    def is_ready_for_review(self) -> bool:
        """Check if PR is ready for review (not draft, has passing checks)."""
        if self.draft or not self.is_active:
            return False

        # If there are no checks, consider it ready
        latest_checks = self.get_latest_check_runs()
        if not latest_checks:
            return True

        # All checks must be completed and successful
        from .enums import CheckConclusion, CheckStatus

        return all(
            check.status == CheckStatus.COMPLETED
            and check.conclusion == CheckConclusion.SUCCESS
            for check in latest_checks
        )
