"""Database connection management.

Provides async SQLAlchemy engine management, connection pooling, and database
session handling optimized for high-throughput PR processing workloads.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

from .config import DatabaseConfig, get_database_config

logger = logging.getLogger(__name__)

# Global engine instance
_engine_instance: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class DatabaseConnectionManager:
    """Manages database connections and provides session handling.

    Handles connection pooling, health checks, and provides context managers
    for database operations with proper cleanup and error handling.
    """

    def __init__(self, config: DatabaseConfig | None = None):
        self.config = config or get_database_config()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Get or create async database engine."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get or create async session factory."""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,  # Keep objects usable after commit
            )
        return self._session_factory

    def _create_engine(self) -> AsyncEngine:
        """Create async SQLAlchemy engine with optimized settings."""
        engine = create_async_engine(
            self.config.get_sqlalchemy_url(),
            # Connection pool settings
            poolclass=AsyncAdaptedQueuePool,
            pool_size=self.config.pool.pool_size,
            max_overflow=self.config.pool.max_overflow,
            pool_pre_ping=self.config.pool.pool_pre_ping,
            pool_recycle=self.config.pool.pool_recycle,
            pool_timeout=self.config.pool.pool_timeout,
            # Connection settings
            connect_args={
                "timeout": self.config.connect_timeout,
                "command_timeout": self.config.command_timeout,
            },
            # Logging and debugging
            echo=self.config.should_echo_sql(),
            echo_pool=False,  # Set to True for pool debugging
            # Performance settings
            future=True,  # Use SQLAlchemy 2.0 style
        )

        # Register connection event handlers for monitoring
        self._register_connection_events(engine)

        logger.info(
            "Created database engine",
            extra={
                "pool_size": self.config.pool.pool_size,
                "max_overflow": self.config.pool.max_overflow,
                "pool_timeout": self.config.pool.pool_timeout,
            },
        )

        return engine

    def _register_connection_events(self, engine: AsyncEngine) -> None:
        """Register SQLAlchemy events for connection monitoring."""

        @event.listens_for(engine.sync_engine, "connect")
        def on_connect(dbapi_connection: Any, connection_record: Any) -> None:
            """Handle new database connections."""
            logger.debug("New database connection established")

        @event.listens_for(engine.sync_engine, "checkout")
        def on_checkout(
            dbapi_connection: Any, connection_record: Any, connection_proxy: Any
        ) -> None:
            """Handle connection checkout from pool."""
            logger.debug("Connection checked out from pool")

        @event.listens_for(engine.sync_engine, "checkin")
        def on_checkin(dbapi_connection: Any, connection_record: Any) -> None:
            """Handle connection checkin to pool."""
            logger.debug("Connection checked back into pool")

        @event.listens_for(engine.sync_engine, "invalidate")
        def on_invalidate(
            dbapi_connection: Any, connection_record: Any, exception: Exception | None
        ) -> None:
            """Handle connection invalidation."""
            logger.warning(
                "Database connection invalidated",
                extra={"error": str(exception) if exception else None},
            )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with automatic cleanup.

        Usage:
            async with connection_manager.get_session() as session:
                # Use session for database operations
                result = await session.execute(query)
        """
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @asynccontextmanager
    async def get_transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with explicit transaction control.

        Usage:
            async with connection_manager.get_transaction() as session:
                # Perform multiple operations
                # Transaction is NOT automatically committed
                await session.commit()  # Explicit commit required
        """
        session = self.session_factory()
        try:
            yield session
            # No automatic commit - caller must commit explicitly
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def health_check(self) -> bool:
        """Perform database health check.

        Returns:
            bool: True if database is healthy, False otherwise
        """
        try:
            async with self.get_session() as session:
                # Simple query to test connection
                result = await session.execute(text("SELECT 1"))
                return result.scalar() == 1
        except SQLAlchemyError as e:
            logger.error("Database health check failed", extra={"error": str(e)})
            return False
        except Exception as e:
            logger.error(
                "Unexpected error during health check", extra={"error": str(e)}
            )
            return False

    async def close(self) -> None:
        """Close database engine and clean up connections."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database engine disposed")


# Global connection manager instance
_connection_manager: DatabaseConnectionManager | None = None


def get_connection_manager() -> DatabaseConnectionManager:
    """Get global database connection manager instance."""
    global _connection_manager

    if _connection_manager is None:
        _connection_manager = DatabaseConnectionManager()

    return _connection_manager


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session using global connection manager.

    Convenience function for getting database sessions.
    """
    connection_manager = get_connection_manager()
    async with connection_manager.get_session() as session:
        yield session


async def check_database_health() -> bool:
    """Check database health using global connection manager.

    Returns:
        bool: True if database is healthy, False otherwise
    """
    connection_manager = get_connection_manager()
    return await connection_manager.health_check()


async def close_database_connections() -> None:
    """Close all database connections and clean up resources."""
    global _connection_manager

    if _connection_manager:
        await _connection_manager.close()
        _connection_manager = None


class DatabaseRetry:
    """Utility class for implementing retry logic for database operations."""

    @staticmethod
    async def with_retry(
        operation: Any,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
        exceptions: tuple[type[Exception], ...] = (SQLAlchemyError,),
    ) -> Any:
        """Execute database operation with exponential backoff retry.

        Args:
            operation: Async callable to execute
            max_retries: Maximum number of retry attempts
            base_delay: Base delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            exceptions: Tuple of exceptions that should trigger retry

        Returns:
            Result of the operation

        Raises:
            Last exception if all retries are exhausted
        """
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return await operation()
            except exceptions as e:
                last_exception = e

                if attempt < max_retries:
                    delay = min(base_delay * (2**attempt), max_delay)
                    logger.warning(
                        "Database operation failed, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "delay": delay,
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Database operation failed after all retries",
                        extra={"max_retries": max_retries, "error": str(e)},
                    )

        # Re-raise the last exception
        if last_exception:
            raise last_exception


def reset_connection_manager() -> None:
    """Reset global connection manager (useful for testing)."""
    global _connection_manager
    if _connection_manager:
        # Note: This doesn't await the close() method, so use carefully
        _connection_manager = None
