"""Abstract base classes and interfaces for PR Discovery and Processing.

This module defines the contracts that all discovery components must implement,
ensuring consistent behavior and enabling easy testing through dependency injection.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

# Enums for type safety


class ChangeType(Enum):
    """Types of changes that can be detected."""

    CREATED = "created"
    UPDATED = "updated"
    STATE_CHANGED = "state_changed"
    DELETED = "deleted"


class EntityType(Enum):
    """Types of entities in the discovery system."""

    PULL_REQUEST = "pull_request"
    CHECK_RUN = "check_run"
    REPOSITORY = "repository"


class DiscoveryPriority(Enum):
    """Priority levels for discovery operations."""

    CRITICAL = 1  # Recently active repositories
    HIGH = 2  # Repositories with recent failures
    NORMAL = 3  # Regular monitoring
    LOW = 4  # Inactive repositories


# Core Data Transfer Objects


@dataclass
class DiscoveredPR:
    """Discovered pull request with complete metadata."""

    pr_number: int
    title: str
    author: str
    state: str  # 'open', 'closed', 'merged'
    draft: bool
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str
    url: str
    body: str | None
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None
    metadata: dict[str, Any]  # Additional GitHub metadata
    check_runs: list["DiscoveredCheckRun"]

    @property
    def is_active(self) -> bool:
        """Check if PR is in an active state."""
        return self.state == "open" and not self.draft


@dataclass
class DiscoveredCheckRun:
    """Discovered check run with status and output."""

    external_id: str
    name: str
    status: str  # 'queued', 'in_progress', 'completed'
    conclusion: str | None  # 'success', 'failure', 'cancelled', etc.
    started_at: datetime | None
    completed_at: datetime | None
    details_url: str | None
    output: dict[str, Any] | None  # Check output including title, summary, text

    @property
    def is_failed(self) -> bool:
        """Check if the check run failed."""
        return self.status == "completed" and self.conclusion == "failure"


@dataclass
class PRDiscoveryResult:
    """Result of PR discovery for a single repository."""

    repository_id: uuid.UUID
    repository_url: str
    discovered_prs: list[DiscoveredPR]
    discovery_timestamp: datetime
    api_calls_used: int
    cache_hits: int
    cache_misses: int
    processing_time_ms: float
    errors: list["DiscoveryError"]

    @property
    def success_rate(self) -> float:
        """Calculate success rate of discovery."""
        total = len(self.discovered_prs) + len(self.errors)
        return len(self.discovered_prs) / total if total > 0 else 1.0


@dataclass
class DiscoveryError:
    """Error encountered during discovery."""

    error_type: str
    message: str
    context: dict[str, Any]
    timestamp: datetime
    recoverable: bool


@dataclass
class StateChange:
    """Detected state change in PR or check."""

    entity_type: EntityType
    entity_id: uuid.UUID
    external_id: str  # PR number or check run ID
    old_state: str | None
    new_state: str
    change_type: ChangeType
    metadata: dict[str, Any]
    detected_at: datetime

    @property
    def is_significant(self) -> bool:
        """Check if the state change requires immediate action."""
        return self.change_type == ChangeType.STATE_CHANGED or (
            self.entity_type == EntityType.CHECK_RUN and self.new_state == "failure"
        )


@dataclass
class RepositoryState:
    """Current state of a repository's PRs and checks."""

    repository_id: uuid.UUID
    pull_requests: dict[int, "StoredPRState"]  # Keyed by PR number
    last_updated: datetime

    def get_pr_state(self, pr_number: int) -> Optional["StoredPRState"]:
        """Get state of a specific PR."""
        return self.pull_requests.get(pr_number)


@dataclass
class StoredPRState:
    """Stored state of a PR for comparison."""

    pr_id: uuid.UUID
    pr_number: int
    state: str
    head_sha: str
    updated_at: datetime
    check_runs: dict[str, str]  # name -> conclusion


