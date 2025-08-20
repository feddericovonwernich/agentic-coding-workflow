"""Query optimization utilities and eager loading strategies."""

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import Select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, joinedload, selectinload

from ..models import CheckRun, PullRequest, Repository
from ..models.base import BaseModel

F = TypeVar("F", bound=Callable[..., Any])


class QueryOptimizer:
    """Utilities for optimizing database queries."""

    @staticmethod
    def optimize_relationship_loading(
        query: Select[Any],
        load_strategy: str = "selectin",
        relationships: list[str] | None = None,
    ) -> Select[Any]:
        """Add optimized relationship loading to query.

        Args:
            query: SQLAlchemy select query
            load_strategy: Loading strategy ('selectin', 'joined', 'eager')
            relationships: List of relationship names to load
        """
        if not relationships:
            return query

        if load_strategy == "selectin":
            for rel in relationships:
                query = query.options(
                    selectinload(getattr(query.column_descriptions[0]["type"], rel))
                )
        elif load_strategy == "joined":
            for rel in relationships:
                query = query.options(
                    joinedload(getattr(query.column_descriptions[0]["type"], rel))
                )

        return query

    @staticmethod
    def add_pagination_optimization(
        query: Select[Any],
        limit: int,
        offset: int = 0,
        order_by_id: bool = True,
    ) -> Select[Any]:
        """Add optimized pagination to query."""
        if order_by_id:
            # Ensure consistent ordering for pagination
            model = query.column_descriptions[0]["type"]
            query = query.order_by(model.id)

        return query.offset(offset).limit(limit)

    @staticmethod
    def optimize_count_query(query: Select[Any]) -> Select[Any]:
        """Optimize query for counting results."""
        # Remove unnecessary columns and ordering for count
        model = query.column_descriptions[0]["type"]
        return query.with_only_columns(model.id).order_by(None)

    @staticmethod
    def add_index_hints(
        query: Select[Any],
        hints: dict[str, str] | None = None,
    ) -> Select[Any]:
        """Add database-specific index hints to query.

        Args:
            query: SQLAlchemy select query
            hints: Dictionary of table -> index name mappings
        """
        # This would be database-specific implementation
        # For now, return query unchanged
        return query

    @staticmethod
    def batch_load_by_ids(
        session: AsyncSession,
        model_class: type[BaseModel],
        ids: list[Any],
        batch_size: int = 100,
    ) -> list[Select[Any]]:
        """Create batched queries for loading entities by IDs."""
        queries: list[Select[Any]] = []
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            query: Select[Any] = Select(model_class).where(
                model_class.id.in_(batch_ids)
            )
            queries.append(query)
        return queries


def eager_load_relationships(*relationships: str) -> Callable[[F], F]:
    """Decorator to automatically eager load relationships in repository methods."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # This is a simplified implementation
            # In practice, you'd need to modify the query before execution
            result = await func(*args, **kwargs)

            # If result is a query object, add eager loading
            if hasattr(result, "options"):
                for rel in relationships:
                    result = result.options(selectinload(rel))  # type: ignore

            return result

        return wrapper  # type: ignore

    return decorator


class PullRequestQueryOptimizer:
    """Specialized query optimizations for PullRequest queries."""

    @staticmethod
    def optimize_pr_with_checks_query(base_query: Select[Any]) -> Select[Any]:
        """Optimize query that loads PRs with their check runs."""
        return base_query.options(
            selectinload(PullRequest.check_runs),
            selectinload(PullRequest.repository),
        )

    @staticmethod
    def optimize_pr_with_history_query(base_query: Select[Any]) -> Select[Any]:
        """Optimize query that loads PRs with state history."""
        return base_query.options(
            selectinload(PullRequest.state_history),
            selectinload(PullRequest.repository),
        )

    @staticmethod
    def optimize_active_prs_query(base_query: Select[Any]) -> Select[Any]:
        """Optimize query for active PRs with minimal data."""
        return base_query.options(
            selectinload(PullRequest.repository).load_only(
                Repository.name, Repository.url
            ),
        )

    @staticmethod
    def create_efficient_failed_checks_query(session: AsyncSession) -> Select[Any]:
        """Create optimized query for PRs with failed checks using joins."""
        return (
            Select(PullRequest)
            .join(CheckRun)
            .where(
                and_(
                    CheckRun.status == "completed",
                    CheckRun.conclusion == "failure",
                )
            )
            .options(
                selectinload(PullRequest.repository),
                contains_eager(PullRequest.check_runs),
            )
            .distinct()
        )


class CheckRunQueryOptimizer:
    """Specialized query optimizations for CheckRun queries."""

    @staticmethod
    def optimize_check_runs_with_pr_query(base_query: Select[Any]) -> Select[Any]:
        """Optimize query that loads check runs with PR data."""
        return base_query.options(
            selectinload(CheckRun.pull_request).selectinload(PullRequest.repository),
        )

    @staticmethod
    def optimize_failed_checks_query(base_query: Select[Any]) -> Select[Any]:
        """Optimize query for failed check runs."""
        return base_query.where(
            and_(
                CheckRun.status == "completed",
                CheckRun.conclusion.in_(["failure", "timed_out"]),
            )
        ).options(
            selectinload(CheckRun.pull_request).load_only(
                PullRequest.pr_number, PullRequest.title, PullRequest.repository_id
            ),
        )


class RepositoryQueryOptimizer:
    """Specialized query optimizations for Repository queries."""

    @staticmethod
    def optimize_repositories_with_stats_query(base_query: Select[Any]) -> Select[Any]:
        """Optimize query that loads repositories with PR statistics."""
        return base_query.options(
            selectinload(Repository.pull_requests).load_only(
                PullRequest.state, PullRequest.draft
            ),
        )

    @staticmethod
    def optimize_active_repositories_query(base_query: Select[Any]) -> Select[Any]:
        """Optimize query for active repositories."""
        return base_query.where(Repository.status == "active").options(
            # Only load essential fields for monitoring
            Repository.id,  # type: ignore
            Repository.name,  # type: ignore
            Repository.url,  # type: ignore
            Repository.last_polled_at,  # type: ignore
            Repository.polling_interval_minutes,  # type: ignore
        )


class QueryBatchProcessor:
    """Process multiple queries efficiently."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def batch_load_entities(
        self,
        model_class: type[BaseModel],
        ids: list[Any],
        batch_size: int = 100,
    ) -> dict[Any, BaseModel]:
        """Load multiple entities by ID in batches."""
        results = {}

        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]

            query: Select[Any] = Select(model_class).where(
                model_class.id.in_(batch_ids)
            )
            result = await self.session.execute(query)
            entities = result.scalars().all()

            for entity in entities:
                results[entity.id] = entity

        return results

    async def batch_execute_queries(
        self,
        queries: list[Select[Any]],
        batch_size: int = 5,
    ) -> list[Any]:
        """Execute multiple queries in batches."""
        results = []

        for i in range(0, len(queries), batch_size):
            batch_queries = queries[i : i + batch_size]
            batch_results = []

            for query in batch_queries:
                result = await self.session.execute(query)
                batch_results.append(result.scalars().all())

            results.extend(batch_results)

        return results


