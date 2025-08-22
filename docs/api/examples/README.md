# API Examples

This directory contains comprehensive code examples demonstrating all major APIs and integration patterns in the agentic coding workflow system.

## Overview

Each example file provides complete, runnable code that demonstrates real-world usage patterns, best practices, and common integration scenarios.

## Examples Index

### [GitHub Integration](github-integration.py)
Comprehensive GitHub API client usage examples including:
- **Basic Operations**: Authentication, user/repository access, PR monitoring
- **Pull Request Monitoring**: Automated PR detection and analysis queuing  
- **Repository Analysis**: Metrics collection, commit history, activity tracking
- **Pagination Handling**: Efficient processing of large datasets
- **Rate Limiting**: Graceful handling of GitHub API limits
- **Error Handling**: Robust error recovery and retry patterns
- **GitHub App Authentication**: Using GitHub Apps for enhanced permissions

**Key Features Demonstrated:**
- Personal Access Token and GitHub App authentication
- Circuit breaker pattern for reliability
- Concurrent request handling with proper rate limiting
- Repository health analysis and metrics collection

### [Configuration Management](configuration-management.py)
Complete configuration system usage examples including:
- **Basic Loading**: File-based configuration with validation
- **Environment Variables**: Substitution and validation patterns
- **Hot Reload**: Live configuration updates without restarts
- **Programmatic Configuration**: Building configs in code
- **Configuration Comparison**: Diff and validation utilities
- **Caching**: Performance optimization techniques
- **Testing Support**: Mock configurations for testing

**Key Features Demonstrated:**
- Hierarchical configuration loading
- Type-safe configuration models with Pydantic
- Environment variable substitution with defaults
- Configuration validation and error handling
- Performance optimization with caching

### [Database Operations](database-operations.py)
Comprehensive database usage examples including:
- **Basic CRUD**: Repository pattern implementation
- **Pull Request Lifecycle**: Complete PR state management
- **Check Runs Management**: CI/CD check tracking
- **Complex Queries**: Aggregations and reporting
- **Transaction Management**: ACID compliance and rollback
- **Connection Management**: Pool optimization and health checks
- **Performance Optimization**: Batch operations and indexing

**Key Features Demonstrated:**
- Repository pattern with async SQLAlchemy
- Transaction management and error handling
- Connection pooling and health monitoring
- State machine implementation for PR workflows
- Performance optimization techniques

### [Webhook Integration](webhook-integration.py)
Complete webhook handling examples including:
- **GitHub Webhook Processing**: Event parsing and routing
- **Outgoing Notifications**: System alerts and monitoring
- **Event Routing**: Pattern-based event distribution
- **Security**: Signature verification and authentication
- **Error Handling**: Retry logic and dead letter queues
- **FastAPI Integration**: Production webhook endpoints

**Key Features Demonstrated:**
- GitHub webhook signature verification
- Event-driven architecture patterns
- Retry logic with exponential backoff
- Middleware pipeline for event processing
- Production-ready endpoint implementation

### [Worker Implementation](worker-implementation.py)
Advanced worker system examples including:
- **Basic Workers**: Message processing patterns
- **Multi-Worker Pipelines**: Chained processing workflows
- **Batch Processing**: Performance optimization techniques
- **Error Handling**: Retry mechanisms and failure recovery
- **Queue Management**: Message prioritization and routing
- **Worker Management**: Lifecycle and monitoring

**Key Features Demonstrated:**
- Abstract base classes for extensibility
- Queue management with priority handling
- Batch processing optimization
- Worker lifecycle management
- Error handling and retry patterns

## Running the Examples

### Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (for relevant examples)
export GITHUB_TOKEN="your_github_token"
export DATABASE_URL="sqlite:///./examples.db"
export ANTHROPIC_API_KEY="your_anthropic_key"
```

### GitHub Integration Example

```bash
# Edit the token in github-integration.py
python docs/api/examples/github-integration.py
```

### Configuration Management Example

```bash
python docs/api/examples/configuration-management.py
```

### Database Operations Example

```bash
# Requires database setup
python docs/api/examples/database-operations.py
```

### Webhook Integration Example

```bash
# Run webhook examples
python docs/api/examples/webhook-integration.py

