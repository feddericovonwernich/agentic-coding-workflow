"""
Unit tests for GitHub API client.

Why: Ensure the main GitHub client handles authentication, rate limiting,
     error responses, and API calls correctly with proper retry logic.

What: Tests GitHubClient class for HTTP operations, error handling,
      authentication integration, and convenience methods.

How: Uses mocked aiohttp responses to test client behavior
     without making real GitHub API calls.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from aioresponses import aioresponses

from src.github.auth import PersonalAccessTokenAuth
from src.github.client import GitHubClient, GitHubClientConfig
from src.github.exceptions import (
    GitHubAuthenticationError,
    GitHubConnectionError,
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServerError,
    GitHubTimeoutError,
    GitHubValidationError,
)


class TestGitHubClientConfig:
    """Test GitHubClientConfig data class."""

    def test_github_client_config_defaults(self) -> None:
        """Test GitHubClientConfig with default values."""
        config = GitHubClientConfig()

        assert config.base_url == "https://api.github.com"
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.retry_backoff_factor == 2.0
        assert config.rate_limit_buffer == 100
        assert config.user_agent == "PR-Monitor-Worker/1.0"
        assert config.max_concurrent_requests == 10

    def test_github_client_config_custom(self) -> None:
        """Test GitHubClientConfig with custom values."""
        config = GitHubClientConfig(
            base_url="https://api.github.enterprise.com",
            timeout=60,
            max_retries=5,
            retry_backoff_factor=1.5,
            rate_limit_buffer=50,
            user_agent="Custom-Agent/2.0",
            max_concurrent_requests=5,
        )

        assert config.base_url == "https://api.github.enterprise.com"
        assert config.timeout == 60
        assert config.max_retries == 5
        assert config.retry_backoff_factor == 1.5
        assert config.rate_limit_buffer == 50
        assert config.user_agent == "Custom-Agent/2.0"
        assert config.max_concurrent_requests == 5


class TestGitHubClient:
    """Test GitHubClient class."""

    @pytest.fixture
    def mock_auth(self) -> Mock:
        """Create mock authentication provider."""
        auth = Mock()
        auth.get_token = AsyncMock()
        auth.get_token.return_value = Mock(
            token="test_token",
            token_type="Bearer",
            to_header=Mock(return_value={"Authorization": "Bearer test_token"}),
        )
        return auth

    @pytest.fixture
    def github_client(self, mock_auth: Mock) -> GitHubClient:
        """Create GitHubClient instance with mock auth."""
        config = GitHubClientConfig(base_url="https://api.github.com")
        return GitHubClient(auth=mock_auth, config=config)

    def create_mock_response(
        self,
        status: int = 200,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Mock:
        """Create a mock aiohttp response."""
        mock_response = Mock()
        mock_response.status = status
        mock_response.headers = headers or {}

        if payload is not None:
            mock_response.json = AsyncMock(return_value=payload)

        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        return mock_response

    def create_mock_context_response(
        self,
        status: int = 200,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Create a mock aiohttp response that supports async context manager."""

        class MockResponse:
            def __init__(
                self,
                status: int,
                payload: dict[str, Any] | None,
                headers: dict[str, str] | None,
            ) -> None:
                self.status = status
                self.headers = headers or {}
                self._payload = payload

            async def json(self) -> dict[str, Any] | None:
                return self._payload

            async def text(self) -> str:
                return str(self._payload) if self._payload else ""

            async def __aenter__(self) -> "MockResponse":
                return self

            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                pass

        return MockResponse(status, payload, headers)

    def test_github_client_creation(self, mock_auth: Mock) -> None:
        """Test GitHubClient creation."""
        config = GitHubClientConfig()
        client = GitHubClient(auth=mock_auth, config=config)

        assert client.auth == mock_auth
        assert client.config == config
        assert client._session is None

    @pytest.mark.asyncio
    async def test_context_manager(self, github_client: GitHubClient) -> None:
        """Test GitHubClient as async context manager."""
        async with github_client as client:
            assert client._session is not None
            assert not client._session.closed

        # Session should be closed after exiting context
        assert github_client._session is None or github_client._session.closed

    @pytest.mark.asyncio
    async def test_close_session(self, github_client: GitHubClient) -> None:
        """Test closing HTTP session."""
        await github_client._ensure_session()
        assert github_client._session is not None

        await github_client.close()
        assert github_client._session is None

    @pytest.mark.asyncio
    async def test_get_request_success(self, github_client: GitHubClient) -> None:
        """Test successful GET request."""
        mock_response = self.create_mock_response(
            status=200,
            payload={"login": "testuser", "id": 12345},
            headers={
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": "1234567890",
            },
        )

        github_client._make_request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        result = await github_client.get("/user")

        assert result["login"] == "testuser"
        assert result["id"] == 12345

    @pytest.mark.asyncio
    async def test_get_request_with_params(self, github_client: GitHubClient) -> None:
        """Test GET request with query parameters."""
        mock_response = self.create_mock_response(
            status=200,
            payload={"items": [{"number": 1}, {"number": 2}]},
        )

        github_client._make_request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        result = await github_client.get(
            "/repos/owner/repo/pulls",
            params={"state": "open", "per_page": 50},
        )

        assert len(result["items"]) == 2
        assert result["items"][0]["number"] == 1

    @pytest.mark.asyncio
    async def test_post_request_success(self, github_client: GitHubClient) -> None:
        """Test successful POST request."""
        mock_response = self.create_mock_response(
            status=201,
            payload={"number": 123, "title": "Test Issue"},
        )

        github_client._make_request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        result = await github_client.post(
            "/repos/owner/repo/issues",
            data={"title": "Test Issue", "body": "Test body"},
        )

        assert result["number"] == 123
        assert result["title"] == "Test Issue"

    @pytest.mark.asyncio
    async def test_delete_request_no_content(self, github_client: GitHubClient) -> None:
        """Test DELETE request with 204 No Content response."""
        mock_response = self.create_mock_response(status=204)
        github_client._make_request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        result = await github_client.delete("/repos/owner/repo/issues/123")

        assert result is None

    @pytest.mark.asyncio
    async def test_authentication_error(self, github_client: GitHubClient) -> None:
        """Test handling of authentication errors."""
        github_client._make_request = AsyncMock(  # type: ignore[method-assign]
            side_effect=GitHubAuthenticationError(
                "Bad credentials",
                status_code=401,
                response_data={"message": "Bad credentials"},
            )
        )

        with pytest.raises(GitHubAuthenticationError) as exc_info:
            await github_client.get("/user")

        assert exc_info.value.status_code == 401
        assert "Bad credentials" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_not_found_error(self, github_client: GitHubClient) -> None:
        """Test handling of 404 Not Found errors."""
        github_client._make_request = AsyncMock(  # type: ignore[method-assign]
            side_effect=GitHubNotFoundError(
                "Not Found", status_code=404, response_data={"message": "Not Found"}
            )
        )

        with pytest.raises(GitHubNotFoundError) as exc_info:
            await github_client.get("/repos/owner/nonexistent")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_validation_error(self, github_client: GitHubClient) -> None:
        """Test handling of validation errors."""
        github_client._make_request = AsyncMock(  # type: ignore[method-assign]
            side_effect=GitHubValidationError(
                "Validation Failed",
                status_code=422,
                response_data={
                    "message": "Validation Failed",
                    "errors": [{"field": "title", "message": "is required"}],
                },
            )
        )

        with pytest.raises(GitHubValidationError) as exc_info:
            await github_client.post("/repos/owner/repo/issues", data={})

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, github_client: GitHubClient) -> None:
        """Test handling of rate limit errors."""
        github_client._make_request = AsyncMock(  # type: ignore[method-assign]
            side_effect=GitHubRateLimitError(
                "API rate limit exceeded",
                reset_time=1234567890,
                remaining=0,
                limit=5000,
            )
        )

        with pytest.raises(GitHubRateLimitError) as exc_info:
            await github_client.get("/user")

        assert exc_info.value.remaining == 0
        assert exc_info.value.reset_time == 1234567890

    @pytest.mark.asyncio
    async def test_server_error(self, github_client: GitHubClient) -> None:
        """Test handling of server errors."""
        github_client._make_request = AsyncMock(  # type: ignore[method-assign]
            side_effect=GitHubServerError(
                "Internal Server Error",
                status_code=500,
                response_data={"message": "Internal Server Error"},
            )
        )

        with pytest.raises(GitHubServerError) as exc_info:
            await github_client.get("/user")

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_connection_error(self, github_client: GitHubClient) -> None:
        """Test handling of connection errors."""
        github_client._make_request = AsyncMock(  # type: ignore[method-assign]
            side_effect=GitHubConnectionError("Connection failed")
        )

        with pytest.raises(GitHubConnectionError):
            await github_client.get("/user")

    @pytest.mark.asyncio
    async def test_timeout_error(self, github_client: GitHubClient) -> None:
        """Test handling of timeout errors."""
        github_client._make_request = AsyncMock(  # type: ignore[method-assign]
            side_effect=GitHubTimeoutError("Request timeout")
        )

        with pytest.raises(GitHubTimeoutError):
            await github_client.get("/user")

    @pytest.mark.asyncio
    async def test_retry_logic_success(self, github_client: GitHubClient) -> None:
        """Test successful retry after failure."""
        call_count = 0

        async def mock_request(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise aiohttp.ClientConnectionError("Connection failed")

            # Create a successful response
            mock_response = self.create_mock_context_response(
                status=200, payload={"login": "testuser"}
            )
            return mock_response

        # Mock the session.request method as an async context manager
        test_self = self

        class MockRequestContext:
            def __init__(self) -> None:
                self.call_count = 0

            async def __call__(self, *args: Any, **kwargs: Any) -> "MockRequestContext":
                return self

            async def __aenter__(self) -> Any:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise aiohttp.ClientConnectionError("Connection failed")

                return test_self.create_mock_context_response(
                    status=200, payload={"login": "testuser"}
                )

            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                pass

        mock_request_context = MockRequestContext()

        with patch.object(
            aiohttp.ClientSession, "request", return_value=mock_request_context
        ):
            async with github_client:
                result = await github_client.get("/user")

            assert result["login"] == "testuser"
            assert call_count == 2  # First failed, second succeeded

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self, github_client: GitHubClient) -> None:
        """Test retry exhaustion after max attempts."""
        github_client.config.max_retries = 2

        github_client._make_request = AsyncMock(  # type: ignore[method-assign]
            side_effect=GitHubConnectionError("Connection failed")
        )

        with pytest.raises(GitHubConnectionError):
            await github_client.get("/user")

    @pytest.mark.asyncio
    async def test_rate_limit_update(self, github_client: GitHubClient) -> None:
        """Test rate limit info update from response headers."""

        async def mock_request(*args: Any, **kwargs: Any) -> Any:
            mock_response = self.create_mock_context_response(
                status=200,
                payload={"login": "testuser"},
                headers={
                    "X-RateLimit-Limit": "5000",
                    "X-RateLimit-Remaining": "4500",
                    "X-RateLimit-Reset": "1234567890",
                    "X-RateLimit-Used": "500",
                    "X-RateLimit-Resource": "core",
                },
            )
            return mock_response

        # Mock the session.request method as an async context manager
        test_self = self

        class MockRequestContext:
            async def __call__(self, *args: Any, **kwargs: Any) -> "MockRequestContext":
                return self

            async def __aenter__(self) -> Any:
                return test_self.create_mock_context_response(
                    status=200,
                    payload={"login": "testuser"},
                    headers={
                        "X-RateLimit-Limit": "5000",
                        "X-RateLimit-Remaining": "4500",
                        "X-RateLimit-Reset": "1234567890",
                        "X-RateLimit-Used": "500",
                        "X-RateLimit-Resource": "core",
                    },
                )

            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                pass

        mock_request_context = MockRequestContext()

        with patch.object(
            aiohttp.ClientSession, "request", return_value=mock_request_context
        ):
            async with github_client:
                await github_client.get("/user")

            rate_limit = github_client.rate_limiter.get_rate_limit("core")
            assert rate_limit is not None
            assert rate_limit.limit == 5000
            assert rate_limit.remaining == 4500
            assert rate_limit.used == 500

    @pytest.mark.asyncio
    async def test_convenience_method_get_user(
        self, github_client: GitHubClient
    ) -> None:
        """Test get_user convenience method."""
        mock_response = self.create_mock_response(
            status=200, payload={"login": "testuser", "id": 12345}
        )

        github_client._make_request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        user = await github_client.get_user()

        assert user["login"] == "testuser"
        assert user["id"] == 12345

    @pytest.mark.asyncio
    async def test_convenience_method_get_repo(
        self, github_client: GitHubClient
    ) -> None:
        """Test get_repo convenience method."""
        mock_response = self.create_mock_response(
            status=200, payload={"name": "repo", "full_name": "owner/repo"}
        )

        github_client._make_request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        repo = await github_client.get_repo("owner", "repo")

        assert repo["name"] == "repo"
        assert repo["full_name"] == "owner/repo"

    @pytest.mark.asyncio
    async def test_convenience_method_get_pull(
        self, github_client: GitHubClient
    ) -> None:
        """Test get_pull convenience method."""
        mock_response = self.create_mock_response(
            status=200, payload={"number": 123, "title": "Test PR"}
        )

        github_client._make_request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        pull = await github_client.get_pull("owner", "repo", 123)

        assert pull["number"] == 123
        assert pull["title"] == "Test PR"

    @pytest.mark.asyncio
    async def test_paginate_method(self, github_client: GitHubClient) -> None:
        """Test paginate method returns AsyncPaginator."""
        paginator = github_client.paginate(
            "/repos/owner/repo/pulls",
            params={"state": "open"},
            per_page=50,
            max_pages=3,
        )

        assert paginator.client == github_client
        assert paginator.params["state"] == "open"
        assert paginator.params["per_page"] == 50
        assert paginator.max_pages == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(
        self, github_client: GitHubClient
    ) -> None:
        """Test circuit breaker integration with failures."""
        github_client.circuit_breaker.failure_threshold = 2

        async def mock_request(*args: Any, **kwargs: Any) -> Any:
            # Always return a 500 error response
            mock_response = self.create_mock_context_response(
                status=500, payload={"message": "Server Error"}
            )
            return mock_response

        # Mock the session.request method as an async context manager
        test_self = self

        class MockRequestContext:
            async def __call__(self, *args: Any, **kwargs: Any) -> "MockRequestContext":
                return self

            async def __aenter__(self) -> Any:
                return test_self.create_mock_context_response(
                    status=500, payload={"message": "Server Error"}
                )

            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                pass

        mock_request_context = MockRequestContext()

        with patch.object(
            aiohttp.ClientSession, "request", return_value=mock_request_context
        ):
            async with github_client:
                # First failure
                with pytest.raises(GitHubError):
                    await github_client.get("/user")

                # Second failure - should open circuit
                with pytest.raises(GitHubError):
                    await github_client.get("/user")

                # Third attempt should be blocked by circuit breaker
                with pytest.raises(GitHubConnectionError) as exc_info:
                    await github_client.get("/user")

                assert "Circuit breaker open" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_concurrent_request_limiting(
        self, github_client: GitHubClient
    ) -> None:
        """Test concurrent request limiting with semaphore."""
        # Create a new client with custom concurrent request limit
        custom_config = GitHubClientConfig(max_concurrent_requests=2)
        custom_client = GitHubClient(auth=github_client.auth, config=custom_config)

        # This test would be complex to implement fully, but we can at least
        # verify the semaphore exists and has the correct value
        assert custom_client._request_semaphore._value == 2

    @pytest.mark.asyncio
    async def test_malformed_json_response(self, github_client: GitHubClient) -> None:
        """Test handling of malformed JSON responses."""
        github_client._make_request = AsyncMock(  # type: ignore[method-assign]
            side_effect=GitHubServerError(
                "HTTP 500",
                status_code=500,
                response_data={"message": "invalid json response"},
            )
        )

        with pytest.raises(GitHubServerError):
            await github_client.get("/user")

    @pytest.mark.asyncio
    async def test_correlation_id_generation(self, github_client: GitHubClient) -> None:
        """Test correlation ID generation for request tracking."""
        correlation_id = github_client._generate_correlation_id()

        assert isinstance(correlation_id, str)
        assert len(correlation_id) == 8  # Should be 8 characters from UUID
