"""Database health monitoring and validation utilities.

Provides comprehensive health checks, monitoring capabilities, and validation
tools for database operations and connectivity.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .connection import DatabaseConnectionManager, get_connection_manager

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""

    name: str
    status: HealthStatus
    duration_ms: float
    details: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class DatabaseHealthReport:
    """Comprehensive database health report."""

    overall_status: HealthStatus
    checks: list[HealthCheckResult]
    timestamp: float
    total_duration_ms: float

    @property
    def is_healthy(self) -> bool:
        """Check if database is healthy."""
        return self.overall_status == HealthStatus.HEALTHY

    @property
    def failed_checks(self) -> list[HealthCheckResult]:
        """Get list of failed health checks."""
        return [check for check in self.checks if check.status != HealthStatus.HEALTHY]


class DatabaseHealthChecker:
    """Comprehensive database health monitoring.

    Provides various health checks including connectivity, performance,
    and operational status validation.
    """

    def __init__(self, connection_manager: DatabaseConnectionManager | None = None):
        self.connection_manager = connection_manager or get_connection_manager()

    async def check_connectivity(self) -> HealthCheckResult:
        """Test basic database connectivity.

        Returns:
            HealthCheckResult: Result of connectivity test
        """
        start_time = time.time()

        try:
            async with self.connection_manager.get_session() as session:
                result = await session.execute(text("SELECT 1"))
                value = result.scalar()

                duration_ms = (time.time() - start_time) * 1000

                if value == 1:
                    return HealthCheckResult(
                        name="connectivity",
                        status=HealthStatus.HEALTHY,
                        duration_ms=duration_ms,
                        details={"response": "Connected successfully"},
                    )
                return HealthCheckResult(
                    name="connectivity",
                    status=HealthStatus.UNHEALTHY,
                    duration_ms=duration_ms,
                    error="Unexpected response from database",
                )

        except SQLAlchemyError as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="connectivity",
                status=HealthStatus.UNHEALTHY,
                duration_ms=duration_ms,
                error=f"Database error: {e!s}",
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="connectivity",
                status=HealthStatus.UNHEALTHY,
                duration_ms=duration_ms,
                error=f"Unexpected error: {e!s}",
            )

    async def check_connection_pool(self) -> HealthCheckResult:
        """Check connection pool status and health.

        Returns:
            HealthCheckResult: Result of connection pool check
        """
        start_time = time.time()

        try:
            engine = self.connection_manager.engine
            pool = engine.pool

            # Get pool statistics
            pool_size = getattr(pool, "size", lambda: 0)()
            checked_out = getattr(pool, "checkedout", lambda: 0)()
            overflow = getattr(pool, "overflow", lambda: 0)()
            checked_in = getattr(pool, "checkedin", lambda: 0)()

            duration_ms = (time.time() - start_time) * 1000

            # Calculate pool utilization
            total_capacity = pool_size + overflow if overflow >= 0 else pool_size
            utilization = (
                (checked_out / total_capacity) * 100 if total_capacity > 0 else 0
            )

            details = {
                "pool_size": pool_size,
                "checked_out": checked_out,
                "checked_in": checked_in,
                "overflow": overflow,
                "utilization_percent": round(utilization, 2),
                "total_capacity": total_capacity,
            }

            # Determine health status based on utilization
            if utilization >= 95:
                status = HealthStatus.UNHEALTHY
                details["warning"] = "Connection pool nearly exhausted"
            elif utilization >= 80:
                status = HealthStatus.DEGRADED
                details["warning"] = "Connection pool utilization high"
            else:
                status = HealthStatus.HEALTHY

            return HealthCheckResult(
                name="connection_pool",
                status=status,
                duration_ms=duration_ms,
                details=details,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="connection_pool",
                status=HealthStatus.UNHEALTHY,
                duration_ms=duration_ms,
                error=f"Failed to check connection pool: {e!s}",
            )

    async def check_response_time(
        self, query_timeout: float = 1.0
    ) -> HealthCheckResult:
        """Check database response time with a simple query.

        Args:
            query_timeout: Maximum acceptable query time in seconds

        Returns:
            HealthCheckResult: Result of response time check
        """
        start_time = time.time()

        try:
            async with self.connection_manager.get_session() as session:
                # Use a slightly more complex query to test performance
                result = await session.execute(
                    text("SELECT COUNT(*) FROM information_schema.tables")
                )
                count = result.scalar()

                duration_ms = (time.time() - start_time) * 1000

                details = {
                    "query_duration_ms": duration_ms,
                    "timeout_ms": query_timeout * 1000,
                    "table_count": count,
                }

                if duration_ms > query_timeout * 1000:
                    return HealthCheckResult(
                        name="response_time",
                        status=HealthStatus.DEGRADED,
                        duration_ms=duration_ms,
                        details=details,
                        error=(
                            f"Query took {duration_ms:.2f}ms "
                            f"(timeout: {query_timeout * 1000}ms)"
                        ),
                    )
                return HealthCheckResult(
                    name="response_time",
                    status=HealthStatus.HEALTHY,
                    duration_ms=duration_ms,
                    details=details,
                )

        except TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="response_time",
                status=HealthStatus.UNHEALTHY,
                duration_ms=duration_ms,
                error=f"Query timed out after {duration_ms:.2f}ms",
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="response_time",
                status=HealthStatus.UNHEALTHY,
                duration_ms=duration_ms,
                error=f"Query failed: {e!s}",
            )

    async def check_database_version(self) -> HealthCheckResult:
        """Check database version and compatibility.

        Returns:
            HealthCheckResult: Result of version check
        """
        start_time = time.time()

        try:
            async with self.connection_manager.get_session() as session:
                result = await session.execute(text("SELECT version()"))
                version = result.scalar()

                duration_ms = (time.time() - start_time) * 1000

                details = {"version": version}

                # Check if PostgreSQL version is supported (12+)
                if version and "PostgreSQL" in version:
                    # Extract version number (e.g., "PostgreSQL 14.2")
                    try:
                        version_parts = version.split()
                        version_num = float(version_parts[1].split(".")[0])
                        details["major_version"] = version_num

                        if version_num >= 12:
                            status = HealthStatus.HEALTHY
                        elif version_num >= 10:
                            status = HealthStatus.DEGRADED
                            details["warning"] = (
                                "PostgreSQL version is older than recommended (12+)"
                            )
                        else:
                            status = HealthStatus.UNHEALTHY
                            details["error"] = (
                                "PostgreSQL version is too old (minimum: 10)"
                            )
                    except (IndexError, ValueError):
                        status = HealthStatus.DEGRADED
                        details["warning"] = "Could not parse PostgreSQL version"
                else:
                    status = HealthStatus.DEGRADED
                    details["warning"] = "Database is not PostgreSQL"

                return HealthCheckResult(
                    name="database_version",
                    status=status,
                    duration_ms=duration_ms,
                    details=details,
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="database_version",
                status=HealthStatus.UNHEALTHY,
                duration_ms=duration_ms,
                error=f"Failed to get database version: {e!s}",
            )

    async def check_write_permissions(self) -> HealthCheckResult:
        """Check if database has proper write permissions.

        Returns:
            HealthCheckResult: Result of write permission check
        """
        start_time = time.time()

        try:
            async with self.connection_manager.get_session() as session:
                # Try to create a temporary table
                await session.execute(
                    text("""
                    CREATE TEMP TABLE health_check_test (
                        id SERIAL PRIMARY KEY,
                        test_data VARCHAR(50)
                    )
                """)
                )

                # Try to insert data
                await session.execute(
                    text("""
                    INSERT INTO health_check_test (test_data)
                    VALUES ('health_check')
                """)
                )

                # Try to read data back
                result = await session.execute(
                    text("""
                    SELECT test_data FROM health_check_test LIMIT 1
                """)
                )
                test_data = result.scalar()

                # Clean up
                await session.execute(text("DROP TABLE health_check_test"))

                duration_ms = (time.time() - start_time) * 1000

                if test_data == "health_check":
                    return HealthCheckResult(
                        name="write_permissions",
                        status=HealthStatus.HEALTHY,
                        duration_ms=duration_ms,
                        details={"operations": ["create", "insert", "select", "drop"]},
                    )
                return HealthCheckResult(
                    name="write_permissions",
                    status=HealthStatus.UNHEALTHY,
                    duration_ms=duration_ms,
                    error="Data integrity check failed",
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name="write_permissions",
                status=HealthStatus.UNHEALTHY,
                duration_ms=duration_ms,
                error=f"Write permission test failed: {e!s}",
            )

    async def run_comprehensive_health_check(
        self, include_performance: bool = True, query_timeout: float = 1.0
    ) -> DatabaseHealthReport:
        """Run all health checks and generate comprehensive report.

        Args:
            include_performance: Whether to include performance tests
            query_timeout: Timeout for performance tests in seconds

        Returns:
            DatabaseHealthReport: Comprehensive health report
        """
        start_time = time.time()
        checks = []

        # Always run basic checks
        basic_checks = [
            self.check_connectivity(),
            self.check_connection_pool(),
            self.check_database_version(),
            self.check_write_permissions(),
        ]

        # Add performance checks if requested
        if include_performance:
            basic_checks.append(self.check_response_time(query_timeout))

        # Run all checks concurrently
        try:
            checks = await asyncio.gather(*basic_checks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Failed to run health checks: {e}")
            checks = []

        # Handle any exceptions in results
        final_checks: list[HealthCheckResult] = []
        for i, result in enumerate(checks):
            if isinstance(result, Exception):
                final_checks.append(
                    HealthCheckResult(
                        name=f"check_{i}",
                        status=HealthStatus.UNHEALTHY,
                        duration_ms=0,
                        error=f"Health check failed: {result!s}",
                    )
                )
            elif isinstance(result, HealthCheckResult):
                final_checks.append(result)

        total_duration_ms = (time.time() - start_time) * 1000

        # Determine overall status
        unhealthy_count = sum(
            1 for check in final_checks if check.status == HealthStatus.UNHEALTHY
        )
        degraded_count = sum(
            1 for check in final_checks if check.status == HealthStatus.DEGRADED
        )

        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return DatabaseHealthReport(
            overall_status=overall_status,
            checks=final_checks,
            timestamp=time.time(),
            total_duration_ms=total_duration_ms,
        )


# Global health checker instance
_health_checker: DatabaseHealthChecker | None = None


def get_health_checker() -> DatabaseHealthChecker:
    """Get global database health checker instance."""
    global _health_checker

    if _health_checker is None:
        _health_checker = DatabaseHealthChecker()

    return _health_checker


async def quick_health_check() -> bool:
    """Perform quick database health check.

    Returns:
        bool: True if database is healthy, False otherwise
    """
    health_checker = get_health_checker()
    connectivity_result = await health_checker.check_connectivity()
    return connectivity_result.status == HealthStatus.HEALTHY


async def comprehensive_health_check() -> DatabaseHealthReport:
    """Perform comprehensive database health check.

    Returns:
        DatabaseHealthReport: Detailed health report
    """
    health_checker = get_health_checker()
    return await health_checker.run_comprehensive_health_check()


def reset_health_checker() -> None:
    """Reset global health checker instance (useful for testing)."""
    global _health_checker
    _health_checker = None
