"""
Integration tests for GitHub API client.

Why: Verify that the GitHub client works correctly with real GitHub API
     endpoints and handles authentication, rate limiting, and pagination
     in realistic scenarios.

What: Tests the complete GitHub client integration including authentication,
      real API calls (when token available), pagination, and error handling.

How: Uses real GitHub API calls when GITHUB_TOKEN is available, otherwise
     skips tests. Tests against public repositories to avoid auth issues.
"""

import os
from typing import Optional

import pytest

from src.github import (
    GitHubClient,
    GitHubClientConfig,
    PersonalAccessTokenAuth,
)

# Skip integration tests if no GitHub token available
pytestmark = pytest.mark.skipif(
    not os.getenv("GITHUB_TOKEN"), reason="GITHUB_TOKEN environment variable not set"
)


@pytest.fixture
def github_token() -> str | None:
    """Get GitHub token from environment."""
    return os.getenv("GITHUB_TOKEN")


@pytest.fixture
def github_client(github_token) -> GitHubClient:
    """Create GitHub client with real authentication."""
    if not github_token:
        pytest.skip("No GitHub token available")

    auth = PersonalAccessTokenAuth(github_token)
    config = GitHubClientConfig(
        timeout=30,
        max_retries=2,
        rate_limit_buffer=50,
    )
    return GitHubClient(auth=auth, config=config)


