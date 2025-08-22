# API Documentation

Welcome to the comprehensive API documentation for the Agentic Coding Workflow project. This documentation covers all public interfaces and APIs that enable integration, extension, and development with the system.

> **📚 Navigation**: This is the **API reference hub**. For user configuration scenarios, see [User Configuration Guide](../user-guide/configuration.md). For developer setup, see [Developer Guide](../developer/README.md). For troubleshooting API integration issues, see [Configuration Troubleshooting](../config/troubleshooting.md).

## Table of Contents

- [Getting Started](#getting-started)
- [Available APIs](#available-apis)
- [Code Examples](#code-examples)
- [Authentication & Security](#authentication--security)
- [Error Handling](#error-handling)
- [Performance Considerations](#performance-considerations)

## Getting Started

### Prerequisites

Before using the APIs, ensure you have:

- **Python 3.11+** with the project dependencies installed
- **GitHub Personal Access Token** for GitHub API operations
- **Database connection** configured (PostgreSQL for production, SQLite for development)
- **API keys** for LLM providers (Anthropic Claude or OpenAI)

### Quick Setup

```python
# Basic setup for API usage
import asyncio
from src.github.client import GitHubClient, GitHubClientConfig
from src.github.auth import PersonalAccessTokenAuth
from src.config.loader import load_config

# Load configuration
config = load_config()

# Setup GitHub client
auth = PersonalAccessTokenAuth(token="your_github_token")
github_config = GitHubClientConfig(
    timeout=30,
    max_retries=3,
    rate_limit_buffer=100
)
client = GitHubClient(auth=auth, config=github_config)

# Use the client
async def main():
    user = await client.get_user("username")
    print(f"User: {user['login']}")

asyncio.run(main())
```

## Available APIs

### [GitHub API Client](github-client.md)
Comprehensive GitHub API integration with advanced features:
- **Authentication**: Personal Access Token, GitHub App, OAuth support
- **Rate Limiting**: Automatic rate limit management with circuit breaker
- **Pagination**: Async pagination for large datasets
- **Error Handling**: Comprehensive exception hierarchy
- **Performance**: Concurrent request management and caching

### [Configuration Management API](configuration-api.md)
Powerful configuration system with validation and hot reload:
- **Loading**: Multi-source configuration loading with environment variable substitution
- **Validation**: Schema validation with Pydantic models and business logic checks
- **Utilities**: Configuration tools, debugging, and testing utilities
- **Caching**: Performance optimization with intelligent caching
- **Hot Reload**: Runtime configuration updates without restart

### [Database API](database-api.md)
Database models and repository patterns for data persistence:
- **Models**: SQLAlchemy models with relationships and validation
- **Repositories**: Repository pattern implementation with base classes
- **Transactions**: Transaction management and rollback procedures
- **Performance**: Connection pooling, query optimization, and monitoring
- **Migrations**: Database schema management and version control

### [Worker Interfaces](worker-interfaces.md)
Worker and message queue interfaces for extensibility:
- **Message Formats**: Standardized message structures and serialization
- **Worker Base Classes**: Abstract interfaces for implementing custom workers
- **Queue Management**: Message queue integration patterns
- **Event Handling**: Event-driven architecture patterns
- **Extension Points**: Plugin architecture and custom integrations

### [Webhook Interfaces](webhooks.md)
Webhook handling and event processing:
- **Event Formats**: GitHub webhook structures and custom events
- **Authentication**: Webhook signature verification and security
- **Processing**: Event routing, filtering, and transformation
- **Integration**: Connection with worker queues and processing pipelines
- **Error Handling**: Retry mechanisms and dead letter queues

## Code Examples

Complete working examples for all APIs are available in the [examples/](examples/) directory:

### Quick Access Examples

**GitHub Client Usage:**
```python
# [examples/github-client-usage.py](examples/github-client-usage.py)
# Comprehensive examples of GitHub API operations
```

**Configuration Management:**
```python
# [examples/config-management.py](examples/config-management.py)
# Configuration loading, validation, and utilities
```

**Database Operations:**
```python
# [examples/database-queries.py](examples/database-queries.py)
# Model usage, repository patterns, and transactions
```

**Webhook Handling:**
```python
# [examples/webhook-handlers.py](examples/webhook-handlers.py)
# Webhook endpoint implementation and event processing
```

## Authentication & Security

### GitHub Authentication

The system supports multiple GitHub authentication methods:

1. **Personal Access Token (PAT)** - Simplest method for development
2. **GitHub App** - Recommended for production with fine-grained permissions
3. **OAuth** - For user-facing applications requiring user authorization

```python
from src.github.auth import PersonalAccessTokenAuth, GitHubAppAuth

# Personal Access Token
pat_auth = PersonalAccessTokenAuth(token="ghp_your_token")

# GitHub App
app_auth = GitHubAppAuth(
    app_id=12345,
    private_key_path="/path/to/private-key.pem",
    installation_id=67890
)
```

### API Security Best Practices

- **Token Management**: Store tokens securely, rotate regularly
- **Rate Limiting**: Respect API rate limits to avoid blocking
- **Webhook Security**: Verify webhook signatures for authenticity
- **Error Handling**: Don't expose sensitive information in error messages
- **Logging**: Log API usage without including tokens or sensitive data

## Error Handling

All APIs use a comprehensive exception hierarchy for consistent error handling:

### GitHub API Errors

```python
from src.github.exceptions import (
    GitHubError,                 # Base exception
    GitHubAuthenticationError,   # 401 Unauthorized
    GitHubRateLimitError,       # 429 Rate Limit Exceeded
    GitHubNotFoundError,        # 404 Not Found
    GitHubServerError,          # 5xx Server Errors
    GitHubTimeoutError,         # Request timeout
    GitHubConnectionError       # Network issues
)

try:
    user = await client.get_user("username")
except GitHubRateLimitError as e:
    # Handle rate limiting with backoff
    await asyncio.sleep(e.retry_after)
except GitHubNotFoundError:
    # Handle missing resources
    print("User not found")
except GitHubError as e:
    # Handle all other GitHub errors
    print(f"GitHub API error: {e}")
```

### Configuration Errors

```python
from src.config.exceptions import (
    ConfigurationError,         # Base configuration error
    ConfigurationFileError,     # File loading issues
    ConfigurationValidationError # Validation failures
)

try:
    config = load_config("config.yaml")
except ConfigurationValidationError as e:
    print(f"Configuration validation failed: {e.errors}")
except ConfigurationFileError as e:
    print(f"Failed to load config file: {e}")
```

## Performance Considerations

### GitHub API Client

- **Rate Limiting**: Automatic rate limit management with configurable buffer
- **Circuit Breaker**: Prevents cascading failures during API issues
- **Concurrent Requests**: Configurable concurrency limits for optimal performance
- **Caching**: Response caching for frequently accessed data
- **Connection Pooling**: Efficient HTTP connection reuse

### Configuration System

- **Caching**: Configuration is cached after first load for performance
- **Hot Reload**: Minimal overhead configuration updates
- **Validation**: Efficient validation with early exit on errors
- **Memory Usage**: Optimized for low memory footprint

### Database Operations

- **Connection Pooling**: Configurable connection pool for optimal database performance
- **Query Optimization**: Repository patterns encourage efficient queries
- **Transaction Management**: Proper transaction boundaries to minimize lock time
- **Monitoring**: Built-in performance monitoring and health checks

## API Versioning

Currently, all APIs are in **version 1.0** and follow semantic versioning:

- **Major Version**: Breaking changes to public interfaces
- **Minor Version**: New features with backward compatibility
- **Patch Version**: Bug fixes and performance improvements

### Compatibility Promise

We maintain backward compatibility within major versions:
- **Public interfaces** remain stable within major versions
- **Configuration schemas** maintain backward compatibility
- **Database models** use migrations for schema evolution
- **Deprecation policy** provides 2 minor version notice before removal

## Getting Help

### Documentation
- **[Complete API Reference](README.md)** - This comprehensive guide
- **[Code Examples](examples/)** - Working code for all APIs
- **[Integration Patterns](../developer/testing-guide.md)** - Testing and integration guidance
- **[🛠️ Troubleshooting Hub](../troubleshooting-hub.md)** - Find the right troubleshooting guide for your issue
- **[Configuration Issues](../config/troubleshooting.md)** - Technical configuration and API integration problems
- **[Development Issues](../developer/debugging.md)** - Local development and debugging problems

### Community Support
- **[GitHub Issues](https://github.com/feddericovonwernich/agentic-coding-workflow/issues)** - Bug reports and feature requests
- **[GitHub Discussions](https://github.com/feddericovonwernich/agentic-coding-workflow/discussions)** - API questions and community help

### Integration Support

For complex integrations:
1. **Start with examples** - Use the comprehensive code examples
2. **Check existing tests** - Review test files for usage patterns
3. **Follow best practices** - Implement proper error handling and performance optimization
4. **Contribute back** - Share successful integration patterns with the community

---

**Ready to start integrating?**
- 🚀 **New to APIs**: Start with [GitHub Client Documentation](github-client.md)
- ⚙️ **Configuration**: See [Configuration Management API](configuration-api.md)
- 🗄️ **Database**: Check [Database API Documentation](database-api.md)
- 📬 **Webhooks**: Review [Webhook Interfaces](webhooks.md)