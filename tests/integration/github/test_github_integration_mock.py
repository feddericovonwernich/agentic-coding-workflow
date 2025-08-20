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
    """Get the URL of the mock GitHub server."""
    # Default to localhost for local testing
    # In CI/CD, this might be set to a service name
    import os

    return os.getenv("MOCK_GITHUB_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def ensure_mock_server_running(mock_github_server_url):
    """Ensure the mock GitHub server is running."""
    import time

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
    mock_github_server_url, ensure_mock_server_running
) -> GitHubClient:
    """Create GitHub client configured to use the mock server."""

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
    async def test_get_authenticated_user_mock(self, mock_github_client):
        """Test getting authenticated user information from mock server."""
        async with mock_github_client:
            user = await mock_github_client.get_user()

        assert "login" in user
        assert "id" in user
        assert isinstance(user["id"], int)

    @pytest.mark.asyncio
    async def test_get_public_repository_mock(self, mock_github_client):
        """Test getting public repository information from mock server."""
        async with mock_github_client:
            repo = await mock_github_client.get_repo("octocat", "Hello-World")

        assert repo["name"] == "Hello-World"
        assert repo["full_name"] == "octocat/Hello-World"
        assert repo["private"] is False

    @pytest.mark.asyncio
    async def test_list_repository_pulls_mock(self, mock_github_client):
        """Test listing pull requests from mock server."""
        async with mock_github_client:
            # Use a repository that has mocked pull requests
            paginator = mock_github_client.list_pulls(
                "microsoft", "vscode", state="all", per_page=10
            )

            pulls = await paginator.collect_pages(1)  # Just get first page

        assert len(pulls) <= 10  # Should not exceed per_page limit
        # The mock server should return realistic pull request data
        if pulls:  # If there are any PRs
            assert "number" in pulls[0]
            assert "title" in pulls[0]
            assert "state" in pulls[0]

    @pytest.mark.asyncio
    async def test_pagination_functionality_mock(self, mock_github_client):
        """Test pagination with mock server."""
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
        assert len(repos) <= 10

    @pytest.mark.asyncio
    async def test_rate_limit_tracking_mock(self, mock_github_client):
        """Test that rate limit information is tracked from mock server."""
        async with mock_github_client:
            # Make a request to populate rate limit info
            await mock_github_client.get_user()

            rate_limit = mock_github_client.rate_limiter.get_rate_limit("core")

        assert rate_limit is not None
        assert rate_limit.limit > 0
        assert rate_limit.remaining >= 0
        assert rate_limit.reset > 0

    @pytest.mark.asyncio
    async def test_get_rate_limit_endpoint_mock(self, mock_github_client):
        """Test the rate limit endpoint on mock server."""
        async with mock_github_client:
            rate_limit_info = await mock_github_client.get_rate_limit()

        assert "resources" in rate_limit_info
        assert "core" in rate_limit_info["resources"]

        core_limits = rate_limit_info["resources"]["core"]
        assert "limit" in core_limits
        assert "remaining" in core_limits
        assert "reset" in core_limits

    @pytest.mark.asyncio
    async def test_error_handling_not_found_mock(self, mock_github_client):
        """Test error handling for 404 responses from mock server."""
        from src.github.exceptions import GitHubNotFoundError

        async with mock_github_client:
            with pytest.raises(GitHubNotFoundError):
                await mock_github_client.get_repo(
                    "nonexistent-user", "nonexistent-repo"
                )

    @pytest.mark.asyncio
    async def test_check_runs_endpoint_mock(self, mock_github_client):
        """Test getting check runs from mock server."""
        async with mock_github_client:
            # Use a known repository and commit with check runs
            paginator = mock_github_client.list_check_runs(
                "microsoft", "vscode", "main", per_page=5
            )

            # Collect first page only
            check_runs = await paginator.collect_pages(1)

        # Mock server should return realistic check runs data
        assert isinstance(check_runs, list)
        # The specific response depends on the mock data
        if check_runs:
            assert "id" in check_runs[0]
            assert "name" in check_runs[0]

    @pytest.mark.asyncio
    async def test_concurrent_requests_mock(self, mock_github_client):
        """Test concurrent requests work correctly with mock server."""

        async def fetch_user():
            async with mock_github_client:
                return await mock_github_client.get_user()

        async def fetch_rate_limit():
            async with mock_github_client:
                return await mock_github_client.get_rate_limit()

        # Run concurrent requests
        results = await asyncio.gather(
            fetch_user(), fetch_rate_limit(), return_exceptions=True
        )

        # Both should succeed
        assert len(results) == 2
        assert not isinstance(results[0], Exception)
        assert not isinstance(results[1], Exception)

        user_data, rate_limit_data = results
        assert "login" in user_data
        assert "resources" in rate_limit_data

    @pytest.mark.asyncio
    async def test_authentication_validation_mock(self, mock_github_client):
        """Test that authentication works with mock server."""
        async with mock_github_client:
            # Get user info - mock server should return realistic user data
            user = await mock_github_client.get_user()

        # Should have authentication-specific fields (mock server provides these)
        assert "login" in user
        assert user["login"] is not None

    @pytest.mark.asyncio
    async def test_large_response_handling_mock(self, mock_github_client):
        """Test handling of large responses from mock server."""
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
        assert isinstance(repos, list)
        # Mock server generates repositories, so there should be some
        assert len(repos) > 0

    @pytest.mark.asyncio
    async def test_client_session_reuse_mock(self, mock_github_client):
        """Test that HTTP session is reused across requests."""
        async with mock_github_client:
            # Make first request
            await mock_github_client.get_user()
            first_session = mock_github_client._session

            # Make second request
            await mock_github_client.get_rate_limit()
            second_session = mock_github_client._session

            # Should be the same session
            assert first_session is second_session
            assert not first_session.closed

    @pytest.mark.asyncio
    async def test_custom_headers_mock(self, mock_github_client):
        """Test requests with custom headers to mock server."""
        async with mock_github_client:
            # Test with custom Accept header
            user = await mock_github_client.get(
                "/user", headers={"Accept": "application/vnd.github.v3+json"}
            )

        assert "login" in user

    @pytest.mark.asyncio
    async def test_url_construction_mock(self, mock_github_client):
        """Test that URLs are constructed correctly with mock server."""
        async with mock_github_client:
            # Test with path that has leading slash
            user1 = await mock_github_client.get("/user")

            # Test with path without leading slash
            user2 = await mock_github_client.get("user")

            # Both should work and return the same data
            assert user1["login"] == user2["login"]

    @pytest.mark.asyncio
    async def test_dynamic_repository_generation_mock(self, mock_github_client):
        """Test that mock server can generate dynamic repository responses."""
        async with mock_github_client:
            # Request a repository that doesn't have a fixed response
            repo = await mock_github_client.get_repo("test-user", "test-repo")

        # Should get a dynamically generated repository response
        assert repo["name"] == "test-repo"
        assert repo["full_name"] == "test-user/test-repo"
        assert repo["owner"]["login"] == "test-user"

    @pytest.mark.asyncio
    async def test_mock_server_headers(self, mock_github_client):
        """Test that mock server returns realistic GitHub API headers."""
        async with mock_github_client:
            # Make a request and check that we get GitHub-like headers
            await mock_github_client.get_user()

        # The mock server should add realistic headers that our rate limiter can parse
        rate_limit = mock_github_client.rate_limiter.get_rate_limit("core")

        # Headers should be parsed correctly from the mock server
        assert rate_limit is not None
        assert rate_limit.limit > 0


