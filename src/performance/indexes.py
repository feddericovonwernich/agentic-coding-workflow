"""Database index optimization and suggestions."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@dataclass
class IndexSuggestion:
    """Suggestion for creating a database index."""

    table_name: str
    columns: list[str]
    index_type: str = "btree"
    partial_condition: str | None = None
    rationale: str = ""
    estimated_benefit: str = "medium"
    sql_command: str = ""


class IndexOptimizer:
    """Analyze queries and suggest optimal indexes."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    def get_recommended_indexes(self) -> list[IndexSuggestion]:
        """Get list of recommended indexes for the application."""
        suggestions = []

        # Repository indexes
        suggestions.extend(self._get_repository_indexes())

        # PullRequest indexes
        suggestions.extend(self._get_pull_request_indexes())

        # CheckRun indexes
        suggestions.extend(self._get_check_run_indexes())

        # PRStateHistory indexes
        suggestions.extend(self._get_state_history_indexes())

        return suggestions

    def _get_repository_indexes(self) -> list[IndexSuggestion]:
        """Get recommended indexes for repositories table."""
        return [
            IndexSuggestion(
                table_name="repositories",
                columns=["url"],
                index_type="btree",
                rationale="Fast lookup by repository URL for uniqueness checks",
                estimated_benefit="high",
                sql_command=(
                    "CREATE UNIQUE INDEX idx_repositories_url ON repositories(url);"
                ),
            ),
            IndexSuggestion(
                table_name="repositories",
                columns=["status"],
                index_type="btree",
                rationale="Filter active repositories for monitoring",
                estimated_benefit="medium",
                sql_command=(
                    "CREATE INDEX idx_repositories_status ON repositories(status);"
                ),
            ),
            IndexSuggestion(
                table_name="repositories",
                columns=["last_polled_at"],
                index_type="btree",
                partial_condition="status = 'active'",
                rationale="Find repositories needing polling",
                estimated_benefit="high",
                sql_command=(
                    "CREATE INDEX idx_repositories_polling ON "
                    "repositories(last_polled_at) WHERE status = 'active';"
                ),
            ),
            IndexSuggestion(
                table_name="repositories",
                columns=["failure_count"],
                index_type="btree",
                partial_condition="failure_count > 0",
                rationale="Monitor repositories with failures",
                estimated_benefit="medium",
                sql_command=(
                    "CREATE INDEX idx_repositories_failures ON "
                    "repositories(failure_count) WHERE failure_count > 0;"
                ),
            ),
        ]

    def _get_pull_request_indexes(self) -> list[IndexSuggestion]:
        """Get recommended indexes for pull_requests table."""
        return [
            IndexSuggestion(
                table_name="pull_requests",
                columns=["repository_id", "pr_number"],
                index_type="btree",
                rationale="Unique constraint and fast lookup by repo + PR number",
                estimated_benefit="high",
                sql_command=(
                    "CREATE UNIQUE INDEX idx_pull_requests_repo_number ON "
                    "pull_requests(repository_id, pr_number);"
                ),
            ),
            IndexSuggestion(
                table_name="pull_requests",
                columns=["state"],
                index_type="btree",
                rationale="Filter PRs by state (opened, closed, merged)",
                estimated_benefit="high",
                sql_command=(
                    "CREATE INDEX idx_pull_requests_state ON pull_requests(state);"
                ),
            ),
            IndexSuggestion(
                table_name="pull_requests",
                columns=["repository_id", "state"],
                index_type="btree",
                rationale="Get active PRs for a specific repository",
                estimated_benefit="high",
                sql_command=(
                    "CREATE INDEX idx_pull_requests_repo_state ON "
                    "pull_requests(repository_id, state);"
                ),
            ),
            IndexSuggestion(
                table_name="pull_requests",
                columns=["last_checked_at"],
                index_type="btree",
                partial_condition="state = 'opened'",
                rationale="Find PRs needing check updates",
                estimated_benefit="high",
                sql_command=(
                    "CREATE INDEX idx_pull_requests_check_needed ON "
                    "pull_requests(last_checked_at) WHERE state = 'opened';"
                ),
            ),
            IndexSuggestion(
                table_name="pull_requests",
                columns=["updated_at"],
                index_type="btree",
                rationale="Sort PRs by recency and find recent changes",
                estimated_benefit="medium",
                sql_command=(
                    "CREATE INDEX idx_pull_requests_updated_at ON "
                    "pull_requests(updated_at);"
                ),
            ),
            IndexSuggestion(
                table_name="pull_requests",
                columns=["author"],
                index_type="btree",
                rationale="Filter PRs by author for user-specific queries",
                estimated_benefit="medium",
                sql_command=(
                    "CREATE INDEX idx_pull_requests_author ON pull_requests(author);"
                ),
            ),
            IndexSuggestion(
                table_name="pull_requests",
                columns=["draft"],
                index_type="btree",
                partial_condition="draft = false",
                rationale="Filter out draft PRs efficiently",
                estimated_benefit="medium",
                sql_command=(
                    "CREATE INDEX idx_pull_requests_non_draft ON "
                    "pull_requests(draft) WHERE draft = false;"
                ),
            ),
        ]

    def _get_check_run_indexes(self) -> list[IndexSuggestion]:
        """Get recommended indexes for check_runs table."""
        return [
            IndexSuggestion(
                table_name="check_runs",
                columns=["pr_id"],
                index_type="btree",
                rationale="Get all check runs for a PR",
                estimated_benefit="high",
                sql_command="CREATE INDEX idx_check_runs_pr_id ON check_runs(pr_id);",
            ),
            IndexSuggestion(
                table_name="check_runs",
                columns=["external_id"],
                index_type="btree",
                rationale="Fast lookup by external check ID from GitHub",
                estimated_benefit="high",
                sql_command=(
                    "CREATE UNIQUE INDEX idx_check_runs_external_id ON "
                    "check_runs(external_id);"
                ),
            ),
            IndexSuggestion(
                table_name="check_runs",
                columns=["pr_id", "check_name"],
                index_type="btree",
                rationale="Find specific check type for a PR",
                estimated_benefit="high",
                sql_command=(
                    "CREATE INDEX idx_check_runs_pr_check_name ON "
                    "check_runs(pr_id, check_name);"
                ),
            ),
            IndexSuggestion(
                table_name="check_runs",
                columns=["status", "conclusion"],
                index_type="btree",
                rationale="Filter by check status and outcome",
                estimated_benefit="high",
                sql_command=(
                    "CREATE INDEX idx_check_runs_status_conclusion ON "
                    "check_runs(status, conclusion);"
                ),
            ),
            IndexSuggestion(
                table_name="check_runs",
                columns=["pr_id", "conclusion"],
                index_type="btree",
                partial_condition="status = 'completed'",
                rationale="Find failed checks for a PR efficiently",
                estimated_benefit="high",
                sql_command=(
                    "CREATE INDEX idx_check_runs_pr_failed ON "
                    "check_runs(pr_id, conclusion) WHERE status = 'completed';"
                ),
            ),
            IndexSuggestion(
                table_name="check_runs",
                columns=["updated_at"],
                index_type="btree",
                rationale="Sort check runs by recency",
                estimated_benefit="medium",
                sql_command=(
                    "CREATE INDEX idx_check_runs_updated_at ON check_runs(updated_at);"
                ),
            ),
        ]

    def _get_state_history_indexes(self) -> list[IndexSuggestion]:
        """Get recommended indexes for pr_state_history table."""
        return [
            IndexSuggestion(
                table_name="pr_state_history",
                columns=["pr_id"],
                index_type="btree",
                rationale="Get complete state history for a PR",
                estimated_benefit="high",
                sql_command=(
                    "CREATE INDEX idx_pr_state_history_pr_id ON "
                    "pr_state_history(pr_id);"
                ),
            ),
            IndexSuggestion(
                table_name="pr_state_history",
                columns=["pr_id", "created_at"],
                index_type="btree",
                rationale="Get state history in chronological order",
                estimated_benefit="high",
                sql_command=(
                    "CREATE INDEX idx_pr_state_history_pr_created ON "
                    "pr_state_history(pr_id, created_at);"
                ),
            ),
            IndexSuggestion(
                table_name="pr_state_history",
                columns=["trigger_event"],
                index_type="btree",
                rationale="Analyze specific types of state changes",
                estimated_benefit="medium",
                sql_command=(
                    "CREATE INDEX idx_pr_state_history_trigger ON "
                    "pr_state_history(trigger_event);"
                ),
            ),
            IndexSuggestion(
                table_name="pr_state_history",
                columns=["new_state"],
                index_type="btree",
                rationale="Find all transitions to a specific state",
                estimated_benefit="medium",
                sql_command=(
                    "CREATE INDEX idx_pr_state_history_new_state ON "
                    "pr_state_history(new_state);"
                ),
            ),
            IndexSuggestion(
                table_name="pr_state_history",
                columns=["created_at"],
                index_type="btree",
                rationale="Time-based analysis of state changes",
                estimated_benefit="medium",
                sql_command=(
                    "CREATE INDEX idx_pr_state_history_created_at ON "
                    "pr_state_history(created_at);"
                ),
            ),
        ]

    async def analyze_missing_indexes(
        self, session: AsyncSession
    ) -> list[IndexSuggestion]:
        """Analyze current database and suggest missing indexes."""
        existing_indexes = await self._get_existing_indexes(session)
        recommended_indexes = self.get_recommended_indexes()

        missing_indexes = []
        for suggestion in recommended_indexes:
            index_key = (suggestion.table_name, tuple(suggestion.columns))
            if index_key not in existing_indexes:
                missing_indexes.append(suggestion)

        return missing_indexes

    async def _get_existing_indexes(self, session: AsyncSession) -> set:
        """Get existing indexes from the database."""
        existing_indexes = set()

        # PostgreSQL specific query to get indexes
        query = text("""
            SELECT
                schemaname,
                tablename,
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname;
        """)

        try:
            result = await session.execute(query)
            for row in result:
                # Parse index definition to extract columns
                # This is a simplified approach
                table_name = row.tablename
                index_def = row.indexdef.lower()

                # Extract column names (simplified parsing)
                if "(" in index_def and ")" in index_def:
                    cols_part = index_def.split("(")[1].split(")")[0]
                    columns = tuple(col.strip() for col in cols_part.split(","))
                    existing_indexes.add((table_name, columns))

        except Exception as e:
            # Fallback for non-PostgreSQL databases or errors
            # Log the error for debugging but continue gracefully
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to get existing indexes: {e}")

        return existing_indexes

    async def generate_index_creation_script(
        self,
        session: AsyncSession,
        include_existing: bool = False,
    ) -> str:
        """Generate SQL script to create recommended indexes."""
        if include_existing:
            suggestions = self.get_recommended_indexes()
        else:
            suggestions = await self.analyze_missing_indexes(session)

        script_lines = [
            "-- Recommended database indexes for optimal performance",
            "-- Generated by IndexOptimizer",
            "",
        ]

        # Group by table for organization
        by_table: dict[str, list[IndexSuggestion]] = {}
        for suggestion in suggestions:
            if suggestion.table_name not in by_table:
                by_table[suggestion.table_name] = []
            by_table[suggestion.table_name].append(suggestion)

        for table_name, table_suggestions in by_table.items():
            script_lines.append(f"-- Indexes for {table_name} table")

            for suggestion in table_suggestions:
                script_lines.append(f"-- {suggestion.rationale}")
                script_lines.append(
                    f"-- Estimated benefit: {suggestion.estimated_benefit}"
                )
                script_lines.append(suggestion.sql_command)
                script_lines.append("")

        return "\n".join(script_lines)

    async def estimate_index_impact(
        self,
        session: AsyncSession,
        suggestion: IndexSuggestion,
    ) -> dict[str, Any]:
        """Estimate the performance impact of creating an index."""
        try:
            # Get table statistics
            table_stats = await self._get_table_stats(session, suggestion.table_name)

            # Estimate index size and creation time
            estimated_size_mb = (
                table_stats["row_count"] * len(suggestion.columns) * 8 / (1024 * 1024)
            )
            estimated_creation_time = max(1, estimated_size_mb / 100)  # Rough estimate

            # Estimate query improvement
            selectivity = await self._estimate_column_selectivity(
                session, suggestion.table_name, suggestion.columns
            )

            return {
                "estimated_size_mb": round(estimated_size_mb, 2),
                "estimated_creation_time_minutes": round(estimated_creation_time, 1),
                "column_selectivity": selectivity,
                "potential_speedup": self._calculate_potential_speedup(selectivity),
                "table_size_mb": table_stats["size_mb"],
                "table_row_count": table_stats["row_count"],
            }

        except Exception as e:
            return {"error": str(e)}

    async def _get_table_stats(
        self, session: AsyncSession, table_name: str
    ) -> dict[str, Any]:
        """Get table statistics."""
        try:
            # PostgreSQL specific
            query = text("""
                SELECT
                    schemaname,
                    tablename,
                    attname,
                    null_frac,
                    avg_width,
                    n_distinct,
                    correlation
                FROM pg_stats
                WHERE tablename = :table_name;
            """)

            result = await session.execute(query, {"table_name": table_name})
            stats = result.fetchall()

            # Get table size
            size_query = text("""
                SELECT
                    pg_size_pretty(
                        pg_total_relation_size(:table_name::regclass)
                    ) as size,
                    pg_total_relation_size(:table_name::regclass) as size_bytes,
                    (
                        SELECT reltuples
                        FROM pg_class
                        WHERE relname = :table_name
                    ) as row_count;
            """)

            size_result = await session.execute(size_query, {"table_name": table_name})
            size_info = size_result.fetchone()

            return {
                "size_mb": size_info.size_bytes / (1024 * 1024)
                if size_info and size_info.size_bytes
                else 0,
                "row_count": int(size_info.row_count)
                if size_info and size_info.row_count
                else 0,
                "column_stats": [dict(row._mapping) for row in stats],
            }

        except Exception:
            return {"size_mb": 0, "row_count": 0, "column_stats": []}

    async def _estimate_column_selectivity(
        self, session: AsyncSession, table_name: str, columns: list[str]
    ) -> float:
        """Estimate selectivity of columns for index effectiveness."""
        try:
            # Simple approach: get distinct count for first column
            if not columns:
                return 0.5

            # Validate identifiers to prevent SQL injection
            safe_table_name = self._validate_identifier(table_name)
            safe_column_name = self._validate_identifier(columns[0])

            if not safe_table_name or not safe_column_name:
                return 0.5  # Invalid identifiers

            # Use text() with safe identifiers (already validated)
            # SQL injection is prevented by identifier validation above
            query_str = f"""
                SELECT
                    COUNT(DISTINCT {safe_column_name}) as distinct_count,
                    COUNT(*) as total_count
                FROM {safe_table_name};
            """  # nosec B608
            query = text(query_str)

            result = await session.execute(query)
            row = result.fetchone()

            if row and row.total_count > 0:
                return float(row.distinct_count / row.total_count)

            return 0.5  # Default selectivity

        except Exception:
            return 0.5

    def _validate_identifier(self, identifier: str) -> str | None:
        """Validate SQL identifier to prevent injection.

        Returns the identifier if valid, None if invalid.
        """
        if not identifier:
            return None

        # Only allow alphanumeric characters and underscores
        # Must start with letter or underscore
        import re

        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
            return None

        # Additional length check
        if len(identifier) > 63:  # PostgreSQL identifier limit
            return None

        return identifier

    def _calculate_potential_speedup(self, selectivity: float) -> str:
        """Calculate potential query speedup based on selectivity."""
        if selectivity < 0.01:  # Very selective
            return "10x-100x faster"
        elif selectivity < 0.1:  # Moderately selective
            return "2x-10x faster"
        elif selectivity < 0.5:  # Somewhat selective
            return "1.5x-3x faster"
        else:  # Not very selective
            return "Minimal improvement"


