"""PR Discovery Engine for the PR Monitor Worker.

This module implements a robust PR Discovery Engine that efficiently fetches pull
requests from GitHub repositories with support for filtering, pagination, caching,
and incremental updates. The implementation follows the existing architecture
patterns and integrates with the data models defined in models.py.

Key features:
- Async PR discovery with intelligent pagination
- Comprehensive caching layer for API responses
- Rate limit aware with circuit breaker integration
- Support for filtering by state, dates, and repository criteria
- Performance monitoring and metrics collection
- Robust error handling with exponential backoff
"""

import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from ...cache.cache_manager import CacheManager
from ...github.client import GitHubClient
from ...github.exceptions import (
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)
from ...models.enums import CheckConclusion, CheckStatus, PRState
from .models import (
    ChangeType,
    CheckRunDiscovery,
    CheckRunDiscoveryInterface,
    DiscoveryResult,
    PRDiscoveryInterface,
    ProcessingMetrics,
    StateChangeEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryConfig:
    """Configuration for PR discovery operations."""

    # Pagination settings
    per_page: int = 100
    max_pages: int | None = None
    max_concurrent_repos: int = 5

    # Cache settings
    cache_ttl: int = 300  # 5 minutes
    cache_pr_details_ttl: int = 900  # 15 minutes
    use_etag_caching: bool = True

    # Performance settings
    batch_size: int = 20
    request_delay: float = 0.1  # Delay between requests
    max_retries: int = 3

    # Filtering settings
    default_state_filter: PRState = PRState.OPENED
    include_drafts: bool = False
    max_age_days: int = 30  # Maximum age for incremental updates

    def validate(self) -> None:
        """Validate configuration parameters."""
        if self.per_page < 1 or self.per_page > 100:
            raise ValueError("per_page must be between 1 and 100")

        if self.max_concurrent_repos < 1:
            raise ValueError("max_concurrent_repos must be positive")

        if self.cache_ttl < 0:
            raise ValueError("cache_ttl cannot be negative")


@dataclass
class RepositoryContext:
    """Context information for repository processing."""

    repository_id: uuid.UUID
    repository_owner: str
    repository_name: str
    last_updated: datetime | None = None
    etag: str | None = None
    processing_priority: int = 1  # Higher = more important


class PRDiscoveryEngine(PRDiscoveryInterface):
    """Robust PR Discovery Engine with caching and performance optimization.

    This engine provides efficient PR discovery capabilities with:
    - Intelligent caching with ETag support
    - Rate limit aware request management
    - Concurrent processing with batching
    - Comprehensive error handling and recovery
    - Performance metrics collection
    """

    def __init__(
        self,
        github_client: GitHubClient,
        cache_manager: CacheManager,
        config: DiscoveryConfig | None = None,
    ) -> None:
        """Initialize PR Discovery Engine.

        Args:
            github_client: GitHub API client instance
            cache_manager: Cache manager for API response caching
            config: Engine configuration options
        """
        self.github_client = github_client
        self.cache_manager = cache_manager
        self.config = config or DiscoveryConfig()
        self.config.validate()

        # Performance tracking
        self._metrics = ProcessingMetrics()
        self._start_time: float | None = None

        # Rate limiting and error tracking
        self._request_semaphore = asyncio.Semaphore(self.config.max_concurrent_repos)
        self._error_tracker: dict[str, int] = {}

    async def discover_prs(
        self,
        repositories: list[RepositoryContext],
        since: datetime | None = None,
        state_filter: PRState | None = None,
        include_drafts: bool | None = None,
    ) -> tuple[list[DiscoveryResult], ProcessingMetrics]:
        """Main entry point for bulk PR discovery across multiple repositories.

        Args:
            repositories: List of repositories to discover PRs from
            since: Only return PRs modified since this datetime
            state_filter: Filter by PR state (defaults to config setting)
            include_drafts: Whether to include draft PRs

        Returns:
            Tuple of (discovered PRs, processing metrics)
        """
        self._start_time = time.time()
        logger.info(f"Starting PR discovery for {len(repositories)} repositories")

        # Apply configuration defaults
        state_filter = state_filter or self.config.default_state_filter
        include_drafts = (
            include_drafts if include_drafts is not None else self.config.include_drafts
        )

        # Group repositories by priority for processing order
        prioritized_repos = self._prioritize_repositories(repositories)

        all_results: list[DiscoveryResult] = []

        try:
            # Process repositories in batches to manage concurrency
            for batch in self._create_batches(
                prioritized_repos, self.config.batch_size
            ):
                batch_results = await self._process_repository_batch(
                    batch, since, state_filter, include_drafts
                )
                all_results.extend(batch_results)

                # Small delay between batches to be respectful to API
                if self.config.request_delay > 0:
                    await asyncio.sleep(self.config.request_delay)

        except Exception as e:
            logger.error(f"Error in PR discovery: {e}")
            self._metrics = replace(
                self._metrics,
                errors_encountered=[*self._metrics.errors_encountered, str(e)],
            )

        # Finalize metrics
        final_metrics = self._finalize_metrics(len(all_results))

        logger.info(
            f"PR discovery completed: {len(all_results)} PRs discovered "
            f"in {final_metrics.discovery_duration:.2f}s"
        )

        return all_results, final_metrics

    async def discover_pull_requests(
        self,
        repository_id: uuid.UUID,
        repository_owner: str,
        repository_name: str,
        since: datetime | None = None,
        state_filter: PRState | None = None,
        include_drafts: bool = False,
    ) -> list[DiscoveryResult]:
        """Discover pull requests from a GitHub repository.

        This implements the abstract interface method from PRDiscoveryInterface.

        Args:
            repository_id: UUID of the repository in our database
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            since: Only return PRs modified since this datetime
            state_filter: Filter by PR state (opened, closed, merged)
            include_drafts: Whether to include draft PRs

        Returns:
            List of discovered pull request results
        """
        return await self.discover_prs_for_repo(
            repository_id=repository_id,
            repository_owner=repository_owner,
            repository_name=repository_name,
            since=since,
            state_filter=state_filter,
            include_drafts=include_drafts,
        )

    async def discover_prs_for_repo(
        self,
        repository_id: uuid.UUID,
        repository_owner: str,
        repository_name: str,
        since: datetime | None = None,
        state_filter: PRState | None = None,
        include_drafts: bool | None = None,
    ) -> list[DiscoveryResult]:
        """Discover pull requests for a single repository.

        Args:
            repository_id: UUID of the repository in our database
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            since: Only return PRs modified since this datetime
            state_filter: Filter by PR state
            include_drafts: Whether to include draft PRs

        Returns:
            List of discovered pull request results
        """
        repo_context = RepositoryContext(
            repository_id=repository_id,
            repository_owner=repository_owner,
            repository_name=repository_name,
        )

        results, _ = await self.discover_prs(
            repositories=[repo_context],
            since=since,
            state_filter=state_filter,
            include_drafts=include_drafts,
        )

        return results

    async def get_pull_request_details(
        self,
        repository_owner: str,
        repository_name: str,
        pr_number: int,
    ) -> DiscoveryResult:
        """Get detailed information for a specific pull request.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            pr_number: Pull request number

        Returns:
            Detailed pull request information

        Raises:
            GitHubNotFoundError: If PR doesn't exist
            GitHubError: For other GitHub API errors
        """
        cache_key = f"pr_details:{repository_owner}/{repository_name}:{pr_number}"

        # Try cache first
        cached_result = await self.cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for PR details: {cache_key}")
            return DiscoveryResult(**cached_result)

        try:
            # Fetch from GitHub API
            pr_data = await self.github_client.get_pull(
                repository_owner, repository_name, pr_number
            )

            # Convert to our model
            result = await self._convert_github_pr_to_discovery_result(
                pr_data,
                uuid.uuid4(),  # We don't have repo UUID in this context
            )

            # Cache the result
            await self.cache_manager.set(
                cache_key, result.to_dict(), ttl=self.config.cache_pr_details_ttl
            )

            return result

        except GitHubNotFoundError:
            logger.debug(
                f"PR not found: {repository_owner}/{repository_name}#{pr_number}"
            )
            raise
        except GitHubError as e:
            logger.error(f"Error fetching PR details: {e}")
            raise

    async def check_pr_exists(
        self,
        repository_owner: str,
        repository_name: str,
        pr_number: int,
    ) -> bool:
        """Check if a pull request exists without fetching full details.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            pr_number: Pull request number

        Returns:
            True if PR exists, False otherwise
        """
        try:
            await self.get_pull_request_details(
                repository_owner, repository_name, pr_number
            )
            return True
        except GitHubNotFoundError:
            return False
        except GitHubError:
            # For other errors, we can't be sure, so return False
            return False

    async def _process_repository_batch(
        self,
        repositories: list[RepositoryContext],
        since: datetime | None,
        state_filter: PRState,
        include_drafts: bool,
    ) -> list[DiscoveryResult]:
        """Process a batch of repositories concurrently.

        Args:
            repositories: Batch of repositories to process
            since: Filter for modified PRs
            state_filter: PR state filter
            include_drafts: Include draft PRs flag

        Returns:
            List of discovered PRs from all repositories in batch
        """

        async def process_single_repo(repo: RepositoryContext) -> list[DiscoveryResult]:
            async with self._request_semaphore:
                try:
                    return await self._fetch_prs_for_repository(
                        repo, since, state_filter, include_drafts
                    )
                except Exception as e:
                    repo_key = f"{repo.repository_owner}/{repo.repository_name}"
                    self._error_tracker[repo_key] = (
                        self._error_tracker.get(repo_key, 0) + 1
                    )
                    logger.error(f"Error processing repository {repo_key}: {e}")
                    return []

        # Execute all repositories in batch concurrently
        tasks = [process_single_repo(repo) for repo in repositories]
        batch_results = await asyncio.gather(*tasks)

        # Flatten results
        all_results = []
        for results in batch_results:
            all_results.extend(results)

        return all_results

    async def _fetch_prs_for_repository(
        self,
        repo: RepositoryContext,
        since: datetime | None,
        state_filter: PRState,
        include_drafts: bool,
    ) -> list[DiscoveryResult]:
        """Fetch PRs for a single repository with caching support.

        Args:
            repo: Repository context
            since: Filter for modified PRs
            state_filter: PR state filter
            include_drafts: Include draft PRs flag

        Returns:
            List of discovered PRs for the repository
        """
        cache_key = self._generate_cache_key(repo, state_filter, since, include_drafts)

        # Check cache first
        cached_data = await self._get_cached_prs(cache_key, repo.etag)
        if cached_data:
            logger.debug(
                f"Cache hit for repository: "
                f"{repo.repository_owner}/{repo.repository_name}"
            )
            return cached_data

        try:
            # Build query parameters
            params = {
                "state": self._convert_state_to_github(state_filter),
                "sort": "updated",
                "direction": "desc",
            }

            if since:
                params["since"] = since.isoformat()

            # Use pagination to fetch all PRs
            paginator = self.github_client.paginate(
                f"/repos/{repo.repository_owner}/{repo.repository_name}/pulls",
                params=params,
                per_page=self.config.per_page,
                max_pages=self.config.max_pages,
            )

            prs_data = []
            async for pr_data in paginator:
                prs_data.append(pr_data)

                # Respect max age if set and no explicit since filter
                if (
                    not since
                    and self.config.max_age_days > 0
                    and self._is_pr_too_old(pr_data, self.config.max_age_days)
                ):
                    break

            # Convert to our model and apply filters
            results = []
            for pr_data in prs_data:
                try:
                    discovery_result = (
                        await self._convert_github_pr_to_discovery_result(
                            pr_data, repo.repository_id
                        )
                    )

                    # Apply local filters
                    if self._passes_filters(discovery_result, include_drafts):
                        results.append(discovery_result)

                except Exception as e:
                    logger.warning(f"Error converting PR data: {e}")
                    continue

            # Cache the results
            await self._cache_prs(cache_key, results, repo.etag)

            logger.debug(
                f"Fetched {len(results)} PRs for "
                f"{repo.repository_owner}/{repo.repository_name}"
            )

            return results

        except GitHubRateLimitError as e:
            logger.warning(
                f"Rate limit hit for "
                f"{repo.repository_owner}/{repo.repository_name}: {e}"
            )
            # Wait and retry once
            await asyncio.sleep(e.reset_time - time.time() if e.reset_time else 60)
            # Return empty for now - could implement retry logic here
            return []

        except GitHubNotFoundError:
            logger.debug(
                f"Repository not found: {repo.repository_owner}/{repo.repository_name}"
            )
            return []

        except Exception as e:
            logger.error(
                f"Unexpected error fetching PRs for "
                f"{repo.repository_owner}/{repo.repository_name}: {e}"
            )
            return []

    async def _convert_github_pr_to_discovery_result(
        self, pr_data: dict[str, Any], repository_id: uuid.UUID
    ) -> DiscoveryResult:
        """Convert GitHub API PR data to our DiscoveryResult model.

        Args:
            pr_data: Raw PR data from GitHub API
            repository_id: UUID of the repository

        Returns:
            Converted DiscoveryResult instance
        """
        # Extract required fields with safe defaults
        pr_number = pr_data.get("number", 0)
        title = pr_data.get("title", "")
        author = pr_data.get("user", {}).get("login", "")

        # Convert state
        state_str = pr_data.get("state", "open").lower()
        if pr_data.get("merged", False):
            state = PRState.MERGED
        elif state_str == "closed":
            state = PRState.CLOSED
        else:
            state = PRState.OPENED

        # Extract branch information
        base_info = pr_data.get("base", {})
        head_info = pr_data.get("head", {})

        base_branch = base_info.get("ref", "")
        head_branch = head_info.get("ref", "")
        base_sha = base_info.get("sha", "")
        head_sha = head_info.get("sha", "")

        # Extract repository info from base
        repo_info = base_info.get("repo", {})
        repository_owner = repo_info.get("owner", {}).get("login", "")
        repository_name = repo_info.get("name", "")

        # Parse dates
        updated_at = None
        if pr_data.get("updated_at"):
            with contextlib.suppress(ValueError, TypeError):
                updated_at = datetime.fromisoformat(
                    pr_data["updated_at"].replace("Z", "+00:00")
                )

        return DiscoveryResult(
            repository_id=repository_id,
            repository_name=repository_name,
            repository_owner=repository_owner,
            pr_number=pr_number,
            title=title,
            author=author,
            state=state,
            draft=pr_data.get("draft", False),
            base_branch=base_branch,
            head_branch=head_branch,
            base_sha=base_sha,
            head_sha=head_sha,
            url=pr_data.get("html_url", ""),
            body=pr_data.get("body"),
            pr_metadata={
                "github_created_at": pr_data.get("created_at"),
                "github_updated_at": pr_data.get("updated_at"),
                "mergeable": pr_data.get("mergeable"),
                "mergeable_state": pr_data.get("mergeable_state"),
                "labels": [label.get("name") for label in pr_data.get("labels", [])],
                "assignees": [
                    user.get("login") for user in pr_data.get("assignees", [])
                ],
            },
            last_updated_at=updated_at,
            github_id=pr_data.get("id", 0),
            github_node_id=pr_data.get("node_id", ""),
        )

    def _generate_cache_key(
        self,
        repo: RepositoryContext,
        state_filter: PRState,
        since: datetime | None,
        include_drafts: bool,
    ) -> str:
        """Generate cache key for PR list request."""
        repo_key = f"{repo.repository_owner}/{repo.repository_name}"
        since_key = since.isoformat() if since else "none"
        return f"prs:{repo_key}:{state_filter.value}:{since_key}:{include_drafts}"

    async def _get_cached_prs(
        self, cache_key: str, etag: str | None
    ) -> list[DiscoveryResult] | None:
        """Get cached PRs with ETag validation if configured."""
        if not self.config.use_etag_caching or not etag:
            # Simple cache lookup
            cached_data = await self.cache_manager.get(cache_key)
            if cached_data:
                return [DiscoveryResult(**pr_dict) for pr_dict in cached_data]
            return None

        # ETag-based caching
        etag_key = f"{cache_key}:etag"
        cached_etag = await self.cache_manager.get(etag_key)

        if cached_etag == etag:
            cached_data = await self.cache_manager.get(cache_key)
            if cached_data:
                return [DiscoveryResult(**pr_dict) for pr_dict in cached_data]

        return None

    async def _cache_prs(
        self, cache_key: str, results: list[DiscoveryResult], etag: str | None
    ) -> None:
        """Cache PR results with optional ETag."""
        # Cache the results
        results_dict = [result.to_dict() for result in results]
        await self.cache_manager.set(cache_key, results_dict, ttl=self.config.cache_ttl)

        # Cache ETag if configured
        if self.config.use_etag_caching and etag:
            etag_key = f"{cache_key}:etag"
            await self.cache_manager.set(etag_key, etag, ttl=self.config.cache_ttl)

    def _convert_state_to_github(self, state: PRState) -> str:
        """Convert our PRState enum to GitHub API state parameter."""
        match state:
            case PRState.OPENED:
                return "open"
            case PRState.CLOSED:
                return "closed"
            case PRState.MERGED:
                return "closed"  # GitHub API uses 'closed' for merged PRs too

    def _passes_filters(self, pr: DiscoveryResult, include_drafts: bool) -> bool:
        """Apply local filters to PR data."""
        # Draft filter
        return include_drafts or not pr.draft

    def _is_pr_too_old(self, pr_data: dict[str, Any], max_age_days: int) -> bool:
        """Check if PR is older than max age."""
        updated_at_str = pr_data.get("updated_at")
        if not updated_at_str:
            return False

        try:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            # Use UTC for comparison to avoid timezone issues
            age_cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
            # Ensure both datetimes are timezone-aware for comparison
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)
            return updated_at < age_cutoff
        except (ValueError, TypeError):
            return False

    def _prioritize_repositories(
        self, repositories: list[RepositoryContext]
    ) -> list[RepositoryContext]:
        """Sort repositories by processing priority."""
        return sorted(repositories, key=lambda r: r.processing_priority, reverse=True)

    def _create_batches(
        self, items: list[RepositoryContext], batch_size: int
    ) -> list[list[RepositoryContext]]:
        """Create batches of repositories for processing."""
        batches = []
        for i in range(0, len(items), batch_size):
            batches.append(items[i : i + batch_size])
        return batches

    def _finalize_metrics(self, discovered_count: int) -> ProcessingMetrics:
        """Finalize and return processing metrics."""
        end_time = time.time()
        duration = end_time - (self._start_time or end_time)

        return replace(
            self._metrics,
            discovery_duration=duration,
            total_processing_duration=duration,
            prs_discovered=discovered_count,
            prs_processed_successfully=discovered_count,  # All discovered PRs
            errors_encountered=list(self._error_tracker.keys()),
        )

    async def get_metrics(self) -> ProcessingMetrics:
        """Get current processing metrics."""
        return self._metrics

    async def clear_cache(self, pattern: str | None = None) -> int:
        """Clear cached PR data.

        Args:
            pattern: Optional pattern to match cache keys (e.g., "prs:*")

        Returns:
            Number of cache entries cleared
        """
        pattern = pattern or "prs:*"
        return await self.cache_manager.clear(pattern)


