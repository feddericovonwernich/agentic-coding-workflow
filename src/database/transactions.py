"""Transaction management for database operations."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TransactionError(Exception):
    """Exception raised during transaction operations."""

    pass


class DatabaseTransaction:
    """Database transaction context manager with rollback support."""

    def __init__(self, session: AsyncSession, auto_commit: bool = True):
        """Initialize transaction manager.

        Args:
            session: Database session to manage
            auto_commit: Whether to auto-commit on successful completion
        """
        self.session = session
        self.auto_commit = auto_commit
        self._committed = False
        self._rolled_back = False

    async def __aenter__(self) -> AsyncSession:
        """Enter transaction context."""
        try:
            # Begin transaction if not already in one
            if not self.session.in_transaction():
                await self.session.begin()
            return self.session
        except Exception as e:
            logger.error(f"Failed to begin transaction: {e}")
            raise TransactionError(f"Failed to begin transaction: {e}") from e

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit transaction context with automatic rollback on errors."""
        try:
            if exc_type is not None:
                # Exception occurred, rollback
                await self.rollback()
                logger.warning(
                    f"Transaction rolled back due to {exc_type.__name__}: {exc_val}"
                )
                return None  # Re-raise the exception

            # No exception, commit if auto_commit is enabled
            if self.auto_commit and not self._committed:
                await self.commit()
        except Exception as e:
            logger.error(f"Error during transaction cleanup: {e}")
            await self.rollback()
            raise TransactionError(f"Transaction cleanup failed: {e}") from e

    async def commit(self) -> None:
        """Manually commit the transaction."""
        if self._rolled_back:
            raise TransactionError("Cannot commit after rollback")

        if not self._committed:
            try:
                await self.session.commit()
                self._committed = True
                logger.debug("Transaction committed successfully")
            except Exception as e:
                logger.error(f"Failed to commit transaction: {e}")
                await self.rollback()
                raise TransactionError(f"Failed to commit transaction: {e}") from e

    async def rollback(self) -> None:
        """Manually rollback the transaction."""
        if not self._rolled_back:
            try:
                await self.session.rollback()
                self._rolled_back = True
                logger.debug("Transaction rolled back successfully")
            except Exception as e:
                logger.error(f"Failed to rollback transaction: {e}")
                raise TransactionError(f"Failed to rollback transaction: {e}") from e

    async def flush(self) -> None:
        """Flush pending changes without committing."""
        if self._rolled_back:
            raise TransactionError("Cannot flush after rollback")

        try:
            await self.session.flush()
        except Exception as e:
            logger.error(f"Failed to flush session: {e}")
            raise TransactionError(f"Failed to flush session: {e}") from e


