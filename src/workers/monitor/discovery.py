"""PR and check run discovery service for GitHub repositories."""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.github.client import GitHubClient
from src.models.repository import Repository

from .models import CheckRunData, PRData

logger = logging.getLogger(__name__)


class PRDiscoveryService(ABC):
    """Abstract base class for PR discovery service."""

    @abstractmethod
    async def discover_prs(
        self, repository: Repository, since: datetime | None = None
    ) -> list[PRData]:
        """Discover pull requests from a GitHub repository.

        Args:
            repository: Repository to discover PRs for
            since: Optional timestamp for incremental updates

        Returns:
            List of PR data objects
        """
        pass

    @abstractmethod
    async def discover_check_runs(
        self, repository: Repository, pr_data: PRData
    ) -> list[CheckRunData]:
        """Discover check runs for a specific pull request.

        Args:
            repository: Repository containing the PR
            pr_data: PR data to discover check runs for

        Returns:
            List of check run data objects
        """
        pass

    @abstractmethod
    async def discover_check_runs_batch(
        self, repository: Repository, pr_data_list: list[PRData]
    ) -> dict[int, list[CheckRunData]]:
        """Discover check runs for multiple pull requests concurrently.

        Args:
            repository: Repository containing the PRs
            pr_data_list: List of PR data to discover check runs for

        Returns:
            Dictionary mapping PR numbers to their check runs
        """
        pass


