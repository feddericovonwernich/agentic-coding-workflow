"""Integration Component Factory for creating real discovery components.

This module provides a factory for creating fully functional discovery components
for integration testing, with real implementations and controlled dependencies.
"""

import asyncio
import logging
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.github.client import GitHubClient
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.repositories.repository import RepositoryRepository
from src.repositories.state_history import PRStateHistoryRepository
from src.workers.discovery.api_resource_manager import GitHubAPIResourceManager
from src.workers.discovery.check_discoverer import GitHubCheckDiscoverer
from src.workers.discovery.data_synchronizer import DatabaseSynchronizer
from src.workers.discovery.discovery_cache import DiscoveryCache
from src.workers.discovery.interfaces import (
    CacheStrategy,
    CheckDiscoveryStrategy,
    DataSynchronizationStrategy,
    DiscoveredCheckRun,
    DiscoveredPR,
    DiscoveryConfig,
    EventPublisher,
    PRDiscoveryStrategy,
    RateLimitStrategy,
    StateChange,
    StateChangeDetector,
)
from src.workers.discovery.pr_discovery_engine import PRDiscoveryEngine
from src.workers.discovery.repository_scanner import GitHubRepositoryScanner
from src.workers.discovery.state_detector import DatabaseStateChangeDetector
from src.workers.discovery.state_manager import RepositoryStateManager

logger = logging.getLogger(__name__)


