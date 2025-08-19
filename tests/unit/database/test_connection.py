"""
Unit tests for database connection management module.

Tests connection manager functionality, session handling, retry mechanisms,
and health check operations.

Available fixtures from conftest.py:
- mock_database_config: Provides a MagicMock DatabaseConfig with test values
- mock_async_session: Provides an AsyncMock database session
- mock_connection_manager: Provides a mocked DatabaseConnectionManager
- test_env_vars: Temporarily injects DATABASE_* environment variables via patch.dict
- sample_health_check_results: Provides pre-built HealthCheckResult test data
"""

from unittest.mock import AsyncMock, call, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.database.connection import (
    DatabaseRetry,
)


class TestDatabaseRetry:
    """Test database retry mechanism."""

    @pytest.mark.asyncio
    async def test_successful_operation_no_retry(self) -> None:
        """
        Why: Ensure operations that succeed on first try don't trigger retry logic
        What: Tests that DatabaseRetry executes operation once when it succeeds
        How: Provides operation that returns immediately and validates no retries occur
        """
        operation = AsyncMock(return_value="success")

        result = await DatabaseRetry.with_retry(
            operation, max_retries=3, base_delay=0.1
        )

        assert result == "success"
        operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_sqlalchemy_error(self) -> None:
        """
        Why: Test that transient database errors trigger retry mechanism
        What: Tests DatabaseRetry retries operations that fail with SQLAlchemyError
        How: Makes operation fail twice then succeed, validates retry attempts
        """
        operation = AsyncMock(
            side_effect=[
                SQLAlchemyError("Connection lost"),
                SQLAlchemyError("Still failing"),
                "success",
            ]
        )

        result = await DatabaseRetry.with_retry(
            operation, max_retries=2, base_delay=0.01
        )

        assert result == "success"
        assert operation.call_count == 3

    @pytest.mark.asyncio
    async def test_max_attempts_exceeded(self) -> None:
        """
        Why: Ensure retry mechanism eventually gives up to prevent infinite loops
        What: Tests that DatabaseRetry raises exception after max_attempts reached
        How: Makes operation always fail and validates exception raised
             after max attempts
        """
        operation = AsyncMock(side_effect=SQLAlchemyError("Persistent failure"))

        with pytest.raises(SQLAlchemyError, match="Persistent failure"):
            await DatabaseRetry.with_retry(operation, max_retries=1, base_delay=0.01)

        assert operation.call_count == 2  # max_retries=1 means 2 total attempts

    @pytest.mark.asyncio
    async def test_non_retryable_error_not_retried(self) -> None:
        """
        Why: Ensure non-transient errors fail immediately without retries
        What: Tests that ValueError and other non-SQLAlchemy errors
              don't trigger retries
        How: Makes operation raise ValueError and validates only one attempt made
        """
        operation = AsyncMock(side_effect=ValueError("Non-retryable error"))

        with pytest.raises(ValueError, match="Non-retryable error"):
            await DatabaseRetry.with_retry(operation, max_retries=3, base_delay=0.01)

        operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self) -> None:
        """
        Why: Verify retry delays increase exponentially to reduce database load
        What: Tests that DatabaseRetry implements exponential backoff between attempts
        How: Patches asyncio.sleep and validates delay increases with backoff multiplier
        """
        operation = AsyncMock(
            side_effect=[
                SQLAlchemyError("Fail 1"),
                SQLAlchemyError("Fail 2"),
                "success",
            ]
        )

        with patch("asyncio.sleep") as mock_sleep:
            result = await DatabaseRetry.with_retry(
                operation, max_retries=2, base_delay=0.1
            )

        assert result == "success"

        # Verify exponential backoff: 0.1, 0.2 (base_delay * 2^attempt)
        expected_calls = [call(0.1), call(0.2)]
        mock_sleep.assert_has_calls(expected_calls)