class TestGitHubIntegration:
    """Integration tests for GitHub client."""

    @pytest.mark.asyncio
    async def test_get_authenticated_user(self, github_client):
        """Test getting authenticated user information."""
        async with github_client:
            user = await github_client.get_user()

        assert "login" in user
        assert "id" in user
        assert isinstance(user["id"], int)

    @pytest.mark.asyncio
    async def test_get_public_repository(self, github_client):
        """Test getting public repository information."""
        async with github_client:
            repo = await github_client.get_repo("octocat", "Hello-World")

        assert repo["name"] == "Hello-World"
        assert repo["full_name"] == "octocat/Hello-World"
        assert repo["private"] is False

    @pytest.mark.asyncio
    async def test_list_repository_pulls(self, github_client):
        """Test listing pull requests for a repository."""
        async with github_client:
            # Use a repository known to have PRs
            paginator = github_client.list_pulls(
                "microsoft", "vscode", state="all", per_page=10
            )

            pulls = await paginator.collect_pages(1)  # Just get first page

        assert len(pulls) <= 10  # Should not exceed per_page limit
        if pulls:  # If there are any PRs
            assert "number" in pulls[0]
            assert "title" in pulls[0]
            assert "state" in pulls[0]

    @pytest.mark.asyncio
    async def test_pagination_functionality(self, github_client):
        """Test pagination with multiple pages."""
        async with github_client:
            # Get repositories for a user with many repos
            paginator = github_client.paginate(
                "/users/octocat/repos",
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
    async def test_rate_limit_tracking(self, github_client):
        """Test that rate limit information is tracked."""
        async with github_client:
            # Make a request to populate rate limit info
            await github_client.get_user()

            rate_limit = github_client.rate_limiter.get_rate_limit("core")

        assert rate_limit is not None
        assert rate_limit.limit > 0
        assert rate_limit.remaining >= 0
        assert rate_limit.reset > 0

    @pytest.mark.asyncio
    async def test_get_rate_limit_endpoint(self, github_client):
        """Test the rate limit endpoint."""
        async with github_client:
            rate_limit_info = await github_client.get_rate_limit()

        assert "resources" in rate_limit_info
        assert "core" in rate_limit_info["resources"]

        core_limits = rate_limit_info["resources"]["core"]
        assert "limit" in core_limits
        assert "remaining" in core_limits
        assert "reset" in core_limits

    @pytest.mark.asyncio
    async def test_error_handling_not_found(self, github_client):
        """Test error handling for 404 responses."""
        from src.github.exceptions import GitHubNotFoundError

        async with github_client:
            with pytest.raises(GitHubNotFoundError):
                await github_client.get_repo("nonexistent-user", "nonexistent-repo")

    @pytest.mark.asyncio
    async def test_check_runs_endpoint(self, github_client):
        """Test getting check runs for a commit."""
        async with github_client:
            # Use a known repository and commit with check runs
            paginator = github_client.list_check_runs(
                "microsoft", "vscode", "main", per_page=5
            )

            # Collect first page only
            check_runs = await paginator.collect_pages(1)

        # May or may not have check runs, but should not error
        assert isinstance(check_runs, list)
        if check_runs:
            assert "id" in check_runs[0]
            assert "name" in check_runs[0]

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, github_client):
        """Test concurrent requests work correctly."""
        import asyncio

        async def fetch_user():
            async with github_client:
                return await github_client.get_user()

        async def fetch_rate_limit():
            async with github_client:
                return await github_client.get_rate_limit()

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
    async def test_authentication_validation(self, github_client):
        """Test that authentication is working."""
        async with github_client:
            # Get user info - this requires authentication
            user = await github_client.get_user()

        # Should have authentication-specific fields
        assert "login" in user
        assert user["login"] is not None

        # Private information should be available with proper auth
        assert "private_gists" in user or "total_private_repos" in user

    @pytest.mark.asyncio
    async def test_large_response_handling(self, github_client):
        """Test handling of large responses."""
        async with github_client:
            # Get a large response (list of all repos for a prolific user)
            paginator = github_client.paginate(
                "/users/torvalds/repos",
                params={"type": "all"},
                per_page=100,
                max_pages=1,  # Limit to prevent too many API calls
            )

            repos = await paginator.collect_all()

        # Should handle the response without issues
        assert isinstance(repos, list)
        # Linus Torvalds likely has repositories
        assert len(repos) > 0

    @pytest.mark.asyncio
    async def test_client_session_reuse(self, github_client):
        """Test that HTTP session is reused across requests."""
        async with github_client:
            # Make first request
            await github_client.get_user()
            first_session = github_client._session

            # Make second request
            await github_client.get_rate_limit()
            second_session = github_client._session

            # Should be the same session
            assert first_session is second_session
            assert not first_session.closed

    @pytest.mark.asyncio
    async def test_custom_headers(self, github_client):
        """Test requests with custom headers."""
        async with github_client:
            # Test with custom Accept header
            user = await github_client.get(
                "/user", headers={"Accept": "application/vnd.github.v3+json"}
            )

        assert "login" in user

    @pytest.mark.asyncio
    async def test_url_construction(self, github_client):
        """Test that URLs are constructed correctly."""
        async with github_client:
            # Test with path that has leading slash
            user1 = await github_client.get("/user")

            # Test with path without leading slash
            user2 = await github_client.get("user")

            # Both should work and return the same data
            assert user1["login"] == user2["login"]


@pytest.mark.skipif(
    os.getenv("GITHUB_TOKEN") is None,
    reason="GitHub token required for performance tests",
)
class TestGitHubPerformance:
    """Performance tests for GitHub client."""

    @pytest.mark.asyncio
    async def test_request_timing(self, github_client):
        """Test that requests complete within reasonable time."""
        import time

        async with github_client:
            start_time = time.time()
            await github_client.get_user()
            end_time = time.time()

            request_time = end_time - start_time

        # Should complete within 5 seconds under normal conditions
        assert request_time < 5.0

    @pytest.mark.asyncio
    async def test_pagination_performance(self, github_client):
        """Test pagination performance with multiple pages."""
        import time

        async with github_client:
            start_time = time.time()

            paginator = github_client.paginate(
                "/users/microsoft/repos",
                per_page=50,
                max_pages=3,
            )

            repos = await paginator.collect_all()
            end_time = time.time()

            processing_time = end_time - start_time

        # Should complete within reasonable time
        assert processing_time < 10.0
        # Should have fetched some repositories
        assert len(repos) > 0
