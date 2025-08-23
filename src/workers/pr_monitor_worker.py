"""PR Monitor Worker for scheduled discovery execution.

This module implements the main worker that runs the PR discovery process
on a schedule, managing configuration, health checks, and error handling.
"""

import asyncio
import contextlib
import logging
import signal
import sys
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.loader import ConfigurationLoader
from src.database.config import get_database_config
from src.github.auth import TokenAuth
from src.github.client import GitHubClient
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.repositories.repository import RepositoryRepository
from src.repositories.state_history import PRStateHistoryRepository

from .discovery.api_resource_manager import GitHubAPIResourceManager
from .discovery.check_discoverer import GitHubCheckDiscoverer
from .discovery.data_synchronizer import DatabaseSynchronizer
from .discovery.discovery_cache import DiscoveryCache
from .discovery.interfaces import (
    DiscoveredCheckRun,
    DiscoveredPR,
    DiscoveryConfig,
    EventPublisher,
    PRDiscoveryResult,
    StateChange,
)
from .discovery.pr_discovery_engine import PRDiscoveryEngine
from .discovery.repository_scanner import GitHubRepositoryScanner
from .discovery.state_detector import DatabaseStateChangeDetector
from .discovery.state_manager import RepositoryStateManager

logger = logging.getLogger(__name__)


class NoOpEventPublisher(EventPublisher):
    """No-op event publisher for when event system is not configured."""

    async def publish_new_pr(
        self, repository_id: uuid.UUID, pr_data: DiscoveredPR
    ) -> None:
        """Publish new PR event (no-op)."""
        logger.debug(f"Would publish new PR event for repo {repository_id}")

    async def publish_state_change(self, state_change: StateChange) -> None:
        """Publish state change event (no-op)."""
        logger.debug(f"Would publish state change: {state_change.change_type.value}")

    async def publish_failed_check(
        self, repository_id: uuid.UUID, pr_number: int, check_run: DiscoveredCheckRun
    ) -> None:
        """Publish failed check event (no-op)."""
        logger.debug(f"Would publish failed check for PR #{pr_number}")

    async def publish_discovery_complete(
        self, results: list[PRDiscoveryResult]
    ) -> None:
        """Publish discovery complete event (no-op)."""
        logger.info(f"Discovery completed for {len(results)} repositories")


