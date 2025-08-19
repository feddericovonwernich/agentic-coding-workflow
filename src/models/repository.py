"""Repository SQLAlchemy model."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import PullRequest

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel
from .enums import RepositoryStatus


class Repository(BaseModel):
    """Model for repository configuration and tracking."""

    __tablename__ = "repositories"

    # Repository identification
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    full_name: Mapped[str | None] = mapped_column(
        String(300), nullable=True
    )  # owner/repo

    # Repository status and health
    status: Mapped[RepositoryStatus] = mapped_column(
        default=RepositoryStatus.ACTIVE, nullable=False
    )

    # Polling and failure tracking
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    polling_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=15, nullable=False
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Configuration overrides
    config_override: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # GitHub API configuration
    github_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    github_app_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_installation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Additional metadata
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    default_branch: Mapped[str] = mapped_column(
        String(200), default="main", nullable=False
    )
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    repo_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # Relationships
    pull_requests: Mapped[list["PullRequest"]] = relationship(
        "PullRequest", back_populates="repository", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (UniqueConstraint("url", name="uq_repository_url"),)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Repository(id={self.id}, name={self.name}, status={self.status})>"

    @property
    def is_active(self) -> bool:
        """Check if repository is active."""
        return self.status == RepositoryStatus.ACTIVE

    @property
    def is_healthy(self) -> bool:
        """Check if repository is healthy (active with low failure count)."""
        return self.is_active and self.failure_count < 5

    @property
    def needs_polling(self) -> bool:
        """Check if repository needs to be polled."""
        if not self.is_active:
            return False

        if self.last_polled_at is None:
            return True

        now = datetime.now(UTC)
        time_since_poll = now - self.last_polled_at
        return time_since_poll.total_seconds() > (self.polling_interval_minutes * 60)

    @property
    def owner(self) -> str | None:
        """Extract owner from full_name or URL."""
        if self.full_name and "/" in self.full_name:
            return self.full_name.split("/")[0]

        # Extract from URL as fallback
        if "github.com/" in self.url:
            parts = self.url.rstrip("/").split("/")
            if len(parts) >= 2:
                return parts[-2]

        return None

    @property
    def repo_name(self) -> str:
        """Extract repository name from full_name or URL."""
        if self.full_name and "/" in self.full_name:
            return self.full_name.split("/")[1]

        # Extract from URL as fallback
        if "github.com/" in self.url:
            return self.url.rstrip("/").split("/")[-1]

        return self.name

    def update_last_polled(self) -> None:
        """Update the last polled timestamp to now."""
        self.last_polled_at = datetime.now(UTC)

    def increment_failure_count(self, reason: str | None = None) -> None:
        """Increment failure count and update failure details."""
        self.failure_count += 1
        self.last_failure_at = datetime.now(UTC)
        if reason:
            self.last_failure_reason = reason[:500]  # Truncate if too long

        # Suspend repository if too many failures
        if self.failure_count >= 10:
            self.status = RepositoryStatus.ERROR

    def reset_failure_count(self) -> None:
        """Reset failure count after successful operation."""
        self.failure_count = 0
        self.last_failure_at = None
        self.last_failure_reason = None

        # Reactivate if it was in error state
        if self.status == RepositoryStatus.ERROR:
            self.status = RepositoryStatus.ACTIVE

    def suspend(self, reason: str | None = None) -> None:
        """Suspend repository monitoring."""
        self.status = RepositoryStatus.SUSPENDED
        if reason:
            self.last_failure_reason = reason[:500]
            self.last_failure_at = datetime.now(UTC)

    def activate(self) -> None:
        """Activate repository monitoring."""
        self.status = RepositoryStatus.ACTIVE
        self.reset_failure_count()

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get configuration value with override support."""
        if self.config_override and key in self.config_override:
            return self.config_override[key]
        return default

    def set_config_override(self, key: str, value: Any) -> None:
        """Set configuration override value."""
        if self.config_override is None:
            self.config_override = {}
        self.config_override[key] = value

    def remove_config_override(self, key: str) -> None:
        """Remove configuration override value."""
        if self.config_override and key in self.config_override:
            del self.config_override[key]
            if not self.config_override:
                self.config_override = None

    def get_auth_config(self) -> dict[str, Any]:
        """Get authentication configuration for GitHub API."""
        config = {}

        if self.github_token:
            config["token"] = self.github_token

        if self.github_app_id and self.github_installation_id:
            config["app_id"] = str(self.github_app_id)
            config["installation_id"] = str(self.github_installation_id)

        return config

    def update_from_github_repo(self, repo_data: dict[str, Any]) -> None:
        """Update repository information from GitHub API response."""
        if "full_name" in repo_data:
            self.full_name = repo_data["full_name"]

        if "description" in repo_data:
            self.description = repo_data["description"]

        if "default_branch" in repo_data:
            self.default_branch = repo_data["default_branch"]

        if "private" in repo_data:
            self.is_private = repo_data["private"]

        # Store additional metadata
        if self.repo_metadata is None:
            self.repo_metadata = {}

        github_metadata = {
            "github_id": repo_data.get("id"),
            "clone_url": repo_data.get("clone_url"),
            "ssh_url": repo_data.get("ssh_url"),
            "language": repo_data.get("language"),
            "size": repo_data.get("size"),
            "stargazers_count": repo_data.get("stargazers_count"),
            "forks_count": repo_data.get("forks_count"),
        }

        self.repo_metadata.update(
            {k: v for k, v in github_metadata.items() if v is not None}
        )
