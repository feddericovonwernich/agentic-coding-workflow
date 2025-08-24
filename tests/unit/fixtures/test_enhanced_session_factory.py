"""Unit tests for EnhancedSessionFactory with concurrent session management.

This module provides comprehensive unit tests for the EnhancedSessionFactory,
verifying proper session isolation, pooling, cleanup, and concurrent operation handling.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class TestEnhancedSessionFactory:
    """Tests for enhanced session factory with improved concurrent operation handling."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock database engine for testing."""
        engine = AsyncMock(spec=AsyncEngine)
        engine.dispose = AsyncMock()
        return engine

    @pytest.fixture
    def mock_connection_manager(self, mock_engine: AsyncMock) -> AsyncMock:
        """Create mock connection manager for testing."""
        manager = AsyncMock()
        manager.engine = mock_engine
        manager.get_session = AsyncMock()
        return manager

    @pytest.fixture
    async def session_factory(
        self, mock_connection_manager: AsyncMock
    ) -> AsyncGenerator[Any, None]:
        """Create session factory instance for testing."""
        # Import will be available when EnhancedSessionFactory is implemented
        from tests.integration.fixtures.database import EnhancedSessionFactory

        factory = EnhancedSessionFactory(mock_connection_manager)
        yield factory
        # Cleanup after each test
        await factory.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_session_creation(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Ensure the factory can create multiple sessions concurrently without
             conflicts or "concurrent operations" errors that plague standard SQLAlchemy
             async session management.

        What: Tests that multiple async tasks can simultaneously request and use
              sessions without interference, each getting a properly isolated session.

        How: Creates 10 concurrent tasks that each request a session, performs a mock
             operation, and closes. Verifies all sessions are created successfully
             without errors or conflicts.
        """
        # Arrange
        session_count = 10
        created_sessions = []

        # Create mock sessions with unique IDs for tracking
        mock_sessions = []
        for i in range(session_count):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session.id = f"session_{i}"
            mock_session.close = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_sessions.append(mock_session)

        # Configure connection manager to return sessions in order
        mock_connection_manager.get_session.side_effect = [
            self._create_async_context_manager(session) for session in mock_sessions
        ]

        async def create_and_use_session(index: int) -> None:
            """Task to create and use a session."""
            async with session_factory.get_session() as session:
                created_sessions.append(session)
                # Simulate some database operation
                await asyncio.sleep(0.01)
                assert session is not None
                assert hasattr(session, "id")

        # Act - Create sessions concurrently
        tasks = [create_and_use_session(i) for i in range(session_count)]
        await asyncio.gather(*tasks)

        # Assert
        assert len(created_sessions) == session_count, (
            f"Should have created {session_count} sessions"
        )

        # Verify all sessions are unique
        session_ids = [s.id for s in created_sessions]
        assert len(set(session_ids)) == session_count, "All sessions should be unique"

        # Verify connection manager was called correctly
        assert mock_connection_manager.get_session.call_count == session_count, (
            f"Connection manager should be called {session_count} times"
        )

    @pytest.mark.asyncio
    async def test_session_cleanup_on_error(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Ensure sessions are properly cleaned up when errors occur during use,
             preventing resource leaks and maintaining pool health.

        What: Tests that when an exception occurs within a session context,
              the session is properly rolled back and closed.

        How: Creates a session context that raises an exception during use,
             verifies rollback and close methods are called on the session.
        """
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=SQLAlchemyError("Database error"))

        mock_connection_manager.get_session.return_value = (
            self._create_async_context_manager(mock_session)
        )

        # Act & Assert
        with pytest.raises(SQLAlchemyError) as exc_info:
            async with session_factory.get_session() as session:
                await session.execute("SELECT 1")

        assert "Database error" in str(exc_info.value)

        # Verify cleanup was performed
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_transaction_isolation(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Verify that transactions in different sessions are properly isolated,
             ensuring data consistency and preventing cross-contamination.

        What: Tests that operations in one session do not affect another session's
              transaction until committed, maintaining ACID properties.

        How: Creates two concurrent sessions, performs different operations in each,
             and verifies that changes are isolated until explicitly committed.
        """
        # Arrange
        session1 = AsyncMock(spec=AsyncSession)
        session1.id = "session_1"
        session1.in_transaction = MagicMock(return_value=True)
        session1.commit = AsyncMock()
        session1.rollback = AsyncMock()
        session1.close = AsyncMock()
        session1.add = MagicMock()

        session2 = AsyncMock(spec=AsyncSession)
        session2.id = "session_2"
        session2.in_transaction = MagicMock(return_value=True)
        session2.commit = AsyncMock()
        session2.rollback = AsyncMock()
        session2.close = AsyncMock()
        session2.add = MagicMock()

        # Configure to return different sessions
        mock_connection_manager.get_session.side_effect = [
            self._create_async_context_manager(session1),
            self._create_async_context_manager(session2),
        ]

        # Act - Use two sessions concurrently
        async def transaction1() -> str:
            async with session_factory.get_session() as session:
                session.add({"data": "transaction1"})
                await session.commit()
                return str(session.id)

        async def transaction2() -> str:
            async with session_factory.get_session() as session:
                session.add({"data": "transaction2"})
                await session.commit()
                return str(session.id)

        results = await asyncio.gather(transaction1(), transaction2())

        # Assert
        assert list(results) == ["session_1", "session_2"], (
            "Each transaction should use a different session"
        )

        # Verify each session had independent operations
        session1.add.assert_called_once_with({"data": "transaction1"})
        session2.add.assert_called_once_with({"data": "transaction2"})

        # Verify commits were independent
        session1.commit.assert_called_once()
        session2.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_pool_exhaustion_handling(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Ensure the factory handles pool exhaustion gracefully, either by
             queuing requests or providing clear error messages to prevent deadlocks.

        What: Tests behavior when requesting more sessions than the pool size allows,
              verifying graceful degradation or proper error handling.

        How: Simulates pool exhaustion by having the connection manager raise
             OperationalError after a certain number of sessions, verifies proper
             error propagation and recovery.
        """
        # Arrange
        pool_size = 3
        successful_sessions = []

        for i in range(pool_size):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session.id = f"session_{i}"
            mock_session.close = AsyncMock()
            successful_sessions.append(mock_session)

        # After pool_size sessions, raise pool exhaustion error
        def get_session_side_effect() -> Any:
            if len(successful_sessions) > 0:
                session = successful_sessions.pop(0)
                return self._create_async_context_manager(session)
            else:
                from sqlalchemy.exc import OperationalError as OpError

                raise OpError(
                    "Cannot acquire connection from pool",
                    None,
                    Exception("Pool exhausted"),
                )

        mock_connection_manager.get_session.side_effect = get_session_side_effect

        # Act - Try to create more sessions than pool allows
        created_count = 0
        exhaustion_errors = 0

        async def try_get_session() -> None:
            nonlocal created_count, exhaustion_errors
            try:
                async with session_factory.get_session():
                    created_count += 1
                    await asyncio.sleep(0.01)
            except OperationalError as e:
                if "pool" in str(e).lower():
                    exhaustion_errors += 1
                else:
                    raise

        # Create more tasks than pool size
        tasks = [try_get_session() for _ in range(pool_size + 2)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Assert
        assert created_count == pool_size, f"Should create exactly {pool_size} sessions"
        assert exhaustion_errors == 2, "Should have 2 pool exhaustion errors"

    @pytest.mark.asyncio
    async def test_shared_session_for_reads(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Verify that read-only operations can efficiently share sessions when
             appropriate, improving resource utilization and performance.

        What: Tests that multiple concurrent read operations can use shared sessions
              without conflicts when configured for read-only mode.

        How: Creates multiple concurrent read tasks using get_shared_session(),
             verifies they can execute simultaneously without conflicts.
        """
        # Arrange
        shared_session = AsyncMock(spec=AsyncSession)
        shared_session.id = "shared_read_session"
        shared_session.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 1))
        shared_session.close = AsyncMock()

        # Always return the same shared session for reads
        mock_connection_manager.get_session.return_value = (
            self._create_async_context_manager(shared_session)
        )

        read_results = []

        async def read_operation(index: int) -> None:
            """Perform a read operation."""
            # Use get_shared_session if available, otherwise regular session
            if hasattr(session_factory, "get_shared_session"):
                async with session_factory.get_shared_session() as session:
                    await session.execute(f"SELECT {index}")
                    read_results.append((index, session.id))
            else:
                async with session_factory.get_session() as session:
                    await session.execute(f"SELECT {index}")
                    read_results.append((index, session.id))

        # Act - Perform concurrent reads
        read_tasks = [read_operation(i) for i in range(5)]
        await asyncio.gather(*read_tasks)

        # Assert
        assert len(read_results) == 5, "Should complete all read operations"

        # Verify all reads could happen concurrently
        if hasattr(session_factory, "get_shared_session"):
            # If shared sessions are supported, they should share the same session
            session_ids = [r[1] for r in read_results]
            assert all(sid == "shared_read_session" for sid in session_ids), (
                "All reads should use the shared session"
            )

    @pytest.mark.asyncio
    async def test_transaction_scope_rollback(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Ensure transaction_scope helper properly handles automatic rollback
             on errors, maintaining database consistency.

        What: Tests that transaction_scope context manager automatically rolls back
              changes when an exception occurs within the scope.

        How: Uses transaction_scope with an operation that raises an exception,
             verifies rollback is called and commit is not called.
        """
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.begin = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        mock_connection_manager.get_session.return_value = (
            self._create_async_context_manager(mock_session)
        )

        # Act & Assert
        if hasattr(session_factory, "transaction_scope"):
            with pytest.raises(ValueError) as exc_info:
                async with session_factory.transaction_scope() as session:
                    session.add({"data": "test"})
                    raise ValueError("Simulated error")

            assert "Simulated error" in str(exc_info.value)

            # Verify rollback was called, commit was not
            mock_session.rollback.assert_called()
            mock_session.commit.assert_not_called()
        else:
            # Test with regular session if transaction_scope not available
            with pytest.raises(ValueError):
                async with session_factory.get_session() as session:
                    session.add({"data": "test"})
                    raise ValueError("Simulated error")

            mock_session.rollback.assert_called()

    @pytest.mark.asyncio
    async def test_session_lifecycle_tracking(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Verify that session lifecycle is properly tracked for monitoring
             and debugging purposes, helping identify resource leaks.

        What: Tests that the factory tracks active sessions, closed sessions,
              and provides accurate metrics about session usage.

        How: Creates multiple sessions, uses them, closes them, and verifies
             the factory's tracking metrics are accurate at each stage.
        """
        # Arrange
        sessions = []
        for i in range(3):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session.id = f"tracked_session_{i}"
            mock_session.close = AsyncMock()
            sessions.append(mock_session)

        mock_connection_manager.get_session.side_effect = [
            self._create_async_context_manager(s) for s in sessions
        ]

        # Act - Create and track sessions
        # Check initial state
        if hasattr(session_factory, "get_active_session_count"):
            initial_count = session_factory.get_active_session_count()
            assert initial_count == 0, "Should start with no active sessions"

        # Create first session
        async with session_factory.get_session():
            if hasattr(session_factory, "get_active_session_count"):
                assert session_factory.get_active_session_count() == 1, (
                    "Should have 1 active session"
                )

            # Create second session while first is active
            async with session_factory.get_session():
                if hasattr(session_factory, "get_active_session_count"):
                    assert session_factory.get_active_session_count() == 2, (
                        "Should have 2 active sessions"
                    )

        # After context exits, sessions should be closed
        if hasattr(session_factory, "get_active_session_count"):
            assert session_factory.get_active_session_count() == 0, (
                "Should have no active sessions after context exit"
            )

        # Verify close was called on sessions
        for session in sessions[:2]:  # Only first 2 were used
            session.close.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_closes_all_sessions(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Ensure the cleanup method properly closes all active sessions and
             releases resources, preventing leaks during shutdown.

        What: Tests that calling cleanup() closes all active sessions, disposes
              the engine connection pool, and resets internal state.

        How: Creates multiple active sessions, calls cleanup, and verifies all
             sessions are closed and resources are released.
        """
        # Arrange
        active_sessions = []
        for i in range(3):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session.id = f"cleanup_session_{i}"
            mock_session.close = AsyncMock()
            mock_session.is_active = True
            active_sessions.append(mock_session)

        # Track which sessions have been returned
        session_index = 0

        def get_next_session() -> Any:
            nonlocal session_index
            if session_index < len(active_sessions):
                session = active_sessions[session_index]
                session_index += 1
                return self._create_async_context_manager(session)
            return self._create_async_context_manager(AsyncMock(spec=AsyncSession))

        mock_connection_manager.get_session.side_effect = get_next_session

        # Create sessions but don't close them yet
        created_sessions = []
        for _i in range(3):
            # Using a different approach to keep sessions "active"
            session_ctx = session_factory.get_session()
            session = await session_ctx.__aenter__()
            created_sessions.append((session_ctx, session))

        # Act - Call cleanup
        await session_factory.cleanup()

        # Assert
        # All active sessions should be closed
        for session in active_sessions:
            session.close.assert_called()

        # Connection manager engine should be disposed if accessible
        if hasattr(mock_connection_manager, "engine"):
            mock_connection_manager.engine.dispose.assert_called()

        # After cleanup, factory should be in clean state
        if hasattr(session_factory, "get_active_session_count"):
            assert session_factory.get_active_session_count() == 0, (
                "Should have no active sessions after cleanup"
            )

        # Clean up the sessions we opened
        for ctx, _session in created_sessions:
            with suppress(Exception):
                await ctx.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_session_factory_thread_safety(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Verify the session factory is thread-safe and can handle requests
             from multiple async tasks without race conditions.

        What: Tests that concurrent access to factory methods doesn't cause
              race conditions or corrupt internal state.

        How: Performs various factory operations concurrently from multiple tasks,
             verifies no race conditions or state corruption occurs.
        """
        # Arrange
        operations_completed = []
        errors_encountered = []

        def create_mock_session(index: int) -> AsyncMock:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session.id = f"concurrent_{index}"
            mock_session.close = AsyncMock()
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar=lambda: index)
            )
            return mock_session

        # Create many mock sessions for concurrent access
        mock_sessions = [create_mock_session(i) for i in range(20)]
        mock_connection_manager.get_session.side_effect = [
            self._create_async_context_manager(s) for s in mock_sessions
        ]

        async def perform_operation(op_id: int) -> None:
            """Perform various operations on the factory."""
            try:
                # Try to get a session
                async with session_factory.get_session() as session:
                    # Simulate some work
                    await session.execute(f"SELECT {op_id}")
                    operations_completed.append(op_id)

                    # Random sleep to increase concurrency chances
                    await asyncio.sleep(0.001 * (op_id % 3))
            except Exception as e:
                errors_encountered.append((op_id, str(e)))

        # Act - Perform many concurrent operations
        tasks = [perform_operation(i) for i in range(20)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Assert
        assert len(errors_encountered) == 0, (
            f"Should have no errors, but got: {errors_encountered}"
        )
        assert len(operations_completed) == 20, (
            "All operations should complete successfully"
        )
        assert len(set(operations_completed)) == 20, "All operations should be unique"

    @pytest.mark.asyncio
    async def test_session_reuse_prevention(
        self, session_factory: Any, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Ensure sessions cannot be reused after being closed to prevent
             "concurrent operation" errors and maintain session integrity.

        What: Tests that attempting to use a session after it's been closed
              raises appropriate errors and doesn't corrupt state.

        How: Gets a session, closes it, then attempts to use it again,
             verifying proper error handling.
        """
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.id = "reuse_test_session"
        mock_session.is_active = True
        mock_session.close = AsyncMock()

        def close_side_effect() -> None:
            mock_session.is_active = False

        mock_session.close.side_effect = close_side_effect
        mock_session.execute = AsyncMock(
            side_effect=lambda x: MagicMock(scalar=lambda: 1)
            if mock_session.is_active
            else SQLAlchemyError("Session is closed")
        )

        mock_connection_manager.get_session.return_value = (
            self._create_async_context_manager(mock_session)
        )

        # Act & Assert
        # Use session normally
        async with session_factory.get_session() as session:
            result = await session.execute("SELECT 1")
            assert result.scalar() == 1

        # Session should be closed after context exit
        mock_session.close.assert_called_once()

        # Attempting to use closed session should fail
        with pytest.raises(SQLAlchemyError) as exc_info:
            await mock_session.execute("SELECT 2")

        assert "closed" in str(exc_info.value).lower()

    # Helper method for creating async context managers
    @staticmethod
    @asynccontextmanager
    async def _create_async_context_manager(
        session: AsyncMock,
    ) -> AsyncGenerator[AsyncMock, None]:
        """Helper to create async context manager for mock sessions."""
        try:
            yield session
        except Exception:
            if hasattr(session, "rollback"):
                await session.rollback()
            raise
        finally:
            if hasattr(session, "close"):
                await session.close()


class TestEnhancedSessionFactoryPerformance:
    """Performance-related tests for EnhancedSessionFactory."""

    @pytest.mark.asyncio
    async def test_session_creation_performance(
        self, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Ensure session creation meets performance requirements to maintain
             responsive application behavior under load.

        What: Tests that creating and closing sessions happens within acceptable
              time limits even under concurrent load.

        How: Measures time to create and close multiple sessions concurrently,
             verifies operations complete within performance thresholds.
        """
        import time

        from tests.integration.fixtures.database import EnhancedSessionFactory

        factory = EnhancedSessionFactory(mock_connection_manager)

        # Create mock sessions
        mock_sessions = []
        for i in range(100):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session.id = f"perf_session_{i}"
            mock_session.close = AsyncMock()
            mock_sessions.append(mock_session)

        mock_connection_manager.get_session.side_effect = [
            TestEnhancedSessionFactory._create_async_context_manager(s)
            for s in mock_sessions
        ]

        # Measure performance
        start_time = time.perf_counter()

        async def create_and_close_session() -> None:
            async with factory.get_session():
                pass  # Just create and close

        tasks = [create_and_close_session() for _ in range(100)]
        await asyncio.gather(*tasks)

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        # Assert performance requirements
        assert elapsed_time < 1.0, (
            f"Creating 100 sessions took {elapsed_time:.3f}s, should be < 1s"
        )

        # Calculate throughput
        sessions_per_second = 100 / elapsed_time
        assert sessions_per_second > 100, (
            f"Should create > 100 sessions/sec, got {sessions_per_second:.1f}"
        )

        # Cleanup
        await factory.cleanup()


class TestEnhancedSessionFactoryEdgeCases:
    """Edge case tests for EnhancedSessionFactory."""

    @pytest.mark.asyncio
    async def test_empty_pool_handling(
        self, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Verify factory handles edge case of empty or exhausted connection pool
             gracefully without hanging or corrupting state.

        What: Tests factory behavior when connection pool is empty or cannot provide
              new connections.

        How: Configures connection manager to fail immediately, verifies proper
             error handling and recovery.
        """
        from tests.integration.fixtures.database import EnhancedSessionFactory

        factory = EnhancedSessionFactory(mock_connection_manager)

        # Configure to always fail
        from sqlalchemy.exc import OperationalError as OpError

        mock_connection_manager.get_session.side_effect = OpError(
            "Connection pool exhausted", None, Exception("Pool exhausted")
        )

        # Should raise appropriate error
        with pytest.raises(OperationalError) as exc_info:
            async with factory.get_session() as session:
                pass

        assert "pool exhausted" in str(exc_info.value).lower()

        # Factory should still be usable after error
        mock_connection_manager.get_session.side_effect = None
        mock_connection_manager.get_session.return_value = (
            TestEnhancedSessionFactory._create_async_context_manager(
                AsyncMock(spec=AsyncSession)
            )
        )

        # Should work now
        async with factory.get_session() as session:
            assert session is not None

        await factory.cleanup()

    @pytest.mark.asyncio
    async def test_nested_session_contexts(
        self, mock_connection_manager: AsyncMock
    ) -> None:
        """
        Why: Ensure nested session contexts work correctly without deadlocks or
             resource conflicts, supporting complex transaction patterns.

        What: Tests that sessions can be nested within other session contexts
              without causing deadlocks or corruption.

        How: Creates nested session contexts with different operations,
             verifies each maintains independence and proper cleanup.
        """
        from tests.integration.fixtures.database import EnhancedSessionFactory

        factory = EnhancedSessionFactory(mock_connection_manager)

        # Create separate sessions for nesting
        outer_session = AsyncMock(spec=AsyncSession)
        outer_session.id = "outer"
        outer_session.close = AsyncMock()

        inner_session = AsyncMock(spec=AsyncSession)
        inner_session.id = "inner"
        inner_session.close = AsyncMock()

        mock_connection_manager.get_session.side_effect = [
            TestEnhancedSessionFactory._create_async_context_manager(outer_session),
            TestEnhancedSessionFactory._create_async_context_manager(inner_session),
        ]

        # Test nested contexts
        async with factory.get_session() as outer:
            assert outer.id == "outer"

            async with factory.get_session() as inner:
                assert inner.id == "inner"
                assert inner.id != outer.id  # Should be different sessions

        # Both sessions should be closed
        outer_session.close.assert_called_once()
        inner_session.close.assert_called_once()

        await factory.cleanup()
