"""GitHub API client package."""

from .auth import (
    AuthProvider,
    AuthToken,
    GitHubAppAuth,
    PersonalAccessTokenAuth,
    TokenAuth,
)
from .client import GitHubClient, GitHubClientConfig
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
from .pagination import AsyncPaginator, LinkHeader, PaginatedResponse
from .rate_limiting import CircuitBreaker, RateLimitInfo, RateLimitManager

__all__ = [
    "AsyncPaginator",
    "AuthProvider",
    "AuthToken",
    "CircuitBreaker",
    "GitHubAppAuth",
    "GitHubAuthenticationError",
    "GitHubClient",
    "GitHubClientConfig",
    "GitHubConnectionError",
    "GitHubError",
    "GitHubNotFoundError",
    "GitHubRateLimitError",
    "GitHubServerError",
    "GitHubTimeoutError",
    "GitHubValidationError",
    "LinkHeader",
    "PaginatedResponse",
    "PersonalAccessTokenAuth",
    "RateLimitInfo",
    "RateLimitManager",
    "TokenAuth",
]
