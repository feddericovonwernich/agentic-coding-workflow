"""
Unit tests for GitHub authentication module.

Why: Ensure authentication providers work correctly for different token types
     and handle token refresh, validation, and error scenarios properly.

What: Tests PersonalAccessTokenAuth, GitHubAppAuth, and TokenAuth classes
      for proper token management and authentication workflows.

How: Uses pytest fixtures and mocks to test authentication without real
     GitHub tokens, validates token formats and expiry logic.
"""

import time
from unittest.mock import Mock, patch

import pytest

from src.github.auth import (
    AuthToken,
    GitHubAppAuth,
    PersonalAccessTokenAuth,
    TokenAuth,
)
from src.github.exceptions import GitHubAuthenticationError


class TestAuthToken:
    """Test AuthToken data class."""

    def test_auth_token_creation(self) -> None:
        """
        Why: Ensure AuthToken data class initializes correctly with required fields
             for consistent token representation across authentication providers.
        What: Tests basic AuthToken creation.
        How: Creates token with explicit parameters and validates field assignment.
        """
        token = AuthToken(token="test_token", token_type="Bearer")
        assert token.token == "test_token"
        assert token.token_type == "Bearer"
        assert token.expires_at is None

    def test_auth_token_with_expiry(self) -> None:
        """
        Why: Verify AuthToken properly handles expiry times for tokens that expire
             (like JWT tokens) to enable automatic refresh logic.
        What: Tests AuthToken with expiry time.
        How: Creates token with future expiry and validates expiration logic.
        """
        future_time = int(time.time()) + 3600
        token = AuthToken(
            token="test_token", token_type="Bearer", expires_at=future_time
        )
        assert not token.is_expired
        assert token.expires_at == future_time

    def test_auth_token_expired(self) -> None:
        """
        Why: Ensure AuthToken correctly identifies expired tokens to trigger
             refresh or reauthentication before API calls.
        What: Tests expired AuthToken.
        How: Creates token with past expiry time and validates is_expired property.
        """
        past_time = int(time.time()) - 3600
        token = AuthToken(token="test_token", token_type="Bearer", expires_at=past_time)
        assert token.is_expired

    def test_auth_token_to_header(self) -> None:
        """
        Why: Verify AuthToken generates correct HTTP Authorization headers
             for different token types used by GitHub API.
        What: Tests conversion to authorization header.
        How: Creates token and validates header format matches HTTP standards.
        """
        token = AuthToken(token="test_token", token_type="Bearer")
        header = token.to_header()
        assert header == {"Authorization": "Bearer test_token"}

    def test_auth_token_default_type(self) -> None:
        """Test default token type."""
        token = AuthToken(token="test_token")
        assert token.token_type == "Bearer"


class TestPersonalAccessTokenAuth:
    """Test PersonalAccessTokenAuth provider."""

    def test_pat_auth_creation(self) -> None:
        """
        Why: Ensure Personal Access Token authentication initializes correctly
             with proper token format validation for GitHub API access.
        What: Tests PAT authentication creation.
        How: Creates PAT auth with token and validates token storage and type.
        """
        auth = PersonalAccessTokenAuth("ghp_test_token")
        assert auth._token.token == "ghp_test_token"
        assert auth._token.token_type == "token"

    def test_pat_auth_empty_token(self) -> None:
        """
        Why: Ensure PAT authentication rejects empty tokens to prevent
             invalid API requests and provide clear error messages.
        What: Tests PAT authentication with empty token.
        How: Attempts creation with empty token and validates exception is raised.
        """
        with pytest.raises(GitHubAuthenticationError):
            PersonalAccessTokenAuth("")

    async def test_pat_auth_get_token(self) -> None:
        """
        Why: Verify PAT authentication returns valid token objects
             for API request authentication.
        What: Tests getting PAT token.
        How: Creates PAT auth, calls get_token, and validates returned token.
        """
        auth = PersonalAccessTokenAuth("ghp_test_token")
        token = await auth.get_token()
        assert token.token == "ghp_test_token"
        assert token.token_type == "token"

    async def test_pat_auth_refresh_token(self) -> None:
        """Test PAT token refresh (should return same token)."""
        auth = PersonalAccessTokenAuth("ghp_test_token")
        original_token = await auth.get_token()
        refreshed_token = await auth.refresh_token()
        assert original_token.token == refreshed_token.token

    async def test_pat_auth_validate_token(self) -> None:
        """Test PAT token validation (always valid)."""
        auth = PersonalAccessTokenAuth("ghp_test_token")
        assert await auth.validate_token()


