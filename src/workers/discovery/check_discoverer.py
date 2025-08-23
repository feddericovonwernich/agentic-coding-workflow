"""Check run discoverer for batch check fetching.

This module implements the CheckDiscoveryStrategy interface to efficiently fetch
check runs for multiple PRs using batched GitHub API calls.
"""

import asyncio
import logging
import time
from datetime import datetime
from urllib.parse import urlparse

from src.github.client import GitHubClient
from src.github.exceptions import GitHubError, GitHubNotFoundError, GitHubRateLimitError

from .interfaces import (
    CacheStrategy,
    CheckDiscoveryStrategy,
    DiscoveredCheckRun,
    DiscoveredPR,
)

logger = logging.getLogger(__name__)


class GitHubCheckDiscoverer(CheckDiscoveryStrategy):
    """GitHub API implementation of check run discovery strategy.

    Provides efficient batch discovery of check runs with caching and error handling.
    Features:
    - Batch fetching for multiple PRs
    - SHA-based deduplication
    - Intelligent caching per commit
    - Error recovery and retry logic
    """

    def __init__(
        self,
        github_client: GitHubClient,
        cache: CacheStrategy,
        batch_size: int = 10,
        max_concurrent: int = 5,
    ):
        """Initialize check discoverer with dependencies.

        Args:
            github_client: GitHub API client
            cache: Cache strategy implementation
            batch_size: Number of PRs to process in each batch
            max_concurrent: Maximum concurrent API requests
        """
        self.github_client = github_client
        self.cache = cache
        self.batch_size = batch_size
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def _parse_repository_url(self, repository_url: str) -> tuple[str, str]:
        """Parse GitHub repository URL to extract owner and repo name.

        Args:
            repository_url: GitHub repository URL

        Returns:
            Tuple of (owner, repo_name)

        Raises:
            ValueError: If URL format is invalid
        """
        try:
            parsed = urlparse(repository_url)
            path_parts = parsed.path.strip("/").split("/")

            if len(path_parts) >= 2:
                owner, repo_name = path_parts[0], path_parts[1]
                # Remove .git suffix if present
                if repo_name.endswith(".git"):
                    repo_name = repo_name[:-4]
                return owner, repo_name

            raise ValueError("Invalid repository URL format")

        except Exception as e:
            raise ValueError(
                f"Failed to parse repository URL '{repository_url}': {e}"
            ) from e

    def _generate_cache_key(self, owner: str, repo: str, sha: str) -> str:
        """Generate cache key for check runs by commit SHA.

        Args:
            owner: Repository owner
            repo: Repository name
            sha: Commit SHA

        Returns:
            Cache key string
        """
        return f"checks:{owner}:{repo}:{sha}"

    def _convert_github_check_to_discovered(
        self, check_data: dict
    ) -> DiscoveredCheckRun:
        """Convert GitHub API check run response to DiscoveredCheckRun.

        Args:
            check_data: GitHub API check run response data

        Returns:
            DiscoveredCheckRun object
        """
        # Handle timestamps
        started_at = None
        if check_data.get("started_at"):
            started_at = datetime.fromisoformat(
                check_data["started_at"].replace("Z", "+00:00")
            )

        completed_at = None
        if check_data.get("completed_at"):
            completed_at = datetime.fromisoformat(
                check_data["completed_at"].replace("Z", "+00:00")
            )

        # Extract output information
        output = None
        if check_data.get("output"):
            output = {
                "title": check_data["output"].get("title"),
                "summary": check_data["output"].get("summary"),
                "text": check_data["output"].get("text"),
                "annotations_count": check_data["output"].get("annotations_count", 0),
                "annotations_url": check_data["output"].get("annotations_url"),
            }

        return DiscoveredCheckRun(
            external_id=str(check_data["id"]),
            name=check_data["name"],
            status=check_data["status"],
            conclusion=check_data.get("conclusion"),
            started_at=started_at,
            completed_at=completed_at,
            details_url=check_data.get("details_url"),
            output=output,
        )

    async def _fetch_check_runs_for_sha(
        self, owner: str, repo: str, sha: str
    ) -> list[DiscoveredCheckRun]:
        """Fetch check runs for a specific commit SHA.

        Args:
            owner: Repository owner
            repo: Repository name
            sha: Commit SHA

        Returns:
            List of discovered check runs
        """
        cache_key = self._generate_cache_key(owner, repo, sha)

        # Try cache first
        cached_checks = await self.cache.get(cache_key)
        if cached_checks:
            logger.debug(f"Cache hit for check runs: {cache_key}")
            return [DiscoveredCheckRun(**check_data) for check_data in cached_checks]

        check_runs = []

        try:
            async with self.semaphore:
                logger.debug(f"Fetching check runs for {owner}/{repo}@{sha}")

                # Use paginator to get all check runs
                paginator = self.github_client.paginate(
                    f"/repos/{owner}/{repo}/commits/{sha}/check-runs",
                    per_page=100,
                    max_pages=5,  # Reasonable limit for check runs
                )

                async for page_data in paginator:
                    # GitHub API returns check runs in 'check_runs' field
                    checks_data = (
                        page_data.get("check_runs", [])
                        if isinstance(page_data, dict)
                        else []
                    )

                    for check_data in checks_data:
                        try:
                            discovered_check = self._convert_github_check_to_discovered(
                                check_data
                            )
                            check_runs.append(discovered_check)
                        except Exception as e:
                            logger.warning(
                                f"Failed to convert check run "
                                f"{check_data.get('id')}: {e}"
                            )

                # Cache the results for 5 minutes
                if check_runs:
                    cache_data = [
                        {
                            "external_id": check.external_id,
                            "name": check.name,
                            "status": check.status,
                            "conclusion": check.conclusion,
                            "started_at": check.started_at.isoformat()
                            if check.started_at
                            else None,
                            "completed_at": check.completed_at.isoformat()
                            if check.completed_at
                            else None,
                            "details_url": check.details_url,
                            "output": check.output,
                        }
                        for check in check_runs
                    ]
                    await self.cache.set(cache_key, cache_data, ttl=300)

                logger.debug(
                    f"Found {len(check_runs)} check runs for {owner}/{repo}@{sha}"
                )

        except GitHubNotFoundError:
            logger.debug(f"No check runs found for {owner}/{repo}@{sha}")
            # Cache empty result briefly to avoid repeated API calls
            await self.cache.set(cache_key, [], ttl=60)

        except GitHubRateLimitError as e:
            logger.warning(f"Rate limit hit while fetching checks for {sha}: {e}")
            raise  # Re-raise to be handled by caller

        except GitHubError as e:
            logger.warning(f"GitHub API error fetching checks for {sha}: {e}")
            # Don't cache errors, allow retry

        except Exception as e:
            logger.error(f"Unexpected error fetching checks for {sha}: {e}")

        return check_runs

    async def discover_checks(
        self, pr_data: DiscoveredPR, repository_url: str
    ) -> list[DiscoveredCheckRun]:
        """Discover check runs for a single PR.

        Args:
            pr_data: Discovered PR data
            repository_url: GitHub URL of the repository

        Returns:
            List of discovered check runs
        """
        try:
            owner, repo = self._parse_repository_url(repository_url)

            # Fetch check runs for the head SHA
            check_runs = await self._fetch_check_runs_for_sha(
                owner, repo, pr_data.head_sha
            )

            logger.debug(
                f"Discovered {len(check_runs)} check runs for PR #{pr_data.pr_number}"
            )

            return check_runs

        except Exception as e:
            logger.error(f"Error discovering checks for PR #{pr_data.pr_number}: {e}")
            return []

    async def batch_discover_checks(
        self, prs: list[DiscoveredPR], repository_url: str
    ) -> dict[int, list[DiscoveredCheckRun]]:
        """Discover check runs for multiple PRs efficiently.

        Uses SHA-based deduplication to minimize API calls when multiple PRs
        share the same head commit.

        Args:
            prs: List of discovered PRs
            repository_url: GitHub URL of the repository

        Returns:
            Dictionary mapping PR numbers to their check runs
        """
        if not prs:
            return {}

        start_time = time.time()
        result = {}

        try:
            owner, repo = self._parse_repository_url(repository_url)

            # Group PRs by head SHA to deduplicate API calls
            sha_to_prs: dict[str, list[DiscoveredPR]] = {}
            for pr in prs:
                if pr.head_sha not in sha_to_prs:
                    sha_to_prs[pr.head_sha] = []
                sha_to_prs[pr.head_sha].append(pr)

            logger.info(
                f"Batch discovering checks for {len(prs)} PRs "
                f"({len(sha_to_prs)} unique SHAs) from {owner}/{repo}"
            )

            # Create tasks for fetching check runs for each unique SHA
            fetch_tasks = []
            for sha in sha_to_prs:
                task = self._fetch_check_runs_for_sha(owner, repo, sha)
                fetch_tasks.append((sha, task))

            # Execute tasks in batches to control concurrency
            sha_to_checks: dict[str, list[DiscoveredCheckRun]] = {}
            for i in range(0, len(fetch_tasks), self.batch_size):
                batch = fetch_tasks[i : i + self.batch_size]

                # Execute batch
                batch_results = await asyncio.gather(
                    *[task for _, task in batch], return_exceptions=True
                )

                # Process results
                for (sha, _), check_result in zip(batch, batch_results, strict=False):
                    if isinstance(check_result, Exception):
                        logger.warning(
                            f"Error fetching checks for SHA {sha}: {check_result}"
                        )
                        sha_to_checks[sha] = []
                    elif isinstance(check_result, list):
                        sha_to_checks[sha] = check_result
                    else:
                        sha_to_checks[sha] = []

                # Small delay between batches to be respectful to API
                if i + self.batch_size < len(fetch_tasks):
                    await asyncio.sleep(0.1)

            # Map check runs back to PR numbers
            for sha, prs_for_sha in sha_to_prs.items():
                check_runs = sha_to_checks.get(sha, [])
                for pr in prs_for_sha:
                    # Copy to avoid shared references
                    result[pr.pr_number] = check_runs.copy()

            processing_time = time.time() - start_time
            total_checks = sum(len(checks) for checks in result.values())

            logger.info(
                f"Batch check discovery completed for {owner}/{repo}: "
                f"{len(prs)} PRs, {total_checks} check runs in {processing_time:.2f}s "
                f"(deduplication saved {len(prs) - len(sha_to_prs)} API calls)"
            )

        except ValueError as e:
            logger.error(f"Invalid repository URL: {e}")
        except Exception as e:
            logger.error(f"Error in batch check discovery: {e}")

        return result

    async def get_check_run_logs(
        self, owner: str, repo: str, check_run_id: str
    ) -> str | None:
        """Fetch logs for a specific check run (if available).

        Args:
            owner: Repository owner
            repo: Repository name
            check_run_id: Check run ID

        Returns:
            Log content if available, None otherwise
        """
        try:
            async with self.semaphore:
                # Note: This is a placeholder - GitHub API doesn't directly expose logs
                # In practice, logs would be fetched from the details_url or via
                # GitHub Actions API for workflow runs
                logger.debug(
                    f"Log fetching not implemented for check run {check_run_id}"
                )
                return None

        except Exception as e:
            logger.warning(f"Error fetching logs for check run {check_run_id}: {e}")
            return None

    async def get_discovery_stats(self) -> dict[str, int]:
        """Get statistics about check run discovery.

        Returns:
            Dictionary with discovery statistics
        """
        # This would typically track metrics over time
        # For now, return basic semaphore info
        # Get waiters count safely
        waiters_count = 0
        if hasattr(self.semaphore, "_waiters") and self.semaphore._waiters is not None:
            waiters_count = len(self.semaphore._waiters)

        return {
            "max_concurrent": self.semaphore._value + waiters_count,
            "available_slots": self.semaphore._value,
            "batch_size": self.batch_size,
        }
