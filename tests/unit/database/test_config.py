"""
Unit tests for database configuration module.

Tests configuration loading, validation, environment variable substitution,
and database URL construction.

Available fixtures from conftest.py:
- mock_database_config: Provides a MagicMock DatabaseConfig with test values
- mock_async_session: Provides an AsyncMock database session
- mock_connection_manager: Provides a mocked DatabaseConnectionManager
- test_env_vars: Temporarily injects DATABASE_* environment variables via patch.dict
- sample_health_check_results: Provides pre-built HealthCheckResult test data
"""

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.database.config import (
    DatabaseConfig,
    DatabasePoolConfig,
    get_database_config,
    reset_database_config,
)


class TestDatabasePoolConfig:
    """Test database pool configuration."""

    def test_default_pool_config(self) -> None:
        """
        Why: Ensure pool configuration has reasonable defaults for production use
        What: Tests that DatabasePoolConfig initializes with expected default values
        How: Creates instance without parameters and validates all default values
        """
        pool_config = DatabasePoolConfig()

        assert pool_config.pool_size == 20
        assert pool_config.max_overflow == 30
        assert pool_config.pool_timeout == 30
        assert pool_config.pool_recycle == 3600
        assert pool_config.pool_pre_ping is True

    def test_custom_pool_config(self) -> None:
        """
        Why: Verify pool configuration accepts custom values for optimization
        What: Tests DatabasePoolConfig initialization with custom values
        How: Creates instance with all custom parameters and validates
             they're set correctly
        """
        pool_config = DatabasePoolConfig(
            pool_size=10,
            max_overflow=20,
            pool_timeout=60,
            pool_recycle=7200,
            pool_pre_ping=False,
        )

        assert pool_config.pool_size == 10
        assert pool_config.max_overflow == 20
        assert pool_config.pool_timeout == 60
        assert pool_config.pool_recycle == 7200
        assert pool_config.pool_pre_ping is False

    def test_pool_config_accepts_valid_values(self) -> None:
        """
        Why: Ensure pool configuration accepts valid integer values
        What: Tests that DatabasePoolConfig accepts reasonable positive values
        How: Creates instances with various valid values and validates they're accepted
        """
        # Test with minimal valid values
        config = DatabasePoolConfig(pool_size=1, max_overflow=0, pool_timeout=1)
        assert config.pool_size == 1
        assert config.max_overflow == 0
        assert config.pool_timeout == 1

        # Test with larger values
        config2 = DatabasePoolConfig(pool_size=100, max_overflow=200, pool_timeout=300)
        assert config2.pool_size == 100
        assert config2.max_overflow == 200
        assert config2.pool_timeout == 300