class TestMockServerPerformance:
    """Performance tests using the mock server."""

    @pytest.mark.asyncio
    async def test_request_timing_mock(self, mock_github_client):
        """Test that requests complete quickly with mock server."""
        import time

        async with mock_github_client:
            start_time = time.time()
            await mock_github_client.get_user()
            end_time = time.time()

            request_time = end_time - start_time

        # Mock server should be much faster than real GitHub API
        assert request_time < 2.0

    @pytest.mark.asyncio
    async def test_pagination_performance_mock(self, mock_github_client):
        """Test pagination performance with mock server."""
        import time

        async with mock_github_client:
            start_time = time.time()

            paginator = mock_github_client.paginate(
                "/users/torvalds/repos",
                per_page=50,
                max_pages=3,
            )

            repos = await paginator.collect_all()
            end_time = time.time()

            processing_time = end_time - start_time

        # Should complete very quickly with mock server
        assert processing_time < 5.0
        # Should have fetched some repositories
        assert len(repos) > 0


# Helper functions for test utilities


def start_mock_server_subprocess(port: int = 8080) -> None:
    """Start the mock server in a subprocess for testing."""
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


def wait_for_mock_server(url: str, timeout: int = 30) -> bool:
    """Wait for the mock server to become available."""
    import time

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{url}/", timeout=2)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)

    return False
