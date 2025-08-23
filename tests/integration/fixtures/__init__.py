"""Integration test fixtures for real component testing.

This module provides pytest fixtures for real database integration, GitHub API 
mocking, and complete integration test contexts following the architectural plan.
"""

import asyncio
import pytest
import pytest_asyncio
import uuid
from typing import AsyncGenerator

# Component factory classes will be implemented in future phases
# from .component_factory import (
#     ComponentFactoryBuilder,
#     IntegrationComponentFactory,
#     IntegrationTestContext,
#     TestEventPublisher,
#     create_error_testing_config,
#     create_minimal_testing_config,
#     create_performance_testing_config,
# )

# Import database fixtures (with fallback for missing scratch_pad module)
try:
    from .database import (
        RealTestDatabaseManager, 
        get_test_database_manager,
        reset_test_database_manager
    )
    # Import directly from database module to avoid circular imports
    TestDatabaseContext = None
    PerformanceMetrics = None
    DATABASE_FIXTURES_AVAILABLE = True
except ImportError:
    # Fallback when scratch_pad module is not available
    DATABASE_FIXTURES_AVAILABLE = False
    RealTestDatabaseManager = None
    TestDatabaseContext = None
    PerformanceMetrics = None


if DATABASE_FIXTURES_AVAILABLE:
    @pytest_asyncio.fixture
    async def test_database_manager() -> AsyncGenerator[RealTestDatabaseManager, None]:
        """Provide test database manager for integration tests.
        
        Creates a fresh database manager instance for each test function,
        ensuring proper isolation and cleanup.
        """
        # Reset global manager to ensure clean state
        reset_test_database_manager()
        
        manager = get_test_database_manager()
        try:
            yield manager
        finally:
            # Cleanup any remaining resources
            reset_test_database_manager()


    @pytest_asyncio.fixture
    async def test_database_context(
        test_database_manager: RealTestDatabaseManager
    ) -> AsyncGenerator[TestDatabaseContext, None]:
        """Provide isolated test database context.
        
        Creates a real database instance with applied migrations and 
        transaction-based isolation for each test.
        """
        # Generate unique isolation ID for this test
        isolation_id = str(uuid.uuid4())
        
        # Create test database
        context = await test_database_manager.create_test_database(isolation_id)
        
        try:
            # Apply migrations
            await test_database_manager.apply_migrations(context)
            
            yield context
            
        finally:
            # Cleanup database
            await test_database_manager.cleanup_database(context)

    @pytest_asyncio.fixture
    async def seeded_database_context(
        test_database_manager: RealTestDatabaseManager,
        test_database_context: TestDatabaseContext
    ) -> AsyncGenerator[TestDatabaseContext, None]:
        """Provide database context with basic test data.
        
        Creates database with "basic_discovery" scenario data for tests
        that need some initial data to work with.
        """
        # Seed with basic discovery data
        await test_database_manager.seed_test_data(
            test_database_context, 
            "basic_discovery"
        )
        
        yield test_database_context

    @pytest_asyncio.fixture
    async def large_dataset_context(
        test_database_manager: RealTestDatabaseManager,
        test_database_context: TestDatabaseContext
    ) -> AsyncGenerator[TestDatabaseContext, None]:
        """Provide database context with large dataset for performance testing.
        
        Creates database with "large_repository" scenario data for performance
        and load testing scenarios.
        """
        # Seed with large repository data
        await test_database_manager.seed_test_data(
            test_database_context,
            "large_repository" 
        )
        
        yield test_database_context

    @pytest_asyncio.fixture
    async def error_conditions_context(
        test_database_manager: RealTestDatabaseManager,
        test_database_context: TestDatabaseContext
    ) -> AsyncGenerator[TestDatabaseContext, None]:
        """Provide database context with error condition data.
        
        Creates database with "error_conditions" scenario data for testing
        error handling and recovery mechanisms.
        """
        # Seed with error condition data
        await test_database_manager.seed_test_data(
            test_database_context,
            "error_conditions"
        )
        
        yield test_database_context

    @pytest_asyncio.fixture
    async def performance_metrics_collector(
        test_database_manager: RealTestDatabaseManager,
        test_database_context: TestDatabaseContext
    ) -> AsyncGenerator[tuple[TestDatabaseContext, callable], None]:
        """Provide database context with performance metrics collection.
        
        Returns tuple of (context, metrics_getter) where metrics_getter is a 
        callable that returns current performance metrics.
        """
        # Extract isolation ID from context
        isolation_id = None
        for handler in test_database_context.cleanup_handlers:
            # This is a bit of a hack to extract the isolation ID
            if hasattr(handler, '__closure__') and handler.__closure__:
                for cell in handler.__closure__:
                    if isinstance(cell.cell_contents, str) and cell.cell_contents.count('-') == 4:
                        isolation_id = cell.cell_contents
                        break
        
        def get_metrics() -> PerformanceMetrics | None:
            """Get current performance metrics."""
            if isolation_id:
                return test_database_manager.get_performance_metrics(isolation_id)
            return None
        
        yield test_database_context, get_metrics


# Pytest configuration for integration tests
def pytest_configure(config):
    """Configure pytest for integration testing."""
    # Add custom markers
    config.addinivalue_line(
        "markers", 
        "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", 
        "database: marks tests that require real database"
    )
    config.addinivalue_line(
        "markers", 
        "performance: marks tests as performance tests"
    )
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add appropriate markers."""
    for item in items:
        # Mark integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Mark database tests
        if any(fixture in item.fixturenames for fixture in [
            "test_database_context",
            "seeded_database_context", 
            "large_dataset_context",
            "error_conditions_context"
        ]):
            item.add_marker(pytest.mark.database)
        
        # Mark performance tests
        if "performance" in item.name or "performance_metrics_collector" in item.fixturenames:
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.slow)


# Export key classes and functions
__all__ = [
    # Component factory exports (will be added in future phases)
    # "IntegrationComponentFactory",
    # "ComponentFactoryBuilder", 
    # "IntegrationTestContext",
    # "TestEventPublisher",
    # "create_performance_testing_config",
    # "create_error_testing_config",
    # "create_minimal_testing_config",
]

# Add database fixtures to exports if available
if DATABASE_FIXTURES_AVAILABLE:
    __all__.extend([
        "RealTestDatabaseManager",
        "get_test_database_manager", 
        "reset_test_database_manager",
        "test_database_manager",
        "test_database_context",
        "seeded_database_context",
        "large_dataset_context", 
        "error_conditions_context",
        "performance_metrics_collector"
    ])