class IndexMaintenanceManager:
    """Manage index maintenance and monitoring."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def analyze_index_usage(self, session: AsyncSession) -> dict[str, Any]:
        """Analyze how indexes are being used."""
        try:
            # PostgreSQL specific query for index usage stats
            query = text("""
                SELECT
                    schemaname,
                    tablename,
                    indexname,
                    idx_tup_read,
                    idx_tup_fetch,
                    idx_scan
                FROM pg_stat_user_indexes
                ORDER BY idx_scan DESC;
            """)

            result = await session.execute(query)
            usage_stats = [dict(row._mapping) for row in result]

            # Identify unused indexes
            unused_indexes = [stat for stat in usage_stats if stat["idx_scan"] == 0]

            # Identify heavily used indexes
            heavy_indexes = [stat for stat in usage_stats if stat["idx_scan"] > 1000]

            return {
                "total_indexes": len(usage_stats),
                "unused_indexes": len(unused_indexes),
                "heavily_used_indexes": len(heavy_indexes),
                "usage_details": usage_stats[:20],  # Top 20
                "unused_details": unused_indexes,
            }

        except Exception as e:
            return {"error": str(e)}

    async def get_index_health_report(self, session: AsyncSession) -> dict[str, Any]:
        """Generate comprehensive index health report."""
        optimizer = IndexOptimizer(self.engine)

        usage_stats = await self.analyze_index_usage(session)
        missing_indexes = await optimizer.analyze_missing_indexes(session)

        return {
            "summary": {
                "total_indexes": usage_stats.get("total_indexes", 0),
                "unused_indexes": usage_stats.get("unused_indexes", 0),
                "missing_recommended": len(missing_indexes),
                "health_score": self._calculate_health_score(
                    usage_stats, missing_indexes
                ),
            },
            "recommendations": {
                "create_indexes": [
                    {
                        "table": idx.table_name,
                        "columns": idx.columns,
                        "benefit": idx.estimated_benefit,
                        "rationale": idx.rationale,
                    }
                    for idx in missing_indexes[:5]  # Top 5
                ],
                "consider_dropping": [
                    idx["indexname"]
                    for idx in usage_stats.get("unused_details", [])[:5]
                ],
            },
            "usage_analysis": usage_stats,
        }

    def _calculate_health_score(
        self, usage_stats: dict[str, Any], missing_indexes: list[IndexSuggestion]
    ) -> int:
        """Calculate index health score (0-100)."""
        score = 100

        # Penalize unused indexes
        unused_count = usage_stats.get("unused_indexes", 0)
        total_count = usage_stats.get("total_indexes", 1)
        unused_ratio = unused_count / max(total_count, 1)
        score -= int(unused_ratio * 20)  # Up to -20 points

        # Penalize missing critical indexes
        critical_missing = len(
            [idx for idx in missing_indexes if idx.estimated_benefit == "high"]
        )
        score -= critical_missing * 15  # -15 per critical missing index

        # Penalize missing medium importance indexes
        medium_missing = len(
            [idx for idx in missing_indexes if idx.estimated_benefit == "medium"]
        )
        score -= medium_missing * 5  # -5 per medium missing index

        return max(0, min(100, score))
