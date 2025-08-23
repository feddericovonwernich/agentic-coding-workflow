"""Health check endpoints and monitoring for PR Discovery system.

This module provides comprehensive health monitoring capabilities for all
discovery system components with detailed status reporting and alerting.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of individual health check."""

    name: str
    status: HealthStatus
    message: str
    details: dict[str, Any]
    timestamp: datetime
    response_time_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "response_time_ms": self.response_time_ms,
        }


class HealthCheckRegistry:
    """Registry for health check functions."""

    def __init__(self) -> None:
        """Initialize health check registry."""
        self.checks: dict[str, Callable] = {}
        self.check_configs: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        check_func: Callable,
        timeout_seconds: float = 10.0,
        required: bool = True,
    ) -> None:
        """Register a health check function.

        Args:
            name: Check name
            check_func: Async function that returns HealthCheckResult
            timeout_seconds: Timeout for the check
            required: Whether this check is required for overall health
        """
        self.checks[name] = check_func
        self.check_configs[name] = {
            "timeout_seconds": timeout_seconds,
            "required": required,
        }
        logger.debug(f"Registered health check: {name}")

    def unregister(self, name: str) -> None:
        """Unregister a health check.

        Args:
            name: Check name to remove
        """
        self.checks.pop(name, None)
        self.check_configs.pop(name, None)
        logger.debug(f"Unregistered health check: {name}")

    def get_check_names(self) -> list[str]:
        """Get list of registered check names."""
        return list(self.checks.keys())