class TestGitHubAppAuth:
    """Test GitHubAppAuth provider."""

    def test_github_app_auth_creation(self) -> None:
        """
        Why: Ensure GitHub App authentication initializes with required parameters
             for JWT-based authentication with GitHub Apps.
        What: Tests GitHub App authentication creation.
        How: Creates auth with app credentials and validates parameter storage.
        """
        auth = GitHubAppAuth(
            app_id="12345",
            private_key="test_private_key",
            installation_id="67890",
        )
        assert auth.app_id == "12345"
        assert auth.private_key == "test_private_key"
        assert auth.installation_id == "67890"

    @patch("src.github.auth.jwt.encode")
    def test_generate_jwt(self, mock_jwt_encode: Mock) -> None:
        """Test JWT generation for GitHub App."""
        mock_jwt_encode.return_value = "test_jwt_token"

        auth = GitHubAppAuth(
            app_id="12345",
            private_key="test_private_key",
        )

        jwt_token = auth._generate_jwt()
        assert jwt_token == "test_jwt_token"

        # Verify JWT payload structure
        call_args = mock_jwt_encode.call_args
        payload = call_args[0][0]
        assert payload["iss"] == "12345"
        assert "iat" in payload
        assert "exp" in payload

    @patch("src.github.auth.jwt.encode")
    def test_generate_jwt_bytes_response(self, mock_jwt_encode: Mock) -> None:
        """Test JWT generation when jwt.encode returns bytes."""
        mock_jwt_encode.return_value = b"test_jwt_token"

        auth = GitHubAppAuth(
            app_id="12345",
            private_key="test_private_key",
        )

        jwt_token = auth._generate_jwt()
        assert jwt_token == "test_jwt_token"

    @patch("src.github.auth.jwt.encode")
    def test_generate_jwt_error(self, mock_jwt_encode: Mock) -> None:
        """Test JWT generation error handling."""
        mock_jwt_encode.side_effect = Exception("JWT encoding failed")

        auth = GitHubAppAuth(
            app_id="12345",
            private_key="test_private_key",
        )

        with pytest.raises(GitHubAuthenticationError):
            auth._generate_jwt()

    @patch("src.github.auth.GitHubAppAuth._generate_jwt")
    async def test_github_app_get_token(self, mock_generate_jwt: Mock) -> None:
        """Test getting GitHub App token."""
        mock_generate_jwt.return_value = "test_jwt_token"

        auth = GitHubAppAuth(
            app_id="12345",
            private_key="test_private_key",
        )

        token = await auth.get_token()
        assert token.token == "test_jwt_token"
        assert token.token_type == "Bearer"
        assert token.expires_at is not None

    @patch("src.github.auth.GitHubAppAuth._generate_jwt")
    async def test_github_app_refresh_token(self, mock_generate_jwt: Mock) -> None:
        """Test GitHub App token refresh."""
        mock_generate_jwt.return_value = "new_jwt_token"

        auth = GitHubAppAuth(
            app_id="12345",
            private_key="test_private_key",
        )

        token = await auth.refresh_token()
        assert token.token == "new_jwt_token"
        assert token.token_type == "Bearer"

    @patch("src.github.auth.GitHubAppAuth._generate_jwt")
    async def test_github_app_cached_token(self, mock_generate_jwt: Mock) -> None:
        """Test GitHub App token caching."""
        mock_generate_jwt.return_value = "test_jwt_token"

        auth = GitHubAppAuth(
            app_id="12345",
            private_key="test_private_key",
        )

        # First call should generate new token
        token1 = await auth.get_token()
        assert mock_generate_jwt.call_count == 1

        # Second call should use cached token
        token2 = await auth.get_token()
        assert mock_generate_jwt.call_count == 1
        assert token1.token == token2.token

    async def test_github_app_validate_token_no_token(self) -> None:
        """Test GitHub App token validation with no current token."""
        auth = GitHubAppAuth(
            app_id="12345",
            private_key="test_private_key",
        )

        assert not await auth.validate_token()

    @patch("src.github.auth.GitHubAppAuth._generate_jwt")
    async def test_github_app_validate_token_expired(
        self, mock_generate_jwt: Mock
    ) -> None:
        """Test GitHub App token validation with expired token."""
        mock_generate_jwt.return_value = "test_jwt_token"

        auth = GitHubAppAuth(
            app_id="12345",
            private_key="test_private_key",
        )

        # Create expired token
        past_time = int(time.time()) - 3600
        auth._current_token = AuthToken(
            token="expired_token",
            expires_at=past_time,
        )

        assert not await auth.validate_token()


class TestTokenAuth:
    """Test TokenAuth provider."""

    def test_token_auth_creation(self) -> None:
        """Test TokenAuth creation."""
        auth = TokenAuth("test_token", "Bearer")
        assert auth._token.token == "test_token"
        assert auth._token.token_type == "Bearer"

    def test_token_auth_default_type(self) -> None:
        """Test TokenAuth with default token type."""
        auth = TokenAuth("test_token")
        assert auth._token.token_type == "Bearer"

    async def test_token_auth_get_token(self) -> None:
        """Test getting token."""
        auth = TokenAuth("test_token", "Custom")
        token = await auth.get_token()
        assert token.token == "test_token"
        assert token.token_type == "Custom"

    async def test_token_auth_refresh_token(self) -> None:
        """Test token refresh (should return same token)."""
        auth = TokenAuth("test_token")
        original_token = await auth.get_token()
        refreshed_token = await auth.refresh_token()
        assert original_token.token == refreshed_token.token

    async def test_token_auth_validate_token(self) -> None:
        """Test token validation (always valid)."""
        auth = TokenAuth("test_token")
        assert await auth.validate_token()
