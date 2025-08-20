"""GitHub API client with authentication, rate limiting, and pagination."""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import aiohttp

from .auth import AuthProvider
from .exceptions import (
    GitHubAuthenticationError,
    GitHubConnectionError,
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServerError,
    GitHubTimeoutError,
    GitHubValidationError,
)
from .pagination import AsyncPaginator, PaginatedResponse
from .rate_limiting import CircuitBreaker, RateLimitManager

logger = logging.getLogger(__name__)


@dataclass
class GitHubClientConfig:
    """Configuration for GitHub client."""

    base_url: str = "https://api.github.com"
    timeout: int = 30
    max_retries: int = 3
    retry_backoff_factor: float = 2.0
    rate_limit_buffer: int = 100
    user_agent: str = "PR-Monitor-Worker/1.0"
    max_concurrent_requests: int = 10


class GitHubClient:
    """Async GitHub API client with comprehensive features."""

    def __init__(
        self,
        auth: AuthProvider,
        config: GitHubClientConfig | None = None,
    ) -> None:
        """Initialize GitHub client.

        Args:
            auth: Authentication provider
            config: Client configuration
        """
        self.auth = auth
        self.config = config or GitHubClientConfig()
        self.rate_limiter = RateLimitManager(buffer=self.config.rate_limit_buffer)
        self.circuit_breaker = CircuitBreaker()

        # HTTP session will be initialized on first use
        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()
        self._request_semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)

    async def __aenter__(self) -> "GitHubClient":
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self) -> None:
        """Ensure HTTP session is initialized."""
        if self._session is None or self._session.closed:
            async with self._session_lock:
                if self._session is None or self._session.closed:
                    timeout = aiohttp.ClientTimeout(total=self.config.timeout)
                    connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)

                    self._session = aiohttp.ClientSession(
                        timeout=timeout,
                        connector=connector,
                        headers={
                            "User-Agent": self.config.user_agent,
                            "Accept": "application/vnd.github.v3+json",
                        },
                    )

    async def close(self) -> None:
        """Close HTTP session and cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _generate_correlation_id(self) -> str:
        """Generate correlation ID for request tracking."""
        return str(uuid.uuid4())[:8]

    async def _make_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        correlation_id: str | None = None,
    ) -> aiohttp.ClientResponse:
        """Make HTTP request with retry logic and error handling.

        Args:
            method: HTTP method
            url: Request URL
            params: Query parameters
            data: Request body data
            headers: Additional headers
            correlation_id: Request correlation ID

        Returns:
            HTTP response

        Raises:
            GitHubError: Various GitHub API errors
        """
        if not correlation_id:
            correlation_id = self._generate_correlation_id()

        # Check circuit breaker
        if not self.circuit_breaker.can_attempt_request():
            wait_time = self.circuit_breaker.get_wait_time()
            raise GitHubConnectionError(
                f"Circuit breaker open. Wait {wait_time:.1f}s before retry."
            )

        # Check rate limits
        await self.rate_limiter.check_rate_limit()

        # Prepare headers
        request_headers = headers or {}
        auth_token = await self.auth.get_token()
        request_headers.update(auth_token.to_header())

        # Ensure session is ready
        await self._ensure_session()

        if not self._session:
            raise GitHubConnectionError("Failed to initialize HTTP session")

        # Prepare request data
        request_kwargs: dict[str, Any] = {
            "params": params,
            "headers": request_headers,
        }

        if data is not None:
            request_kwargs["json"] = data

        # Retry logic
        last_exception: GitHubError | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with self._request_semaphore:
                    start_time = time.time()

                    logger.debug(
                        f"GitHub API request [{correlation_id}] {method} {url} "
                        f"(attempt {attempt + 1})"
                    )

                    async with self._session.request(
                        method, url, **request_kwargs
                    ) as response:
                        request_time = time.time() - start_time

                        # Update rate limit info
                        self.rate_limiter.update_rate_limit(dict(response.headers))

                        logger.debug(
                            f"GitHub API response [{correlation_id}] "
                            f"{response.status} in {request_time:.2f}s"
                        )

                        # Handle response
                        if response.status in (200, 201, 204):
                            self.circuit_breaker.record_success()
                            return response
                        else:
                            # Handle error responses
                            await self._handle_error_response(response, correlation_id)

            except TimeoutError:
                last_exception = GitHubTimeoutError(
                    f"Request timeout for {method} {url}"
                )
                self.circuit_breaker.record_failure()

            except aiohttp.ClientError as e:
                last_exception = GitHubConnectionError(
                    f"Connection error for {method} {url}: {e}"
                )
                self.circuit_breaker.record_failure()

            except Exception as e:
                last_exception = GitHubError(f"Unexpected error: {e}")
                self.circuit_breaker.record_failure()

            # Calculate backoff time
            if attempt < self.config.max_retries:
                backoff_time = self.config.retry_backoff_factor**attempt
                logger.warning(
                    f"Request [{correlation_id}] failed (attempt {attempt + 1}), "
                    f"retrying in {backoff_time:.1f}s: {last_exception}"
                )
                await asyncio.sleep(backoff_time)

        # All retries exhausted
        if last_exception:
            raise last_exception
        else:
            raise GitHubError(f"Request failed after {self.config.max_retries} retries")

    async def _handle_error_response(
        self, response: aiohttp.ClientResponse, correlation_id: str
    ) -> None:
        """Handle error responses from GitHub API.

        Args:
            response: HTTP response
            correlation_id: Request correlation ID

        Raises:
            GitHubError: Appropriate error based on status code
        """
        try:
            error_data = await response.json()
        except (json.JSONDecodeError, aiohttp.ContentTypeError):
            error_data = {"message": await response.text()}

        error_message = error_data.get("message", f"HTTP {response.status}")

        logger.warning(
            f"GitHub API error [{correlation_id}] {response.status}: {error_message}"
        )

        if response.status == 401:
            raise GitHubAuthenticationError(error_message, response.status, error_data)
        elif response.status == 403:
            # Check if it's a rate limit error
            if "rate limit" in error_message.lower():
                reset_time = response.headers.get("X-RateLimit-Reset")
                remaining = response.headers.get("X-RateLimit-Remaining", "0")
                limit = response.headers.get("X-RateLimit-Limit", "0")

                raise GitHubRateLimitError(
                    error_message,
                    reset_time=int(reset_time) if reset_time else None,
                    remaining=int(remaining),
                    limit=int(limit),
                )
            else:
                raise GitHubAuthenticationError(
                    error_message, response.status, error_data
                )
        elif response.status == 404:
            raise GitHubNotFoundError(error_message, response.status, error_data)
        elif response.status == 422:
            raise GitHubValidationError(error_message, response.status, error_data)
        elif 500 <= response.status < 600:
            self.circuit_breaker.record_failure()
            raise GitHubServerError(error_message, response.status, error_data)
        else:
            raise GitHubError(error_message, response.status, error_data)

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make GET request to GitHub API.

        Args:
            path: API path (e.g., '/repos/owner/repo/pulls')
            params: Query parameters
            headers: Additional headers

        Returns:
            JSON response data
        """
        url = urljoin(self.config.base_url, path.lstrip("/"))

        response = await self._make_request("GET", url, params, headers=headers)
        async with response:
            json_data: dict[str, Any] = await response.json()
            return json_data

    async def post(
        self,
        path: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make POST request to GitHub API.

        Args:
            path: API path
            data: Request body data
            params: Query parameters
            headers: Additional headers

        Returns:
            JSON response data
        """
        url = urljoin(self.config.base_url, path.lstrip("/"))

        response = await self._make_request("POST", url, params, data, headers)
        async with response:
            json_data: dict[str, Any] = await response.json()
            return json_data

    async def put(
        self,
        path: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make PUT request to GitHub API.

        Args:
            path: API path
            data: Request body data
            params: Query parameters
            headers: Additional headers

        Returns:
            JSON response data
        """
        url = urljoin(self.config.base_url, path.lstrip("/"))

        response = await self._make_request("PUT", url, params, data, headers)
        async with response:
            json_data: dict[str, Any] = await response.json()
            return json_data

    async def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Make DELETE request to GitHub API.

        Args:
            path: API path
            params: Query parameters
            headers: Additional headers

        Returns:
            JSON response data if any
        """
        url = urljoin(self.config.base_url, path.lstrip("/"))

        response = await self._make_request("DELETE", url, params, headers=headers)
        async with response:
            if response.status == 204:
                return None
            json_data: dict[str, Any] = await response.json()
            return json_data

    async def _fetch_paginated(
        self, url: str, params: dict[str, Any] | None = None
    ) -> PaginatedResponse:
        """Fetch paginated response (used by AsyncPaginator).

        Args:
            url: URL to fetch
            params: Query parameters

        Returns:
            PaginatedResponse with data and headers
        """
        response = await self._make_request("GET", url, params)
        async with response:
            data = await response.json()
            return PaginatedResponse(data, dict(response.headers), url)

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        per_page: int = 100,
        max_pages: int | None = None,
    ) -> AsyncPaginator:
        """Create async paginator for GitHub API endpoint.

        Args:
            path: API path
            params: Query parameters
            per_page: Items per page (max 100)
            max_pages: Maximum pages to fetch

        Returns:
            AsyncPaginator for iterating through results
        """
        url = urljoin(self.config.base_url, path.lstrip("/"))
        return AsyncPaginator(
            client=self,
            initial_url=url,
            params=params,
            per_page=per_page,
            max_pages=max_pages,
        )

    # Convenience methods for common GitHub API endpoints

    async def get_user(self) -> dict[str, Any]:
        """Get authenticated user information."""
        return await self.get("/user")

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Get repository information.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository data
        """
        return await self.get(f"/repos/{owner}/{repo}")

    async def list_pulls(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 100,
    ) -> AsyncPaginator:
        """List pull requests for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            state: PR state (open, closed, all)
            per_page: Items per page

        Returns:
            AsyncPaginator for pull requests
        """
        return self.paginate(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state},
            per_page=per_page,
        )

    async def get_pull(self, owner: str, repo: str, pull_number: int) -> dict[str, Any]:
        """Get specific pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: Pull request number

        Returns:
            Pull request data
        """
        return await self.get(f"/repos/{owner}/{repo}/pulls/{pull_number}")

    async def list_check_runs(
        self,
        owner: str,
        repo: str,
        ref: str,
        per_page: int = 100,
    ) -> AsyncPaginator:
        """List check runs for a commit.

        Args:
            owner: Repository owner
            repo: Repository name
            ref: Git reference (commit SHA, branch, tag)
            per_page: Items per page

        Returns:
            AsyncPaginator for check runs
        """
        return self.paginate(
            f"/repos/{owner}/{repo}/commits/{ref}/check-runs",
            per_page=per_page,
        )

    async def get_rate_limit(self) -> dict[str, Any]:
        """Get current rate limit status."""
        return await self.get("/rate_limit")