@dataclass
class SynchronizationResult:
    """Result of data synchronization operation."""

    total_prs_processed: int
    prs_created: int
    prs_updated: int
    total_checks_processed: int
    checks_created: int
    checks_updated: int
    state_changes_recorded: int
    errors: list[DiscoveryError]
    processing_time_ms: float

    @property
    def success(self) -> bool:
        """Check if synchronization was successful."""
        return len(self.errors) == 0


@dataclass
class DiscoveryConfig:
    """Configuration for discovery operations."""

    max_concurrent_repositories: int = 10
    max_prs_per_repository: int = 1000
    cache_ttl_seconds: int = 300
    use_etag_caching: bool = True
    batch_size: int = 100
    discovery_timeout_seconds: int = 300
    priority_scheduling: bool = True


# Abstract Base Classes


class PRDiscoveryStrategy(ABC):
    """Abstract base class for PR discovery strategies."""

    @abstractmethod
    async def discover_prs(
        self,
        repository_id: uuid.UUID,
        repository_url: str,
        since: datetime | None = None,
        max_prs: int | None = None,
    ) -> PRDiscoveryResult:
        """Discover PRs for a repository.

        Args:
            repository_id: Database ID of the repository
            repository_url: GitHub URL of the repository
            since: Only discover PRs updated after this time
            max_prs: Maximum number of PRs to discover

        Returns:
            Discovery result with PRs and metadata
        """
        pass

    @abstractmethod
    async def get_priority(self, repository_id: uuid.UUID) -> DiscoveryPriority:
        """Get discovery priority for a repository.

        Args:
            repository_id: Database ID of the repository

        Returns:
            Priority level for discovery scheduling
        """
        pass


class CheckDiscoveryStrategy(ABC):
    """Abstract base class for check run discovery."""

    @abstractmethod
    async def discover_checks(
        self, pr_data: DiscoveredPR, repository_url: str
    ) -> list[DiscoveredCheckRun]:
        """Discover check runs for a PR.

        Args:
            pr_data: Discovered PR data
            repository_url: GitHub URL of the repository

        Returns:
            List of discovered check runs
        """
        pass

    @abstractmethod
    async def batch_discover_checks(
        self, prs: list[DiscoveredPR], repository_url: str
    ) -> dict[int, list[DiscoveredCheckRun]]:
        """Discover check runs for multiple PRs efficiently.

        Args:
            prs: List of discovered PRs
            repository_url: GitHub URL of the repository

        Returns:
            Dictionary mapping PR numbers to their check runs
        """
        pass


class StateChangeDetector(ABC):
    """Abstract base class for state change detection."""

    @abstractmethod
    async def detect_changes(
        self, discovered_data: PRDiscoveryResult, current_state: RepositoryState
    ) -> list[StateChange]:
        """Detect state changes between discovered and current data.

        Args:
            discovered_data: Newly discovered PR data
            current_state: Current stored state

        Returns:
            List of detected state changes
        """
        pass

    @abstractmethod
    async def load_current_state(self, repository_id: uuid.UUID) -> RepositoryState:
        """Load current state for a repository.

        Args:
            repository_id: Database ID of the repository

        Returns:
            Current repository state
        """
        pass


class DataSynchronizationStrategy(ABC):
    """Abstract base class for data synchronization."""

    @abstractmethod
    async def synchronize(
        self,
        discovery_results: list[PRDiscoveryResult],
        state_changes: list[StateChange],
    ) -> SynchronizationResult:
        """Synchronize discovered data with database.

        Args:
            discovery_results: Results from PR discovery
            state_changes: Detected state changes

        Returns:
            Synchronization result with statistics
        """
        pass

    @abstractmethod
    async def begin_transaction(self) -> Any:
        """Begin a database transaction."""
        pass

    @abstractmethod
    async def commit_transaction(self) -> None:
        """Commit the current transaction."""
        pass

    @abstractmethod
    async def rollback_transaction(self) -> None:
        """Rollback the current transaction."""
        pass


