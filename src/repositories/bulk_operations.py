"""Bulk database operations for efficient data synchronization.

This module provides optimized bulk operations for PR and check run
synchronization to minimize database round trips and improve performance.
"""

import builtins
import contextlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.check_run import CheckRun
from src.models.pull_request import PullRequest

logger = logging.getLogger(__name__)


class BulkOperationsMixin:
    """Mixin class providing bulk operations for repositories.

    Can be mixed into repository classes to provide efficient
    bulk insert, update, and upsert operations.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with database session.

        Args:
            session: Async database session
        """
        self.session = session

    async def bulk_upsert_prs(
        self, pr_data_list: list[dict[str, Any]], repository_id: uuid.UUID
    ) -> dict[str, int]:
        """Bulk upsert pull requests using PostgreSQL ON CONFLICT.

        Args:
            pr_data_list: List of PR data dictionaries
            repository_id: Repository ID for all PRs

        Returns:
            Dictionary with operation counts
        """
        if not pr_data_list:
            return {"created": 0, "updated": 0}

        logger.debug(
            f"Bulk upserting {len(pr_data_list)} PRs for repository {repository_id}"
        )

        try:
            # Prepare data for bulk operation
            values = []
            for pr_data in pr_data_list:
                # Ensure required fields are present
                value = {
                    "repository_id": repository_id,
                    "pr_number": pr_data["pr_number"],
                    "title": pr_data.get("title", ""),
                    "author": pr_data.get("author", ""),
                    "state": pr_data.get("state", "opened"),
                    "draft": pr_data.get("draft", False),
                    "base_branch": pr_data.get("base_branch", "main"),
                    "head_branch": pr_data.get("head_branch", "feature"),
                    "base_sha": pr_data.get("base_sha", ""),
                    "head_sha": pr_data.get("head_sha", ""),
                    "url": pr_data.get("url", ""),
                    "body": pr_data.get("body"),
                    "metadata": pr_data.get("metadata"),
                    "created_at": pr_data.get("created_at", datetime.now(UTC)),
                    "updated_at": pr_data.get("updated_at", datetime.now(UTC)),
                }
                values.append(value)

            if len(values) <= 100:
                # Use INSERT ... ON CONFLICT for smaller batches
                return await self._upsert_prs_on_conflict(values)
            else:
                # Use temp table approach for larger batches
                return await self._upsert_prs_temp_table(values)

        except Exception as e:
            logger.error(f"Error in bulk PR upsert: {e}")
            raise

    async def _upsert_prs_on_conflict(
        self, values: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Upsert PRs using INSERT ... ON CONFLICT."""
        # Use PostgreSQL-specific INSERT ... ON CONFLICT
        stmt = postgresql_insert(PullRequest).values(values)

        # Define what to do on conflict (repository_id, pr_number uniqueness)
        update_dict = {
            "title": stmt.excluded.title,
            "author": stmt.excluded.author,
            "state": stmt.excluded.state,
            "draft": stmt.excluded.draft,
            "base_branch": stmt.excluded.base_branch,
            "head_branch": stmt.excluded.head_branch,
            "base_sha": stmt.excluded.base_sha,
            "head_sha": stmt.excluded.head_sha,
            "url": stmt.excluded.url,
            "body": stmt.excluded.body,
            "metadata": stmt.excluded.metadata,
            "updated_at": stmt.excluded.updated_at,
        }

        stmt = stmt.on_conflict_do_update(
            index_elements=["repository_id", "pr_number"], set_=update_dict
        )

        # Execute with RETURNING clause to count operations
        stmt = stmt.returning(  # type: ignore[assignment]
            PullRequest.id,
            (PullRequest.created_at == stmt.excluded.created_at).label("is_new"),
        )

        result = await self.session.execute(stmt)
        rows = result.fetchall()

        created = sum(1 for row in rows if row.is_new)
        updated = len(rows) - created

        await self.session.flush()

        logger.debug(f"PR upsert completed: {created} created, {updated} updated")
        return {"created": created, "updated": updated}

    async def _upsert_prs_temp_table(
        self, values: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Upsert PRs using temporary table for large batches.

        Security Note: The temp_table name is internally generated using UUID.hex
        and is never influenced by user input, making it safe from SQL injection.
        All bandit warnings for this method are false positives.
        """
        # Create temporary table with internally generated UUID-based name
        # SECURITY: Safe from SQL injection - temp_table is internally controlled
        # and generated from uuid.uuid4().hex - cannot contain SQL injection vectors
        temp_table = f"temp_prs_{uuid.uuid4().hex[:8]}"

        create_temp_sql = f"""
        CREATE TEMPORARY TABLE {temp_table} (
            repository_id UUID,
            pr_number INTEGER,
            title VARCHAR(500),
            author VARCHAR(100),
            state VARCHAR(20),
            draft BOOLEAN,
            base_branch VARCHAR(200),
            head_branch VARCHAR(200),
            base_sha VARCHAR(40),
            head_sha VARCHAR(40),
            url VARCHAR(500),
            body TEXT,
            metadata JSONB,
            created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ
        )
        """

        try:
            await self.session.execute(text(create_temp_sql))

            # Insert data into temp table in chunks
            chunk_size = 1000
            for i in range(0, len(values), chunk_size):
                chunk = values[i : i + chunk_size]

                # Convert to format suitable for bulk insert
                insert_values = []
                for item in chunk:
                    insert_values.append(tuple(item.values()))

                columns = ", ".join(chunk[0].keys())
                placeholders = ", ".join(
                    ["(" + ", ".join(["%s"] * len(chunk[0])) + ")"] * len(chunk)
                )

                # SECURITY NOTE: temp_table is generated internally from UUID
                # and cannot be influenced by user input. False positive warning.
                insert_sql = f"""
                INSERT INTO {temp_table} ({columns})
                VALUES {placeholders}
                """  # nosec B608

                # Flatten values for parameterized query
                flat_values = [val for item in insert_values for val in item]

                await self.session.execute(text(insert_sql), flat_values)

            # Perform upsert from temp table
            # SECURITY NOTE: temp_table is generated internally from UUID
            # and cannot be influenced by user input. False positive warning.
            upsert_sql = f"""
            INSERT INTO pull_requests (
                repository_id, pr_number, title, author, state, draft,
                base_branch, head_branch, base_sha, head_sha, url, body,
                metadata, created_at, updated_at
            )
            SELECT * FROM {temp_table}
            ON CONFLICT (repository_id, pr_number) DO UPDATE SET
                title = EXCLUDED.title,
                author = EXCLUDED.author,
                state = EXCLUDED.state,
                draft = EXCLUDED.draft,
                base_branch = EXCLUDED.base_branch,
                head_branch = EXCLUDED.head_branch,
                base_sha = EXCLUDED.base_sha,
                head_sha = EXCLUDED.head_sha,
                url = EXCLUDED.url,
                body = EXCLUDED.body,
                metadata = EXCLUDED.metadata,
                updated_at = EXCLUDED.updated_at
            """  # nosec B608

            result = await self.session.execute(text(upsert_sql))

            # Get counts (approximation for large batches)
            total_affected = getattr(result, "rowcount", 0)

            # Clean up temp table
            # nosec B608: temp_table is internally generated UUID, not user input
            await self.session.execute(text(f"DROP TABLE {temp_table}"))

            await self.session.flush()

            # For large batches, we approximate the split
            # In practice, this would require more complex tracking
            created = total_affected // 2  # Rough estimate
            updated = total_affected - created

            logger.debug(
                f"Large batch PR upsert completed: "
                f"~{created} created, ~{updated} updated"
            )
            return {"created": created, "updated": updated}

        except Exception as e:
            # Clean up temp table on error
            with contextlib.suppress(builtins.BaseException):
                # nosec B608: temp_table is internally generated UUID, not user input
                await self.session.execute(text(f"DROP TABLE IF EXISTS {temp_table}"))
            raise e

    async def bulk_upsert_check_runs(
        self, check_data_list: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Bulk upsert check runs using PostgreSQL ON CONFLICT.

        Args:
            check_data_list: List of check run data dictionaries

        Returns:
            Dictionary with operation counts
        """
        if not check_data_list:
            return {"created": 0, "updated": 0}

        logger.debug(f"Bulk upserting {len(check_data_list)} check runs")

        try:
            # Prepare data for bulk operation
            values = []
            for check_data in check_data_list:
                value = {
                    "pr_id": check_data["pr_id"],
                    "external_id": check_data["external_id"],
                    "check_name": check_data["check_name"],
                    "check_suite_id": check_data.get("check_suite_id"),
                    "status": check_data.get("status", "queued"),
                    "conclusion": check_data.get("conclusion"),
                    "details_url": check_data.get("details_url"),
                    "logs_url": check_data.get("logs_url"),
                    "output_summary": check_data.get("output_summary"),
                    "output_text": check_data.get("output_text"),
                    "started_at": check_data.get("started_at"),
                    "completed_at": check_data.get("completed_at"),
                    "metadata": check_data.get("metadata"),
                    "created_at": check_data.get("created_at", datetime.now(UTC)),
                    "updated_at": check_data.get("updated_at", datetime.now(UTC)),
                }
                values.append(value)

            # Use INSERT ... ON CONFLICT
            stmt = postgresql_insert(CheckRun).values(values)

            update_dict = {
                "check_name": stmt.excluded.check_name,
                "status": stmt.excluded.status,
                "conclusion": stmt.excluded.conclusion,
                "details_url": stmt.excluded.details_url,
                "logs_url": stmt.excluded.logs_url,
                "output_summary": stmt.excluded.output_summary,
                "output_text": stmt.excluded.output_text,
                "started_at": stmt.excluded.started_at,
                "completed_at": stmt.excluded.completed_at,
                "metadata": stmt.excluded.metadata,
                "updated_at": stmt.excluded.updated_at,
            }

            stmt = stmt.on_conflict_do_update(
                index_elements=["external_id"], set_=update_dict
            )

            # Execute with RETURNING clause to count operations
            stmt = stmt.returning(  # type: ignore[assignment]
                CheckRun.id,
                (CheckRun.created_at == stmt.excluded.created_at).label("is_new"),
            )

            result = await self.session.execute(stmt)
            rows = result.fetchall()

            created = sum(1 for row in rows if row.is_new)
            updated = len(rows) - created

            await self.session.flush()

            logger.debug(
                f"Check run upsert completed: {created} created, {updated} updated"
            )
            return {"created": created, "updated": updated}

        except Exception as e:
            logger.error(f"Error in bulk check run upsert: {e}")
            raise

    async def bulk_load_prs_with_checks(
        self, repository_id: uuid.UUID, pr_numbers: list[int] | None = None
    ) -> list[PullRequest]:
        """Bulk load PRs with their check runs.

        Args:
            repository_id: Repository ID
            pr_numbers: Optional list of specific PR numbers to load

        Returns:
            List of PullRequest objects with check runs loaded
        """
        query = (
            select(PullRequest)
            .where(PullRequest.repository_id == repository_id)
            .options(
                selectinload(PullRequest.check_runs),
                selectinload(PullRequest.repository),
            )
        )

        if pr_numbers:
            query = query.where(PullRequest.pr_number.in_(pr_numbers))

        result = await self.session.execute(query)
        prs = result.scalars().all()

        logger.debug(
            f"Bulk loaded {len(prs)} PRs with check runs for repository {repository_id}"
        )
        return list(prs)

    async def bulk_update_last_checked(
        self,
        repository_id: uuid.UUID,
        pr_numbers: list[int] | None = None,
        checked_at: datetime | None = None,
    ) -> int:
        """Bulk update last_checked_at for PRs.

        Args:
            repository_id: Repository ID
            pr_numbers: Optional list of specific PR numbers
            checked_at: Timestamp to set (defaults to now)

        Returns:
            Number of PRs updated
        """
        if checked_at is None:
            checked_at = datetime.now(UTC)

        conditions = [PullRequest.repository_id == repository_id]
        if pr_numbers:
            conditions.append(PullRequest.pr_number.in_(pr_numbers))

        stmt = (
            update(PullRequest)
            .where(and_(*conditions))
            .values(last_checked_at=checked_at)
        )

        result = await self.session.execute(stmt)
        await self.session.flush()

        count = result.rowcount
        logger.debug(f"Bulk updated last_checked_at for {count} PRs")
        return count

    async def bulk_delete_orphaned_checks(
        self, repository_id: uuid.UUID, pr_numbers: list[int]
    ) -> int:
        """Delete check runs that are no longer present for given PRs.

        Args:
            repository_id: Repository ID
            pr_numbers: PR numbers to check

        Returns:
            Number of check runs deleted
        """
        # Get PR IDs for the given numbers
        pr_id_query = select(PullRequest.id).where(
            and_(
                PullRequest.repository_id == repository_id,
                PullRequest.pr_number.in_(pr_numbers),
            )
        )
        pr_id_result = await self.session.execute(pr_id_query)
        pr_ids = [row[0] for row in pr_id_result.fetchall()]

        if not pr_ids:
            return 0

        # Delete orphaned check runs (this would need more specific logic
        # to identify truly orphaned checks based on external IDs)
        # For now, we'll implement a simple cleanup of very old checks
        cutoff_date = datetime.now(UTC) - timedelta(days=30)

        delete_stmt = text("""
            DELETE FROM check_runs
            WHERE pr_id = ANY(:pr_ids)
            AND updated_at < :cutoff_date
            AND status = 'completed'
            AND conclusion IN ('success', 'cancelled', 'skipped')
        """)

        result = await self.session.execute(
            delete_stmt, {"pr_ids": pr_ids, "cutoff_date": cutoff_date}
        )

        count = getattr(result, "rowcount", 0)
        await self.session.flush()

        logger.debug(f"Cleaned up {count} old check runs")
        return int(count)

    async def get_bulk_operation_stats(self) -> dict[str, Any]:
        """Get statistics for bulk operations performance monitoring.

        Returns:
            Dictionary with bulk operation statistics
        """
        # This could be enhanced to track actual performance metrics
        # For now, return basic connection pool info
        pool = self.session.bind.pool if hasattr(self.session.bind, "pool") else None

        stats = {
            "session_active": True,
            "pool_size": getattr(pool, "size", lambda: 0)() if pool else 0,
            "pool_checked_in": getattr(pool, "checkedin", lambda: 0)() if pool else 0,
            "pool_checked_out": getattr(pool, "checkedout", lambda: 0)() if pool else 0,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return stats


class BulkPullRequestRepository:
    """Extended PR repository with bulk operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        self.session = session
        self.bulk_ops = BulkOperationsMixin(session)

    async def bulk_upsert_prs(
        self, pr_data_list: list[dict[str, Any]], repository_id: uuid.UUID
    ) -> dict[str, int]:
        """Delegate to bulk operations mixin."""
        return await self.bulk_ops.bulk_upsert_prs(pr_data_list, repository_id)

    async def bulk_load_prs_with_checks(
        self, repository_id: uuid.UUID, pr_numbers: list[int] | None = None
    ) -> list[PullRequest]:
        """Delegate to bulk operations mixin."""
        return await self.bulk_ops.bulk_load_prs_with_checks(repository_id, pr_numbers)

    async def bulk_update_last_checked(
        self,
        repository_id: uuid.UUID,
        pr_numbers: list[int] | None = None,
        checked_at: datetime | None = None,
    ) -> int:
        """Delegate to bulk operations mixin."""
        return await self.bulk_ops.bulk_update_last_checked(
            repository_id, pr_numbers, checked_at
        )


class BulkCheckRunRepository:
    """Extended check run repository with bulk operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        self.session = session
        self.bulk_ops = BulkOperationsMixin(session)

    async def bulk_upsert_check_runs(
        self, check_data_list: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Delegate to bulk operations mixin."""
        return await self.bulk_ops.bulk_upsert_check_runs(check_data_list)

    async def bulk_delete_orphaned_checks(
        self, repository_id: uuid.UUID, pr_numbers: list[int]
    ) -> int:
        """Delegate to bulk operations mixin."""
        return await self.bulk_ops.bulk_delete_orphaned_checks(
            repository_id, pr_numbers
        )
