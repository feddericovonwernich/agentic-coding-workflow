"""CheckRun repository with domain-specific operations."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import CheckConclusion, CheckRun, CheckStatus

from .base import BaseRepository


class CheckRunRepository(BaseRepository[CheckRun]):
    """Repository for CheckRun operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, CheckRun)

    async def get_by_external_id(self, external_id: str) -> CheckRun | None:
        """Get check run by external (GitHub) ID."""
        query = (
            select(CheckRun)
            .where(CheckRun.external_id == external_id)
            .options(
                selectinload(CheckRun.pull_request),
                selectinload(CheckRun.analysis_results),
            )
        )
        return await self._execute_single_query(query)

    async def get_by_pr_and_check_name(
        self, pr_id: uuid.UUID, check_name: str
    ) -> CheckRun | None:
        """Get check run by PR ID and check name (most recent)."""
        query = (
            select(CheckRun)
            .where(and_(CheckRun.pr_id == pr_id, CheckRun.check_name == check_name))
            .order_by(desc(CheckRun.created_at))
            .options(
                selectinload(CheckRun.pull_request),
                selectinload(CheckRun.analysis_results),
            )
        )
        return await self._execute_single_query(query)

    async def get_all_for_pr(self, pr_id: uuid.UUID) -> list[CheckRun]:
        """Get all check runs for a PR."""
        query = (
            select(CheckRun)
            .where(CheckRun.pr_id == pr_id)
            .order_by(desc(CheckRun.created_at))
            .options(selectinload(CheckRun.analysis_results))
        )
        return await self._execute_query(query)

    async def get_latest_for_pr(self, pr_id: uuid.UUID) -> list[CheckRun]:
        """Get the latest check run for each check name for a PR."""
        # Subquery to get the latest created_at for each check_name
        latest_subquery = (
            select(
                CheckRun.check_name,
                func.max(CheckRun.created_at).label("latest_created_at"),
            )
            .where(CheckRun.pr_id == pr_id)
            .group_by(CheckRun.check_name)
            .subquery()
        )

        # Main query to get the actual check runs
        query = (
            select(CheckRun)
            .join(
                latest_subquery,
                and_(
                    CheckRun.check_name == latest_subquery.c.check_name,
                    CheckRun.created_at == latest_subquery.c.latest_created_at,
                ),
            )
            .where(CheckRun.pr_id == pr_id)
            .order_by(CheckRun.check_name)
            .options(selectinload(CheckRun.analysis_results))
        )
        return await self._execute_query(query)

    async def get_failed_checks_for_pr(self, pr_id: uuid.UUID) -> list[CheckRun]:
        """Get all failed check runs for a PR (latest for each check name)."""
        latest_checks = await self.get_latest_for_pr(pr_id)
        return [check for check in latest_checks if check.is_failed]

    async def get_recent_failures(
        self, hours: int = 24, limit: int | None = None
    ) -> list[CheckRun]:
        """Get recent check run failures."""
        since = datetime.now(UTC).replace(hour=datetime.now(UTC).hour - hours)

        query = (
            select(CheckRun)
            .where(
                and_(
                    CheckRun.status == CheckStatus.COMPLETED,
                    CheckRun.conclusion == CheckConclusion.FAILURE,
                    CheckRun.created_at >= since,
                )
            )
            .order_by(desc(CheckRun.created_at))
            .options(
                selectinload(CheckRun.pull_request),
                selectinload(CheckRun.analysis_results),
            )
        )

        if limit:
            query = query.limit(limit)

        return await self._execute_query(query)

    async def update_status(
        self,
        check_run_id: uuid.UUID,
        status: CheckStatus,
        conclusion: CheckConclusion | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CheckRun:
        """Update check run status with validation."""
        check_run = await self.get_by_id_or_raise(check_run_id)

        # Use the model's validation method
        check_run.update_status(status, conclusion, metadata)

        await self.flush()
        await self.refresh(check_run)
        return check_run

    async def get_actionable_failures(self, limit: int | None = None) -> list[CheckRun]:
        """Get failed check runs that can be automatically fixed."""
        query = (
            select(CheckRun)
            .where(
                and_(
                    CheckRun.status == CheckStatus.COMPLETED,
                    CheckRun.conclusion == CheckConclusion.FAILURE,
                )
            )
            .order_by(desc(CheckRun.created_at))
            .options(
                selectinload(CheckRun.pull_request),
                selectinload(CheckRun.analysis_results),
            )
        )

        if limit:
            query = query.limit(limit)

        all_failures = await self._execute_query(query)

        # Filter for actionable failures using model method
        return [check for check in all_failures if check.is_actionable_failure()]

    async def get_checks_by_category(
        self,
        category: str,
        status: CheckStatus | None = None,
        conclusion: CheckConclusion | None = None,
        limit: int | None = None,
    ) -> list[CheckRun]:
        """Get check runs by failure category."""
        query = select(CheckRun)

        conditions = []
        if status:
            conditions.append(CheckRun.status == status)
        if conclusion:
            conditions.append(CheckRun.conclusion == conclusion)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(CheckRun.created_at)).options(
            selectinload(CheckRun.pull_request), selectinload(CheckRun.analysis_results)
        )

        if limit:
            query = query.limit(limit)

        all_checks = await self._execute_query(query)

        # Filter by category using model method
        return [
            check for check in all_checks if check.get_failure_category() == category
        ]

    async def get_check_statistics(
        self, pr_id: uuid.UUID | None = None, since: datetime | None = None
    ) -> dict[str, Any]:
        """Get check run statistics."""
        conditions = []

        if pr_id:
            conditions.append(CheckRun.pr_id == pr_id)

        if since:
            conditions.append(CheckRun.created_at >= since)

        # Count by status
        status_counts = {}
        for status in CheckStatus:
            status_conditions = [*conditions, CheckRun.status == status]
            count_query = select(func.count(CheckRun.id)).where(
                and_(*status_conditions)
            )
            result = await self.session.execute(count_query)
            status_counts[status.value] = result.scalar_one()

        # Count by conclusion (for completed checks)
        conclusion_counts = {}
        for conclusion in CheckConclusion:
            conclusion_conditions = [
                *conditions,
                CheckRun.status == CheckStatus.COMPLETED,
                CheckRun.conclusion == conclusion,
            ]
            count_query = select(func.count(CheckRun.id)).where(
                and_(*conclusion_conditions)
            )
            result = await self.session.execute(count_query)
            conclusion_counts[conclusion.value] = result.scalar_one()

        # Get failure rate
        total_completed_query = select(func.count(CheckRun.id)).where(
            and_(CheckRun.status == CheckStatus.COMPLETED, *conditions)
        )
        total_completed_result = await self.session.execute(total_completed_query)
        total_completed = total_completed_result.scalar_one()

        failed_count = conclusion_counts.get(CheckConclusion.FAILURE.value, 0)
        failure_rate = (failed_count / total_completed) if total_completed > 0 else 0.0

        return {
            "total": sum(status_counts.values()),
            "by_status": status_counts,
            "by_conclusion": conclusion_counts,
            "total_completed": total_completed,
            "failure_rate": failure_rate,
        }

    async def bulk_update_status(
        self,
        check_run_ids: list[uuid.UUID],
        status: CheckStatus,
        conclusion: CheckConclusion | None = None,
    ) -> int:
        """Bulk update status for multiple check runs."""
        if not check_run_ids:
            return 0

        values: dict[str, Any] = {"status": status}
        if conclusion:
            values["conclusion"] = conclusion

        stmt = update(CheckRun).where(CheckRun.id.in_(check_run_ids)).values(**values)

        result = await self.session.execute(stmt)
        await self.flush()
        return result.rowcount

    async def cleanup_old_checks(
        self, older_than: datetime, keep_latest_per_pr: int = 10
    ) -> int:
        """Clean up old check runs, keeping the latest N per PR."""
        # This is a complex operation that would need careful implementation
        # For now, return 0 as placeholder
        # TODO: Implement proper cleanup logic with ranking and deletion
        return 0

    async def get_check_duration_stats(
        self, check_name: str | None = None, since: datetime | None = None
    ) -> dict[str, Any]:
        """Get statistics about check run durations."""
        conditions = [
            CheckRun.status == CheckStatus.COMPLETED,
            CheckRun.started_at.is_not(None),
            CheckRun.completed_at.is_not(None),
        ]

        if check_name:
            conditions.append(CheckRun.check_name == check_name)

        if since:
            conditions.append(CheckRun.created_at >= since)

        # Calculate average duration
        duration_expr = func.extract(
            "epoch", CheckRun.completed_at - CheckRun.started_at
        )

        stats_query = select(
            func.avg(duration_expr).label("avg_duration"),
            func.min(duration_expr).label("min_duration"),
            func.max(duration_expr).label("max_duration"),
            func.count().label("count"),
        ).where(and_(*conditions))

        result = await self.session.execute(stats_query)
        row = result.fetchone()

        return {
            "count": row.count if row else 0,
            "avg_duration_seconds": float(row.avg_duration)
            if row and row.avg_duration
            else 0.0,
            "min_duration_seconds": float(row.min_duration)
            if row and row.min_duration
            else 0.0,
            "max_duration_seconds": float(row.max_duration)
            if row and row.max_duration
            else 0.0,
        }
