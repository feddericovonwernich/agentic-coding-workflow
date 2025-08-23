"""GitHub authentication handlers."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import jwt

from .exceptions import GitHubAuthenticationError


@dataclass
class AuthToken:
    """Authentication token with metadata."""

    token: str
    token_type: str = "Bearer"
    expires_at: int | None = None

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at

    def to_header(self) -> dict[str, str]:
        """Convert to authorization header."""
        return {"Authorization": f"{self.token_type} {self.token}"}


class AuthProvider(ABC):
    """Abstract base class for authentication providers."""

    @abstractmethod
    async def get_token(self) -> AuthToken:
        """Get authentication token."""
        pass

    @abstractmethod
    async def refresh_token(self) -> AuthToken:
        """Refresh authentication token."""
        pass

    @abstractmethod
    async def validate_token(self) -> bool:
        """Validate current token."""
        pass


class PersonalAccessTokenAuth(AuthProvider):
    """Personal Access Token authentication provider."""

    def __init__(self, token: str):
        """Initialize PAT authentication.

        Args:
            token: GitHub Personal Access Token
        """
        if not token:
            raise GitHubAuthenticationError("Personal Access Token is required")
        self._token = AuthToken(token=token, token_type="token")  # nosec B106

    async def get_token(self) -> AuthToken:
        """Get authentication token."""
        return self._token

    async def refresh_token(self) -> AuthToken:
        """PAT tokens don't need refresh."""
        return self._token

    async def validate_token(self) -> bool:
        """Validate token (always valid for PAT)."""
        return True


class GitHubAppAuth(AuthProvider):
    """GitHub App authentication provider."""

    def __init__(
        self,
        app_id: str,
        private_key: str,
        installation_id: str | None = None,
    ):
        """Initialize GitHub App authentication.

        Args:
            app_id: GitHub App ID
            private_key: Private key for JWT signing
            installation_id: Installation ID for the app
        """
        self.app_id = app_id
        self.private_key = private_key
        self.installation_id = installation_id
        self._current_token: AuthToken | None = None

    def _generate_jwt(self) -> str:
        """Generate JWT for GitHub App authentication."""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # Issued at time (60 seconds in the past)
            "exp": now + 600,  # JWT expiration (10 minutes)
            "iss": self.app_id,  # GitHub App ID
        }

        try:
            token = jwt.encode(payload, self.private_key, algorithm="RS256")
            return token if isinstance(token, str) else token.decode("utf-8")
        except Exception as e:
            raise GitHubAuthenticationError(f"Failed to generate JWT: {e}") from e

    async def get_token(self) -> AuthToken:
        """Get authentication token."""
        if self._current_token and not self._current_token.is_expired:
            return self._current_token

        return await self.refresh_token()

    async def refresh_token(self) -> AuthToken:
        """Refresh GitHub App installation token."""
        # For now, return JWT token
        # In production, this would exchange JWT for installation token
        jwt_token = self._generate_jwt()
        self._current_token = AuthToken(
            token=jwt_token,
            token_type="Bearer",  # nosec B106
            expires_at=int(time.time()) + 3600,  # 1 hour expiry
        )
        return self._current_token

    async def validate_token(self) -> bool:
        """Validate current token."""
        if not self._current_token:
            return False
        return not self._current_token.is_expired


class TokenAuth(AuthProvider):
    """Simple token authentication (for backward compatibility)."""

    DEFAULT_TOKEN_TYPE = "Bearer"  # Standard HTTP authentication scheme  # nosec B105

    def __init__(self, token: str, token_type: str | None = None):
        """Initialize token authentication.

        Args:
            token: Authentication token
            token_type: Type of token (Bearer, token, etc.). Uses Bearer by default.
        """
        if token_type is None:
            token_type = self.DEFAULT_TOKEN_TYPE
        self._token = AuthToken(token=token, token_type=token_type)

    async def get_token(self) -> AuthToken:
        """Get authentication token."""
        return self._token

    async def refresh_token(self) -> AuthToken:
        """Simple tokens don't refresh."""
        return self._token

    async def validate_token(self) -> bool:
        """Always valid for simple tokens."""
        return True
