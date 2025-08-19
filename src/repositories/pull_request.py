"""PullRequest repository with domain-specific operations."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import CheckRun, PRState, PullRequest, Repository, TriggerEvent
from .base import BaseRepository


class PullRequestRepository(BaseRepository[PullRequest]):
    """Repository for PullRequest operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, PullRequest)

    async def get_by_repo_and_number(
        self, 
        repository_id: uuid.UUID, 
        pr_number: int
    ) -> Optional[PullRequest]:
        """Get PR by repository ID and PR number."""
        query = (
            select(PullRequest)
            .where(
                and_(
                    PullRequest.repository_id == repository_id,
                    PullRequest.pr_number == pr_number
                )
            )
            .options(
                selectinload(PullRequest.repository),
                selectinload(PullRequest.check_runs),
                selectinload(PullRequest.state_history)
            )
        )
        return await self._execute_single_query(query)

    async def get_by_repo_url_and_number(
        self, 
        repo_url: str, 
        pr_number: int
    ) -> Optional[PullRequest]:
        """Get PR by repository URL and PR number."""
        query = (
            select(PullRequest)
            .join(Repository)
            .where(
                and_(
                    Repository.url == repo_url,
                    PullRequest.pr_number == pr_number
                )
            )
            .options(
                selectinload(PullRequest.repository),
                selectinload(PullRequest.check_runs),
                selectinload(PullRequest.state_history)
            )
        )
        return await self._execute_single_query(query)

    async def get_active_prs_for_repo(
        self, 
        repository_id: uuid.UUID,
        include_drafts: bool = False
    ) -> list[PullRequest]:
        """Get all active PRs for a repository."""
        conditions = [
            PullRequest.repository_id == repository_id,
            PullRequest.state == PRState.OPENED
        ]
        
        if not include_drafts:
            conditions.append(PullRequest.draft == False)
        
        query = (
            select(PullRequest)
            .where(and_(*conditions))
            .order_by(desc(PullRequest.created_at))
            .options(
                selectinload(PullRequest.repository),
                selectinload(PullRequest.check_runs)
            )
        )
        return await self._execute_query(query)

    async def get_prs_needing_check(
        self, 
        last_checked_before: datetime,
        limit: Optional[int] = None
    ) -> list[PullRequest]:
        """Get PRs that need checking (haven't been checked recently)."""
        conditions = [
            PullRequest.state == PRState.OPENED,
            or_(
                PullRequest.last_checked_at.is_(None),
                PullRequest.last_checked_at < last_checked_before
            )
        ]
        
        query = (
            select(PullRequest)
            .where(and_(*conditions))
            .order_by(PullRequest.last_checked_at.asc().nulls_first())
            .options(
                selectinload(PullRequest.repository),
                selectinload(PullRequest.check_runs)
            )
        )
        
        if limit:
            query = query.limit(limit)
            
        return await self._execute_query(query)

    async def update_state(
        self,
        pr_id: uuid.UUID,
        new_state: PRState,
        trigger_event: TriggerEvent,
        metadata: Optional[dict[str, Any]] = None
    ) -> PullRequest:
        """Update PR state and create state history record."""
        from .state_history import PRStateHistoryRepository
        
        # Get the PR
        pr = await self.get_by_id_or_raise(pr_id)
        old_state = pr.state
        
        # Validate transition
        if not pr.can_transition_to(new_state):
            raise ValueError(f"Invalid state transition from {old_state} to {new_state}")
        
        # Update PR state
        pr.state = new_state
        if metadata:
            if pr.pr_metadata is None:
                pr.pr_metadata = {}
            pr.pr_metadata.update(metadata)
        
        # Create state history record
        history_repo = PRStateHistoryRepository(self.session)
        await history_repo.create_transition(
            pr_id=pr_id,
            old_state=old_state,
            new_state=new_state,
            trigger_event=trigger_event,
            metadata=metadata
        )
        
        await self.flush()
        await self.refresh(pr)
        return pr

    async def mark_as_checked(self, pr_id: uuid.UUID) -> PullRequest:
        """Mark PR as checked (update last_checked_at)."""
        pr = await self.get_by_id_or_raise(pr_id)
        pr.last_checked_at = datetime.now(timezone.utc)
        await self.flush()
        await self.refresh(pr)
        return pr

    async def get_prs_with_failed_checks(
        self, 
        repository_id: Optional[uuid.UUID] = None,
        limit: Optional[int] = None
    ) -> list[PullRequest]:
        """Get PRs that have failed check runs."""
        # Build subquery for PRs with failed checks
        failed_checks_subquery = (
            select(CheckRun.pr_id)
            .where(
                and_(
                    CheckRun.status == "completed",
                    CheckRun.conclusion == "failure"
                )
            )
            .distinct()
        )
        
        conditions = [
            PullRequest.state == PRState.OPENED,
            PullRequest.id.in_(failed_checks_subquery)
        ]
        
        if repository_id:
            conditions.append(PullRequest.repository_id == repository_id)
        
        query = (
            select(PullRequest)
            .where(and_(*conditions))
            .order_by(desc(PullRequest.updated_at))
            .options(
                selectinload(PullRequest.repository),
                selectinload(PullRequest.check_runs)
            )
        )
        
        if limit:
            query = query.limit(limit)
            
        return await self._execute_query(query)

    async def get_recent_prs(
        self,
        since: datetime,
        repository_id: Optional[uuid.UUID] = None,
        states: Optional[list[PRState]] = None,
        limit: Optional[int] = None
    ) -> list[PullRequest]:
        """Get PRs created or updated since a given time."""
        conditions = [
            or_(
                PullRequest.created_at >= since,
                PullRequest.updated_at >= since
            )
        ]
        
        if repository_id:
            conditions.append(PullRequest.repository_id == repository_id)
        
        if states:
            conditions.append(PullRequest.state.in_(states))
        
        query = (
            select(PullRequest)
            .where(and_(*conditions))
            .order_by(desc(PullRequest.updated_at))
            .options(
                selectinload(PullRequest.repository),
                selectinload(PullRequest.check_runs)
            )
        )
        
        if limit:
            query = query.limit(limit)
            
        return await self._execute_query(query)

    async def get_pr_statistics(
        self, 
        repository_id: Optional[uuid.UUID] = None
    ) -> dict[str, Any]:
        """Get statistics about PRs."""
        # Base query conditions
        conditions = []
        if repository_id:
            conditions.append(PullRequest.repository_id == repository_id)
        
        # Count by state
        state_counts = {}
        for state in PRState:
            count_conditions = conditions + [PullRequest.state == state]
            count_query = select(func.count(PullRequest.id)).where(and_(*count_conditions))
            result = await self.session.execute(count_query)
            state_counts[state.value] = result.scalar_one()
        
        # Count active (opened) PRs
        active_conditions = conditions + [
            PullRequest.state == PRState.OPENED,
            PullRequest.draft == False
        ]
        active_query = select(func.count(PullRequest.id)).where(and_(*active_conditions))
        result = await self.session.execute(active_query)
        active_count = result.scalar_one()
        
        # Count draft PRs
        draft_conditions = conditions + [
            PullRequest.state == PRState.OPENED,
            PullRequest.draft == True
        ]
        draft_query = select(func.count(PullRequest.id)).where(and_(*draft_conditions))
        result = await self.session.execute(draft_query)
        draft_count = result.scalar_one()
        
        return {
            "total": sum(state_counts.values()),
            "by_state": state_counts,
            "active": active_count,
            "draft": draft_count,
        }

    async def search_prs(
        self,
        query_text: Optional[str] = None,
        author: Optional[str] = None,
        state: Optional[PRState] = None,
        repository_id: Optional[uuid.UUID] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> list[PullRequest]:
        """Search PRs with various filters."""
        conditions = []
        
        if query_text:
            conditions.append(
                or_(
                    PullRequest.title.ilike(f"%{query_text}%"),
                    PullRequest.body.ilike(f"%{query_text}%")
                )
            )
        
        if author:
            conditions.append(PullRequest.author.ilike(f"%{author}%"))
        
        if state:
            conditions.append(PullRequest.state == state)
        
        if repository_id:
            conditions.append(PullRequest.repository_id == repository_id)
        
        query = (
            select(PullRequest)
            .where(and_(*conditions) if conditions else True)
            .order_by(desc(PullRequest.updated_at))
            .options(
                selectinload(PullRequest.repository),
                selectinload(PullRequest.check_runs)
            )
        )
        
        if offset:
            query = query.offset(offset)
        
        if limit:
            query = query.limit(limit)
            
        return await self._execute_query(query)

    async def bulk_update_last_checked(
        self, 
        pr_ids: list[uuid.UUID], 
        checked_at: Optional[datetime] = None
    ) -> int:
        """Bulk update last_checked_at for multiple PRs."""
        if not pr_ids:
            return 0
            
        if checked_at is None:
            checked_at = datetime.now(timezone.utc)
        
        from sqlalchemy import update
        
        stmt = (
            update(PullRequest)
            .where(PullRequest.id.in_(pr_ids))
            .values(last_checked_at=checked_at)
        )
        
        result = await self.session.execute(stmt)
        await self.flush()
        return result.rowcount