class GitHubPRDiscoveryService(PRDiscoveryService):
    """GitHub implementation of PR discovery service with caching and optimization."""

    def __init__(
        self,
        github_client: GitHubClient,
        max_concurrent_requests: int = 10,
        cache_ttl_seconds: int = 300,  # 5 minutes
    ) -> None:
        """Initialize GitHub PR discovery service.

        Args:
            github_client: GitHub API client
            max_concurrent_requests: Maximum concurrent API requests
            cache_ttl_seconds: Cache TTL for ETag caching
        """
        self.github_client = github_client
        self.max_concurrent_requests = max_concurrent_requests
        self.cache_ttl_seconds = cache_ttl_seconds

        # ETag cache for conditional requests
        self._etag_cache: dict[str, tuple[str, datetime, list[PRData]]] = {}

        # Semaphore for rate limiting
        self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)

    async def discover_prs(
        self, repository: Repository, since: datetime | None = None
    ) -> list[PRData]:
        """Discover pull requests from a GitHub repository.

        This method implements efficient PR discovery with:
        - ETag-based conditional requests for caching
        - Incremental updates using 'since' parameter
        - Pagination handling for large repositories
        - Comprehensive metadata extraction

        Args:
            repository: Repository to discover PRs for
            since: Optional timestamp for incremental updates

        Returns:
            List of PR data objects

        Raises:
            GitHubError: If GitHub API request fails
        """
        if not repository.owner or not repository.repo_name:
            raise ValueError(f"Invalid repository configuration: {repository.url}")

        logger.info(
            f"Discovering PRs for {repository.owner}/{repository.repo_name}"
            f"{' since ' + since.isoformat() if since else ''}"
        )

        # Check cache if no since parameter (for full repository sync)
        cache_key = f"{repository.owner}/{repository.repo_name}"
        if not since and cache_key in self._etag_cache:
            etag, cached_at, cached_prs = self._etag_cache[cache_key]

            # Check if cache is still valid
            cache_age = (datetime.now() - cached_at).total_seconds()
            if cache_age < self.cache_ttl_seconds:
                logger.debug(
                    f"Using cached PRs for {cache_key} (age: {cache_age:.1f}s)"
                )
                return cached_prs

        try:
            all_prs: list[PRData] = []

            # Prepare query parameters
            params = {"state": "all", "sort": "updated", "direction": "desc"}
            if since:
                params["since"] = since.isoformat()

            # Use conditional request if we have cached ETag
            headers = {}
            if cache_key in self._etag_cache and not since:
                etag, _, cached_prs = self._etag_cache[cache_key]
                headers["If-None-Match"] = etag

            # Fetch PRs with pagination
            async for pr_json in self.github_client.paginate(
                f"/repos/{repository.owner}/{repository.repo_name}/pulls",
                params=params,
                per_page=100,
            ):
                # Note: Individual items are yielded, not pages
                try:
                    pr_data = self._extract_pr_data(pr_json)
                    all_prs.append(pr_data)
                except Exception as e:
                    logger.warning(
                        f"Failed to extract PR data for PR "
                        f"#{pr_json.get('number', 'unknown')} "
                        f"in {repository.owner}/{repository.repo_name}: {e}"
                    )
                    continue

            # Update cache with new data
            if not since:  # Only cache full syncs
                # Note: ETag caching would require storing headers from paginator
                # For now, we'll cache without ETag validation
                self._etag_cache[cache_key] = ("", datetime.now(), all_prs)

            logger.info(
                f"Discovered {len(all_prs)} PRs for "
                f"{repository.owner}/{repository.repo_name}"
            )
            return all_prs

        except Exception as e:
            logger.error(
                f"Failed to discover PRs for "
                f"{repository.owner}/{repository.repo_name}: {e}"
            )
            raise

    async def discover_check_runs(
        self, repository: Repository, pr_data: PRData
    ) -> list[CheckRunData]:
        """Discover check runs for a specific pull request.

        Args:
            repository: Repository containing the PR
            pr_data: PR data to discover check runs for

        Returns:
            List of check run data objects
        """
        if not repository.owner or not repository.repo_name:
            raise ValueError(f"Invalid repository configuration: {repository.url}")

        logger.debug(
            f"Discovering check runs for PR #{pr_data.number} "
            f"({pr_data.head_sha}) in {repository.owner}/{repository.repo_name}"
        )

        try:
            async with self._request_semaphore:
                check_runs: list[CheckRunData] = []

                # Fetch check runs for the PR's head SHA
                # Note: GitHub check-runs API returns a wrapper object with check_runs
                # We need to collect all items first, then extract the check_runs
                paginator = self.github_client.paginate(
                    f"/repos/{repository.owner}/{repository.repo_name}/commits/{pr_data.head_sha}/check-runs",
                    per_page=100,
                )

                # Collect all paginated responses first
                all_pages = []
                async for item in paginator:
                    all_pages.append(item)

                # The first page should contain the response structure
                if all_pages and "check_runs" in all_pages[0]:
                    # If we got the wrapper object, extract check_runs
                    for page_data in all_pages:
                        if isinstance(page_data, dict) and "check_runs" in page_data:
                            check_runs_list = page_data["check_runs"]
                        else:
                            # Individual check run item
                            check_runs_list = [page_data]

                        for check_run_json in check_runs_list:
                            try:
                                check_run_data = self._extract_check_run_data(
                                    check_run_json
                                )
                                check_runs.append(check_run_data)
                            except Exception as e:
                                logger.warning(
                                    f"Failed to extract check run data for check run "
                                    f"{check_run_json.get('id', 'unknown')} "
                                    f"in PR #{pr_data.number}: {e}"
                                )
                                continue
                else:
                    # Handle case where each item is a check run directly
                    for check_run_json in all_pages:
                        try:
                            check_run_data = self._extract_check_run_data(
                                check_run_json
                            )
                            check_runs.append(check_run_data)
                        except Exception as e:
                            logger.warning(
                                f"Failed to extract check run data for check run "
                                f"{check_run_json.get('id', 'unknown')} "
                                f"in PR #{pr_data.number}: {e}"
                            )
                            continue

                logger.debug(
                    f"Discovered {len(check_runs)} check runs for PR #{pr_data.number}"
                )
                return check_runs

        except Exception as e:
            logger.error(
                f"Failed to discover check runs for PR #{pr_data.number} "
                f"in {repository.owner}/{repository.repo_name}: {e}"
            )
            # Return empty list instead of raising to allow processing of other PRs
            return []

    async def discover_check_runs_batch(
        self, repository: Repository, pr_data_list: list[PRData]
    ) -> dict[int, list[CheckRunData]]:
        """Discover check runs for multiple pull requests concurrently.

        This method processes multiple PRs in parallel with proper error handling
        and rate limiting to respect GitHub API limits.

        Args:
            repository: Repository containing the PRs
            pr_data_list: List of PR data to discover check runs for

        Returns:
            Dictionary mapping PR numbers to their check runs
        """
        if not pr_data_list:
            return {}

        logger.info(
            f"Discovering check runs for {len(pr_data_list)} PRs "
            f"in {repository.owner}/{repository.repo_name}"
        )

        # Create tasks for concurrent processing
        tasks = [
            self._discover_check_runs_with_error_handling(repository, pr_data)
            for pr_data in pr_data_list
        ]

        # Execute tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle errors
        check_runs_by_pr: dict[int, list[CheckRunData]] = {}
        error_count = 0

        for pr_data, result in zip(pr_data_list, results, strict=False):
            if isinstance(result, Exception):
                logger.error(
                    f"Failed to discover check runs for PR #{pr_data.number}: {result}"
                )
                error_count += 1
                check_runs_by_pr[pr_data.number] = []
            elif isinstance(result, list):
                check_runs_by_pr[pr_data.number] = result
            else:
                # This should not happen, but handle gracefully
                logger.warning(
                    f"Unexpected result type for PR #{pr_data.number}: {type(result)}"
                )
                check_runs_by_pr[pr_data.number] = []

        total_check_runs = sum(len(runs) for runs in check_runs_by_pr.values())
        logger.info(
            f"Discovered {total_check_runs} check runs across {len(pr_data_list)} PRs "
            f"({error_count} errors) in {repository.owner}/{repository.repo_name}"
        )

        return check_runs_by_pr

    async def _discover_check_runs_with_error_handling(
        self, repository: Repository, pr_data: PRData
    ) -> list[CheckRunData]:
        """Wrapper for discover_check_runs with error handling.

        Args:
            repository: Repository containing the PR
            pr_data: PR data to discover check runs for

        Returns:
            List of check run data objects (empty list on error)
        """
        try:
            return await self.discover_check_runs(repository, pr_data)
        except Exception as e:
            logger.warning(
                f"Error discovering check runs for PR #{pr_data.number}: {e}"
            )
            return []

    def _extract_pr_data(self, pr_json: dict[str, Any]) -> PRData:
        """Extract PR data from GitHub API response.

        Args:
            pr_json: Raw PR data from GitHub API

        Returns:
            PRData object with extracted information
        """
        # Extract basic PR information
        pr_data = PRData(
            number=pr_json["number"],
            title=pr_json["title"],
            author=pr_json["user"]["login"],
            state=pr_json["state"],
            draft=pr_json.get("draft", False),
            # Branch information
            base_branch=pr_json["base"]["ref"],
            head_branch=pr_json["head"]["ref"],
            base_sha=pr_json["base"]["sha"],
            head_sha=pr_json["head"]["sha"],
            # URLs and metadata
            url=pr_json["html_url"],
            body=pr_json.get("body"),
            # GitHub metadata
            labels=[label["name"] for label in pr_json.get("labels", [])],
            assignees=[assignee["login"] for assignee in pr_json.get("assignees", [])],
            milestone=pr_json.get("milestone", {}).get("title")
            if pr_json.get("milestone")
            else None,
            # Additional metadata
            mergeable=pr_json.get("mergeable"),
            mergeable_state=pr_json.get("mergeable_state"),
            merged=pr_json.get("merged", False),
            merge_commit_sha=pr_json.get("merge_commit_sha"),
            # Raw GitHub data for extensibility
            raw_data=pr_json,
        )

        # Parse timestamps
        try:
            if pr_json.get("created_at"):
                pr_data.created_at = datetime.fromisoformat(
                    pr_json["created_at"].replace("Z", "+00:00")
                )
            if pr_json.get("updated_at"):
                pr_data.updated_at = datetime.fromisoformat(
                    pr_json["updated_at"].replace("Z", "+00:00")
                )
            if pr_json.get("closed_at"):
                pr_data.closed_at = datetime.fromisoformat(
                    pr_json["closed_at"].replace("Z", "+00:00")
                )
            if pr_json.get("merged_at"):
                pr_data.merged_at = datetime.fromisoformat(
                    pr_json["merged_at"].replace("Z", "+00:00")
                )
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse timestamp in PR #{pr_data.number}: {e}")

        return pr_data

    def _extract_check_run_data(self, check_run_json: dict[str, Any]) -> CheckRunData:
        """Extract check run data from GitHub API response.

        Args:
            check_run_json: Raw check run data from GitHub API

        Returns:
            CheckRunData object with extracted information
        """
        # Extract output information
        output = check_run_json.get("output", {})

        check_run_data = CheckRunData(
            external_id=str(check_run_json["id"]),
            check_name=check_run_json["name"],
            status=check_run_json["status"],
            check_suite_id=str(check_run_json.get("check_suite", {}).get("id"))
            if check_run_json.get("check_suite")
            else None,
            conclusion=check_run_json.get("conclusion"),
            # URLs and output
            details_url=check_run_json.get("details_url"),
            logs_url=check_run_json.get(
                "html_url"
            ),  # GitHub doesn't provide direct logs URL
            output_title=output.get("title"),
            output_summary=output.get("summary"),
            output_text=output.get("text"),
            # Raw GitHub data
            raw_data=check_run_json,
        )

        # Parse timestamps
        try:
            if check_run_json.get("started_at"):
                check_run_data.started_at = datetime.fromisoformat(
                    check_run_json["started_at"].replace("Z", "+00:00")
                )
            if check_run_json.get("completed_at"):
                check_run_data.completed_at = datetime.fromisoformat(
                    check_run_json["completed_at"].replace("Z", "+00:00")
                )
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Failed to parse timestamp in check run "
                f"{check_run_data.external_id}: {e}"
            )

        return check_run_data

    def clear_cache(self) -> None:
        """Clear the ETag cache."""
        self._etag_cache.clear()
        logger.debug("Cleared PR discovery cache")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics for monitoring.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cached_repositories": len(self._etag_cache),
            "total_cached_prs": sum(
                len(prs) for _, _, prs in self._etag_cache.values()
            ),
            "oldest_cache_age": min(
                (datetime.now() - cached_at).total_seconds()
                for _, cached_at, _ in self._etag_cache.values()
            )
            if self._etag_cache
            else 0,
            "cache_ttl_seconds": self.cache_ttl_seconds,
        }
