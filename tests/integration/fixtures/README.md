# Integration Component Factory

This directory provides the `IntegrationComponentFactory` for creating real discovery components in integration tests, as specified in the implementation plan.

## Overview

The `IntegrationComponentFactory` creates fully functional, real discovery system components for integration testing while maintaining test isolation and performance. It provides controlled dependencies for testing scenarios without using mocks for the core business logic.

## Key Components

### IntegrationComponentFactory

The main factory class that creates real discovery components:

- **Real PRDiscoveryEngine** with all dependencies properly injected
- **Real repository classes** (PullRequestRepository, CheckRunRepository, etc.)  
- **Real cache implementation** (DiscoveryCache with Redis/memory backend)
- **Real GitHub client** configured for mock server
- **All discovery workers** (scanner, discoverer, synchronizer, etc.)

### ComponentFactoryBuilder

Builder pattern implementation for creating the factory with different configurations:

```python
factory = (
    ComponentFactoryBuilder()
    .with_database_session(session)
    .with_github_client(client)
    .with_redis_url("redis://localhost:6379")
    .build()
)
```

### IntegrationTestContext

Context manager for automatic setup and cleanup:

```python
async with IntegrationTestContext(
    database_session=session,
    github_client=client,
) as factory:
    # Use factory
    engine = factory.create_discovery_engine()
    # Automatic cleanup on exit
```

### TestEventPublisher

Test-specific event publisher that captures events for validation:

```python
events = factory.event_publisher.get_events_by_type("new_pr")
assert len(events) == expected_count
```

## Configuration Presets

Pre-configured settings for different testing scenarios:

- **`create_performance_testing_config()`** - High concurrency and large datasets
- **`create_error_testing_config()`** - Failure injection points and short timeouts  
- **`create_minimal_testing_config()`** - Fast execution for unit-like integration tests

## Usage Examples

### Basic Usage

```python
from tests.integration.fixtures.component_factory import IntegrationComponentFactory

# Create factory
factory = IntegrationComponentFactory(
    database_session=session,
    github_client=client,
    redis_url=None,  # Use memory cache
)

# Create discovery engine  
engine = factory.create_discovery_engine()

# Create individual components
pr_strategy = factory.create_pr_discovery_strategy()
check_strategy = factory.create_check_discovery_strategy() 
state_detector = factory.create_state_detector()

# Cleanup
await factory.cleanup()
```

### With Custom Configuration

```python
config = DiscoveryConfig(
    max_concurrent_repositories=20,
    max_prs_per_repository=200,
    cache_ttl_seconds=600,
)

engine = factory.create_discovery_engine(config=config)
```

### Integration Test Pattern

```python
async def test_complete_discovery_workflow(database_session, github_mock):
    async with IntegrationTestContext(
        database_session=database_session,
        github_client=github_mock,
    ) as factory:
        # Create engine with performance config
        config = create_performance_testing_config()
        engine = factory.create_discovery_engine(config=config)
        
        # Run discovery
        repository_ids = [repo1_id, repo2_id]
        results = await engine.run_discovery_cycle(repository_ids)
        
        # Validate results
        assert len(results) == len(repository_ids)
        
        # Check events
        events = factory.event_publisher.get_events_by_type("discovery_complete")
        assert len(events) == 1
```

## Real Components Created

The factory creates actual implementations, not mocks:

- **GitHubRepositoryScanner** - Real PR discovery from GitHub API
- **GitHubCheckDiscoverer** - Real check run discovery with batching
- **DatabaseStateChangeDetector** - Real state change detection with database queries
- **DatabaseSynchronizer** - Real database synchronization with transactions
- **GitHubAPIResourceManager** - Real rate limiting and resource management
- **DiscoveryCache** - Real caching with Redis/memory backends
- **PRDiscoveryEngine** - Real orchestration with concurrency control

## Dependency Injection

All components are properly wired with real dependencies:

- **Database Operations**: Real database sessions, repositories, and transactions
- **GitHub API**: Real HTTP client configured for mock server
- **Caching**: Real cache implementations with proper TTL and invalidation
- **Rate Limiting**: Real token bucket algorithms and backpressure
- **Event Publishing**: Real event capture and validation

## Test Isolation

The factory ensures proper test isolation:

- **Database**: Each test gets isolated database transactions
- **Cache**: Test-specific cache namespaces  
- **GitHub Mock**: Scenario-based response configuration
- **Resources**: Automatic cleanup of connections and state

## Performance Testing

The factory supports performance testing with real I/O:

- **Concurrency**: Real async/await patterns and semaphores
- **Database Load**: Real database connection pools and query optimization  
- **Network I/O**: Real HTTP requests to controlled mock servers
- **Memory Usage**: Real object creation and garbage collection

## Files

- `component_factory.py` - Main factory implementation
- `test_component_factory.py` - Comprehensive tests demonstrating usage  
- `example_usage.py` - Complete usage examples
- `__init__.py` - Package exports with fallback for missing dependencies

## Integration with Existing Tests

The component factory integrates with existing integration test infrastructure while maintaining backward compatibility. It can be used alongside existing database fixtures and GitHub mock servers.

## Benefits

1. **Real Integration Testing** - Tests actual component interactions, not mocks
2. **Controlled Dependencies** - Real implementations with test-controlled inputs
3. **Performance Validation** - Actual I/O timing and resource usage measurement  
4. **Error Scenario Testing** - Real error conditions and recovery mechanisms
5. **Database Integration** - Real transactions, constraints, and consistency validation
6. **Easy Configuration** - Multiple preset configurations for different test scenarios
7. **Automatic Cleanup** - Proper resource management and test isolation
8. **Event Validation** - Capture and validate all system events

This implementation fulfills the requirements from the implementation plan for creating real discovery components in integration tests while maintaining test performance and reliability.