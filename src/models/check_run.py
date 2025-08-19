"""CheckRun SQLAlchemy model."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel
from .enums import CheckConclusion, CheckStatus


class CheckRun(BaseModel):
    """Model for GitHub check run tracking."""

    __tablename__ = "check_runs"

    # Foreign key to pull request
    pr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pull_requests.id"), nullable=False
    )

    # GitHub check run information
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    check_name: Mapped[str] = mapped_column(String(200), nullable=False)
    check_suite_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[CheckStatus] = mapped_column(nullable=False)
    conclusion: Mapped[Optional[CheckConclusion]] = mapped_column(nullable=True)

    # URLs and metadata
    details_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    logs_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    output_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing information
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Additional data
    check_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    pull_request: Mapped["PullRequest"] = relationship(
        "PullRequest", back_populates="check_runs"
    )
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(
        "AnalysisResult", back_populates="check_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<CheckRun(id={self.id}, pr_id={self.pr_id}, name={self.check_name}, status={self.status})>"

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
    def duration(self) -> Optional[float]:
        """Get duration of check run in seconds."""
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def can_transition_to_status(self, new_status: CheckStatus) -> bool:
        """Check if check run can transition to new status."""
        current = self.status
        
        # Valid status transitions
        valid_transitions = {
            CheckStatus.QUEUED: {CheckStatus.IN_PROGRESS, CheckStatus.CANCELLED},
            CheckStatus.IN_PROGRESS: {CheckStatus.COMPLETED, CheckStatus.CANCELLED},
            CheckStatus.COMPLETED: set(),  # Cannot transition from completed
            CheckStatus.CANCELLED: {CheckStatus.QUEUED},  # Can restart cancelled
        }
        
        return new_status in valid_transitions.get(current, set())

    def update_status(
        self,
        new_status: CheckStatus,
        conclusion: Optional[CheckConclusion] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> None:
        """Update check run status with validation."""
        if not self.can_transition_to_status(new_status):
            raise ValueError(
                f"Invalid status transition from {self.status} to {new_status}"
            )
        
        old_status = self.status
        self.status = new_status
        
        # Set conclusion if provided and status is completed
        if new_status == CheckStatus.COMPLETED and conclusion is not None:
            self.conclusion = conclusion
            if self.completed_at is None:
                self.completed_at = datetime.now(timezone.utc)
        
        # Set started_at if transitioning to in_progress for the first time
        if (
            new_status == CheckStatus.IN_PROGRESS 
            and old_status == CheckStatus.QUEUED 
            and self.started_at is None
        ):
            self.started_at = datetime.now(timezone.utc)
        
        # Update metadata if provided
        if metadata:
            if self.check_metadata is None:
                self.check_metadata = {}
            self.check_metadata.update(metadata)

    def is_actionable_failure(self) -> bool:
        """Check if this is a failure that can be automatically fixed."""
        if not self.is_failed:
            return False
        
        # Define patterns that indicate actionable failures
        actionable_patterns = [
            "lint", "format", "style", "test", "build", "compile"
        ]
        
        check_name_lower = self.check_name.lower()
        return any(pattern in check_name_lower for pattern in actionable_patterns)

    def get_failure_category(self) -> Optional[str]:
        """Categorize the type of failure for routing to appropriate handlers."""
        if not self.is_failed:
            return None
        
        check_name_lower = self.check_name.lower()
        
        # Categorize based on check name patterns
        if any(word in check_name_lower for word in ["lint", "eslint", "flake8", "ruff"]):
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

    def extract_error_summary(self) -> Optional[str]:
        """Extract a concise error summary from output."""
        if not self.is_failed or not self.output_text:
            return None
        
        # Try to extract key error information
        lines = self.output_text.split('\n')
        
        # Look for common error patterns
        error_lines = []
        for line in lines:
            line = line.strip()
            if any(keyword in line.lower() for keyword in ['error:', 'failed:', 'exception:']):
                error_lines.append(line)
        
        if error_lines:
            # Return first few error lines, limited in length
            summary = ' | '.join(error_lines[:3])
            return summary[:500] if len(summary) > 500 else summary
        
        # Fallback to output summary if available
        if self.output_summary:
            return self.output_summary[:200] if len(self.output_summary) > 200 else self.output_summary
        
        return "Check failed - see logs for details"