class TestEventPublisher(EventPublisher):
    """Test event publisher that logs events instead of publishing."""

    def __init__(self):
        """Initialize test event publisher."""
        self.published_events: list[dict[str, Any]] = []

    async def publish_new_pr(self, repository_id: uuid.UUID, pr_data: DiscoveredPR) -> None:
        """Log new PR event."""
        event = {
            "type": "new_pr",
            "repository_id": str(repository_id),
            "pr_number": pr_data.pr_number,
            "pr_title": pr_data.title,
        }
        self.published_events.append(event)
        logger.debug(f"Published new PR event: {event}")

    async def publish_state_change(self, state_change: StateChange) -> None:
        """Log state change event."""
        event = {
            "type": "state_change",
            "entity_type": state_change.entity_type.value,
            "entity_id": str(state_change.entity_id),
            "old_state": state_change.old_state,
            "new_state": state_change.new_state,
        }
        self.published_events.append(event)
        logger.debug(f"Published state change event: {event}")

    async def publish_failed_check(
        self, repository_id: uuid.UUID, pr_number: int, check_run: DiscoveredCheckRun
    ) -> None:
        """Log failed check event."""
        event = {
            "type": "failed_check",
            "repository_id": str(repository_id),
            "pr_number": pr_number,
            "check_name": check_run.name,
            "conclusion": check_run.conclusion,
        }
        self.published_events.append(event)
        logger.debug(f"Published failed check event: {event}")

    async def publish_discovery_complete(self, results: list) -> None:
        """Log discovery complete event."""
        event = {
            "type": "discovery_complete",
            "repositories_processed": len(results),
            "total_prs": sum(len(r.discovered_prs) for r in results),
            "total_errors": sum(len(r.errors) for r in results),
        }
        self.published_events.append(event)
        logger.debug(f"Published discovery complete event: {event}")

    def get_events_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Get all events of a specific type."""
        return [event for event in self.published_events if event["type"] == event_type]

    def clear_events(self) -> None:
        """Clear all recorded events."""
        self.published_events.clear()


class IntegrationComponentFactory:
    """Factory for creating real discovery components for integration testing.

    This factory creates fully functional discovery components with real implementations
    while providing controlled dependencies for testing scenarios.
    """

    def __init__(
        self,
        database_session: AsyncSession,
        github_client: GitHubClient,
        redis_url: Optional[str] = None,
    ):
        """Initialize component factory with core dependencies.

        Args:
            database_session: Real database session for operations
            github_client: Real GitHub client configured for mock server
            redis_url: Optional Redis URL for caching (uses memory cache if None)
        """
        self.database_session = database_session
        self.github_client = github_client
        self.redis_url = redis_url

        # Initialize repositories
        self.repository_repo = RepositoryRepository(database_session)
        self.pr_repository = PullRequestRepository(database_session)
        self.check_repository = CheckRunRepository(database_session)
        self.state_history_repository = PRStateHistoryRepository(database_session)

        # Initialize cache
        self.cache = self._create_cache()

        # Initialize event publisher
        self.event_publisher = TestEventPublisher()

    def _create_cache(self) -> CacheStrategy:
        """Create cache implementation based on configuration.

        Returns:
            Cache strategy instance (Redis or memory-based)
        """
        return DiscoveryCache(
            redis_url=self.redis_url,
            memory_cache_size=1000,
            default_ttl=300,
            compression_threshold=1024,
        )

    def create_discovery_engine(
        self,
        config: Optional[DiscoveryConfig] = None,
    ) -> PRDiscoveryEngine:
        """Create real PR Discovery Engine with all dependencies.

        Args:
            config: Discovery configuration (uses defaults if None)

        Returns:
            Fully configured PR Discovery Engine
        """
        if config is None:
            config = DiscoveryConfig(
                max_concurrent_repositories=5,
                max_prs_per_repository=100,
                cache_ttl_seconds=300,
                use_etag_caching=True,
                batch_size=10,
                discovery_timeout_seconds=30,
                priority_scheduling=True,
            )

        # Create strategies
        pr_discovery = self.create_pr_discovery_strategy()
        check_discovery = self.create_check_discovery_strategy()
        state_detector = self.create_state_detector()
        data_sync = self.create_data_synchronization_strategy()
        rate_limiter = self.create_rate_limiter()

        # Create state manager
        state_manager = RepositoryStateManager(
            pr_repository=self.pr_repository,
            check_repository=self.check_repository,
            cache=self.cache,
        )

        return PRDiscoveryEngine(
            config=config,
            pr_discovery=pr_discovery,
            check_discovery=check_discovery,
            state_detector=state_detector,
            data_sync=data_sync,
            rate_limiter=rate_limiter,
            cache=self.cache,
            event_publisher=self.event_publisher,
            repository_repo=self.repository_repo,
            pr_repository=self.pr_repository,
            check_repository=self.check_repository,
            state_manager=state_manager,
        )

    def create_repositories(self) -> tuple[
        RepositoryRepository,
        PullRequestRepository,
        CheckRunRepository,
    ]:
        """Create repository instances.

        Returns:
            Tuple of repository instances
        """
        return (
            self.repository_repo,
            self.pr_repository,
            self.check_repository,
        )

    def create_pr_discovery_strategy(self) -> PRDiscoveryStrategy:
        """Create real PR discovery strategy.

        Returns:
            GitHub repository scanner implementation
        """
        return GitHubRepositoryScanner(
            github_client=self.github_client,
            repository_repo=self.repository_repo,
            cache=self.cache,
            max_pages=10,
            items_per_page=100,
        )

    def create_check_discovery_strategy(self) -> CheckDiscoveryStrategy:
        """Create real check discovery strategy.

        Returns:
            GitHub check discoverer implementation
        """
        return GitHubCheckDiscoverer(
            github_client=self.github_client,
            cache=self.cache,
            batch_size=10,
            max_concurrent=5,
        )

    def create_state_detector(self) -> StateChangeDetector:
        """Create real state change detector.

        Returns:
            PR state change detector implementation
        """
        return DatabaseStateChangeDetector(
            pr_repository=self.pr_repository,
            check_repository=self.check_repository,
        )

    def create_data_synchronization_strategy(self) -> DataSynchronizationStrategy:
        """Create real data synchronization strategy.

        Returns:
            Database synchronizer implementation
        """
        return DatabaseSynchronizer(
            session=self.database_session,
            pr_repository=self.pr_repository,
            check_repository=self.check_repository,
            state_history_repository=self.state_history_repository,
        )

    def create_rate_limiter(self) -> RateLimitStrategy:
        """Create real rate limiter.

        Returns:
            API resource manager implementation
        """
        return GitHubAPIResourceManager(
            core_limit=5000,
            search_limit=30,
            graphql_limit=5000,
        )

    def create_cache_strategy(
        self,
        memory_cache_size: int = 1000,
        default_ttl: int = 300,
    ) -> CacheStrategy:
        """Create cache strategy with custom settings.

        Args:
            memory_cache_size: Size of memory cache
            default_ttl: Default TTL in seconds

        Returns:
            Cache strategy instance
        """
        return DiscoveryCache(
            redis_url=self.redis_url,
            memory_cache_size=memory_cache_size,
            default_ttl=default_ttl,
            compression_threshold=1024,
        )

    async def cleanup(self) -> None:
        """Clean up resources."""
        try:
            if hasattr(self.cache, "close"):
                await self.cache.close()
        except Exception as e:
            logger.warning(f"Error during cache cleanup: {e}")

        try:
            await self.database_session.close()
        except Exception as e:
            logger.warning(f"Error during database session cleanup: {e}")


class ComponentFactoryBuilder:
    """Builder for creating component factory with different configurations."""

    def __init__(self):
        """Initialize builder."""
        self._database_session: Optional[AsyncSession] = None
        self._github_client: Optional[GitHubClient] = None
        self._redis_url: Optional[str] = None

    def with_database_session(self, session: AsyncSession) -> "ComponentFactoryBuilder":
        """Set database session.

        Args:
            session: Database session

        Returns:
            Builder instance for chaining
        """
        self._database_session = session
        return self

    def with_github_client(self, client: GitHubClient) -> "ComponentFactoryBuilder":
        """Set GitHub client.

        Args:
            client: GitHub client

        Returns:
            Builder instance for chaining
        """
        self._github_client = client
        return self

    def with_redis_url(self, redis_url: str) -> "ComponentFactoryBuilder":
        """Set Redis URL for caching.

        Args:
            redis_url: Redis connection URL

        Returns:
            Builder instance for chaining
        """
        self._redis_url = redis_url
        return self

    def build(self) -> IntegrationComponentFactory:
        """Build component factory.

        Returns:
            Configured component factory

        Raises:
            ValueError: If required dependencies are missing
        """
        if not self._database_session:
            raise ValueError("Database session is required")

        if not self._github_client:
            raise ValueError("GitHub client is required")

        return IntegrationComponentFactory(
            database_session=self._database_session,
            github_client=self._github_client,
            redis_url=self._redis_url,
        )


# Configuration presets for different testing scenarios

def create_performance_testing_config() -> DiscoveryConfig:
    """Create configuration optimized for performance testing.

    Returns:
        Discovery configuration for performance testing
    """
    return DiscoveryConfig(
        max_concurrent_repositories=20,
        max_prs_per_repository=500,
        cache_ttl_seconds=600,
        use_etag_caching=True,
        batch_size=50,
        discovery_timeout_seconds=120,
        priority_scheduling=True,
    )


def create_error_testing_config() -> DiscoveryConfig:
    """Create configuration with failure injection points.

    Returns:
        Discovery configuration for error testing
    """
    return DiscoveryConfig(
        max_concurrent_repositories=3,
        max_prs_per_repository=50,
        cache_ttl_seconds=60,
        use_etag_caching=False,  # Disable caching for error testing
        batch_size=5,
        discovery_timeout_seconds=10,  # Short timeout to trigger timeouts
        priority_scheduling=False,
    )


def create_minimal_testing_config() -> DiscoveryConfig:
    """Create minimal configuration for fast testing.

    Returns:
        Minimal discovery configuration
    """
    return DiscoveryConfig(
        max_concurrent_repositories=2,
        max_prs_per_repository=10,
        cache_ttl_seconds=30,
        use_etag_caching=True,
        batch_size=2,
        discovery_timeout_seconds=15,
        priority_scheduling=False,
    )


class IntegrationTestContext:
    """Context manager for integration test setup and cleanup."""

    def __init__(
        self,
        database_session: AsyncSession,
        github_client: GitHubClient,
        redis_url: Optional[str] = None,
    ):
        """Initialize integration test context.

        Args:
            database_session: Database session
            github_client: GitHub client
            redis_url: Optional Redis URL
        """
        self.database_session = database_session
        self.github_client = github_client
        self.redis_url = redis_url
        self.component_factory: Optional[IntegrationComponentFactory] = None

    async def __aenter__(self) -> IntegrationComponentFactory:
        """Enter context and create component factory."""
        self.component_factory = IntegrationComponentFactory(
            database_session=self.database_session,
            github_client=self.github_client,
            redis_url=self.redis_url,
        )
        return self.component_factory

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and cleanup resources."""
        if self.component_factory:
            await self.component_factory.cleanup()