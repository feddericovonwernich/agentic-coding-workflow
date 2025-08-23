"""Repository state manager for loading and caching repository states.

This module provides efficient loading and caching of repository states
to support state change detection and minimize database queries.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository

from .interfaces import CacheStrategy, RepositoryState, StoredPRState

logger = logging.getLogger(__name__)


class RepositoryStateManager:
    """Manages loading and caching of repository states.

    Provides efficient access to current repository states with
    intelligent caching and batch loading capabilities.
    """

    def __init__(
        self,
        pr_repository: PullRequestRepository,
        check_repository: CheckRunRepository,
        cache: CacheStrategy | None = None,
        cache_ttl: int = 300,
        max_concurrent_loads: int = 10,
    ):
        """Initialize state manager.

        Args:
            pr_repository: Pull request repository
            check_repository: Check run repository
            cache: Optional cache strategy for state caching
            cache_ttl: Cache TTL in seconds
            max_concurrent_loads: Maximum concurrent state loads
        """
        self.pr_repository = pr_repository
        self.check_repository = check_repository
        self.cache = cache
        self.cache_ttl = cache_ttl

        # Concurrency control
        self.load_semaphore = asyncio.Semaphore(max_concurrent_loads)

        # In-memory state cache for short-term caching
        self.memory_cache: dict[uuid.UUID, tuple[RepositoryState, float]] = {}
        self.memory_cache_ttl = 60  # 1 minute memory cache

        # Metrics tracking
        self.stats = {
            "loads": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "batch_loads": 0,
        }

    def _generate_cache_key(self, repository_id: uuid.UUID) -> str:
        """Generate cache key for repository state.

        Args:
            repository_id: Repository ID

        Returns:
            Cache key string
        """
        return f"repo_state:{repository_id}"

    async def _load_repository_state_from_db(
        self, repository_id: uuid.UUID
    ) -> RepositoryState:
        """Load repository state from database.

        Args:
            repository_id: Repository ID

        Returns:
            Repository state loaded from database
        """
        try:
            async with self.load_semaphore:
                logger.debug(
                    f"Loading state from database for repository {repository_id}"
                )

                # Load all active PRs for the repository
                prs = await self.pr_repository.get_active_prs_for_repo(
                    repository_id, include_drafts=True
                )

                # Build state map
                pull_requests = {}
                for pr in prs:
                    # Get latest check runs
                    latest_checks = pr.get_latest_check_runs()

                    # Build check run state map
                    check_runs: dict[str, str] = {}
                    for check in latest_checks:
                        conclusion = None
                        if check.conclusion:
                            conclusion = (
                                check.conclusion.value
                                if hasattr(check.conclusion, "value")
                                else str(check.conclusion)
                            )
                        # StoredPRState expects dict[str, str], convert None
                        check_runs[check.check_name] = conclusion or ""

                    pr_state = StoredPRState(
                        pr_id=pr.id,
                        pr_number=pr.pr_number,
                        state=pr.state.value
                        if hasattr(pr.state, "value")
                        else str(pr.state),
                        head_sha=pr.head_sha,
                        updated_at=pr.updated_at,
                        check_runs=check_runs,
                    )

                    pull_requests[pr.pr_number] = pr_state

                state = RepositoryState(
                    repository_id=repository_id,
                    pull_requests=pull_requests,
                    last_updated=datetime.utcnow(),
                )

                logger.debug(
                    f"Loaded state for repository {repository_id}: "
                    f"{len(pull_requests)} PRs"
                )

                return state

        except Exception as e:
            logger.error(f"Error loading repository state from database: {e}")
            # Return empty state on error
            return RepositoryState(
                repository_id=repository_id,
                pull_requests={},
                last_updated=datetime.utcnow(),
            )

    async def get_repository_state(
        self, repository_id: uuid.UUID, force_refresh: bool = False
    ) -> RepositoryState:
        """Get repository state with caching.

        Args:
            repository_id: Repository ID
            force_refresh: Force refresh from database

        Returns:
            Repository state
        """
        self.stats["loads"] += 1

        # Check memory cache first (if not forcing refresh)
        if not force_refresh:
            cached_entry = self.memory_cache.get(repository_id)
            if cached_entry:
                state, cached_at = cached_entry
                if time.time() - cached_at < self.memory_cache_ttl:
                    self.stats["cache_hits"] += 1
                    logger.debug(f"Memory cache hit for repository {repository_id}")
                    return state

        # Check distributed cache
        if self.cache and not force_refresh:
            try:
                cache_key = self._generate_cache_key(repository_id)
                cached_data = await self.cache.get(cache_key)

                if cached_data:
                    # Reconstruct state from cached data
                    deserialized_state = self._deserialize_state(
                        cached_data, repository_id
                    )
                    if deserialized_state is not None:
                        # Update memory cache
                        self.memory_cache[repository_id] = (
                            deserialized_state,
                            time.time(),
                        )
                        self.stats["cache_hits"] += 1
                        logger.debug(
                            f"Distributed cache hit for repository {repository_id}"
                        )
                        return deserialized_state

            except Exception as e:
                logger.warning(f"Error reading from cache: {e}")

        # Load from database
        self.stats["cache_misses"] += 1
        state = await self._load_repository_state_from_db(repository_id)

        # Update caches
        self.memory_cache[repository_id] = (state, time.time())

        if self.cache:
            try:
                cache_key = self._generate_cache_key(repository_id)
                serialized = self._serialize_state(state)
                await self.cache.set(cache_key, serialized, ttl=self.cache_ttl)
            except Exception as e:
                logger.warning(f"Error writing to cache: {e}")

        return state

    async def batch_get_repository_states(
        self, repository_ids: list[uuid.UUID], force_refresh: bool = False
    ) -> dict[uuid.UUID, RepositoryState]:
        """Get multiple repository states efficiently.

        Args:
            repository_ids: List of repository IDs
            force_refresh: Force refresh from database

        Returns:
            Dictionary mapping repository IDs to their states
        """
        if not repository_ids:
            return {}

        self.stats["batch_loads"] += 1
        logger.info(f"Batch loading states for {len(repository_ids)} repositories")

        # Create tasks for concurrent loading
        tasks = [
            self.get_repository_state(repo_id, force_refresh)
            for repo_id in repository_ids
        ]

        # Execute tasks with error handling
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dictionary
        states: dict[uuid.UUID, RepositoryState] = {}
        for repo_id, result in zip(repository_ids, results, strict=False):
            if isinstance(result, Exception):
                logger.error(f"Error loading state for repository {repo_id}: {result}")
                self.stats["errors"] += 1
                # Provide empty state for failed loads
                states[repo_id] = RepositoryState(
                    repository_id=repo_id,
                    pull_requests={},
                    last_updated=datetime.utcnow(),
                )
            else:
                # result is RepositoryState in success case - validate for type checker
                if not isinstance(result, RepositoryState):
                    raise TypeError(
                        f"Expected RepositoryState, got {type(result)} "
                        f"for repository {repo_id}"
                    )
                states[repo_id] = result

        logger.info(f"Batch load completed: {len(states)} states loaded")
        return states

    def _serialize_state(self, state: RepositoryState) -> dict:
        """Serialize repository state for caching.

        Args:
            state: Repository state to serialize

        Returns:
            Serializable dictionary
        """
        prs_data = {}
        for pr_number, pr_state in state.pull_requests.items():
            prs_data[str(pr_number)] = {
                "pr_id": str(pr_state.pr_id),
                "pr_number": pr_state.pr_number,
                "state": pr_state.state,
                "head_sha": pr_state.head_sha,
                "updated_at": pr_state.updated_at.isoformat(),
                "check_runs": pr_state.check_runs,
            }

        return {
            "repository_id": str(state.repository_id),
            "pull_requests": prs_data,
            "last_updated": state.last_updated.isoformat(),
        }

    def _deserialize_state(
        self, data: dict, repository_id: uuid.UUID
    ) -> RepositoryState | None:
        """Deserialize repository state from cache data.

        Args:
            data: Serialized state data
            repository_id: Repository ID

        Returns:
            Deserialized repository state or None on error
        """
        try:
            pull_requests = {}

            for pr_number_str, pr_data in data.get("pull_requests", {}).items():
                pr_number = int(pr_number_str)

                pr_state = StoredPRState(
                    pr_id=uuid.UUID(pr_data["pr_id"]),
                    pr_number=pr_data["pr_number"],
                    state=pr_data["state"],
                    head_sha=pr_data["head_sha"],
                    updated_at=datetime.fromisoformat(pr_data["updated_at"]),
                    check_runs=pr_data.get("check_runs", {}),
                )

                pull_requests[pr_number] = pr_state

            return RepositoryState(
                repository_id=repository_id,
                pull_requests=pull_requests,
                last_updated=datetime.fromisoformat(data["last_updated"]),
            )

        except Exception as e:
            logger.warning(f"Error deserializing cached state: {e}")
            return None

    async def invalidate_repository_state(self, repository_id: uuid.UUID) -> None:
        """Invalidate cached state for a repository.

        Args:
            repository_id: Repository ID to invalidate
        """
        # Remove from memory cache
        self.memory_cache.pop(repository_id, None)

        # Invalidate distributed cache
        if self.cache:
            try:
                cache_key = self._generate_cache_key(repository_id)
                await self.cache.invalidate(cache_key)
                logger.debug(f"Invalidated cache for repository {repository_id}")
            except Exception as e:
                logger.warning(f"Error invalidating cache: {e}")

    async def invalidate_all_states(self) -> None:
        """Invalidate all cached repository states."""
        # Clear memory cache
        self.memory_cache.clear()

        # Invalidate distributed cache pattern
        if self.cache:
            try:
                invalidated = await self.cache.invalidate("repo_state:*")
                logger.info(f"Invalidated {invalidated} cached repository states")
            except Exception as e:
                logger.warning(f"Error invalidating all cache entries: {e}")

    def cleanup_memory_cache(self) -> None:
        """Remove expired entries from memory cache."""
        current_time = time.time()
        expired_keys = []

        for repo_id, (_, cached_at) in self.memory_cache.items():
            if current_time - cached_at > self.memory_cache_ttl:
                expired_keys.append(repo_id)

        for key in expired_keys:
            del self.memory_cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    async def warm_cache(
        self, repository_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, bool]:
        """Warm cache with repository states.

        Args:
            repository_ids: Repository IDs to warm

        Returns:
            Dictionary mapping repository IDs to success status
        """
        logger.info(f"Warming cache for {len(repository_ids)} repositories")

        # Load states with force refresh to ensure fresh data
        states = await self.batch_get_repository_states(
            repository_ids, force_refresh=True
        )

        # Return success status for each repository
        return {repo_id: repo_id in states for repo_id in repository_ids}

    def get_stats(self) -> dict[str, int]:
        """Get state manager statistics.

        Returns:
            Dictionary with statistics
        """
        stats = self.stats.copy()
        stats.update(
            {
                "memory_cache_size": len(self.memory_cache),
                "memory_cache_ttl": self.memory_cache_ttl,
                "cache_ttl": self.cache_ttl,
            }
        )
        return stats

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on state manager.

        Returns:
            Health check results
        """
        health: dict[str, Any] = {
            "healthy": True,
            "memory_cache_size": len(self.memory_cache),
            "stats": self.get_stats(),
            "errors": [],
        }

        try:
            # Test database connectivity by attempting a simple query
            test_repo_id = uuid.uuid4()  # Random UUID for test

            # This will fail gracefully and return empty state
            test_state = await self.get_repository_state(test_repo_id)

            if test_state.repository_id != test_repo_id:
                errors_list = health["errors"]
                if isinstance(errors_list, list):
                    errors_list.append("Database connectivity test failed")
                health["healthy"] = False

        except Exception as e:
            errors_list = health["errors"]
            if isinstance(errors_list, list):
                errors_list.append(f"Health check error: {e!s}")
            health["healthy"] = False

        return health
