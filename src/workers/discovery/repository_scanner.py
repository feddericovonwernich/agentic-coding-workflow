"""Repository scanner for GitHub PR discovery.

This module implements the PRDiscoveryStrategy interface to fetch PRs from GitHub
repositories with intelligent pagination, caching, and error recovery.
"""

import logging
import time
import uuid
from datetime import datetime
from urllib.parse import urlparse

from src.github.client import GitHubClient
from src.github.exceptions import (
    GitHubAuthenticationError,
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)
from src.repositories.repository import RepositoryRepository

from .interfaces import (
    CacheStrategy,
    DiscoveredPR,
    DiscoveryError,
    DiscoveryPriority,
    PRDiscoveryResult,
    PRDiscoveryStrategy,
)

logger = logging.getLogger(__name__)


class GitHubRepositoryScanner(PRDiscoveryStrategy):
    """GitHub API implementation of PR discovery strategy.

    Provides efficient PR discovery with caching, pagination, and error handling.
    Features:
    - ETag-based conditional requests
    - Intelligent pagination
    - Priority-based scheduling
    - Error recovery with exponential backoff
    """

    def __init__(
        self,
        github_client: GitHubClient,
        repository_repo: RepositoryRepository,
        cache: CacheStrategy,
        max_pages: int = 10,
        items_per_page: int = 100,
    ):
        """Initialize scanner with dependencies.

        Args:
            github_client: GitHub API client
            repository_repo: Repository repository for database access
            cache: Cache strategy implementation
            max_pages: Maximum pages to fetch per repository
            items_per_page: Items per page (max 100)
        """
        self.github_client = github_client
        self.repository_repo = repository_repo
        self.cache = cache
        self.max_pages = max_pages
        self.items_per_page = min(items_per_page, 100)  # GitHub API limit

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

    def _generate_cache_key(self, owner: str, repo: str, state: str = "all") -> str:
        """Generate cache key for PR list.

        Args:
            owner: Repository owner
            repo: Repository name
            state: PR state filter

        Returns:
            Cache key string
        """
        return f"prs:{owner}:{repo}:{state}"

    def _convert_github_pr_to_discovered(self, pr_data: dict) -> DiscoveredPR:
        """Convert GitHub API PR response to DiscoveredPR.

        Args:
            pr_data: GitHub API PR response data

        Returns:
            DiscoveredPR object
        """
        # Handle timestamps
        created_at = datetime.fromisoformat(
            pr_data["created_at"].replace("Z", "+00:00")
        )
        updated_at = datetime.fromisoformat(
            pr_data["updated_at"].replace("Z", "+00:00")
        )
        merged_at = None
        if pr_data.get("merged_at"):
            merged_at = datetime.fromisoformat(
                pr_data["merged_at"].replace("Z", "+00:00")
            )

        # Extract branch information
        base_branch = pr_data["base"]["ref"]
        head_branch = pr_data["head"]["ref"]
        base_sha = pr_data["base"]["sha"]
        head_sha = pr_data["head"]["sha"]

        # Build metadata
        metadata = {
            "github_id": pr_data["id"],
            "node_id": pr_data.get("node_id"),
            "assignees": [
                assignee["login"] for assignee in pr_data.get("assignees", [])
            ],
            "reviewers": [
                reviewer["login"] for reviewer in pr_data.get("requested_reviewers", [])
            ],
            "labels": [label["name"] for label in pr_data.get("labels", [])],
            "milestone": pr_data.get("milestone", {}).get("title")
            if pr_data.get("milestone")
            else None,
            "commits": pr_data.get("commits", 0),
            "additions": pr_data.get("additions", 0),
            "deletions": pr_data.get("deletions", 0),
            "changed_files": pr_data.get("changed_files", 0),
        }

        return DiscoveredPR(
            pr_number=pr_data["number"],
            title=pr_data["title"],
            author=pr_data["user"]["login"],
            state=pr_data["state"],
            draft=pr_data.get("draft", False),
            base_branch=base_branch,
            head_branch=head_branch,
            base_sha=base_sha,
            head_sha=head_sha,
            url=pr_data["html_url"],
            body=pr_data.get("body"),
            created_at=created_at,
            updated_at=updated_at,
            merged_at=merged_at,
            metadata=metadata,
            check_runs=[],  # Will be populated by CheckDiscoveryStrategy
        )

    async def discover_prs(
        self,
        repository_id: uuid.UUID,
        repository_url: str,
        since: datetime | None = None,
        max_prs: int | None = None,
    ) -> PRDiscoveryResult:
        """Discover PRs for a repository with caching and error handling.

        Args:
            repository_id: Database ID of the repository
            repository_url: GitHub URL of the repository
            since: Only discover PRs updated after this time
            max_prs: Maximum number of PRs to discover

        Returns:
            Discovery result with PRs and metadata
        """
        start_time = time.time()
        errors: list[DiscoveryError] = []
        discovered_prs: list[DiscoveredPR] = []
        api_calls_used = 0
        cache_hits = 0
        cache_misses = 0

        try:
            # Parse repository URL
            owner, repo = self._parse_repository_url(repository_url)

            # Generate cache key
            cache_key = self._generate_cache_key(owner, repo)

            # Try to get cached data with ETag
            cached_data, etag = await self.cache.get_with_etag(cache_key)

            # Prepare GitHub API parameters
            params = {
                "state": "all",  # Get all PRs for comprehensive discovery
                "sort": "updated",
                "direction": "desc",
                "per_page": self.items_per_page,
            }

            # Add since parameter if provided
            if since:
                params["since"] = since.isoformat()

            # Make GitHub API request with conditional headers
            headers = {}
            if etag:
                headers["If-None-Match"] = etag

            try:
                # Use paginator for efficient fetching
                paginator = self.github_client.paginate(
                    f"/repos/{owner}/{repo}/pulls",
                    params=params,
                    per_page=self.items_per_page,
                    max_pages=self.max_pages,
                )

                pr_count = 0
                async for pr_data in paginator:
                    # Note: paginator yields individual PR items, not pages
                    # Each iteration processes one PR (guaranteed to be dict[str, Any])

                    try:
                        discovered_pr = self._convert_github_pr_to_discovered(pr_data)

                        # Apply max_prs limit if specified
                        if max_prs and pr_count >= max_prs:
                            break

                        discovered_prs.append(discovered_pr)
                        pr_count += 1

                    except Exception as e:
                        # At this point, we know pr_data is a dict due to check
                        pr_number = pr_data.get("number", "unknown")

                        error = DiscoveryError(
                            error_type="pr_conversion_error",
                            message=(f"Failed to convert PR #{pr_number}: {e!s}"),
                            context={"pr_data": pr_data},
                            timestamp=datetime.utcnow(),
                            recoverable=True,
                        )
                        errors.append(error)
                        logger.warning(f"PR conversion error: {e}")

                    # Break if max_prs limit reached
                    if max_prs and pr_count >= max_prs:
                        break

                # Track API calls made by the paginator
                api_calls_used = getattr(paginator, "_current_page", 0)

                # Cache the results
                if discovered_prs:
                    cache_misses += 1
                    # Extract ETag from last response if available
                    new_etag = (
                        paginator.get_last_etag()
                        if hasattr(paginator, "get_last_etag")
                        else None
                    )
                    await self.cache.set_with_etag(
                        cache_key,
                        discovered_prs,
                        new_etag or f"scan-{int(time.time())}",
                        ttl=300,
                    )
                else:
                    cache_hits += 1 if cached_data else 0
                    cache_misses += 0 if cached_data else 1

                logger.info(
                    f"Discovered {len(discovered_prs)} PRs from {owner}/{repo} "
                    f"(API calls: {api_calls_used}, errors: {len(errors)})"
                )

            except GitHubNotFoundError:
                error = DiscoveryError(
                    error_type="repository_not_found",
                    message=f"Repository not found: {owner}/{repo}",
                    context={"repository_url": repository_url},
                    timestamp=datetime.utcnow(),
                    recoverable=False,
                )
                errors.append(error)

            except GitHubAuthenticationError as e:
                error = DiscoveryError(
                    error_type="authentication_error",
                    message=f"Authentication failed for {owner}/{repo}: {e!s}",
                    context={"repository_url": repository_url},
                    timestamp=datetime.utcnow(),
                    recoverable=False,
                )
                errors.append(error)

            except GitHubRateLimitError as e:
                error = DiscoveryError(
                    error_type="rate_limit_exceeded",
                    message=f"Rate limit exceeded for {owner}/{repo}: {e!s}",
                    context={
                        "repository_url": repository_url,
                        "reset_time": e.reset_time,
                        "remaining": e.remaining,
                    },
                    timestamp=datetime.utcnow(),
                    recoverable=True,
                )
                errors.append(error)

            except GitHubError as e:
                error = DiscoveryError(
                    error_type="github_api_error",
                    message=f"GitHub API error for {owner}/{repo}: {e!s}",
                    context={
                        "repository_url": repository_url,
                        "status_code": getattr(e, "status_code", None),
                    },
                    timestamp=datetime.utcnow(),
                    recoverable=True,
                )
                errors.append(error)

        except ValueError as e:
            error = DiscoveryError(
                error_type="invalid_repository_url",
                message=str(e),
                context={"repository_url": repository_url},
                timestamp=datetime.utcnow(),
                recoverable=False,
            )
            errors.append(error)

        except Exception as e:
            error = DiscoveryError(
                error_type="unexpected_error",
                message=f"Unexpected error during PR discovery: {e!s}",
                context={"repository_url": repository_url},
                timestamp=datetime.utcnow(),
                recoverable=True,
            )
            errors.append(error)
            logger.exception(
                f"Unexpected error during PR discovery for {repository_url}"
            )

        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000

        return PRDiscoveryResult(
            repository_id=repository_id,
            repository_url=repository_url,
            discovered_prs=discovered_prs,
            discovery_timestamp=datetime.utcnow(),
            api_calls_used=api_calls_used,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            processing_time_ms=processing_time_ms,
            errors=errors,
        )

    async def get_priority(self, repository_id: uuid.UUID) -> DiscoveryPriority:
        """Get discovery priority for a repository.

        Determines priority based on:
        - Recent activity (PRs, commits)
        - Failure history
        - Last discovery time
        - Manual priority overrides

        Args:
            repository_id: Database ID of the repository

        Returns:
            Priority level for discovery scheduling
        """
        try:
            repository = await self.repository_repo.get_by_id(repository_id)
            if not repository:
                return DiscoveryPriority.LOW

            # Check for manual priority override
            manual_priority = repository.get_config_value("discovery_priority")
            if manual_priority:
                try:
                    return DiscoveryPriority(int(manual_priority))
                except (ValueError, TypeError):
                    pass

            # Calculate priority based on various factors
            now = datetime.utcnow()

            # Factor 1: Recent failures (higher priority for fixing issues)
            if repository.failure_count > 3:
                return DiscoveryPriority.CRITICAL
            elif repository.failure_count > 1:
                return DiscoveryPriority.HIGH

            # Factor 2: Time since last poll
            if repository.last_polled_at:
                time_since_poll = now - repository.last_polled_at
                if time_since_poll.total_seconds() > 3600:  # > 1 hour
                    return DiscoveryPriority.HIGH
                elif time_since_poll.total_seconds() > 1800:  # > 30 minutes
                    return DiscoveryPriority.NORMAL
            else:
                # Never polled - high priority
                return DiscoveryPriority.HIGH

            # Factor 3: Repository activity level (could be enhanced with more metrics)
            polling_interval = repository.polling_interval_minutes
            if polling_interval <= 5:  # Very active repositories
                return DiscoveryPriority.HIGH
            elif polling_interval <= 15:
                return DiscoveryPriority.NORMAL

            return DiscoveryPriority.LOW

        except Exception as e:
            logger.warning(
                f"Error determining priority for repository {repository_id}: {e}"
            )
            return DiscoveryPriority.NORMAL

    async def get_repository_stats(self, repository_id: uuid.UUID) -> dict:
        """Get discovery statistics for a repository.

        Args:
            repository_id: Database ID of the repository

        Returns:
            Dictionary with repository statistics
        """
        try:
            repository = await self.repository_repo.get_by_id(repository_id)
            if not repository:
                return {}

            owner, repo = self._parse_repository_url(repository.url)
            cache_key = self._generate_cache_key(owner, repo)

            # Check cache status
            cached_data, etag = await self.cache.get_with_etag(cache_key)

            return {
                "repository_id": str(repository_id),
                "owner": owner,
                "repo": repo,
                "last_polled_at": repository.last_polled_at.isoformat()
                if repository.last_polled_at
                else None,
                "failure_count": repository.failure_count,
                "polling_interval_minutes": repository.polling_interval_minutes,
                "priority": (await self.get_priority(repository_id)).name,
                "cached_data_available": cached_data is not None,
                "cache_etag": etag,
            }

        except Exception as e:
            logger.warning(f"Error getting repository stats for {repository_id}: {e}")
            return {"error": str(e)}
