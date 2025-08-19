"""
Integration tests for database schema migrations using testcontainers.

Why: Ensure that database migrations work correctly in a real PostgreSQL environment
     and that the schema is created properly with all constraints, indexes, and
     triggers.

What: Tests the core database schema migration including table creation, relationships,
      indexes, triggers, and rollback functionality.

How: Uses testcontainers to spin up a real PostgreSQL instance, applies migrations,
     and validates the resulting schema structure and functionality.
"""

import asyncio
import contextlib
import os
import subprocess
import uuid
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from testcontainers.postgres import PostgresContainer

from alembic import command
from alembic.config import Config
from src.database.config import DatabaseConfig


class TestDatabaseMigration:
    """Test database schema migration functionality."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, None, None]:
        """Start PostgreSQL container for testing."""
        with PostgresContainer("postgres:15") as postgres:
            yield postgres

    @pytest.fixture(scope="class")
    def database_url(self, postgres_container: PostgresContainer) -> str:
        """Get database URL from container."""
        sync_url: str = postgres_container.get_connection_url()
        return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")

    @pytest.fixture(scope="class")
    def sync_database_url(self, postgres_container: PostgresContainer) -> str:
        """Get sync database URL for Alembic."""
        sync_url: str = postgres_container.get_connection_url()
        return sync_url.replace("postgresql+psycopg2://", "postgresql://")

    @pytest.fixture(scope="class")
    def alembic_config(self, sync_database_url: str) -> Generator[Config, None, None]:
        """Create Alembic configuration for testing using project alembic.ini."""
        # Get path to project root alembic.ini
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        alembic_ini_path = os.path.join(project_root, "alembic.ini")

        # Load the existing alembic.ini
        config = Config(alembic_ini_path)

        # Override the database URL for testing
        config.set_main_option("sqlalchemy.url", sync_database_url)

        yield config

    @pytest.fixture(scope="class")
    async def engine(self, database_url: str) -> AsyncGenerator[AsyncEngine, None]:
        """Create async database engine."""
        engine = create_async_engine(database_url, echo=False, poolclass=pool.NullPool)
        try:
            yield engine
        finally:
            await engine.dispose()

    @pytest.fixture(scope="function")
    async def session_factory(self, engine: Any) -> async_sessionmaker[AsyncSession]:
        """Create session factory."""
        return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @pytest.fixture(scope="class", autouse=True)
    def setup_migration(self, alembic_config: Config) -> Generator[None, None, None]:
        """Run migration setup once per test class."""
        # Run migration upgrade before any tests
        command.upgrade(alembic_config, "head")
        yield
        # Optional: cleanup after all tests (rollback migration)
        with contextlib.suppress(Exception):
            # Ignore cleanup errors
            command.downgrade(alembic_config, "base")

    async def test_migration_upgrade(self, alembic_config: Config) -> None:
        """
        Why: Verify that the migration can be applied successfully without errors

        What: Tests that alembic upgrade head completes successfully

        How: Runs alembic upgrade command and checks for successful completion
        """
        # Run migration
        try:
            command.upgrade(alembic_config, "head")
        except Exception as e:
            pytest.fail(f"Migration upgrade failed: {e}")

    async def test_schema_structure(self, engine: Any) -> None:
        """
        Why: Verify that all expected tables, columns, and constraints are created

        What: Tests the complete database schema structure matches requirements

        How: Queries information_schema to validate table and column existence
        """
        async with engine.begin() as conn:
            # Check that all expected tables exist
            result = await conn.execute(
                text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            )
            tables = [row[0] for row in result.fetchall()]

            expected_tables = [
                "alembic_version",
                "analysis_results",
                "check_runs",
                "fix_attempts",
                "pr_state_history",
                "pull_requests",
                "repositories",
                "reviews",
            ]

            for table in expected_tables:
                assert table in tables, f"Table {table} not found in database"

    async def test_enum_types(self, engine: Any) -> None:
        """
        Why: Verify that all ENUM types are created with correct values

        What: Tests that PostgreSQL ENUM types exist with expected values

        How: Queries pg_type and pg_enum to validate ENUM definitions
        """
        async with engine.begin() as conn:
            # Check ENUM types
            result = await conn.execute(
                text("""
                SELECT t.typname,
                       array_agg(e.enumlabel ORDER BY e.enumsortorder) as enum_values
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname IN (
                    'pr_state', 'check_status', 'check_conclusion',
                    'repository_status', 'trigger_event'
                )
                GROUP BY t.typname
                ORDER BY t.typname
            """)
            )

            enum_types = {row[0]: row[1] for row in result.fetchall()}

            expected_enums = {
                "pr_state": ["opened", "closed", "merged"],
                "check_status": ["queued", "in_progress", "completed", "cancelled"],
                "check_conclusion": [
                    "success",
                    "failure",
                    "neutral",
                    "cancelled",
                    "timed_out",
                    "action_required",
                    "stale",
                    "skipped",
                ],
                "repository_status": ["active", "suspended", "error"],
                "trigger_event": [
                    "opened",
                    "synchronize",
                    "closed",
                    "reopened",
                    "edited",
                    "manual_check",
                ],
            }

            for enum_name, expected_values in expected_enums.items():
                assert enum_name in enum_types, f"ENUM type {enum_name} not found"
                actual_values = set(enum_types[enum_name])
                expected_set = set(expected_values)
                assert actual_values == expected_set, (
                    f"ENUM {enum_name} values mismatch: got {actual_values}, "
                    f"expected {expected_set}"
                )

    async def test_indexes_created(self, engine: Any) -> None:
        """
        Why: Verify that all performance indexes are created for query optimization

        What: Tests that all expected indexes exist on the correct columns

        How: Queries pg_indexes to validate index existence and structure
        """
        async with engine.begin() as conn:
            result = await conn.execute(
                text("""
                SELECT indexname, tablename, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                AND indexname LIKE 'idx_%'
                ORDER BY indexname
            """)
            )

            indexes = {
                row[0]: {"table": row[1], "definition": row[2]}
                for row in result.fetchall()
            }

            # Check some key indexes
            expected_indexes = [
                "idx_repositories_status",
                "idx_pull_requests_repository_id",
                "idx_pull_requests_state",
                "idx_check_runs_pr_id",
                "idx_check_runs_status",
                "idx_pr_state_history_pr_id",
            ]

            for index_name in expected_indexes:
                assert index_name in indexes, f"Index {index_name} not found"

    async def test_foreign_key_constraints(self, engine: Any) -> None:
        """
        Why: Verify that foreign key relationships are properly established

        What: Tests that all expected foreign key constraints exist

        How: Queries information_schema for constraint information
        """
        async with engine.begin() as conn:
            result = await conn.execute(
                text("""
                SELECT
                    tc.constraint_name,
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                ORDER BY tc.table_name, tc.constraint_name
            """)
            )

            fk_constraints = result.fetchall()

            # Check key foreign key relationships
            expected_fks = [
                ("pull_requests", "repository_id", "repositories", "id"),
                ("check_runs", "pr_id", "pull_requests", "id"),
                ("pr_state_history", "pr_id", "pull_requests", "id"),
                ("analysis_results", "check_run_id", "check_runs", "id"),
                ("fix_attempts", "analysis_result_id", "analysis_results", "id"),
                ("reviews", "pr_id", "pull_requests", "id"),
            ]

            fk_tuples = [(row[1], row[2], row[3], row[4]) for row in fk_constraints]

            for expected_fk in expected_fks:
                assert expected_fk in fk_tuples, f"Foreign key {expected_fk} not found"

    async def test_triggers_created(self, engine: Any) -> None:
        """
        Why: Verify that database triggers are created for audit logging and updates

        What: Tests that all expected triggers exist and are properly configured

        How: Queries pg_trigger to validate trigger existence
        """
        async with engine.begin() as conn:
            result = await conn.execute(
                text("""
                SELECT
                    t.tgname as trigger_name,
                    c.relname as table_name,
                    p.proname as function_name
                FROM pg_trigger t
                JOIN pg_class c ON t.tgrelid = c.oid
                JOIN pg_proc p ON t.tgfoid = p.oid
                WHERE t.tgisinternal = false
                ORDER BY c.relname, t.tgname
            """)
            )

            triggers = [(row[0], row[1], row[2]) for row in result.fetchall()]

            expected_triggers = [
                (
                    "update_repositories_updated_at",
                    "repositories",
                    "update_updated_at_column",
                ),
                (
                    "update_pull_requests_updated_at",
                    "pull_requests",
                    "update_updated_at_column",
                ),
                (
                    "update_check_runs_updated_at",
                    "check_runs",
                    "update_updated_at_column",
                ),
                (
                    "log_pull_request_state_changes",
                    "pull_requests",
                    "log_pr_state_change",
                ),
            ]

            for expected_trigger in expected_triggers:
                assert expected_trigger in triggers, (
                    f"Trigger {expected_trigger} not found"
                )

    async def test_data_insertion_and_triggers(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """
        Why: Verify that data can be inserted and triggers work correctly

        What: Tests CRUD operations and trigger functionality with sample data

        How: Inserts test data and verifies triggers fire correctly
        """
        async with session_factory() as session:
            # Insert repository
            repo_id = uuid.uuid4()
            await session.execute(
                text("""
                INSERT INTO repositories (id, url, name, status)
                VALUES (:id, :url, :name, 'active')
            """),
                {
                    "id": repo_id,
                    "url": "https://github.com/test/repo",
                    "name": "test-repo",
                },
            )

            # Insert pull request
            pr_id = uuid.uuid4()
            await session.execute(
                text("""
                INSERT INTO pull_requests (
                    id, repository_id, pr_number, title, author, state, draft,
                    base_branch, head_branch, base_sha, head_sha, url
                ) VALUES (
                    :id, :repo_id, :pr_number, :title, :author, 'opened', false,
                    :base_branch, :head_branch, :base_sha, :head_sha, :url
                )
            """),
                {
                    "id": pr_id,
                    "repo_id": repo_id,
                    "pr_number": 1,
                    "title": "Test PR",
                    "author": "testuser",
                    "base_branch": "main",
                    "head_branch": "feature",
                    "base_sha": "a" * 40,
                    "head_sha": "b" * 40,
                    "url": "https://github.com/test/repo/pull/1",
                },
            )

            await session.commit()

            # Check that pr_state_history entry was created by trigger
            result = await session.execute(
                text("""
                SELECT old_state, new_state, trigger_event
                FROM pr_state_history
                WHERE pr_id = :pr_id
            """),
                {"pr_id": pr_id},
            )

            history_entry = result.fetchone()
            assert history_entry is not None, (
                "PR state history entry not created by trigger"
            )
            assert history_entry[0] is None, "Old state should be NULL for new PR"
            assert history_entry[1] == "opened", "New state should be 'opened'"
            assert history_entry[2] == "opened", "Trigger event should be 'opened'"

    async def test_unique_constraints(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """
        Why: Verify that unique constraints prevent duplicate data

        What: Tests that unique constraints work correctly

        How: Attempts to insert duplicate data and expects constraint violations
        """
        async with session_factory() as session:
            repo_id = uuid.uuid4()

            # Insert first repository
            await session.execute(
                text("""
                INSERT INTO repositories (id, url, name, status)
                VALUES (:id, :url, :name, 'active')
            """),
                {
                    "id": repo_id,
                    "url": "https://github.com/test/unique-repo",
                    "name": "unique-repo",
                },
            )
            await session.commit()

            # Try to insert repository with same URL (should fail)
            from sqlalchemy.exc import IntegrityError

            with pytest.raises(IntegrityError):
                await session.execute(
                    text("""
                    INSERT INTO repositories (id, url, name, status)
                    VALUES (:id, :url, :name, 'active')
                """),
                    {
                        "id": uuid.uuid4(),
                        "url": "https://github.com/test/unique-repo",  # Same URL
                        "name": "different-name",
                    },
                )
                await session.commit()

    async def test_migration_rollback(self, alembic_config: Config) -> None:
        """
        Why: Verify that migration rollback works correctly

        What: Tests that the migration can be rolled back cleanly

        How: Runs alembic downgrade and verifies tables are removed
        """
        # First ensure we're at head
        command.upgrade(alembic_config, "head")

        # Now rollback
        try:
            command.downgrade(alembic_config, "base")
        except Exception as e:
            pytest.fail(f"Migration downgrade failed: {e}")

    async def test_schema_after_rollback(self, engine: Any) -> None:
        """
        Why: Verify that rollback completely removes all migration artifacts

        What: Tests that no tables or types remain after rollback

        How: Queries database structure after rollback
        """
        async with engine.begin() as conn:
            # Check that tables are gone (except alembic_version)
            result = await conn.execute(
                text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name != 'alembic_version'
            """)
            )
            tables = [row[0] for row in result.fetchall()]

            migration_tables = [
                "repositories",
                "pull_requests",
                "check_runs",
                "pr_state_history",
                "analysis_results",
                "fix_attempts",
                "reviews",
            ]

            for table in migration_tables:
                assert table not in tables, (
                    f"Table {table} should be removed after rollback"
                )

            # Check that ENUM types are gone
            result = await conn.execute(
                text("""
                SELECT typname FROM pg_type
                WHERE typname IN (
                    'pr_state', 'check_status', 'check_conclusion',
                    'repository_status', 'trigger_event'
                )
            """)
            )
            enum_types = [row[0] for row in result.fetchall()]

            assert len(enum_types) == 0, (
                f"ENUM types should be removed after rollback: {enum_types}"
            )

    async def test_migration_reapply(self, alembic_config: Config) -> None:
        """
        Why: Verify that migration can be reapplied after rollback

        What: Tests that migration is idempotent and can be run multiple times

        How: Applies migration again after rollback
        """
        try:
            command.upgrade(alembic_config, "head")
        except Exception as e:
            pytest.fail(f"Migration re-application failed: {e}")

    async def test_performance_requirements(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """
        Why: Verify that query performance meets requirements

        What: Tests that key queries execute within performance thresholds

        How: Times critical queries and validates they complete quickly
        """
        import time

        async with session_factory() as session:
            # Setup test data with unique URL
            repo_id = uuid.uuid4()
            unique_repo_name = f"perf-test-{repo_id.hex[:8]}"
            unique_url = f"https://github.com/test/{unique_repo_name}"
            await session.execute(
                text("""
                INSERT INTO repositories (id, url, name, status)
                VALUES (:id, :url, :name, 'active')
            """),
                {"id": repo_id, "url": unique_url, "name": unique_repo_name},
            )

            pr_ids = []
            for i in range(10):
                pr_id = uuid.uuid4()
                pr_ids.append(pr_id)
                await session.execute(
                    text("""
                    INSERT INTO pull_requests (
                        id, repository_id, pr_number, title, author, state, draft,
                        base_branch, head_branch, base_sha, head_sha, url
                    ) VALUES (
                        :id, :repo_id, :pr_number, :title, 'testuser', 'opened', false,
                        'main', 'feature', :base_sha, :head_sha, :url
                    )
                """),
                    {
                        "id": pr_id,
                        "repo_id": repo_id,
                        "pr_number": i + 1,
                        "title": f"Test PR {i + 1}",
                        "base_sha": "a" * 40,
                        "head_sha": ("b" + str(i)) * 8,
                        "url": f"{unique_url}/pull/{i + 1}",
                    },
                )

            await session.commit()

            # Test PR lookup performance (should be < 35ms for integration tests)
            start_time = time.time()
            result = await session.execute(
                text("""
                SELECT * FROM pull_requests
                WHERE repository_id = :repo_id AND pr_number = :pr_number
            """),
                {"repo_id": repo_id, "pr_number": 5},
            )

            pr_lookup_time = (time.time() - start_time) * 1000  # Convert to ms

            assert pr_lookup_time < 35, (
                f"PR lookup took {pr_lookup_time:.2f}ms (should be < 35ms)"
            )

            pr = result.fetchone()
            assert pr is not None, "PR should be found"

    async def _test_performance_requirements_with_unique_data(
        self, session_factory: async_sessionmaker[AsyncSession], instance_id: str
    ) -> None:
        """Helper method for performance testing with unique data."""
        import time

        async with session_factory() as session:
            # Setup test data with unique URL using instance_id
            repo_id = uuid.uuid4()
            unique_repo_name = f"lifecycle-perf-test-{instance_id}"
            unique_url = f"https://github.com/test/{unique_repo_name}"
            await session.execute(
                text("""
                INSERT INTO repositories (id, url, name, status)
                VALUES (:id, :url, :name, 'active')
            """),
                {"id": repo_id, "url": unique_url, "name": unique_repo_name},
            )

            pr_ids = []
            for i in range(10):
                pr_id = uuid.uuid4()
                pr_ids.append(pr_id)
                await session.execute(
                    text("""
                    INSERT INTO pull_requests (
                        id, repository_id, pr_number, title, author, state, draft,
                        base_branch, head_branch, base_sha, head_sha, url
                    ) VALUES (
                        :id, :repo_id, :pr_number, :title, 'testuser', 'opened', false,
                        'main', 'feature', :base_sha, :head_sha, :url
                    )
                """),
                    {
                        "id": pr_id,
                        "repo_id": repo_id,
                        "pr_number": i + 1,
                        "title": f"Lifecycle Test PR {i + 1}",
                        "base_sha": "a" * 40,
                        "head_sha": ("c" + str(i))
                        * 8,  # Different pattern to avoid conflicts
                        "url": f"{unique_url}/pull/{i + 1}",
                    },
                )

            await session.commit()

            # Test PR lookup performance (should be < 35ms for integration tests)
            start_time = time.time()
            result = await session.execute(
                text("""
                SELECT * FROM pull_requests
                WHERE repository_id = :repo_id AND pr_number = :pr_number
            """),
                {"repo_id": repo_id, "pr_number": 5},
            )

            pr_lookup_time = (time.time() - start_time) * 1000  # Convert to ms

            assert pr_lookup_time < 35, (
                f"PR lookup took {pr_lookup_time:.2f}ms (should be < 35ms)"
            )

            pr = result.fetchone()
            assert pr is not None, "PR should be found"

    @pytest.mark.asyncio
    async def test_full_migration_lifecycle(
        self, postgres_container: PostgresContainer
    ) -> None:
        """
        Why: Integration test that runs the complete migration lifecycle

        What: Tests upgrade, data operations, and rollback in sequence

        How: Comprehensive test that validates the entire migration process
        """
        # This test orchestrates all the above tests in proper sequence
        # Use unique test instance to avoid data conflicts
        test_instance_id = uuid.uuid4().hex[:8]
        container_url = postgres_container.get_connection_url()
        sync_database_url = container_url.replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        database_url = container_url.replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )

        # Use existing alembic.ini from project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        alembic_ini_path = os.path.join(project_root, "alembic.ini")

        # Load existing alembic.ini and override database URL
        alembic_config = Config(alembic_ini_path)
        alembic_config.set_main_option("sqlalchemy.url", sync_database_url)

        engine = create_async_engine(database_url, echo=False)

        try:
            # Run the full test sequence
            await self.test_migration_upgrade(alembic_config)
            await self.test_schema_structure(engine)
            await self.test_enum_types(engine)
            await self.test_indexes_created(engine)
            await self.test_foreign_key_constraints(engine)
            await self.test_triggers_created(engine)

            session_factory = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            await self.test_data_insertion_and_triggers(session_factory)
            await self.test_unique_constraints(session_factory)
            await self._test_performance_requirements_with_unique_data(
                session_factory, test_instance_id
            )

            await self.test_migration_rollback(alembic_config)
            await self.test_schema_after_rollback(engine)
            await self.test_migration_reapply(alembic_config)

        finally:
            await engine.dispose()