class QueryPlanAnalyzer:
    """Analyze and suggest optimizations for query execution plans."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def analyze_query_plan(self, query: Select[Any]) -> dict[str, Any]:
        """Analyze execution plan for a query (PostgreSQL specific)."""
        try:
            # Get the compiled query
            compiled_query = query.compile(compile_kwargs={"literal_binds": True})

            # Execute EXPLAIN ANALYZE
            explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {compiled_query}"
            from sqlalchemy import text

            result = await self.session.execute(text(explain_query))
            plan_data = result.scalar()

            if plan_data is not None:
                return self._parse_execution_plan(plan_data[0])
            else:
                return {"error": "No execution plan data", "suggestions": []}

        except Exception as e:
            return {"error": str(e), "suggestions": []}

    def _parse_execution_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Parse PostgreSQL execution plan and provide suggestions."""
        suggestions: list[str] = []
        issues: list[str] = []

        # Analyze plan recursively
        self._analyze_plan_node(plan["Plan"], suggestions, issues)

        return {
            "execution_time": plan.get("Execution Time", 0),
            "planning_time": plan.get("Planning Time", 0),
            "total_cost": plan["Plan"]["Total Cost"],
            "issues": issues,
            "suggestions": suggestions,
            "raw_plan": plan,
        }

    def _analyze_plan_node(
        self, node: dict[str, Any], suggestions: list[str], issues: list[str]
    ) -> None:
        """Analyze a single node in the execution plan."""
        node_type = node.get("Node Type", "")

        # Check for expensive operations
        if node_type == "Seq Scan":
            table_name = node.get("Relation Name", "unknown")
            issues.append(f"Sequential scan on {table_name}")
            suggestions.append(f"Consider adding index on {table_name}")

        elif node_type == "Sort" and node.get("Sort Method") == "external merge":
            issues.append("External sort detected (using disk)")
            suggestions.append("Consider increasing work_mem or optimizing query")

        elif node_type == "Nested Loop" and node.get("Actual Rows", 0) > 10000:
            issues.append("Large nested loop detected")
            suggestions.append("Consider using hash join instead")

        # Analyze child nodes
        for child in node.get("Plans", []):
            self._analyze_plan_node(child, suggestions, issues)


# Pre-configured optimization strategies
OPTIMIZATION_STRATEGIES = {
    "pr_with_checks": PullRequestQueryOptimizer.optimize_pr_with_checks_query,
    "pr_with_history": PullRequestQueryOptimizer.optimize_pr_with_history_query,
    "active_prs": PullRequestQueryOptimizer.optimize_active_prs_query,
    "failed_checks": CheckRunQueryOptimizer.optimize_failed_checks_query,
    "check_runs_with_pr": CheckRunQueryOptimizer.optimize_check_runs_with_pr_query,
    "repositories_with_stats": (
        RepositoryQueryOptimizer.optimize_repositories_with_stats_query
    ),
    "active_repositories": RepositoryQueryOptimizer.optimize_active_repositories_query,
}


def apply_optimization_strategy(query: Select[Any], strategy: str) -> Select[Any]:
    """Apply a pre-configured optimization strategy to a query."""
    if strategy in OPTIMIZATION_STRATEGIES:
        return OPTIMIZATION_STRATEGIES[strategy](query)
    return query
