"""GitHub API client exceptions."""

from typing import Any


class GitHubError(Exception):
    """Base exception for GitHub API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict[str, Any] | None = None,
    ):
        """Initialize GitHub error.

        Args:
            message: Error message
            status_code: HTTP status code
            response_data: Response data from GitHub API
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class GitHubAuthenticationError(GitHubError):
    """Raised when authentication fails."""

    pass


class GitHubRateLimitError(GitHubError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        reset_time: int | None = None,
        remaining: int = 0,
        limit: int = 0,
    ):
        """Initialize rate limit error.

        Args:
            message: Error message
            reset_time: Unix timestamp when rate limit resets
            remaining: Remaining API calls
            limit: Total rate limit
        """
        super().__init__(message)
        self.reset_time = reset_time
        self.remaining = remaining
        self.limit = limit


class GitHubNotFoundError(GitHubError):
    """Raised when resource is not found."""

    pass


class GitHubValidationError(GitHubError):
    """Raised when request validation fails."""

    pass


class GitHubServerError(GitHubError):
    """Raised when GitHub server returns 5xx error."""

    pass


class GitHubConnectionError(GitHubError):
    """Raised when connection to GitHub fails."""

    pass


class GitHubTimeoutError(GitHubError):
    """Raised when request times out."""

    pass