class DiscoveryHealthMonitor:
    """Comprehensive health monitor for discovery system.

    Provides endpoints and methods for checking the health of all
    discovery components with configurable checks and alerting.
    """

    def __init__(self) -> None:
        """Initialize health monitor."""
        self.registry = HealthCheckRegistry()
        self.last_health_check: datetime | None = None
        self.cached_health_status: dict[str, Any] | None = None
        self.cache_ttl_seconds = 30  # Cache health status for 30 seconds

        # Health check history for trending
        self.health_history: list[dict[str, Any]] = []
        self.max_history_entries = 100

        # Component references (set by discovery engine)
        self.components: dict[str, Any] = {}

    def set_components(self, components: dict[str, Any]) -> None:
        """Set component references for health checks.

        Args:
            components: Dictionary of component instances
        """
        self.components = components
        logger.info(f"Health monitor configured with {len(components)} components")

    async def register_default_checks(self) -> None:
        """Register default health checks for discovery components."""
        # Database connectivity check
        self.registry.register(
            "database_connectivity",
            self._check_database_connectivity,
            timeout_seconds=5.0,
            required=True,
        )

        # GitHub API connectivity check
        self.registry.register(
            "github_api_connectivity",
            self._check_github_api_connectivity,
            timeout_seconds=10.0,
            required=True,
        )

        # Cache system health
        self.registry.register(
            "cache_system_health",
            self._check_cache_system_health,
            timeout_seconds=5.0,
            required=False,
        )

        # Rate limiter status
        self.registry.register(
            "rate_limiter_status",
            self._check_rate_limiter_status,
            timeout_seconds=2.0,
            required=False,
        )

        # Discovery engine status
        self.registry.register(
            "discovery_engine_status",
            self._check_discovery_engine_status,
            timeout_seconds=5.0,
            required=True,
        )

        # Resource utilization
        self.registry.register(
            "resource_utilization",
            self._check_resource_utilization,
            timeout_seconds=3.0,
            required=False,
        )

        logger.info(f"Registered {len(self.registry.checks)} default health checks")

    async def check_health(self, use_cache: bool = True) -> dict[str, Any]:
        """Perform comprehensive health check of all components.

        Args:
            use_cache: Whether to use cached results if available

        Returns:
            Comprehensive health status
        """
        # Check cache first
        if use_cache and self._is_cache_valid():
            logger.debug("Returning cached health status")
            if self.cached_health_status is None:
                raise RuntimeError("Cache is valid but cached health status is None")
            return self.cached_health_status

        start_time = datetime.now(UTC)

        # Run all health checks
        check_results = await self._run_all_checks()

        # Determine overall status
        overall_status = self._determine_overall_status(check_results)

        # Build comprehensive health report
        health_status = {
            "overall_status": overall_status.value,
            "timestamp": start_time.isoformat(),
            "checks": {result.name: result.to_dict() for result in check_results},
            "summary": self._build_summary(check_results),
            "uptime_info": self._get_uptime_info(),
            "version_info": self._get_version_info(),
        }

        # Update cache and history
        self.cached_health_status = health_status
        self.last_health_check = start_time
        self._update_health_history(health_status)

        logger.info(
            f"Health check completed: {overall_status.value} "
            f"({len(check_results)} checks)"
        )

        return health_status

    async def _run_all_checks(self) -> list[HealthCheckResult]:
        """Run all registered health checks concurrently."""
        if not self.registry.checks:
            logger.warning("No health checks registered")
            return []

        # Create check tasks
        check_tasks = []
        for name, check_func in self.registry.checks.items():
            config = self.registry.check_configs[name]
            task = self._run_single_check(name, check_func, config)
            check_tasks.append(task)

        # Run all checks concurrently
        results = await asyncio.gather(*check_tasks, return_exceptions=True)

        # Process results
        check_results = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                check_name = list(self.registry.checks.keys())[i]
                # Convert BaseException to Exception for compatibility
                if isinstance(result, Exception):
                    error = result
                else:
                    error = Exception(str(result))
                check_results.append(self._create_error_result(check_name, error))
            else:
                # At this point, result is HealthCheckResult
                check_results.append(result)

        return check_results

    async def _run_single_check(
        self, name: str, check_func: Callable, config: dict[str, Any]
    ) -> HealthCheckResult:
        """Run a single health check with timeout."""
        start_time = datetime.now(UTC)

        try:
            # Run check with timeout
            result = await asyncio.wait_for(
                check_func(), timeout=config["timeout_seconds"]
            )

            # Ensure result is HealthCheckResult
            if not isinstance(result, HealthCheckResult):
                result = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    message="Check returned invalid result",
                    details={"raw_result": str(result)},
                    timestamp=start_time,
                    response_time_ms=0.0,
                )

            # Update response time
            response_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            result.response_time_ms = response_time

            return result

        except TimeoutError:
            response_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            return HealthCheckResult(
                name=name,
                status=HealthStatus.CRITICAL,
                message=f"Health check timed out after {config['timeout_seconds']}s",
                details={"timeout_seconds": config["timeout_seconds"]},
                timestamp=start_time,
                response_time_ms=response_time,
            )

        except Exception as e:
            response_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            return self._create_error_result(name, e, start_time, response_time)

    def _create_error_result(
        self,
        name: str,
        error: Exception,
        timestamp: datetime | None = None,
        response_time_ms: float = 0.0,
    ) -> HealthCheckResult:
        """Create error result for failed health check."""
        return HealthCheckResult(
            name=name,
            status=HealthStatus.CRITICAL,
            message=f"Health check failed: {error!s}",
            details={"error_type": type(error).__name__, "error_message": str(error)},
            timestamp=timestamp or datetime.now(UTC),
            response_time_ms=response_time_ms,
        )

    def _determine_overall_status(
        self, check_results: list[HealthCheckResult]
    ) -> HealthStatus:
        """Determine overall health status from check results."""
        if not check_results:
            return HealthStatus.UNKNOWN

        # Check if any required checks are critical
        critical_required = any(
            result.status == HealthStatus.CRITICAL
            and self.registry.check_configs.get(result.name, {}).get("required", False)
            for result in check_results
        )

        if critical_required:
            return HealthStatus.CRITICAL

        # Count status occurrences
        status_counts: dict[HealthStatus, int] = {}
        for result in check_results:
            status = result.status
            status_counts[status] = status_counts.get(status, 0) + 1

        # Determine overall status based on priority
        if (
            HealthStatus.CRITICAL in status_counts
            and status_counts[HealthStatus.CRITICAL] > 0
        ):
            return HealthStatus.CRITICAL
        elif (
            HealthStatus.DEGRADED in status_counts
            and status_counts[HealthStatus.DEGRADED] > 0
        ):
            return HealthStatus.DEGRADED
        elif (
            HealthStatus.WARNING in status_counts
            and status_counts[HealthStatus.WARNING] > 0
        ):
            return HealthStatus.WARNING
        elif HealthStatus.HEALTHY in status_counts:
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN

    def _build_summary(self, check_results: list[HealthCheckResult]) -> dict[str, Any]:
        """Build summary statistics from check results."""
        if not check_results:
            return {}

        # Count by status
        status_counts: dict[str, int] = {}
        for result in check_results:
            status = result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        # Calculate response time stats
        response_times = [result.response_time_ms for result in check_results]
        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )

        return {
            "total_checks": len(check_results),
            "status_counts": status_counts,
            "avg_response_time_ms": avg_response_time,
            "max_response_time_ms": max(response_times) if response_times else 0,
            "failed_checks": [
                result.name
                for result in check_results
                if result.status in (HealthStatus.CRITICAL, HealthStatus.DEGRADED)
            ],
            "warning_checks": [
                result.name
                for result in check_results
                if result.status == HealthStatus.WARNING
            ],
        }

    def _is_cache_valid(self) -> bool:
        """Check if cached health status is still valid."""
        if not self.last_health_check or not self.cached_health_status:
            return False

        age = (datetime.now(UTC) - self.last_health_check).total_seconds()
        return age < self.cache_ttl_seconds

    def _update_health_history(self, health_status: dict[str, Any]) -> None:
        """Update health check history."""
        # Keep only essential info for history
        history_entry = {
            "timestamp": health_status["timestamp"],
            "overall_status": health_status["overall_status"],
            "total_checks": health_status["summary"]["total_checks"],
            "status_counts": health_status["summary"]["status_counts"],
            "avg_response_time_ms": health_status["summary"]["avg_response_time_ms"],
        }

        self.health_history.append(history_entry)

        # Maintain max history size
        if len(self.health_history) > self.max_history_entries:
            self.health_history = self.health_history[-self.max_history_entries :]

    def _get_uptime_info(self) -> dict[str, Any]:
        """Get system uptime information."""
        # This would typically track actual uptime
        # For now, return basic info
        return {
            "discovery_system": "running",
            "health_monitor_started": self.last_health_check.isoformat()
            if self.last_health_check
            else None,
        }

    def _get_version_info(self) -> dict[str, str]:
        """Get version information."""
        return {"discovery_system": "1.0.0", "health_monitor": "1.0.0"}

    # Default health check implementations

    async def _check_database_connectivity(self) -> HealthCheckResult:
        """Check database connectivity."""
        try:
            session = self.components.get("database_session")
            if not session:
                return HealthCheckResult(
                    name="database_connectivity",
                    status=HealthStatus.CRITICAL,
                    message="Database session not available",
                    details={},
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )

            # Simple connectivity test
            result = await session.execute("SELECT 1")
            row = result.scalar()

            if row == 1:
                return HealthCheckResult(
                    name="database_connectivity",
                    status=HealthStatus.HEALTHY,
                    message="Database connection successful",
                    details={"test_query": "SELECT 1"},
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )
            else:
                return HealthCheckResult(
                    name="database_connectivity",
                    status=HealthStatus.DEGRADED,
                    message="Database query returned unexpected result",
                    details={"result": row},
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )

        except Exception as e:
            return HealthCheckResult(
                name="database_connectivity",
                status=HealthStatus.CRITICAL,
                message=f"Database connection failed: {e!s}",
                details={"error": str(e)},
                timestamp=datetime.now(UTC),
                response_time_ms=0.0,
            )

    async def _check_github_api_connectivity(self) -> HealthCheckResult:
        """Check GitHub API connectivity."""
        try:
            github_client = self.components.get("github_client")
            if not github_client:
                return HealthCheckResult(
                    name="github_api_connectivity",
                    status=HealthStatus.CRITICAL,
                    message="GitHub client not available",
                    details={},
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )

            # Test API connectivity
            rate_limit_info = await github_client.get_rate_limit()

            # Check rate limit status
            core_limit = rate_limit_info.get("resources", {}).get("core", {})
            remaining = core_limit.get("remaining", 0)
            limit = core_limit.get("limit", 5000)

            if remaining < 100:
                status = HealthStatus.WARNING
                message = f"GitHub API rate limit low: {remaining}/{limit}"
            elif remaining < 10:
                status = HealthStatus.DEGRADED
                message = f"GitHub API rate limit critical: {remaining}/{limit}"
            else:
                status = HealthStatus.HEALTHY
                message = f"GitHub API connection healthy: {remaining}/{limit}"

            return HealthCheckResult(
                name="github_api_connectivity",
                status=status,
                message=message,
                details=rate_limit_info,
                timestamp=datetime.now(UTC),
                response_time_ms=0.0,
            )

        except Exception as e:
            return HealthCheckResult(
                name="github_api_connectivity",
                status=HealthStatus.CRITICAL,
                message=f"GitHub API connection failed: {e!s}",
                details={"error": str(e)},
                timestamp=datetime.now(UTC),
                response_time_ms=0.0,
            )

    async def _check_cache_system_health(self) -> HealthCheckResult:
        """Check cache system health."""
        try:
            cache = self.components.get("cache")
            if not cache:
                return HealthCheckResult(
                    name="cache_system_health",
                    status=HealthStatus.WARNING,
                    message="Cache not available",
                    details={},
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )

            # Test cache operations
            test_key = f"health_check_{int(datetime.now().timestamp())}"
            test_value = "health_test"

            # Test set and get
            await cache.set(test_key, test_value, ttl=60)
            retrieved_value = await cache.get(test_key)

            if retrieved_value == test_value:
                # Get cache stats if available
                cache_stats = {}
                if hasattr(cache, "get_stats"):
                    cache_stats = cache.get_stats()

                return HealthCheckResult(
                    name="cache_system_health",
                    status=HealthStatus.HEALTHY,
                    message="Cache system operational",
                    details=cache_stats,
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )
            else:
                return HealthCheckResult(
                    name="cache_system_health",
                    status=HealthStatus.DEGRADED,
                    message="Cache operations not working correctly",
                    details={"expected": test_value, "actual": retrieved_value},
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )

        except Exception as e:
            return HealthCheckResult(
                name="cache_system_health",
                status=HealthStatus.DEGRADED,
                message=f"Cache system error: {e!s}",
                details={"error": str(e)},
                timestamp=datetime.now(UTC),
                response_time_ms=0.0,
            )

    async def _check_rate_limiter_status(self) -> HealthCheckResult:
        """Check rate limiter status."""
        try:
            rate_limiter = self.components.get("rate_limiter")
            if not rate_limiter:
                return HealthCheckResult(
                    name="rate_limiter_status",
                    status=HealthStatus.WARNING,
                    message="Rate limiter not available",
                    details={},
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )

            # Get rate limiter status
            if hasattr(rate_limiter, "get_resource_status"):
                status_info = rate_limiter.get_resource_status()

                # Check if any resource is critically low
                critical_resources = []
                for resource, info in status_info.items():
                    info.get("current_tokens", 0)
                    info.get("capacity", 100)
                    utilization = info.get("utilization", 0)

                    if utilization > 0.9:  # > 90% utilized
                        critical_resources.append(resource)

                if critical_resources:
                    return HealthCheckResult(
                        name="rate_limiter_status",
                        status=HealthStatus.WARNING,
                        message=(
                            f"High utilization on resources: "
                            f"{', '.join(critical_resources)}"
                        ),
                        details=status_info,
                        timestamp=datetime.now(UTC),
                        response_time_ms=0.0,
                    )
                else:
                    return HealthCheckResult(
                        name="rate_limiter_status",
                        status=HealthStatus.HEALTHY,
                        message="Rate limiter status normal",
                        details=status_info,
                        timestamp=datetime.now(UTC),
                        response_time_ms=0.0,
                    )
            else:
                return HealthCheckResult(
                    name="rate_limiter_status",
                    status=HealthStatus.UNKNOWN,
                    message="Cannot get rate limiter status",
                    details={},
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )

        except Exception as e:
            return HealthCheckResult(
                name="rate_limiter_status",
                status=HealthStatus.WARNING,
                message=f"Rate limiter check failed: {e!s}",
                details={"error": str(e)},
                timestamp=datetime.now(UTC),
                response_time_ms=0.0,
            )

    async def _check_discovery_engine_status(self) -> HealthCheckResult:
        """Check discovery engine status."""
        try:
            discovery_engine = self.components.get("discovery_engine")
            if not discovery_engine:
                return HealthCheckResult(
                    name="discovery_engine_status",
                    status=HealthStatus.CRITICAL,
                    message="Discovery engine not available",
                    details={},
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )

            # Get discovery engine status
            status_info = await discovery_engine.get_discovery_status()

            overall_status = status_info.get("status", "unknown")
            current_cycle = status_info.get("current_cycle", {})

            if overall_status == "healthy":
                health_status = HealthStatus.HEALTHY
                message = "Discovery engine operating normally"
            elif overall_status == "running":
                health_status = HealthStatus.HEALTHY
                progress = current_cycle.get("progress_percentage", 0)
                message = f"Discovery cycle in progress ({progress:.1f}% complete)"
            elif overall_status == "degraded":
                health_status = HealthStatus.DEGRADED
                message = "Discovery engine performance degraded"
            else:
                health_status = HealthStatus.WARNING
                message = f"Discovery engine status: {overall_status}"

            return HealthCheckResult(
                name="discovery_engine_status",
                status=health_status,
                message=message,
                details=status_info,
                timestamp=datetime.now(UTC),
                response_time_ms=0.0,
            )

        except Exception as e:
            return HealthCheckResult(
                name="discovery_engine_status",
                status=HealthStatus.CRITICAL,
                message=f"Discovery engine check failed: {e!s}",
                details={"error": str(e)},
                timestamp=datetime.now(UTC),
                response_time_ms=0.0,
            )

    async def _check_resource_utilization(self) -> HealthCheckResult:
        """Check system resource utilization."""
        try:
            # This is a placeholder for actual resource monitoring
            # In production, you'd check memory, CPU, disk, etc.

            resource_info = {
                "memory_usage_percent": 45.0,  # Placeholder
                "cpu_usage_percent": 23.0,  # Placeholder
                "disk_usage_percent": 67.0,  # Placeholder
            }

            # Check thresholds
            high_usage = []
            for resource, usage in resource_info.items():
                if usage > 80.0:
                    high_usage.append(f"{resource}: {usage}%")

            if high_usage:
                return HealthCheckResult(
                    name="resource_utilization",
                    status=HealthStatus.WARNING,
                    message=f"High resource usage: {', '.join(high_usage)}",
                    details=resource_info,
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )
            else:
                return HealthCheckResult(
                    name="resource_utilization",
                    status=HealthStatus.HEALTHY,
                    message="Resource utilization normal",
                    details=resource_info,
                    timestamp=datetime.now(UTC),
                    response_time_ms=0.0,
                )

        except Exception as e:
            return HealthCheckResult(
                name="resource_utilization",
                status=HealthStatus.WARNING,
                message=f"Resource check failed: {e!s}",
                details={"error": str(e)},
                timestamp=datetime.now(UTC),
                response_time_ms=0.0,
            )

    def get_health_history(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get health check history for the last N hours.

        Args:
            hours: Hours of history to return

        Returns:
            List of historical health check results
        """
        cutoff_time = datetime.now(UTC) - timedelta(hours=hours)

        return [
            entry
            for entry in self.health_history
            if datetime.fromisoformat(entry["timestamp"]) >= cutoff_time
        ]

    def get_health_trends(self) -> dict[str, Any]:
        """Get health trends analysis.

        Returns:
            Health trends and patterns
        """
        if len(self.health_history) < 2:
            return {"error": "Insufficient data for trends"}

        # Analyze trends over last 24 hours
        recent_history = self.get_health_history(24)

        if not recent_history:
            return {"error": "No recent health data"}

        # Calculate status distribution
        status_counts: dict[str, int] = {}
        for entry in recent_history:
            status = entry["overall_status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        # Calculate average response times
        response_times = [
            entry.get("avg_response_time_ms", 0) for entry in recent_history
        ]
        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )

        return {
            "period_hours": 24,
            "total_checks": len(recent_history),
            "status_distribution": status_counts,
            "avg_response_time_ms": avg_response_time,
            "uptime_percentage": (
                status_counts.get("healthy", 0) / len(recent_history) * 100
                if recent_history
                else 0
            ),
            "generated_at": datetime.now(UTC).isoformat(),
        }
