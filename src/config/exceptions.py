"""Configuration-related exceptions.

This module defines all exceptions that can be raised during configuration
loading, validation, and management operations.
"""

from typing import Any


class ConfigurationError(Exception):
    """Base exception for all configuration-related errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize configuration error.

        Args:
            message: Human-readable error message
            details: Optional dictionary with additional error details
        """
        super().__init__(message)
        self.details = details or {}


class ConfigurationFileError(ConfigurationError):
    """Exception raised when configuration file cannot be read or parsed."""

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize configuration file error.

        Args:
            message: Human-readable error message
            file_path: Path to the problematic configuration file
            details: Optional dictionary with additional error details
        """
        super().__init__(message, details)
        self.file_path = file_path


class ConfigurationValidationError(ConfigurationError):
    """Exception raised when configuration validation fails."""

    def __init__(
        self,
        message: str,
        validation_errors: list[Any] | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize configuration validation error.

        Args:
            message: Human-readable error message
            validation_errors: List of specific validation errors
            details: Optional dictionary with additional error details
        """
        super().__init__(message, details)
        self.validation_errors = validation_errors or []


class ConfigurationMissingError(ConfigurationError):
    """Exception raised when required configuration is missing."""

    def __init__(
        self,
        message: str,
        missing_fields: list[Any] | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize configuration missing error.

        Args:
            message: Human-readable error message
            missing_fields: List of missing required fields
            details: Optional dictionary with additional error details
        """
        super().__init__(message, details)
        self.missing_fields = missing_fields or []


class EnvironmentVariableError(ConfigurationError):
    """Exception raised when environment variable substitution fails."""

    def __init__(
        self,
        message: str,
        variable_name: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize environment variable error.

        Args:
            message: Human-readable error message
            variable_name: Name of the problematic environment variable
            details: Optional dictionary with additional error details
        """
        super().__init__(message, details)
        self.variable_name = variable_name
