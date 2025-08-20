"""
Integration tests for GitHub API client using Mock Server.

Why: Test the complete GitHub client integration without requiring real GitHub tokens,
     making tests faster, more reliable, and runnable in any environment.

What: Tests the complete GitHub client integration using a mock GitHub API server
      that serves realistic responses based on real GitHub API data.

How: Uses a mock HTTP server that mimics GitHub API endpoints with real response
     data collected from the actual GitHub API.
"""

import asyncio
import time
from typing import Optional
from unittest.mock import patch

import pytest
import requests

from src.github import (
    GitHubClient,
    GitHubClientConfig,
    PersonalAccessTokenAuth,
)


@pytest.fixture(scope="session")
def mock_github_server_url() -> str:
    """
    Why: Provide configurable mock server URL for different environments
         (local development vs CI/CD) without hardcoding addresses.
    What: Returns the URL of the mock GitHub server.
    How: Uses environment variable with localhost fallback.
    """
    # Default to localhost for local testing
    # In CI/CD, this might be set to a service name
    import os

    return os.getenv("MOCK_GITHUB_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def ensure_mock_server_running(mock_github_server_url: str) -> str:
    """
    Why: Ensure mock server availability before running tests to prevent
         test failures due to infrastructure issues.
    What: Verifies the mock GitHub server is running and accessible.
    How: Attempts connection with retries, skips tests if server unavailable.
    """

    # Wait for the mock server to be available
    max_retries = 30
    retry_count = 0

    while retry_count < max_retries:
        try:
            response = requests.get(f"{mock_github_server_url}/", timeout=2)
            if response.status_code == 200:
                print(f"✅ Mock GitHub server is ready at {mock_github_server_url}")
                return mock_github_server_url
        except requests.RequestException:
            pass

        retry_count += 1
        time.sleep(1)

    # If we can't connect, skip the tests
    pytest.skip(f"Mock GitHub server is not running at {mock_github_server_url}")


@pytest.fixture
def mock_github_client(
    mock_github_server_url: str, ensure_mock_server_running: str
) -> GitHubClient:
    """
    Why: Create properly configured GitHub client for mock server testing
         with realistic settings that don't require real authentication.
    What: Creates GitHub client configured to use the mock server.
    How: Configures client with mock server URL and test-appropriate settings.
    """

    # Create a fake token (not used by mock server but required by client)
    auth = PersonalAccessTokenAuth("mock_token_for_testing")

    config = GitHubClientConfig(
        timeout=30,
        max_retries=2,
        rate_limit_buffer=50,
        base_url=mock_github_server_url,  # Point to mock server
    )

    return GitHubClient(auth=auth, config=config)


class TestGitHubIntegrationMock:
    """Integration tests for GitHub client using mock server."""

    @pytest.mark.asyncio
    async def test_get_authenticated_user_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Verify mock server returns realistic user data matching GitHub API format
             and client properly handles authenticated user requests.
        What: Tests getting authenticated user information from mock server.
        How: Makes authenticated user API call and validates response structure.
        """
        async with mock_github_client:
            user = await mock_github_client.get_user()

        # Validate required GitHub user fields
        assert "login" in user, "User response must contain login field"
        assert "id" in user, "User response must contain id field"
        assert isinstance(user["id"], int), "User ID must be an integer"
        assert isinstance(user["login"], str), "User login must be a string"
        assert user["login"] != "", "User login must not be empty"

    @pytest.mark.asyncio
    async def test_get_public_repository_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Ensure mock server returns accurate repository data matching GitHub API
             response format for integration testing without external dependencies.
        What: Tests retrieving public repository information from mock server.
        How: Requests specific repository and validates response fields match values.
        """
        async with mock_github_client:
            repo = await mock_github_client.get_repo("octocat", "Hello-World")

        # Validate repository structure and expected values
        assert repo["name"] == "Hello-World", (
            "Repository name must match requested name"
        )
        assert repo["full_name"] == "octocat/Hello-World", (
            "Full name must match owner/name format"
        )
        assert repo["private"] is False, "Hello-World is a public repository"
        assert "id" in repo, "Repository must have an ID field"
        assert "owner" in repo, "Repository must have owner information"
        assert repo["owner"]["login"] == "octocat", (
            "Owner login must match expected value"
        )

    @pytest.mark.asyncio
    async def test_list_repository_pulls_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Verify pagination works correctly with mock server and returns properly
             formatted pull request data for integration testing.
        What: Tests listing pull requests from mock server with pagination.
        How: Requests first page of PRs and validates response structure and limits.
        """
        async with mock_github_client:
            # Use a repository that has mocked pull requests
            paginator = mock_github_client.list_pulls(
                "microsoft", "vscode", state="all", per_page=10
            )

            paginator_instance = await paginator
            pulls = await paginator_instance.collect_pages(1)  # Just get first page

        # Validate pagination constraints
        assert len(pulls) <= 10, (
            f"Should not exceed per_page limit of 10, got {len(pulls)}"
        )
        assert isinstance(pulls, list), "Pulls response must be a list"

        # The mock server should return realistic pull request data
        if pulls:  # If there are any PRs
            first_pr = pulls[0]
            assert "number" in first_pr, "PR must have number field"
            assert "title" in first_pr, "PR must have title field"
            assert "state" in first_pr, "PR must have state field"
            assert isinstance(first_pr["number"], int), "PR number must be integer"
            assert isinstance(first_pr["title"], str), "PR title must be string"
            assert first_pr["state"] in ["open", "closed"], "PR state must be valid"

    @pytest.mark.asyncio
    async def test_pagination_functionality_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Ensure pagination logic works correctly with mock server to validate
             client's ability to handle paginated responses without external API calls.
        What: Tests pagination functionality with mock server using async iteration.
        How: Requests multiple pages with limits and validates pagination behavior.
        """
        async with mock_github_client:
            # Get repositories for a user with many repos (mock will generate them)
            paginator = mock_github_client.paginate(
                "/users/torvalds/repos",
                params={"type": "all", "sort": "created"},
                per_page=5,
                max_pages=2,
            )

            repos = []
            page_count = 0
            async for repo in paginator:
                repos.append(repo)
                if len(repos) % 5 == 0:  # Every 5 items = 1 page
                    page_count += 1
                    if page_count >= 2:
                        break

        # Should have fetched at most 2 pages worth of data
        assert len(repos) <= 10, (
            f"Expected max 10 repos (2 pages x 5 per page), got {len(repos)}"
        )
        assert len(repos) > 0, "Mock server should return at least some repository data"

        # Validate repository structure if data exists
        if repos:
            first_repo = repos[0]
            assert "name" in first_repo, "Repository must have name field"
            assert "full_name" in first_repo, "Repository must have full_name field"
            assert isinstance(first_repo["name"], str), "Repository name must be string"

    @pytest.mark.asyncio
    async def test_rate_limit_tracking_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Verify client properly extracts and tracks rate limit information
             from mock server headers to ensure rate limiting works in tests.
        What: Tests rate limit tracking functionality with mock server responses.
        How: Makes API request and validates rate limit information is properly parsed.
        """
        async with mock_github_client:
            # Make a request to populate rate limit info
            await mock_github_client.get_user()

            rate_limit = mock_github_client.rate_limiter.get_rate_limit("core")

        # Validate rate limit information structure
        assert rate_limit is not None, (
            "Rate limit information should be available after API request"
        )
        assert rate_limit.limit > 0, (
            f"Rate limit should be positive, got {rate_limit.limit}"
        )
        assert rate_limit.remaining >= 0, (
            f"Remaining requests should be non-negative, got {rate_limit.remaining}"
        )
        assert rate_limit.reset > 0, (
            f"Reset timestamp should be positive, got {rate_limit.reset}"
        )
        assert rate_limit.remaining <= rate_limit.limit, (
            "Remaining should not exceed limit"
        )

    @pytest.mark.asyncio
    async def test_get_rate_limit_endpoint_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Validate that mock server provides complete rate limit information
             matching GitHub API format for comprehensive testing.
        What: Tests the dedicated rate limit endpoint on mock server.
        How: Calls rate limit endpoint and validates complete response structure.
        """
        async with mock_github_client:
            rate_limit_info = await mock_github_client.get_rate_limit()

        # Validate top-level structure
        assert "resources" in rate_limit_info, (
            "Rate limit response must contain resources field"
        )
        assert "core" in rate_limit_info["resources"], (
            "Resources must contain core rate limits"
        )

        # Validate core rate limit fields
        core_limits = rate_limit_info["resources"]["core"]
        assert "limit" in core_limits, "Core limits must contain limit field"
        assert "remaining" in core_limits, "Core limits must contain remaining field"
        assert "reset" in core_limits, "Core limits must contain reset field"

        # Validate field types and values
        assert isinstance(core_limits["limit"], int), "Limit must be an integer"
        assert isinstance(core_limits["remaining"], int), "Remaining must be an integer"
        assert isinstance(core_limits["reset"], int), (
            "Reset must be an integer timestamp"
        )
        assert core_limits["limit"] > 0, "Rate limit should be positive"
        assert core_limits["remaining"] >= 0, "Remaining should be non-negative"

    @pytest.mark.asyncio
    async def test_error_handling_not_found_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Ensure client properly handles 404 errors from mock server to validate
             error handling logic without depending on external API failures.
        What: Tests error handling for 404 responses from mock server.
        How: Requests non-existent repository and validates proper exception is raised.
        """
        from src.github.exceptions import GitHubNotFoundError

        async with mock_github_client:
            with pytest.raises(GitHubNotFoundError) as exc_info:
                await mock_github_client.get_repo(
                    "nonexistent-user", "nonexistent-repo"
                )

            # Validate exception details
            assert "nonexistent-user" in str(exc_info.value), (
                "Exception should mention the user"
            )
            assert "nonexistent-repo" in str(exc_info.value), (
                "Exception should mention the repo"
            )

    @pytest.mark.asyncio
    async def test_check_runs_endpoint_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Verify mock server provides realistic check run data for testing
             CI/CD integration features without external dependencies.
        What: Tests getting check runs from mock server with pagination.
        How: Requests check runs for known repository and validates response structure.
        """
        async with mock_github_client:
            # Use a known repository and commit with check runs
            paginator = mock_github_client.list_check_runs(
                "microsoft", "vscode", "main", per_page=5
            )

            # Collect first page only
            paginator_instance = await paginator
            check_runs = await paginator_instance.collect_pages(1)

        # Mock server should return realistic check runs data
        assert isinstance(check_runs, list), "Check runs response must be a list"
        assert len(check_runs) <= 5, (
            f"Should not exceed per_page limit of 5, got {len(check_runs)}"
        )

        # The specific response depends on the mock data
        if check_runs:
            first_check = check_runs[0]
            assert "id" in first_check, "Check run must have id field"
            assert "name" in first_check, "Check run must have name field"
            assert isinstance(first_check["id"], int), "Check run ID must be integer"
            assert isinstance(first_check["name"], str), "Check run name must be string"
            assert first_check["name"] != "", "Check run name must not be empty"

    @pytest.mark.asyncio
    async def test_concurrent_requests_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Ensure client handles concurrent requests properly with mock server
             to validate thread safety and async behavior.
        What: Tests concurrent requests work correctly with mock server.
        How: Runs multiple API calls concurrently and validates all succeed.
        """

        async def fetch_user() -> dict:
            async with mock_github_client:
                return await mock_github_client.get_user()

        async def fetch_rate_limit() -> dict:
            async with mock_github_client:
                return await mock_github_client.get_rate_limit()

        # Run concurrent requests
        results = await asyncio.gather(
            fetch_user(), fetch_rate_limit(), return_exceptions=True
        )

        # Both should succeed
        assert len(results) == 2, f"Expected 2 results, got {len(results)}"
        assert not isinstance(results[0], Exception), (
            f"First request failed: {results[0]}"
        )
        assert not isinstance(results[1], Exception), (
            f"Second request failed: {results[1]}"
        )

        # Type narrow the results after exception checks
        user_data = results[0]
        rate_limit_data = results[1]
        assert isinstance(user_data, dict), "User data must be a dict"
        assert isinstance(rate_limit_data, dict), "Rate limit data must be a dict"

        # Validate user data
        assert "login" in user_data, "User data must contain login field"
        assert isinstance(user_data["login"], str), "User login must be string"

        # Validate rate limit data
        assert "resources" in rate_limit_data, (
            "Rate limit data must contain resources field"
        )

    @pytest.mark.asyncio
    async def test_authentication_validation_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Verify that authentication flow works properly with mock server
             to ensure auth headers are handled correctly.
        What: Tests authentication validation with mock server.
        How: Makes authenticated request and validates user-specific data is returned.
        """
        async with mock_github_client:
            # Get user info - mock server should return realistic user data
            user = await mock_github_client.get_user()

        # Should have authentication-specific fields (mock server provides these)
        assert "login" in user, "Authenticated user must have login field"
        assert user["login"] is not None, "User login must not be None"
        assert isinstance(user["login"], str), "User login must be string"
        assert user["login"] != "", "User login must not be empty string"
        assert "id" in user, "Authenticated user must have id field"
        assert isinstance(user["id"], int), "User id must be integer"

    @pytest.mark.asyncio
    async def test_large_response_handling_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Ensure client can handle large paginated responses from mock server
             to validate memory usage and performance with realistic data volumes.
        What: Tests handling of large responses from mock server.
        How: Requests large dataset and validates proper processing without errors.
        """
        async with mock_github_client:
            # Get a large response (list of all repos for a prolific user)
            paginator = mock_github_client.paginate(
                "/users/torvalds/repos",
                params={"type": "all"},
                per_page=100,
                max_pages=1,  # Limit to prevent too many API calls
            )

            repos = await paginator.collect_all()

        # Should handle the response without issues
        assert isinstance(repos, list), "Repositories response must be a list"
        assert len(repos) <= 100, (
            f"Should not exceed per_page limit of 100, got {len(repos)}"
        )
        # Mock server generates repositories, so there should be some
        assert len(repos) > 0, "Mock server should return at least some repository data"

        # Validate repository structure if data exists
        if repos:
            first_repo = repos[0]
            assert isinstance(first_repo, dict), "Repository must be a dictionary"
            assert "name" in first_repo, "Repository must have name field"

    @pytest.mark.asyncio
    async def test_client_session_reuse_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Verify HTTP session reuse for efficiency and connection pooling
             to ensure optimal performance in integration scenarios.
        What: Tests that HTTP session is reused across requests.
        How: Makes multiple requests and validates same session object is used.
        """
        async with mock_github_client:
            # Make first request
            await mock_github_client.get_user()
            first_session = mock_github_client._session

            # Make second request
            await mock_github_client.get_rate_limit()
            second_session = mock_github_client._session

            # Should be the same session
            assert first_session is second_session, (
                "Client should reuse HTTP session across requests"
            )
            assert first_session is not None, "Session should not be None"
            assert not first_session.closed, (
                "HTTP session should remain open during client usage"
            )

    @pytest.mark.asyncio
    async def test_custom_headers_mock(self, mock_github_client: GitHubClient) -> None:
        """
        Why: Ensure custom headers are properly sent to mock server and don't
             interfere with request processing or response parsing.
        What: Tests requests with custom headers to mock server.
        How: Makes request with specific Accept header and validates response.
        """
        async with mock_github_client:
            # Test with custom Accept header
            user = await mock_github_client.get(
                "/user", headers={"Accept": "application/vnd.github.v3+json"}
            )

        assert "login" in user, "User response must contain login field"
        assert isinstance(user["login"], str), "User login must be string"
        assert "id" in user, "User response must contain id field"

    @pytest.mark.asyncio
    async def test_url_construction_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Verify client handles different URL path formats consistently
             to ensure robust URL construction logic.
        What: Tests that URLs are constructed correctly with mock server.
        How: Makes requests with different path formats and validates consistency.
        """
        async with mock_github_client:
            # Test with path that has leading slash
            user1 = await mock_github_client.get("/user")

            # Test with path without leading slash
            user2 = await mock_github_client.get("user")

            # Both should work and return the same data
            assert "login" in user1, "First request must return user with login"
            assert "login" in user2, "Second request must return user with login"
            assert user1["login"] == user2["login"], (
                "Both URL formats should return same user data"
            )
            assert user1["id"] == user2["id"], (
                "Both URL formats should return same user ID"
            )

    @pytest.mark.asyncio
    async def test_dynamic_repository_generation_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Verify mock server can generate realistic responses for arbitrary
             repositories to support comprehensive testing scenarios.
        What: Tests that mock server can generate dynamic repository responses.
        How: Requests non-fixed repository and validates generated response structure.
        """
        async with mock_github_client:
            # Request a repository that doesn't have a fixed response
            repo = await mock_github_client.get_repo("test-user", "test-repo")

        # Should get a dynamically generated repository response
        assert repo["name"] == "test-repo", (
            "Generated repo name must match requested name"
        )
        assert repo["full_name"] == "test-user/test-repo", (
            "Generated full name must match owner/name format"
        )
        assert "owner" in repo, "Generated repo must have owner field"
        assert repo["owner"]["login"] == "test-user", (
            "Generated owner login must match requested user"
        )
        assert "id" in repo, "Generated repo must have id field"
        assert isinstance(repo["id"], int), "Generated repo id must be integer"
        assert "private" in repo, "Generated repo must have private field"
        assert isinstance(repo["private"], bool), (
            "Generated repo private field must be boolean"
        )

    @pytest.mark.asyncio
    async def test_mock_server_headers(self, mock_github_client: GitHubClient) -> None:
        """
        Why: Ensure mock server provides realistic HTTP headers that match GitHub API
             format for proper rate limiting and client behavior validation.
        What: Tests that mock server returns realistic GitHub API headers.
        How: Makes request and validates headers are properly parsed by rate limiter.
        """
        async with mock_github_client:
            # Make a request and check that we get GitHub-like headers
            await mock_github_client.get_user()

        # The mock server should add realistic headers that our rate limiter can parse
        rate_limit = mock_github_client.rate_limiter.get_rate_limit("core")

        # Headers should be parsed correctly from the mock server
        assert rate_limit is not None, (
            "Rate limiter should extract rate limit info from headers"
        )
        assert rate_limit.limit > 0, (
            f"Rate limit should be positive, got {rate_limit.limit}"
        )
        assert rate_limit.remaining >= 0, (
            f"Rate limit remaining should be non-negative, got {rate_limit.remaining}"
        )
        assert rate_limit.reset > 0, (
            f"Rate limit reset should be positive timestamp, got {rate_limit.reset}"
        )


class TestMockServerPerformance:
    """Performance tests using the mock server."""

    @pytest.mark.asyncio
    async def test_request_timing_mock(self, mock_github_client: GitHubClient) -> None:
        """
        Why: Validate that mock server provides fast response times for efficient
             test execution compared to real GitHub API calls.
        What: Tests that requests complete quickly with mock server.
        How: Measures request timing and validates performance threshold.
        """

        async with mock_github_client:
            start_time = time.perf_counter()  # More precise timing
            await mock_github_client.get_user()
            end_time = time.perf_counter()

            request_time = end_time - start_time

        # Mock server should be much faster than real GitHub API
        assert request_time < 2.0, (
            f"Request should complete under 2 seconds, took {request_time:.3f}s"
        )
        # Also validate it's reasonably fast for a mock server
        assert request_time < 0.5, (
            f"Mock server should be very fast, took {request_time:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_pagination_performance_mock(
        self, mock_github_client: GitHubClient
    ) -> None:
        """
        Why: Ensure pagination operations complete efficiently with mock server
             to validate performance characteristics of paginated requests.
        What: Tests pagination performance with mock server.
        How: Measures time for multi-page request and validates performance thresholds.
        """

        async with mock_github_client:
            start_time = time.perf_counter()  # More precise timing

            paginator = mock_github_client.paginate(
                "/users/torvalds/repos",
                per_page=50,
                max_pages=3,
            )

            repos = await paginator.collect_all()
            end_time = time.perf_counter()

            processing_time = end_time - start_time

        # Should complete very quickly with mock server
        assert processing_time < 5.0, (
            f"Pagination should complete under 5 seconds, took {processing_time:.3f}s"
        )
        # More aggressive threshold for mock server
        assert processing_time < 2.0, (
            f"Mock server pagination should be very fast, took {processing_time:.3f}s"
        )
        # Should have fetched some repositories
        assert len(repos) > 0, "Should have fetched at least some repository data"
        assert len(repos) <= 150, (
            f"Should not exceed 3 pages x 50 per page = 150, got {len(repos)}"
        )


# Helper functions for test utilities


def wait_for_mock_server(url: str, timeout: int = 30) -> bool:
    """
    Why: Provide reusable utility for waiting on mock server availability
         with configurable timeout to support different testing scenarios.
    What: Waits for the mock server to become available.
    How: Polls server endpoint with retries until available or timeout.
    """

    start_time = time.perf_counter()  # More precise timing
    while time.perf_counter() - start_time < timeout:
        try:
            response = requests.get(f"{url}/", timeout=2)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)

    return False


def start_mock_server_subprocess(port: int = 8080) -> None:
    """
    Why: Provide utility function for starting mock server in subprocess
         for programmatic test setup scenarios.
    What: Starts the mock server in a subprocess for testing.
    How: Uses subprocess to launch mock server with specified configuration.
    """
    import subprocess
    import sys
    from pathlib import Path

    mock_server_path = (
        Path(__file__).parent.parent.parent / "fixtures" / "github" / "mock_server.py"
    )
    subprocess.Popen(
        [
            sys.executable,
            str(mock_server_path),
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
        ]
    )