class CheckRunDiscoveryEngine(CheckRunDiscoveryInterface):
    """Robust Check Run Discovery Engine with comprehensive status tracking.

    This engine provides efficient check run discovery capabilities with:
    - Intelligent check run status transition tracking
    - Check suite management and relationship handling
    - Comprehensive change detection with actionable failure categorization
    - Performance optimizations with batch processing and smart caching
    - Error handling for GitHub API edge cases
    """

    def __init__(
        self,
        github_client: GitHubClient,
        cache_manager: CacheManager,
        config: DiscoveryConfig | None = None,
    ) -> None:
        """Initialize Check Run Discovery Engine.

        Args:
            github_client: GitHub API client instance
            cache_manager: Cache manager for API response caching
            config: Engine configuration options
        """
        self.github_client = github_client
        self.cache_manager = cache_manager
        self.config = config or DiscoveryConfig()
        self.config.validate()

        # Performance tracking
        self._metrics = ProcessingMetrics()
        self._start_time: float | None = None

        # Rate limiting and error tracking
        self._request_semaphore = asyncio.Semaphore(self.config.max_concurrent_repos)
        self._error_tracker: dict[str, int] = {}

        # Check run processing cache
        self._check_run_cache: dict[str, dict[str, Any]] = {}
        self._check_suite_cache: dict[str, dict[str, Any]] = {}

    async def discover_check_runs(
        self,
        repository_owner: str,
        repository_name: str,
        pr_number: int,
        ref: str,
    ) -> list[CheckRunDiscovery]:
        """Main entry point for bulk check run discovery.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            pr_number: Pull request number
            ref: Git reference (SHA, branch, tag)

        Returns:
            List of discovered check run results
        """
        self._start_time = time.time()
        logger.info(
            f"Starting check run discovery for PR #{pr_number} "
            f"in {repository_owner}/{repository_name}"
        )

        try:
            # Fetch check runs for the commit
            check_runs = await self.discover_check_runs_for_commit(
                repository_owner, repository_name, ref
            )

            # Filter and enhance check runs with PR context
            pr_check_runs = []
            for check_run in check_runs:
                # Create PR-aware check run discovery result
                pr_check_run = replace(
                    check_run,
                    pr_id=uuid.uuid4(),  # This should be provided by caller
                    pr_number=pr_number,
                )
                pr_check_runs.append(pr_check_run)

            # Update metrics
            self._metrics = replace(
                self._metrics,
                check_runs_discovered=len(pr_check_runs),
                check_runs_processed_successfully=len(pr_check_runs),
            )

            logger.info(
                f"Check run discovery completed: {len(pr_check_runs)} "
                f"check runs found for PR #{pr_number}"
            )

            return pr_check_runs

        except Exception as e:
            logger.error(f"Error in check run discovery: {e}")
            self._metrics = replace(
                self._metrics,
                errors_encountered=[*self._metrics.errors_encountered, str(e)],
            )
            return []

    async def discover_check_runs_for_commit(
        self,
        repository_owner: str,
        repository_name: str,
        commit_sha: str,
    ) -> list[CheckRunDiscovery]:
        """Fetch check runs for a specific commit.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            commit_sha: Commit SHA to fetch check runs for

        Returns:
            List of check run discovery results
        """
        cache_key = f"check_runs:{repository_owner}/{repository_name}:{commit_sha}"

        # Check cache first
        cached_result = await self.cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for check runs: {cache_key}")
            return [CheckRunDiscovery(**cr) for cr in cached_result]

        try:
            # Fetch from GitHub API using check runs endpoint
            endpoint = (
                f"/repos/{repository_owner}/{repository_name}"
                f"/commits/{commit_sha}/check-runs"
            )

            paginator = self.github_client.paginate(
                endpoint,
                per_page=self.config.per_page,
            )

            check_runs_data = []
            async for check_run_data in paginator:
                check_runs_data.append(check_run_data)

            # Convert to our model and process check suites
            results = []
            check_suites_to_process = set()

            for check_run_data in check_runs_data:
                try:
                    check_run = await self._convert_github_check_run(check_run_data)
                    results.append(check_run)

                    # Track check suites for batch processing
                    if check_run.check_suite_id:
                        check_suites_to_process.add(check_run.check_suite_id)

                except Exception as e:
                    logger.warning(f"Error converting check run data: {e}")
                    continue

            # Process check suites if any were found
            if check_suites_to_process:
                await self._process_check_suites(
                    repository_owner, repository_name, list(check_suites_to_process)
                )

            # Cache the results
            results_dict = [result.to_dict() for result in results]
            await self.cache_manager.set(
                cache_key, results_dict, ttl=self.config.cache_ttl
            )

            logger.debug(
                f"Fetched {len(results)} check runs for commit {commit_sha[:8]}"
            )

            return results

        except GitHubRateLimitError as e:
            logger.warning(f"Rate limit hit for check runs: {e}")
            await asyncio.sleep(e.reset_time - time.time() if e.reset_time else 60)
            return []

        except GitHubNotFoundError:
            logger.debug(f"Commit not found: {commit_sha}")
            return []

        except Exception as e:
            logger.error(f"Unexpected error fetching check runs: {e}")
            return []

    async def detect_check_run_changes(
        self,
        old_check_runs: list[CheckRunDiscovery],
        new_check_runs: list[CheckRunDiscovery],
        pr_id: uuid.UUID,
        pr_number: int,
    ) -> list[StateChangeEvent]:
        """Compare current vs stored check runs to detect changes.

        Args:
            old_check_runs: Previously stored check run states
            new_check_runs: Current check run states from discovery
            pr_id: Associated PR UUID
            pr_number: Associated PR number

        Returns:
            List of detected state change events
        """
        changes = []

        # Create lookup maps for efficient comparison
        old_runs_map = {cr.github_check_run_id: cr for cr in old_check_runs}
        new_runs_map = {cr.github_check_run_id: cr for cr in new_check_runs}

        # Detect new check runs
        for check_run_id, new_run in new_runs_map.items():
            if check_run_id not in old_runs_map:
                change_event = StateChangeEvent(
                    event_type=ChangeType.CHECK_RUN_CREATED,
                    pr_id=pr_id,
                    pr_number=pr_number,
                    new_state=new_run.to_dict(),
                    changed_fields=["status", "check_name"],
                    check_run_name=new_run.check_name,
                )
                changes.append(change_event)

        # Detect updated check runs
        for check_run_id, new_run in new_runs_map.items():
            if check_run_id in old_runs_map:
                old_run = old_runs_map[check_run_id]
                detected_changes = self._compare_check_run_states(old_run, new_run)

                if detected_changes:
                    change_event = StateChangeEvent(
                        event_type=(
                            ChangeType.CHECK_RUN_STATUS_CHANGED
                            if (
                                "status" in detected_changes
                                or "conclusion" in detected_changes
                            )
                            else ChangeType.CHECK_RUN_UPDATED
                        ),
                        pr_id=pr_id,
                        pr_number=pr_number,
                        old_state=old_run.to_dict(),
                        new_state=new_run.to_dict(),
                        changed_fields=detected_changes,
                        check_run_name=new_run.check_name,
                    )
                    changes.append(change_event)

        logger.debug(f"Detected {len(changes)} check run changes for PR #{pr_number}")
        return changes

    async def _process_check_suite(
        self,
        repository_owner: str,
        repository_name: str,
        check_suite_id: str,
    ) -> dict[str, Any] | None:
        """Handle check suite relationships and metadata extraction.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            check_suite_id: GitHub check suite ID

        Returns:
            Check suite metadata or None if not found
        """
        # Check cache first
        cache_key = f"check_suite:{repository_owner}/{repository_name}:{check_suite_id}"
        cached_suite = await self.cache_manager.get(cache_key)
        if cached_suite:
            return dict(cached_suite)

        try:
            # Fetch check suite information
            endpoint = (
                f"/repos/{repository_owner}/{repository_name}"
                f"/check-suites/{check_suite_id}"
            )
            suite_data = await self.github_client.get(endpoint)

            # Extract relevant metadata
            suite_metadata = {
                "id": suite_data.get("id"),
                "head_branch": suite_data.get("head_branch"),
                "head_sha": suite_data.get("head_sha"),
                "status": suite_data.get("status"),
                "conclusion": suite_data.get("conclusion"),
                "url": suite_data.get("url"),
                "created_at": suite_data.get("created_at"),
                "updated_at": suite_data.get("updated_at"),
                "app": suite_data.get("app", {}).get("name"),
            }

            # Cache the suite metadata
            await self.cache_manager.set(
                cache_key, suite_metadata, ttl=self.config.cache_ttl
            )

            return suite_metadata

        except Exception as e:
            logger.warning(f"Error processing check suite {check_suite_id}: {e}")
            return None

    async def _extract_check_metadata(
        self, check_run_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract logs, output, and timing data from check run.

        Args:
            check_run_data: Raw check run data from GitHub API

        Returns:
            Extracted metadata dictionary
        """
        metadata = {}

        # Extract output information
        output = check_run_data.get("output", {})
        if output:
            metadata["output"] = {
                "title": output.get("title"),
                "summary": output.get("summary"),
                "text": output.get("text"),
                "annotations_count": len(output.get("annotations", [])),
                "images_count": len(output.get("images", [])),
            }

        # Extract app information
        app = check_run_data.get("app", {})
        if app:
            metadata["app"] = {
                "name": app.get("name"),
                "slug": app.get("slug"),
                "owner": app.get("owner", {}).get("login"),
            }

        # Extract pull request references
        pull_requests = check_run_data.get("pull_requests", [])
        if pull_requests and isinstance(pull_requests, list):
            pr_refs: list[dict[str, Any]] = [
                {
                    "number": pr.get("number"),
                    "head_sha": pr.get("head", {}).get("sha"),
                    "base_sha": pr.get("base", {}).get("sha"),
                }
                for pr in pull_requests
                if isinstance(pr, dict)
            ]
            metadata["pull_requests"] = pr_refs  # type: ignore[assignment]

        # Extract timing metadata
        timing: dict[str, Any] = {}
        for time_field in ["started_at", "completed_at"]:
            time_value = check_run_data.get(time_field)
            if time_value:
                timing[time_field] = time_value
        if timing:
            metadata["timing"] = timing

        # Extract external IDs for tracking
        external_id = check_run_data.get("id")
        node_id = check_run_data.get("node_id")

        if external_id is not None:
            metadata["external_id"] = external_id
        if node_id is not None:
            metadata["node_id"] = node_id

        return metadata

    def _categorize_check_run(self, check_run: CheckRunDiscovery) -> str:
        """Determine check run type and category for routing.

        Args:
            check_run: Check run discovery result

        Returns:
            Category string for routing and processing
        """
        check_name_lower = check_run.check_name.lower()

        # Categorize based on check name patterns
        lint_patterns = ["lint", "eslint", "flake8", "ruff"]
        if any(word in check_name_lower for word in lint_patterns):
            return "lint"

        format_patterns = ["format", "prettier", "black"]
        if any(word in check_name_lower for word in format_patterns):
            return "format"

        test_patterns = ["test", "pytest", "jest", "unit"]
        if any(word in check_name_lower for word in test_patterns):
            return "test"
        elif any(word in check_name_lower for word in ["build", "compile", "webpack"]):
            return "build"
        elif any(word in check_name_lower for word in ["type", "mypy", "typescript"]):
            return "type"
        elif any(word in check_name_lower for word in ["security", "audit", "scan"]):
            return "security"
        elif any(word in check_name_lower for word in ["deploy", "release"]):
            return "deployment"
        else:
            return "other"

    async def _convert_github_check_run(
        self, check_run_data: dict[str, Any]
    ) -> CheckRunDiscovery:
        """Convert GitHub API check run data to our CheckRunDiscovery model.

        Args:
            check_run_data: Raw check run data from GitHub API

        Returns:
            Converted CheckRunDiscovery instance
        """
        # Extract basic information
        github_check_run_id = str(check_run_data.get("id", ""))
        check_name = check_run_data.get("name", "")
        check_suite_id = str(check_run_data.get("check_suite", {}).get("id", ""))

        # Convert status
        status_str = check_run_data.get("status", "queued").lower()
        status = CheckStatus.QUEUED
        try:
            status = CheckStatus(status_str)
        except ValueError:
            logger.warning(f"Unknown check status: {status_str}")

        # Convert conclusion
        conclusion = None
        conclusion_str = check_run_data.get("conclusion")
        if conclusion_str:
            try:
                conclusion = CheckConclusion(conclusion_str.lower())
            except ValueError:
                logger.warning(f"Unknown check conclusion: {conclusion_str}")

        # Extract URLs
        details_url = check_run_data.get("details_url")
        # GitHub doesn't provide direct log URLs
        logs_url = check_run_data.get("html_url")

        # Extract output
        output = check_run_data.get("output", {})
        output_summary = output.get("summary")
        output_text = output.get("text")

        # Parse timing information
        started_at = None
        completed_at = None

        if check_run_data.get("started_at"):
            with contextlib.suppress(ValueError, TypeError):
                started_at = datetime.fromisoformat(
                    check_run_data["started_at"].replace("Z", "+00:00")
                )

        if check_run_data.get("completed_at"):
            with contextlib.suppress(ValueError, TypeError):
                completed_at = datetime.fromisoformat(
                    check_run_data["completed_at"].replace("Z", "+00:00")
                )

        # Extract metadata
        check_metadata = await self._extract_check_metadata(check_run_data)

        return CheckRunDiscovery(
            pr_id=uuid.uuid4(),  # This will be overridden by caller
            pr_number=0,  # This will be overridden by caller
            github_check_run_id=github_check_run_id,
            check_name=check_name,
            check_suite_id=check_suite_id if check_suite_id != "0" else None,
            status=status,
            conclusion=conclusion,
            details_url=details_url,
            logs_url=logs_url,
            output_summary=output_summary,
            output_text=output_text,
            started_at=started_at,
            completed_at=completed_at,
            check_metadata=check_metadata,
        )

    def _compare_check_run_states(
        self,
        old_run: CheckRunDiscovery,
        new_run: CheckRunDiscovery,
    ) -> list[str]:
        """Compare two check run states to detect changes.

        Args:
            old_run: Previous check run state
            new_run: Current check run state

        Returns:
            List of changed field names
        """
        changed_fields = []

        # Compare status
        if old_run.status != new_run.status:
            changed_fields.append("status")

        # Compare conclusion
        if old_run.conclusion != new_run.conclusion:
            changed_fields.append("conclusion")

        # Compare timing
        if old_run.started_at != new_run.started_at:
            changed_fields.append("started_at")

        if old_run.completed_at != new_run.completed_at:
            changed_fields.append("completed_at")

        # Compare output
        if old_run.output_summary != new_run.output_summary:
            changed_fields.append("output_summary")

        if old_run.output_text != new_run.output_text:
            changed_fields.append("output_text")

        # Compare URLs
        if old_run.details_url != new_run.details_url:
            changed_fields.append("details_url")

        if old_run.logs_url != new_run.logs_url:
            changed_fields.append("logs_url")

        return changed_fields

    async def _process_check_suites(
        self,
        repository_owner: str,
        repository_name: str,
        check_suite_ids: list[str],
    ) -> None:
        """Process multiple check suites in batch for performance.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            check_suite_ids: List of check suite IDs to process
        """

        async def process_single_suite(suite_id: str) -> None:
            async with self._request_semaphore:
                await self._process_check_suite(
                    repository_owner, repository_name, suite_id
                )

        # Process suites concurrently
        tasks = [process_single_suite(suite_id) for suite_id in check_suite_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

    # Interface methods implementation

    async def get_check_run_details(
        self,
        repository_owner: str,
        repository_name: str,
        check_run_id: str,
    ) -> CheckRunDiscovery:
        """Get detailed information for a specific check run.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            check_run_id: GitHub check run ID

        Returns:
            Detailed check run information

        Raises:
            GitHubNotFoundError: If check run doesn't exist
            GitHubError: For other GitHub API errors
        """
        cache_key = (
            f"check_run_details:{repository_owner}/{repository_name}:{check_run_id}"
        )

        # Try cache first
        cached_result = await self.cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for check run details: {cache_key}")
            return CheckRunDiscovery(**cached_result)

        try:
            # Fetch from GitHub API
            endpoint = (
                f"/repos/{repository_owner}/{repository_name}/check-runs/{check_run_id}"
            )
            check_run_data = await self.github_client.get(endpoint)

            # Convert to our model
            result = await self._convert_github_check_run(check_run_data)

            # Cache the result
            await self.cache_manager.set(
                cache_key, result.to_dict(), ttl=self.config.cache_pr_details_ttl
            )

            return result

        except GitHubNotFoundError:
            logger.debug(f"Check run not found: {check_run_id}")
            raise
        except GitHubError as e:
            logger.error(f"Error fetching check run details: {e}")
            raise

    async def get_failed_check_runs(
        self,
        repository_owner: str,
        repository_name: str,
        pr_number: int,
        ref: str,
    ) -> list[CheckRunDiscovery]:
        """Get only failed check runs for a pull request.

        Args:
            repository_owner: GitHub repository owner/organization
            repository_name: GitHub repository name
            pr_number: Pull request number
            ref: Git reference (SHA, branch, tag)

        Returns:
            List of failed check run results
        """
        # Get all check runs first
        all_check_runs = await self.discover_check_runs(
            repository_owner, repository_name, pr_number, ref
        )

        # Filter for failed check runs only
        failed_check_runs = [
            check_run for check_run in all_check_runs if check_run.is_failed
        ]

        logger.debug(
            f"Found {len(failed_check_runs)} failed check runs "
            f"out of {len(all_check_runs)} total for PR #{pr_number}"
        )

        return failed_check_runs

    async def get_metrics(self) -> ProcessingMetrics:
        """Get current processing metrics."""
        end_time = time.time()
        duration = end_time - (self._start_time or end_time)

        return replace(
            self._metrics,
            check_run_discovery_duration=duration,
            total_processing_duration=duration,
        )

    async def clear_cache(self, pattern: str | None = None) -> int:
        """Clear cached check run data.

        Args:
            pattern: Optional pattern to match cache keys (e.g., "check_runs:*")

        Returns:
            Number of cache entries cleared
        """
        pattern = pattern or "check_runs:*"
        return await self.cache_manager.clear(pattern)