@asynccontextmanager
async def database_transaction(
    session: AsyncSession, auto_commit: bool = True
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database transactions.

    Args:
        session: Database session to use
        auto_commit: Whether to automatically commit on success

    Yields:
        The database session within transaction context

    Example:
        async with database_transaction(session) as tx_session:
            # Perform database operations
            await repo.create(...)
            await repo.update(...)
            # Transaction auto-commits on success, rolls back on exception
    """
    transaction = DatabaseTransaction(session, auto_commit)
    async with transaction as tx_session:
        yield tx_session


class RetryableTransaction:
    """Transaction manager with retry logic for transient failures."""

    def __init__(
        self,
        session: AsyncSession,
        max_retries: int = 3,
        base_delay: float = 0.1,
        backoff_factor: float = 2.0,
        auto_commit: bool = True,
    ):
        """Initialize retryable transaction.

        Args:
            session: Database session to use
            max_retries: Maximum number of retry attempts
            base_delay: Base delay between retries in seconds
            backoff_factor: Exponential backoff multiplier
            auto_commit: Whether to auto-commit on success
        """
        self.session = session
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.backoff_factor = backoff_factor
        self.auto_commit = auto_commit

    async def execute(self, operation: Any) -> Any:
        """Execute operation with retry logic.

        Args:
            operation: Async callable that performs database operations

        Returns:
            Result of the operation

        Raises:
            TransactionError: After all retries are exhausted
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                async with database_transaction(
                    self.session, self.auto_commit
                ) as session:
                    result = await operation(session)
                    return result
            except SQLAlchemyError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (self.backoff_factor**attempt)
                    logger.warning(
                        f"Transaction attempt {attempt + 1} failed, "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All {self.max_retries + 1} transaction attempts failed"
                    )
            except Exception as e:
                # Non-retryable exception
                logger.error(f"Non-retryable error in transaction: {e}")
                raise TransactionError(f"Non-retryable transaction error: {e}") from e

        # All retries exhausted
        raise TransactionError(
            f"Transaction failed after {self.max_retries + 1} attempts"
        ) from last_exception


@asynccontextmanager
async def retryable_transaction(
    session: AsyncSession,
    max_retries: int = 3,
    base_delay: float = 0.1,
    backoff_factor: float = 2.0,
    auto_commit: bool = True,
) -> AsyncGenerator[RetryableTransaction, None]:
    """Context manager for retryable transactions.

    Args:
        session: Database session to use
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        backoff_factor: Exponential backoff multiplier
        auto_commit: Whether to auto-commit on success

    Yields:
        RetryableTransaction instance

    Example:
        async with retryable_transaction(session) as tx:
            result = await tx.execute(
                lambda session: repo.complex_operation(session)
            )
    """
    tx = RetryableTransaction(
        session, max_retries, base_delay, backoff_factor, auto_commit
    )
    yield tx


def transactional(auto_commit: bool = True, retries: int = 0) -> Any:
    """Decorator for automatic transaction management.

    Args:
        auto_commit: Whether to auto-commit on success
        retries: Number of retries for transient failures

    Example:
        @transactional(retries=3)
        async def complex_operation(self, session: AsyncSession, ...):
            # This method will run in a transaction with retries
            await self.repo1.create(...)
            await self.repo2.update(...)
    """

    def decorator(func: Any) -> Any:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract session from args or kwargs
            session = None
            for arg in args:
                if isinstance(arg, AsyncSession):
                    session = arg
                    break

            if session is None:
                session = kwargs.get("session")

            if session is None:
                raise ValueError("No AsyncSession found in arguments")

            if retries > 0:
                async with retryable_transaction(
                    session, max_retries=retries, auto_commit=auto_commit
                ) as tx:
                    return await tx.execute(lambda s: func(*args, **kwargs))
            else:
                async with database_transaction(session, auto_commit):
                    return await func(*args, **kwargs)

        return wrapper

    return decorator


class UnitOfWork:
    """Unit of Work pattern implementation for complex operations."""

    def __init__(self, session: AsyncSession):
        """Initialize unit of work.

        Args:
            session: Database session to use
        """
        self.session = session
        self._operations: list[tuple[str, Any, dict[str, Any]]] = []
        self._committed = False

    def add_operation(self, operation_type: str, entity: Any, **kwargs: Any) -> None:
        """Add an operation to the unit of work.

        Args:
            operation_type: Type of operation ('create', 'update', 'delete')
            entity: Entity to operate on
            **kwargs: Additional operation parameters
        """
        if self._committed:
            raise TransactionError("Cannot add operations after commit")

        self._operations.append((operation_type, entity, kwargs))

    async def commit(self) -> None:
        """Execute all operations in a single transaction."""
        if self._committed:
            raise TransactionError("Unit of work already committed")

        async with database_transaction(self.session) as session:
            for operation_type, entity, _kwargs in self._operations:
                if operation_type == "create":
                    session.add(entity)
                elif operation_type == "update":
                    await session.merge(entity)
                elif operation_type == "delete":
                    await session.delete(entity)
                else:
                    raise ValueError(f"Unknown operation type: {operation_type}")

            # Flush to ensure all operations are applied
            await session.flush()

        self._committed = True
        logger.debug(f"Unit of work committed {len(self._operations)} operations")

    async def rollback(self) -> None:
        """Clear all pending operations."""
        self._operations.clear()
        logger.debug("Unit of work rolled back")


@asynccontextmanager
async def unit_of_work(session: AsyncSession) -> AsyncGenerator[UnitOfWork, None]:
    """Context manager for unit of work pattern.

    Args:
        session: Database session to use

    Yields:
        UnitOfWork instance

    Example:
        async with unit_of_work(session) as uow:
            uow.add_operation('create', new_entity)
            uow.add_operation('update', existing_entity)
            # All operations committed together on context exit
    """
    uow = UnitOfWork(session)
    try:
        yield uow
        if not uow._committed:
            await uow.commit()
    except Exception:
        await uow.rollback()
        raise


# Alias for compatibility with existing code
transaction_scope = database_transaction
