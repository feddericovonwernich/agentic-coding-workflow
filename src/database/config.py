"""Database configuration module.

Provides type-safe database configuration with environment variable support,
proper defaults, and production-ready connection pool settings.
"""

import os
from typing import Any
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabasePoolConfig(BaseModel):
    """Database connection pool configuration."""

    pool_size: int = Field(
        default=20, description="Number of connections to maintain in the pool"
    )
    max_overflow: int = Field(
        default=30,
        description="Number of additional connections to create when pool is exhausted",
    )
    pool_pre_ping: bool = Field(
        default=True, description="Enable connection health checks before use"
    )
    pool_recycle: int = Field(
        default=3600,
        description="Number of seconds after which a connection is recreated",
    )
    pool_timeout: int = Field(
        default=30, description="Timeout in seconds to get a connection from the pool"
    )


class DatabaseConfig(BaseSettings):
    """Database configuration with environment variable support.

    Environment variables:
    - DATABASE_URL: Full database connection URL
    - DATABASE_HOST: Database host (default: localhost)
    - DATABASE_PORT: Database port (default: 5432)
    - DATABASE_DATABASE: Database name (default: agentic_workflow)
    - DATABASE_USERNAME: Database user (default: postgres)
    - DATABASE_PASSWORD: Database password (required)
    - DATABASE_POOL_SIZE: Connection pool size (default: 20)
    - DATABASE_POOL_MAX_OVERFLOW: Pool max overflow (default: 30)
    - DATABASE_POOL_PRE_PING: Enable pre-ping (default: true)
    - DATABASE_POOL_RECYCLE: Pool recycle time in seconds (default: 3600)
    - DATABASE_POOL_TIMEOUT: Pool timeout in seconds (default: 30)
    """

    # Database connection settings
    database_url: str | None = Field(
        default=None,
        description="Complete database URL (overrides individual components)",
    )
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    database: str = Field(
        default="agentic_workflow",
        description="Database name",
    )
    username: str = Field(
        default="postgres",
        description="Database user",
    )
    password: str | None = Field(
        default=None,
        description="Database password (required unless DATABASE_URL provided)",
    )

    # Connection pool settings
    pool: DatabasePoolConfig = Field(default_factory=DatabasePoolConfig)

    # Additional settings
    echo_sql: bool = Field(
        default=False, description="Enable SQL query logging (development only)"
    )
    ssl_mode: str = Field(
        default="prefer", description="SSL mode for database connections"
    )
    connect_timeout: int = Field(
        default=10, description="Connection timeout in seconds"
    )
    command_timeout: int = Field(default=60, description="Command timeout in seconds")

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        case_sensitive=False,
        env_nested_delimiter="_",
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> Any:
        """Validate database URL if provided."""
        if v:
            # If explicit URL provided (including from env vars), validate it
            parsed = urlparse(v)
            if not all([parsed.scheme, parsed.hostname]):
                raise ValueError("Invalid database URL format")
        return v

    @field_validator("pool", mode="before")
    @classmethod
    def validate_pool_config(cls, v: Any) -> Any:
        """Validate pool configuration from flat environment variables."""
        if isinstance(v, dict):
            return DatabasePoolConfig(**v)
        return v

    @model_validator(mode="after")
    def construct_database_url(self) -> "DatabaseConfig":
        """Construct database URL from components if not explicitly provided."""
        if not self.database_url and self.password:
            # Construct URL from components when password is available
            self.database_url = f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        return self

    def get_sqlalchemy_url(self) -> str:
        """Get SQLAlchemy-compatible database URL."""
        if not self.database_url:
            raise ValueError(
                "No database URL available - provide either database_url or password"
            )
        return self.database_url

    def get_alembic_url(self) -> str:
        """Get Alembic-compatible database URL (sync driver)."""
        if not self.database_url:
            raise ValueError(
                "No database URL available - provide either database_url or password"
            )
        # Alembic requires sync driver, so replace asyncpg with psycopg2
        return self.database_url.replace("+asyncpg", "")

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return os.getenv("ENVIRONMENT", "development").lower() == "production"

    def should_echo_sql(self) -> bool:
        """Determine if SQL should be echoed (never in production)."""
        return self.echo_sql and not self.is_production()


# Global configuration instance
_config_instance: DatabaseConfig | None = None


def get_database_config() -> DatabaseConfig:
    """Get database configuration instance.

    Returns cached instance on subsequent calls for performance.
    """
    global _config_instance

    if _config_instance is None:
        _config_instance = DatabaseConfig()

    return _config_instance


def reset_database_config() -> None:
    """Reset configuration instance (useful for testing)."""
    global _config_instance
    _config_instance = None
