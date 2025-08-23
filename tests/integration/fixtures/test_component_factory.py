"""Tests for IntegrationComponentFactory to demonstrate usage and verify setup.

This test file serves as both validation for the component factory and
documentation for how to use it in integration tests.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from src.github.client import GitHubClient
from src.workers.discovery.interfaces import DiscoveryConfig
from sqlalchemy.ext.asyncio import AsyncSession

from .component_factory import (
    IntegrationComponentFactory,
    ComponentFactoryBuilder,
    IntegrationTestContext,
    TestEventPublisher,
    create_performance_testing_config,
    create_error_testing_config,
    create_minimal_testing_config,
)


class TestIntegrationComponentFactory:
    """Tests for component factory functionality."""

    @pytest.fixture
    def mock_database_session(self):
        """Mock database session for testing."""
        session = AsyncMock(spec=AsyncSession)
        session.commit = AsyncMock()
        session.rollback = AsyncMock() 
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def mock_github_client(self):
        """Mock GitHub client for testing."""
        client = MagicMock(spec=GitHubClient)
        client.base_url = "https://api.github.com"
        client.auth_provider = MagicMock()
        return client

    @pytest.fixture
    def component_factory(self, mock_database_session, mock_github_client):
        """Create component factory with mock dependencies."""
        return IntegrationComponentFactory(
            database_session=mock_database_session,
            github_client=mock_github_client,
            redis_url=None,  # Use memory cache
        )

    def test_component_factory_initialization(self, component_factory):
        """
        Why: Ensure component factory initializes correctly with all dependencies
        What: Tests that factory creates required repository instances and cache
        How: Validates factory initialization and dependency setup
        """
        # Verify factory has required attributes
        assert component_factory.database_session is not None
        assert component_factory.github_client is not None
        assert component_factory.cache is not None
        assert component_factory.event_publisher is not None

        # Verify repositories are initialized
        assert component_factory.repository_repo is not None
        assert component_factory.pr_repository is not None
        assert component_factory.check_repository is not None

    def test_create_discovery_engine_returns_configured_engine(self, component_factory):
        """
        Why: Ensure factory creates properly configured discovery engine
        What: Tests that create_discovery_engine returns real engine with dependencies
        How: Creates engine and validates all dependencies are properly injected
        """
        # Create engine with default config
        engine = component_factory.create_discovery_engine()

        # Verify engine is properly configured
        assert engine is not None
        assert engine.config is not None
        assert engine.pr_discovery is not None
        assert engine.check_discovery is not None
        assert engine.state_detector is not None
        assert engine.data_sync is not None
        assert engine.rate_limiter is not None
        assert engine.cache is not None
        assert engine.event_publisher is not None

        # Verify repositories are connected
        assert engine.repository_repo is not None
        assert engine.pr_repository is not None
        assert engine.check_repository is not None

    def test_create_discovery_engine_with_custom_config(self, component_factory):
        """
        Why: Ensure factory accepts custom configuration for discovery engine
        What: Tests that factory uses provided configuration for engine creation
        How: Creates engine with custom config and validates configuration is applied
        """
        # Create custom config
        custom_config = DiscoveryConfig(
            max_concurrent_repositories=20,
            max_prs_per_repository=200,
            cache_ttl_seconds=600,
        )

        # Create engine with custom config
        engine = component_factory.create_discovery_engine(config=custom_config)

        # Verify custom config is used
        assert engine.config.max_concurrent_repositories == 20
        assert engine.config.max_prs_per_repository == 200
        assert engine.config.cache_ttl_seconds == 600

    def test_create_repositories_returns_real_repositories(self, component_factory):
        """
        Why: Ensure factory creates real repository instances for database operations
        What: Tests that create_repositories returns properly configured repositories
        How: Creates repositories and validates they are real implementations
        """
        # Create repositories
        repo_repo, pr_repo, check_repo = component_factory.create_repositories()

        # Verify repositories are real implementations
        assert repo_repo is not None
        assert pr_repo is not None
        assert check_repo is not None

        # Verify they have the expected database session
        assert repo_repo.session is component_factory.database_session
        assert pr_repo.session is component_factory.database_session
        assert check_repo.session is component_factory.database_session

    def test_create_strategies_returns_real_implementations(self, component_factory):
        """
        Why: Ensure factory creates real strategy implementations for discovery
        What: Tests that factory creates functional PR and check discovery strategies
        How: Creates strategies and validates they are properly configured
        """
        # Create strategies
        pr_strategy = component_factory.create_pr_discovery_strategy()
        check_strategy = component_factory.create_check_discovery_strategy()
        state_detector = component_factory.create_state_detector()
        data_sync = component_factory.create_data_synchronization_strategy()
        rate_limiter = component_factory.create_rate_limiter()

        # Verify strategies are real implementations
        assert pr_strategy is not None
        assert check_strategy is not None
        assert state_detector is not None
        assert data_sync is not None
        assert rate_limiter is not None

    async def test_cleanup_handles_resource_disposal(self, component_factory):
        """
        Why: Ensure factory properly cleans up resources to prevent leaks
        What: Tests that cleanup method properly disposes of cache and database resources
        How: Calls cleanup and verifies proper resource disposal
        """
        # Call cleanup
        await component_factory.cleanup()

        # Verify database session was closed
        component_factory.database_session.close.assert_called_once()

    def test_test_event_publisher_records_events(self):
        """
        Why: Ensure test event publisher correctly records events for validation
        What: Tests that TestEventPublisher captures all published events
        How: Creates publisher, publishes events, validates event recording
        """
        # Create test event publisher
        publisher = TestEventPublisher()

        # Mock event data
        repository_id = uuid.uuid4()
        mock_pr = MagicMock()
        mock_pr.pr_number = 123
        mock_pr.title = "Test PR"

        # Publish event
        import asyncio
        asyncio.run(publisher.publish_new_pr(repository_id, mock_pr))

        # Verify event was recorded
        events = publisher.get_events_by_type("new_pr")
        assert len(events) == 1
        assert events[0]["repository_id"] == str(repository_id)
        assert events[0]["pr_number"] == 123
        assert events[0]["pr_title"] == "Test PR"


class TestComponentFactoryBuilder:
    """Tests for the component factory builder pattern."""

    def test_builder_creates_factory_with_required_dependencies(self):
        """
        Why: Ensure builder pattern correctly creates factory with all dependencies
        What: Tests that ComponentFactoryBuilder creates factory with proper setup
        How: Uses builder to create factory and validates configuration
        """
        # Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        client = MagicMock(spec=GitHubClient)

        # Build factory using builder pattern
        factory = (
            ComponentFactoryBuilder()
            .with_database_session(session)
            .with_github_client(client)
            .with_redis_url("redis://localhost:6379")
            .build()
        )

        # Verify factory is properly configured
        assert factory.database_session is session
        assert factory.github_client is client
        assert factory.redis_url == "redis://localhost:6379"

    def test_builder_raises_error_for_missing_dependencies(self):
        """
        Why: Ensure builder validates required dependencies are provided
        What: Tests that builder raises appropriate errors for missing dependencies
        How: Attempts to build factory without required dependencies
        """
        # Should raise error for missing database session
        with pytest.raises(ValueError, match="Database session is required"):
            ComponentFactoryBuilder().with_github_client(MagicMock()).build()

        # Should raise error for missing GitHub client
        with pytest.raises(ValueError, match="GitHub client is required"):
            ComponentFactoryBuilder().with_database_session(AsyncMock()).build()


class TestConfigurationPresets:
    """Tests for configuration preset functions."""

    def test_performance_testing_config_has_high_limits(self):
        """
        Why: Ensure performance testing config is optimized for high-load scenarios
        What: Tests that performance config has appropriate resource limits
        How: Creates performance config and validates resource limits
        """
        config = create_performance_testing_config()

        # Verify high performance settings
        assert config.max_concurrent_repositories == 20
        assert config.max_prs_per_repository == 500
        assert config.batch_size == 50
        assert config.discovery_timeout_seconds == 120
        assert config.priority_scheduling is True

    def test_error_testing_config_has_failure_inducing_settings(self):
        """
        Why: Ensure error testing config is designed to trigger failure conditions
        What: Tests that error config has settings that promote error scenarios
        How: Creates error config and validates failure-inducing settings
        """
        config = create_error_testing_config()

        # Verify error-inducing settings
        assert config.max_concurrent_repositories == 3
        assert config.discovery_timeout_seconds == 10  # Short timeout
        assert config.use_etag_caching is False  # Disable caching
        assert config.priority_scheduling is False

    def test_minimal_testing_config_has_fast_settings(self):
        """
        Why: Ensure minimal testing config optimizes for fast test execution
        What: Tests that minimal config has settings for quick test runs
        How: Creates minimal config and validates fast execution settings
        """
        config = create_minimal_testing_config()

        # Verify minimal/fast settings
        assert config.max_concurrent_repositories == 2
        assert config.max_prs_per_repository == 10
        assert config.batch_size == 2
        assert config.cache_ttl_seconds == 30


class TestIntegrationTestContext:
    """Tests for integration test context manager."""

    async def test_context_manager_provides_factory_and_cleanup(self):
        """
        Why: Ensure integration context properly manages factory lifecycle
        What: Tests that context manager creates factory and handles cleanup
        How: Uses context manager and validates factory creation and cleanup
        """
        # Mock dependencies
        session = AsyncMock(spec=AsyncSession)
        client = MagicMock(spec=GitHubClient)

        # Use context manager
        async with IntegrationTestContext(
            database_session=session,
            github_client=client,
        ) as factory:
            # Verify factory is created
            assert factory is not None
            assert isinstance(factory, IntegrationComponentFactory)

        # Verify cleanup was called
        session.close.assert_called_once()