class TestDatabaseConfig:
    """Test database configuration and URL construction."""

    def test_database_config_from_components(self) -> None:
        """
        Why: Test that database configuration builds URLs correctly from components
        What: Tests DatabaseConfig URL construction from host, port, database, etc.
        How: Creates config with individual components and validates constructed URL
        """
        config = DatabaseConfig(
            host="testhost",
            port=5433,
            database="testdb",
            username="testuser",
            password="testpass",
        )

        expected_url = "postgresql+asyncpg://testuser:testpass@testhost:5433/testdb"
        assert config.database_url == expected_url

    def test_database_config_from_url(self) -> None:
        """
        Why: Test that database configuration prioritizes explicit
             database_url over components
        What: Tests that database_url takes precedence when both URL and
              components are provided
        How: Creates config with both database_url and components, validates URL is used
        """
        explicit_url = "postgresql+asyncpg://user:pass@host:5432/db"
        config = DatabaseConfig(
            database_url=explicit_url,
            host="different",
            port=9999,
            database="different",
            username="different",
            password="different",
        )

        assert config.database_url == explicit_url

    def test_alembic_url_conversion(self) -> None:
        """
        Why: Ensure Alembic gets sync URL since it doesn't support async drivers
        What: Tests that get_alembic_url() returns URL without +asyncpg driver
        How: Creates config and validates Alembic URL has postgresql:// instead of postgresql+asyncpg://
        """
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="testdb",
            username="user",
            password="pass",
        )

        alembic_url = config.get_alembic_url()
        assert alembic_url.startswith("postgresql://")
        assert "+asyncpg" not in alembic_url

    def test_password_validation(self) -> None:
        """
        Why: Ensure database configuration can be created without password
             when database_url is not needed
        What: Tests that DatabaseConfig allows creation without password
              (database_url will be None)
        How: Creates config without password and validates it's accepted
             with None database_url
        """
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="testdb",
            username="user",
            # No password provided
        )

        # Should succeed but database_url should be None since no password provided
        assert config.database_url is None
        assert config.password is None

    @patch.dict(
        os.environ,
        {
            "DATABASE_HOST": "env_host",
            "DATABASE_PORT": "9999",
            "DATABASE_DATABASE": "env_db",
            "DATABASE_USERNAME": "env_user",
            "DATABASE_PASSWORD": "env_pass",
        },
    )
    def test_environment_variable_substitution(self) -> None:
        """
        Why: Test that configuration reads from environment variables when
             components not provided
        What: Tests DatabaseConfig uses environment variables for missing components
        How: Sets environment variables and creates config without explicit values
        """
        config = DatabaseConfig()

        # Environment variables should be used
        assert config.host == "env_host"
        assert config.port == 9999
        assert config.database == "env_db"
        assert config.username == "env_user"
        assert config.password == "env_pass"

    @patch.dict(
        os.environ,
        {"DATABASE_DATABASE_URL": "postgresql+asyncpg://env:url@host:5432/envdb"},
    )
    def test_database_url_from_environment_automatic(self) -> None:
        """
        Why: Test that DATABASE_URL environment variable is automatically
             read by DatabaseConfig
        What: Tests that DatabaseConfig reads DATABASE_URL from environment
              without explicit passing
        How: Sets DATABASE_URL environment variable, creates config without
             ANY explicit parameters,
             and validates that pydantic-settings automatically populates
             database_url from env
        """
        # Create config without passing ANY parameters - let pydantic-settings
        # read from environment
        config = DatabaseConfig()

        # The URL should be automatically read from DATABASE_URL env var
        # by pydantic-settings
        assert config.database_url == "postgresql+asyncpg://env:url@host:5432/envdb"
        # Password should be None since we're using DATABASE_URL
        assert config.password is None

    def test_ssl_configuration_field_exists(self) -> None:
        """
        Why: Test that SSL configuration field can be set for future URL enhancement
        What: Tests that ssl_mode field is properly stored in configuration
        How: Creates config with SSL settings and validates field is accessible
        """
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="testdb",
            username="user",
            password="pass",
            ssl_mode="require",
        )

        assert config.ssl_mode == "require"

    def test_pool_configuration_integration(self) -> None:
        """
        Why: Test that pool configuration is properly integrated with
             database configuration
        What: Tests that DatabaseConfig includes custom pool configuration
        How: Creates config with custom pool settings and validates they're accessible
        """
        custom_pool = DatabasePoolConfig(pool_size=15, max_overflow=25)
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="testdb",
            username="user",
            password="pass",
            pool=custom_pool,
        )

        assert config.pool.pool_size == 15
        assert config.pool.max_overflow == 25


class TestDatabaseConfigGlobalFunctions:
    """Test global configuration functions."""

    def test_get_database_config_singleton(self) -> None:
        """
        Why: Ensure get_database_config returns same instance to avoid
             duplicate initialization
        What: Tests that get_database_config implements singleton pattern
        How: Calls function twice and validates same instance is returned
        """
        # Reset to ensure clean state
        reset_database_config()

        config1 = get_database_config()
        config2 = get_database_config()

        assert config1 is config2

    def test_reset_database_config(self) -> None:
        """
        Why: Ensure reset function clears singleton for testing and reinitialization
        What: Tests that reset_database_config clears the singleton instance
        How: Gets config, resets, gets again, and validates different instances
        """
        config1 = get_database_config()
        reset_database_config()
        config2 = get_database_config()

        assert config1 is not config2

    @patch.dict(
        os.environ, {"DATABASE_HOST": "global_host", "DATABASE_PASSWORD": "global_pass"}
    )
    def test_global_config_uses_environment(self) -> None:
        """
        Why: Test that global configuration function uses environment variables
        What: Tests get_database_config reads from environment when called
        How: Sets environment variables, resets config, gets new config,
             validates values
        """
        reset_database_config()
        config = get_database_config()

        assert config.host == "global_host"
        assert config.password == "global_pass"

    @patch("src.database.config.DatabaseConfig")
    def test_config_initialization_error_handling(self, mock_config_class: Any) -> None:
        """
        Why: Ensure graceful handling of configuration initialization failures
        What: Tests that configuration errors are properly raised and not
              silently ignored
        How: Mocks DatabaseConfig to raise exception and validates it propagates
        """
        mock_config_class.side_effect = ValidationError.from_exception_data(
            "DatabaseConfig", []
        )

        reset_database_config()

        with pytest.raises(ValidationError):
            get_database_config()

    def test_config_caching_behavior(self) -> None:
        """
        Why: Verify that configuration caching works correctly to avoid
             repeated initialization
        What: Tests that subsequent calls to get_database_config use cached instance
        How: Gets config multiple times and uses mock to verify
             initialization called once
        """
        reset_database_config()

        with patch("src.database.config.DatabaseConfig") as mock_config:
            mock_instance = MagicMock()
            mock_config.return_value = mock_instance

            # Call multiple times
            config1 = get_database_config()
            config2 = get_database_config()
            config3 = get_database_config()

            # DatabaseConfig should only be called once
            mock_config.assert_called_once()
            assert config1 is mock_instance
            assert config2 is mock_instance
            assert config3 is mock_instance