class CacheStrategy(ABC):
    """Abstract base class for caching strategies."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get cached value.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set cached value with optional TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
        """
        pass

    @abstractmethod
    async def invalidate(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern.

        Args:
            pattern: Pattern to match cache keys

        Returns:
            Number of entries invalidated
        """
        pass

    @abstractmethod
    async def get_with_etag(self, key: str) -> tuple[Any | None, str | None]:
        """Get cached value with ETag.

        Args:
            key: Cache key

        Returns:
            Tuple of (cached value, etag)
        """
        pass

    @abstractmethod
    async def set_with_etag(
        self, key: str, value: Any, etag: str, ttl: int | None = None
    ) -> None:
        """Set cached value with ETag.

        Args:
            key: Cache key
            value: Value to cache
            etag: ETag for conditional requests
            ttl: Time-to-live in seconds
        """
        pass


class RateLimitStrategy(ABC):
    """Abstract base class for rate limit management."""

    @abstractmethod
    async def acquire_tokens(self, resource: str, count: int = 1) -> bool:
        """Acquire rate limit tokens.

        Args:
            resource: Resource identifier
            count: Number of tokens to acquire

        Returns:
            True if tokens acquired, False otherwise
        """
        pass

    @abstractmethod
    async def get_available_tokens(self, resource: str) -> int:
        """Get available rate limit tokens.

        Args:
            resource: Resource identifier

        Returns:
            Number of available tokens
        """
        pass

    @abstractmethod
    async def wait_for_tokens(
        self, resource: str, count: int = 1, timeout: float | None = None
    ) -> bool:
        """Wait until tokens are available.

        Args:
            resource: Resource identifier
            count: Number of tokens needed
            timeout: Maximum time to wait in seconds

        Returns:
            True if tokens acquired, False if timeout
        """
        pass

    @abstractmethod
    async def update_limit_info(
        self, resource: str, limit: int, remaining: int, reset_time: datetime
    ) -> None:
        """Update rate limit information from API response.

        Args:
            resource: Resource identifier
            limit: Total rate limit
            remaining: Remaining requests
            reset_time: When the limit resets
        """
        pass


class EventPublisher(ABC):
    """Abstract base class for publishing discovery events."""

    @abstractmethod
    async def publish_new_pr(
        self, repository_id: uuid.UUID, pr_data: DiscoveredPR
    ) -> None:
        """Publish event for newly discovered PR.

        Args:
            repository_id: Database ID of the repository
            pr_data: Discovered PR data
        """
        pass

    @abstractmethod
    async def publish_state_change(self, state_change: StateChange) -> None:
        """Publish state change event.

        Args:
            state_change: Detected state change
        """
        pass

    @abstractmethod
    async def publish_failed_check(
        self, repository_id: uuid.UUID, pr_number: int, check_run: DiscoveredCheckRun
    ) -> None:
        """Publish event for failed check run.

        Args:
            repository_id: Database ID of the repository
            pr_number: PR number
            check_run: Failed check run data
        """
        pass

    @abstractmethod
    async def publish_discovery_complete(
        self, results: list[PRDiscoveryResult]
    ) -> None:
        """Publish event when discovery cycle completes.

        Args:
            results: All discovery results from the cycle
        """
        pass


class DiscoveryOrchestrator(ABC):
    """Abstract base class for orchestrating the discovery process."""

    @abstractmethod
    async def run_discovery_cycle(
        self, repository_ids: list[uuid.UUID]
    ) -> list[PRDiscoveryResult]:
        """Run a complete discovery cycle for repositories.

        Args:
            repository_ids: List of repository IDs to process

        Returns:
            List of discovery results
        """
        pass

    @abstractmethod
    async def process_repository(self, repository_id: uuid.UUID) -> PRDiscoveryResult:
        """Process a single repository.

        Args:
            repository_id: Database ID of the repository

        Returns:
            Discovery result for the repository
        """
        pass

    @abstractmethod
    async def get_discovery_status(self) -> dict[str, Any]:
        """Get current discovery status.

        Returns:
            Status information including progress and metrics
        """
        pass
