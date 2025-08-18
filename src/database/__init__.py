"""Database infrastructure module.

Provides database configuration, connection management, health monitoring,
and migration support for the agentic coding workflow system.
"""

from .config import (
    DatabaseConfig,
    DatabasePoolConfig,
    get_database_config,
    reset_database_config,
)
from .connection import (
    DatabaseConnectionManager,
    DatabaseRetry,
    check_database_health,
    close_database_connections,
    get_connection_manager,
    get_database_session,
    reset_connection_manager,
)
from .health import (
    DatabaseHealthChecker,
    DatabaseHealthReport,
    HealthCheckResult,
    HealthStatus,
    comprehensive_health_check,
    get_health_checker,
    quick_health_check,
    reset_health_checker,
)

__all__ = [
    # Configuration
    "DatabaseConfig",
    # Connection management
    "DatabaseConnectionManager",
    "DatabaseHealthChecker",
    "DatabaseHealthReport",
    "DatabasePoolConfig",
    "DatabaseRetry",
    "HealthCheckResult",
    # Health monitoring
    "HealthStatus",
    "check_database_health",
    "close_database_connections",
    "comprehensive_health_check",
    "get_connection_manager",
    "get_database_config",
    "get_database_session",
    "get_health_checker",
    "quick_health_check",
    "reset_connection_manager",
    "reset_database_config",
    "reset_health_checker",
]
