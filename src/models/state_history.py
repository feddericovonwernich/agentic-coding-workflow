"""PRStateHistory SQLAlchemy model."""

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import PullRequest

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel
from .enums import PRState, TriggerEvent


class PRStateHistory(BaseModel):
    """Model for tracking pull request state changes."""

    __tablename__ = "pr_state_history"

    # Foreign key to pull request
    pr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pull_requests.id"), nullable=False
    )

    # State transition information
    old_state: Mapped[PRState | None] = mapped_column(nullable=True)
    new_state: Mapped[PRState] = mapped_column(nullable=False)
    trigger_event: Mapped[TriggerEvent] = mapped_column(nullable=False)

    # Context and metadata
    triggered_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    history_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # Relationships
    pull_request: Mapped["PullRequest"] = relationship(
        "PullRequest", back_populates="state_history"
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<PRStateHistory(id={self.id}, pr_id={self.pr_id}, "
            f"{self.old_state}->{self.new_state})>"
        )

    @property
    def is_initial_state(self) -> bool:
        """Check if this is the initial state (no old state)."""
        return self.old_state is None

    @property
    def is_reopening(self) -> bool:
        """Check if this represents a PR reopening."""
        return self.old_state == PRState.CLOSED and self.new_state == PRState.OPENED

    @property
    def is_closing(self) -> bool:
        """Check if this represents a PR closing."""
        return self.old_state == PRState.OPENED and self.new_state == PRState.CLOSED

    @property
    def is_merging(self) -> bool:
        """Check if this represents a PR merging."""
        return self.new_state == PRState.MERGED

    def get_transition_description(self) -> str:
        """Get human-readable description of the state transition."""
        if self.is_initial_state:
            return f"PR opened as {self.new_state.value}"

        if self.old_state is not None:
            if self.old_state == PRState.OPENED and self.new_state == PRState.CLOSED:
                return "PR was closed"
            elif self.old_state == PRState.OPENED and self.new_state == PRState.MERGED:
                return "PR was merged"
            elif self.old_state == PRState.CLOSED and self.new_state == PRState.OPENED:
                return "PR was reopened"
            else:
                return (
                    f"PR state changed from {self.old_state.value} "
                    f"to {self.new_state.value}"
                )
        else:
            return f"PR opened as {self.new_state.value}"

    def add_context(self, key: str, value: Any) -> None:
        """Add context information to metadata."""
        if self.history_metadata is None:
            self.history_metadata = {}
        self.history_metadata[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get context information from metadata."""
        if self.history_metadata is None:
            return default
        return self.history_metadata.get(key, default)

    @classmethod
    def create_transition(
        cls,
        pr_id: uuid.UUID,
        old_state: PRState | None,
        new_state: PRState,
        trigger_event: TriggerEvent,
        triggered_by: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "PRStateHistory":
        """Create a new state transition record."""
        return cls(
            pr_id=pr_id,
            old_state=old_state,
            new_state=new_state,
            trigger_event=trigger_event,
            triggered_by=triggered_by,
            history_metadata=metadata or {},
        )