# Run FastAPI webhook server
pip install fastapi uvicorn
uvicorn webhook-integration:app --reload
```

### Worker Implementation Example

```bash
python docs/api/examples/worker-implementation.py
```

## Integration Patterns

### Event-Driven Architecture

The examples demonstrate a complete event-driven architecture:

```
GitHub Webhook → Event Processing → Worker Queue → Analysis → Fixing → Notification
```

### Repository Pattern

Database examples show the repository pattern implementation:

```python
async with DatabaseManager.get_session() as session:
    pr_repo = PullRequestRepository(session)
    pr = await pr_repo.create(...)
    await session.commit()
```

### Configuration-Driven Development

All examples use configuration-driven patterns:

```python
config = load_config("config.yaml")
client = GitHubClient(auth=PersonalAccessTokenAuth(config.github.token))
```

### Worker Pipeline Pattern

Worker examples demonstrate pipeline processing:

```python
analyzer → fixer → notifier
    ↓         ↓        ↓
 analysis   fixes  notifications
  queue     queue     queue
```

## Best Practices Demonstrated

### Error Handling

- Comprehensive exception handling
- Retry logic with exponential backoff
- Circuit breaker patterns
- Dead letter queue implementation

### Performance Optimization

- Connection pooling
- Batch processing
- Caching strategies
- Asynchronous operations

### Security

- Webhook signature verification
- Secure credential management
- Rate limiting implementation
- Input validation

### Testing

- Mock implementations
- Test configuration
- Integration testing patterns
- Error simulation

## Common Use Cases

### PR Monitoring System

Combine GitHub integration + webhooks + workers:

1. GitHub webhook triggers PR analysis
2. Worker processes check results
3. Configuration determines fix strategies
4. Database tracks state transitions
5. Notifications alert on completion

### Automated Fix Pipeline

Integrate all components for automated fixing:

1. Check failure detected via webhook
2. Analysis worker categorizes the failure
3. Fix worker applies appropriate solutions
4. Database tracks fix attempts and results
5. Notification system reports outcomes

### Multi-Repository Monitoring

Scale across multiple repositories:

1. Configuration defines repository list
2. GitHub client monitors all repositories
3. Workers process PRs from all repos
4. Database provides cross-repo analytics
5. Webhooks handle real-time updates

## Advanced Patterns

### Circuit Breaker Implementation

```python
from src.github.client import GitHubClient

client = GitHubClient(
    auth=auth,
    circuit_breaker_failure_threshold=5,
    circuit_breaker_timeout=60
)
```

### Batch Processing Optimization

```python
class BatchWorker(BaseWorker):
    async def process_batch(self, messages: List[WorkerMessage]) -> List[bool]:
        # Batch database operations
        return await self.batch_process(messages)
```

### Hot Configuration Reload

```python
manager = ConfigurationManager(hot_reload=True)
manager.register_reload_callback(on_config_change)
await manager.start()
```

## Troubleshooting

### Common Issues

1. **GitHub Rate Limiting**: Examples show proper rate limit handling
2. **Database Connections**: Pool configuration and cleanup patterns
3. **Worker Deadlocks**: Proper error handling and timeouts
4. **Configuration Errors**: Validation and error reporting

### Debug Logging

Enable debug logging to see detailed execution:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Environment Setup

Ensure all required environment variables are set:

```bash
# Check configuration
python -c "from src.config.loader import load_config; print(load_config())"
```

## Production Considerations

### Scalability

- Worker pools for concurrent processing
- Database connection pooling
- Queue management and monitoring
- Load balancing strategies

### Reliability

- Error handling and recovery
- Health checks and monitoring
- Graceful shutdown procedures
- Data consistency guarantees

### Security

- Credential management
- Webhook signature verification
- Input validation and sanitization
- Rate limiting and DDoS protection

### Monitoring

- Metrics collection and reporting
- Log aggregation and analysis
- Performance monitoring
- Alert configuration

---

These examples provide a complete foundation for building production-ready integrations with the agentic coding workflow system. Each example includes extensive error handling, logging, and best practices suitable for production deployment.