class PRMonitorWorker:
    """Main PR monitoring worker that orchestrates discovery process.

    Manages the complete lifecycle of PR discovery including:
    - Configuration loading and validation
    - Database and external service connections
    - Scheduled discovery execution
    - Error handling and recovery
    - Health monitoring and status reporting
    """

    def __init__(self, config_path: str | None = None):
        """Initialize PR monitor worker.

        Args:
            config_path: Optional path to configuration file
        """
        self.config_path = config_path
        self.config: dict[str, Any] | None = None
        self.discovery_config: DiscoveryConfig | None = None

        # Database components
        self.engine: AsyncEngine | None = None
        self.session_maker: async_sessionmaker[AsyncSession] | None = None
        self.session: AsyncSession | None = None

        # Repositories
        self.repository_repo: RepositoryRepository | None = None
        self.pr_repo: PullRequestRepository | None = None
        self.check_repo: CheckRunRepository | None = None
        self.state_history_repo: PRStateHistoryRepository | None = None

        # Discovery components
        self.github_client: GitHubClient | None = None
        self.discovery_engine: PRDiscoveryEngine | None = None

        # Worker state
        self.running = False
        self.shutdown_event = asyncio.Event()
        self.discovery_task: asyncio.Task | None = None

        # Statistics
        self.stats: dict[str, Any] = {
            "worker_started_at": None,
            "total_discovery_cycles": 0,
            "successful_cycles": 0,
            "failed_cycles": 0,
            "last_cycle_at": None,
            "last_error": None,
        }

    async def initialize(self) -> None:
        """Initialize worker components and connections."""
        logger.info("Initializing PR Monitor Worker...")

        try:
            # Load configuration
            await self._load_configuration()

            # Initialize database
            await self._initialize_database()

            # Initialize repositories
            await self._initialize_repositories()

            # Initialize GitHub client
            await self._initialize_github_client()

            # Initialize discovery components
            await self._initialize_discovery_components()

            # Create discovery engine
            await self._create_discovery_engine()

            self.stats["worker_started_at"] = datetime.now(UTC)
            logger.info("PR Monitor Worker initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize PR Monitor Worker: {e}")
            await self.cleanup()
            raise

    async def _load_configuration(self) -> None:
        """Load and validate configuration."""
        config_loader = ConfigurationLoader()

        if self.config_path:
            loaded_config = config_loader.load_from_file(self.config_path)
        else:
            loaded_config = config_loader.load_default()

        # Convert Config model to dict for compatibility
        self.config = loaded_config.model_dump()

        # Create discovery-specific configuration
        discovery_settings = self.config.get("discovery", {})
        self.discovery_config = DiscoveryConfig(
            max_concurrent_repositories=discovery_settings.get(
                "max_concurrent_repositories", 10
            ),
            max_prs_per_repository=discovery_settings.get(
                "max_prs_per_repository", 1000
            ),
            cache_ttl_seconds=discovery_settings.get("cache_ttl_seconds", 300),
            use_etag_caching=discovery_settings.get("use_etag_caching", True),
            batch_size=discovery_settings.get("batch_size", 100),
            discovery_timeout_seconds=discovery_settings.get(
                "discovery_timeout_seconds", 300
            ),
            priority_scheduling=discovery_settings.get("priority_scheduling", True),
        )

        logger.info(
            f"Configuration loaded: {len(self.config.get('repositories', []))} "
            f"repositories configured"
        )

    async def _initialize_database(self) -> None:
        """Initialize database connections."""
        if not self.config:
            raise RuntimeError("Configuration not loaded")

        db_config = get_database_config()
        database_url = db_config.get_sqlalchemy_url()

        self.engine = create_async_engine(
            database_url,
            pool_size=20,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=self.config.get("database", {}).get("debug", False),
        )

        self.session_maker = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )

        self.session = self.session_maker()

        logger.info("Database connections initialized")

    async def _initialize_repositories(self) -> None:
        """Initialize repository classes."""
        if not self.session:
            raise RuntimeError("Database session not initialized")

        self.repository_repo = RepositoryRepository(self.session)
        self.pr_repo = PullRequestRepository(self.session)
        self.check_repo = CheckRunRepository(self.session)
        self.state_history_repo = PRStateHistoryRepository(self.session)

        logger.info("Repository classes initialized")

    async def _initialize_github_client(self) -> None:
        """Initialize GitHub API client."""
        if not self.config:
            raise RuntimeError("Configuration not loaded")

        github_config = self.config.get("github", {})

        # Create auth provider
        auth_token = github_config.get("token") or github_config.get("auth_token")
        if not auth_token:
            raise ValueError("GitHub authentication token not configured")

        auth_provider = TokenAuth(auth_token)

        # Create GitHub client
        self.github_client = GitHubClient(
            auth=auth_provider,
            config=None,  # Will use defaults
        )

        # Test connection
        try:
            user_info = await self.github_client.get_user()
            logger.info(
                f"GitHub client initialized for user: "
                f"{user_info.get('login', 'unknown')}"
            )
        except Exception as e:
            logger.error(f"GitHub client test failed: {e}")
            raise

    async def _initialize_discovery_components(self) -> None:
        """Initialize discovery system components."""
        if (
            not self.config
            or not self.discovery_config
            or not self.github_client
            or not self.repository_repo
            or not self.session
            or not self.pr_repo
            or not self.check_repo
            or not self.state_history_repo
        ):
            raise RuntimeError("Required components not initialized")

        # Initialize cache
        redis_url = self.config.get("redis", {}).get("url")
        cache = DiscoveryCache(
            redis_url=redis_url,
            memory_cache_size=1000,
            default_ttl=self.discovery_config.cache_ttl_seconds,
        )

        # Initialize API resource manager
        rate_limiter = GitHubAPIResourceManager(
            core_limit=5000,  # GitHub default
            search_limit=30,
            graphql_limit=5000,
            buffer_percentage=0.1,
        )
        await rate_limiter.start()

        # Initialize repository scanner
        repository_scanner = GitHubRepositoryScanner(
            github_client=self.github_client,
            repository_repo=self.repository_repo,
            cache=cache,
        )

        # Initialize check discoverer
        check_discoverer = GitHubCheckDiscoverer(
            github_client=self.github_client, cache=cache, batch_size=10
        )

        # Initialize state change detector
        state_detector = DatabaseStateChangeDetector(
            pr_repository=self.pr_repo, check_repository=self.check_repo
        )

        # Initialize data synchronizer
        data_synchronizer = DatabaseSynchronizer(
            session=self.session,
            pr_repository=self.pr_repo,
            check_repository=self.check_repo,
            state_history_repository=self.state_history_repo,
        )

        # Initialize state manager
        if not self.pr_repo or not self.check_repo:
            raise RuntimeError("PR and Check repositories must be initialized")

        state_manager = RepositoryStateManager(
            pr_repository=self.pr_repo, check_repository=self.check_repo, cache=cache
        )

        # Store components for discovery engine
        self._cache = cache
        self._rate_limiter = rate_limiter
        self._repository_scanner = repository_scanner
        self._check_discoverer = check_discoverer
        self._state_detector = state_detector
        self._data_synchronizer = data_synchronizer
        self._state_manager = state_manager

        logger.info("Discovery components initialized")

    async def _create_discovery_engine(self) -> None:
        """Create the main discovery engine."""
        if not all(
            [
                self.discovery_config,
                hasattr(self, "_repository_scanner"),
                hasattr(self, "_check_discoverer"),
                hasattr(self, "_state_detector"),
                hasattr(self, "_data_synchronizer"),
                hasattr(self, "_rate_limiter"),
                hasattr(self, "_cache"),
                self.repository_repo,
                hasattr(self, "_state_manager"),
            ]
        ):
            raise RuntimeError("Discovery components not initialized")

        # Create no-op event publisher (can be replaced with real implementation)
        event_publisher = NoOpEventPublisher()

        # Ensure all required components are available
        if not all(
            [self.discovery_config, self.repository_repo, self.pr_repo, self.check_repo]
        ):
            raise RuntimeError("Required repositories not initialized")

        self.discovery_engine = PRDiscoveryEngine(
            config=cast(DiscoveryConfig, self.discovery_config),
            pr_discovery=self._repository_scanner,
            check_discovery=self._check_discoverer,
            state_detector=self._state_detector,
            data_sync=self._data_synchronizer,
            rate_limiter=self._rate_limiter,
            cache=self._cache,
            event_publisher=event_publisher,
            repository_repo=cast(RepositoryRepository, self.repository_repo),
            pr_repository=cast(PullRequestRepository, self.pr_repo),
            check_repository=cast(CheckRunRepository, self.check_repo),
            state_manager=self._state_manager,
        )

        logger.info("Discovery engine created")

    async def run(self) -> None:
        """Run the worker main loop."""
        if not self.discovery_engine:
            raise RuntimeError("Worker not initialized. Call initialize() first.")

        self.running = True
        logger.info("Starting PR Monitor Worker...")

        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()

        try:
            # Start discovery loop
            self.discovery_task = asyncio.create_task(self._discovery_loop())

            # Wait for shutdown
            await self.shutdown_event.wait()

        except asyncio.CancelledError:
            logger.info("Worker cancelled")
        except Exception as e:
            logger.error(f"Worker error: {e}")
            self.stats["last_error"] = str(e)
        finally:
            self.running = False

            # Cancel discovery task
            if self.discovery_task and not self.discovery_task.done():
                self.discovery_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.discovery_task

            logger.info("PR Monitor Worker stopped")

    async def _discovery_loop(self) -> None:
        """Main discovery loop."""
        if not self.config:
            raise RuntimeError("Configuration not loaded")

        discovery_interval = self.config.get("discovery", {}).get(
            "interval_seconds", 300
        )  # 5 minutes

        logger.info(f"Starting discovery loop (interval: {discovery_interval}s)")

        while self.running and not self.shutdown_event.is_set():
            try:
                cycle_start = datetime.now(UTC)
                logger.info("Starting discovery cycle...")

                # Get active repositories
                if not self.repository_repo:
                    raise RuntimeError("Repository repository not initialized")

                active_repositories = (
                    await self.repository_repo.get_repositories_needing_poll()
                )
                repository_ids = [repo.id for repo in active_repositories]

                if not repository_ids:
                    logger.info("No repositories need polling")
                else:
                    # Run discovery
                    if not self.discovery_engine:
                        raise RuntimeError("Discovery engine not initialized")

                    results = await self.discovery_engine.run_discovery_cycle(
                        repository_ids
                    )

                    # Update statistics
                    self.stats["total_discovery_cycles"] += 1
                    self.stats["successful_cycles"] += 1
                    self.stats["last_cycle_at"] = cycle_start

                    logger.info(
                        f"Discovery cycle completed: {len(results)} "
                        f"repositories processed"
                    )

            except Exception as e:
                logger.error(f"Discovery cycle failed: {e}")
                self.stats["total_discovery_cycles"] += 1
                self.stats["failed_cycles"] += 1
                self.stats["last_error"] = {
                    "message": str(e),
                    "timestamp": datetime.now(UTC),
                }

                # Continue running despite errors

            # Wait for next cycle
            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(), timeout=discovery_interval
                )
                # Shutdown event was set
                break
            except TimeoutError:
                # Normal timeout, continue to next cycle
                continue

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(sig: int, frame: Any) -> None:
            logger.info(f"Received signal {sig}, initiating shutdown...")
            self.shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def shutdown(self) -> None:
        """Initiate graceful shutdown."""
        logger.info("Shutting down PR Monitor Worker...")
        self.shutdown_event.set()

    async def cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Close GitHub client
            if self.github_client:
                await self.github_client.close()

            # Stop rate limiter
            if hasattr(self, "_rate_limiter"):
                await self._rate_limiter.stop()

            # Close cache
            if hasattr(self, "_cache"):
                await self._cache.close()

            # Close database session
            if self.session:
                await self.session.close()

            # Close database engine
            if self.engine:
                await self.engine.dispose()

            logger.info("Cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    async def get_health_status(self) -> dict[str, Any]:
        """Get worker health status."""
        health = {
            "healthy": True,
            "worker": {"running": self.running, "stats": self.stats},
            "components": {},
            "errors": [],
        }

        try:
            # Check discovery engine health
            if self.discovery_engine:
                discovery_status = await self.discovery_engine.get_discovery_status()
                cast(dict[str, Any], health["components"])["discovery_engine"] = (
                    discovery_status
                )

            # Check database health
            if self.session:
                try:
                    from sqlalchemy import text

                    await self.session.execute(text("SELECT 1"))
                    cast(dict[str, Any], health["components"])["database"] = {
                        "healthy": True
                    }
                except Exception as e:
                    cast(dict[str, Any], health["components"])["database"] = {
                        "healthy": False,
                        "error": str(e),
                    }
                    health["healthy"] = False

            # Check GitHub client health
            if self.github_client:
                try:
                    rate_limit_info = await self.github_client.get_rate_limit()
                    cast(dict[str, Any], health["components"])["github"] = {
                        "healthy": True,
                        "rate_limit": rate_limit_info,
                    }
                except Exception as e:
                    cast(dict[str, Any], health["components"])["github"] = {
                        "healthy": False,
                        "error": str(e),
                    }
                    health["healthy"] = False

            # Check cache health
            if hasattr(self, "_cache"):
                try:
                    cache_health = await self._cache.health_check()
                    cast(dict[str, Any], health["components"])["cache"] = cache_health
                    if not cache_health["healthy"]:
                        health["healthy"] = False
                except Exception as e:
                    cast(dict[str, Any], health["components"])["cache"] = {
                        "healthy": False,
                        "error": str(e),
                    }
                    health["healthy"] = False

        except Exception as e:
            health["healthy"] = False
            cast(list[str], health["errors"]).append(f"Health check error: {e!s}")

        return health


async def main() -> None:
    """Main entry point for PR monitor worker."""
    import argparse

    parser = argparse.ArgumentParser(description="PR Monitor Worker")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--log-level", default="INFO", help="Log level")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    worker = PRMonitorWorker(config_path=args.config)

    try:
        await worker.initialize()
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        sys.exit(1)
    finally:
        await worker.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
