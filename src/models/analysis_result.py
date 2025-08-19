"""AnalysisResult SQLAlchemy model."""

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import CheckRun, FixAttempt, PullRequest

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel


class AnalysisResult(BaseModel):
    """Model for check run analysis results."""

    __tablename__ = "analysis_results"

    # Foreign key to check run
    check_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("check_runs.id"), nullable=False
    )

    # Analysis results
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    analysis_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # Relationships
    check_run: Mapped["CheckRun"] = relationship(
        "CheckRun", back_populates="analysis_results"
    )
    fix_attempts: Mapped[list["FixAttempt"]] = relationship(
        "FixAttempt", back_populates="analysis_result", cascade="all, delete-orphan"
    )

    @property
    def pull_request(self) -> "PullRequest":
        """Get the pull request via the check run."""
        return self.check_run.pull_request

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<AnalysisResult(id={self.id}, category={self.category}, "
            f"confidence={self.confidence_score})>"
        )
