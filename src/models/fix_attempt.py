"""FixAttempt SQLAlchemy model."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel


class FixAttempt(BaseModel):
    """Model for automated fix attempts."""

    __tablename__ = "fix_attempts"

    # Foreign key to analysis result
    analysis_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_results.id"), nullable=False
    )

    # Fix attempt details
    fix_strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    # Timing information
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    analysis_result: Mapped["AnalysisResult"] = relationship(
        "AnalysisResult", back_populates="fix_attempts"
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<FixAttempt(id={self.id}, strategy={self.fix_strategy}, status={self.status})>"