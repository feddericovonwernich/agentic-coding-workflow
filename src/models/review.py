"""Review SQLAlchemy model."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel


class Review(BaseModel):
    """Model for PR review tracking."""

    __tablename__ = "reviews"

    # Foreign key to pull request
    pr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pull_requests.id"), nullable=False
    )

    # Review details
    reviewer_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    decision: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    # Timing information
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    pull_request: Mapped["PullRequest"] = relationship(
        "PullRequest", back_populates="reviews"
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Review(id={self.id}, pr_id={self.pr_id}, reviewer_type={self.reviewer_type})>"