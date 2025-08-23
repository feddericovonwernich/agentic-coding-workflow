"""Example usage of IntegrationComponentFactory for real integration testing.

This file demonstrates how to use the IntegrationComponentFactory to create
real discovery components for integration testing scenarios.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from src.github.client import GitHubClient
from .component_factory import (
    IntegrationComponentFactory,
    ComponentFactoryBuilder,
    IntegrationTestContext,
    create_performance_testing_config,
    create_minimal_testing_config,
)


async def example_basic_usage():
    """Demonstrate basic usage of the component factory."""
    print("=== Basic Usage Example ===")
    
    # Create mock dependencies
    mock_session = AsyncMock(spec=AsyncSession)
    mock_github_client = MagicMock(spec=GitHubClient)
    mock_github_client.base_url = "http://localhost:8080"  # Mock server URL
    
    # Create component factory
    factory = IntegrationComponentFactory(
        database_session=mock_session,
        github_client=mock_github_client,
        redis_url=None,  # Use memory cache
    )
    
    # Create discovery engine
    engine = factory.create_discovery_engine()
    print(f"Created discovery engine: {type(engine).__name__}")
    
    # Create individual strategies
    pr_strategy = factory.create_pr_discovery_strategy()
    check_strategy = factory.create_check_discovery_strategy()
    state_detector = factory.create_state_detector()
    
    print(f"PR Strategy: {type(pr_strategy).__name__}")
    print(f"Check Strategy: {type(check_strategy).__name__}")
    print(f"State Detector: {type(state_detector).__name__}")
    
    # Create repositories
    repo_repo, pr_repo, check_repo = factory.create_repositories()
    print(f"Repositories: {type(repo_repo).__name__}, {type(pr_repo).__name__}, {type(check_repo).__name__}")
    
    # Cleanup
    await factory.cleanup()
    print("✅ Basic usage completed successfully")


async def example_builder_pattern():
    """Demonstrate using the builder pattern."""
    print("\n=== Builder Pattern Example ===")
    
    # Mock dependencies
    session = AsyncMock(spec=AsyncSession)
    client = MagicMock(spec=GitHubClient)
    
    # Use builder pattern
    factory = (
        ComponentFactoryBuilder()
        .with_database_session(session)
        .with_github_client(client)
        .with_redis_url("redis://localhost:6379")
        .build()
    )
    
    print(f"Built factory with Redis URL: {factory.redis_url}")
    
    # Create engine with performance testing config
    performance_config = create_performance_testing_config()
    engine = factory.create_discovery_engine(config=performance_config)
    
    print(f"Engine with performance config - Max concurrent: {engine.config.max_concurrent_repositories}")
    
    await factory.cleanup()
    print("✅ Builder pattern usage completed successfully")


async def example_context_manager():
    """Demonstrate using the context manager."""
    print("\n=== Context Manager Example ===")
    
    session = AsyncMock(spec=AsyncSession)
    client = MagicMock(spec=GitHubClient)
    
    async with IntegrationTestContext(
        database_session=session,
        github_client=client,
    ) as factory:
        print("Inside context manager - factory automatically created")
        
        # Create minimal config engine for fast tests
        minimal_config = create_minimal_testing_config()
        engine = factory.create_discovery_engine(config=minimal_config)
        
        print(f"Minimal config - Max PRs per repo: {engine.config.max_prs_per_repository}")
        
        # Test the event publisher
        event_publisher = factory.event_publisher
        
        # Mock PR data
        mock_pr = MagicMock()
        mock_pr.pr_number = 42
        mock_pr.title = "Test PR for Integration"
        
        await event_publisher.publish_new_pr(uuid.uuid4(), mock_pr)
        
        events = event_publisher.get_events_by_type("new_pr")
        print(f"Published and captured {len(events)} events")
    
    # Context manager handles cleanup automatically
    print("✅ Context manager usage completed successfully")


async def example_discovery_workflow_simulation():
    """Simulate a complete discovery workflow."""
    print("\n=== Discovery Workflow Simulation ===")
    
    session = AsyncMock(spec=AsyncSession)
    client = MagicMock(spec=GitHubClient)
    
    factory = IntegrationComponentFactory(
        database_session=session,
        github_client=client,
    )
    
    try:
        # Create engine
        engine = factory.create_discovery_engine()
        
        # Mock some repository IDs
        repository_ids = [uuid.uuid4(), uuid.uuid4()]
        
        print(f"Simulating discovery for {len(repository_ids)} repositories")
        
        # In a real test, you would:
        # 1. Set up mock GitHub server responses
        # 2. Seed test data in the database
        # 3. Run the discovery cycle
        # 4. Validate results
        
        # Get discovery status
        status = await engine.get_discovery_status()
        print(f"Engine status: {status['status']}")
        
        # Check event publisher
        events = factory.event_publisher.get_events_by_type("discovery_complete")
        print(f"Discovery complete events: {len(events)}")
        
        print("✅ Discovery workflow simulation completed")
        
    finally:
        await factory.cleanup()


async def example_configuration_scenarios():
    """Demonstrate different configuration scenarios."""
    print("\n=== Configuration Scenarios ===")
    
    session = AsyncMock(spec=AsyncSession)
    client = MagicMock(spec=GitHubClient)
    
    configs = {
        "Performance Testing": create_performance_testing_config(),
        "Minimal Testing": create_minimal_testing_config(),
    }
    
    for scenario_name, config in configs.items():
        print(f"\n{scenario_name} Configuration:")
        print(f"  Max Concurrent Repositories: {config.max_concurrent_repositories}")
        print(f"  Max PRs per Repository: {config.max_prs_per_repository}")
        print(f"  Cache TTL: {config.cache_ttl_seconds}s")
        print(f"  Batch Size: {config.batch_size}")
        print(f"  Priority Scheduling: {config.priority_scheduling}")
        
        factory = IntegrationComponentFactory(
            database_session=session,
            github_client=client,
        )
        
        engine = factory.create_discovery_engine(config=config)
        
        # Verify configuration applied
        assert engine.config.max_concurrent_repositories == config.max_concurrent_repositories
        assert engine.config.max_prs_per_repository == config.max_prs_per_repository
        
        await factory.cleanup()
    
    print("✅ All configuration scenarios validated")


async def main():
    """Run all examples."""
    print("🚀 IntegrationComponentFactory Usage Examples")
    print("=" * 50)
    
    await example_basic_usage()
    await example_builder_pattern()
    await example_context_manager()
    await example_discovery_workflow_simulation()
    await example_configuration_scenarios()
    
    print("\n" + "=" * 50)
    print("🎉 All examples completed successfully!")
    print("\nKey takeaways:")
    print("- IntegrationComponentFactory creates real discovery components")
    print("- Use builder pattern for complex configuration")
    print("- Context manager provides automatic cleanup")
    print("- Different configs optimize for different test scenarios")
    print("- Event publisher captures events for validation")
    print("- All components use real implementations, not mocks")


if __name__ == "__main__":
    asyncio.run(main())