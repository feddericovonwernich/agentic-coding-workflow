# GitHub API Client Documentation

The GitHub API client provides a comprehensive, async-first interface to the GitHub REST API with advanced features including authentication, rate limiting, pagination, and error handling.

## Table of Contents

- [Quick Start](#quick-start)
- [Authentication](#authentication)
- [Client Configuration](#client-configuration)
- [Core Operations](#core-operations)
- [Pagination](#pagination)
- [Rate Limiting](#rate-limiting)
- [Error Handling](#error-handling)
- [Advanced Features](#advanced-features)
- [Performance Optimization](#performance-optimization)
- [Best Practices](#best-practices)

## Quick Start

### Basic Usage

```python
import asyncio
from src.github.client import GitHubClient, GitHubClientConfig
from src.github.auth import PersonalAccessTokenAuth

async def main():
    # Setup authentication
    auth = PersonalAccessTokenAuth(token="ghp_your_token_here")
    
    # Create client with default configuration
    client = GitHubClient(auth=auth)
    
    # Get user information
    user = await client.get("user")
    print(f"Authenticated as: {user['login']}")
    
    # Get repository information
    repo = await client.get("repos/owner/repo")
    print(f"Repository: {repo['full_name']}")

asyncio.run(main())
```

### Installation Requirements

```python
# Required dependencies (already included in project)
import aiohttp  # HTTP client
import jwt      # JWT token handling (for GitHub Apps)
```

## Authentication

The client supports multiple authentication methods for different use cases.

### Personal Access Token (PAT)

Simplest method for development and personal use:

```python
from src.github.auth import PersonalAccessTokenAuth

# Basic PAT authentication
auth = PersonalAccessTokenAuth(token="ghp_your_token_here")

# Create client
client = GitHubClient(auth=auth)
```

**When to use:** Development, personal projects, simple automation

**Permissions needed:** Configure token scopes based on required operations:
- `repo` - Full repository access
- `public_repo` - Public repository access only
- `workflow` - GitHub Actions workflow access
- `read:org` - Organization data access

### GitHub App Authentication

Recommended for production applications with fine-grained permissions:

```python
from src.github.auth import GitHubAppAuth

# GitHub App authentication
auth = GitHubAppAuth(
    app_id=12345,
    private_key_path="/path/to/private-key.pem",
    installation_id=67890
)

# Or with private key content
auth = GitHubAppAuth(
    app_id=12345,
    private_key_content="""-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA...
-----END RSA PRIVATE KEY-----""",
    installation_id=67890
)

client = GitHubClient(auth=auth)
```

**When to use:** Production applications, organizations, fine-grained permissions

**Benefits:**
- More granular permissions
- Higher rate limits
- Better security model
- Organization-wide installation

### OAuth Authentication

For user-facing applications requiring user authorization:

```python
from src.github.auth import OAuthAuth

# OAuth authentication (user flow)
auth = OAuthAuth(
    client_id="your_oauth_app_client_id",
    client_secret="your_oauth_app_client_secret",
    access_token="user_access_token"
)

client = GitHubClient(auth=auth)
```

**When to use:** Web applications, user-facing tools, on-behalf-of operations

### Token Management

All authentication providers support automatic token refresh and validation:

```python
# Check token validity
is_valid = await auth.validate_token()

# Refresh token (for GitHub Apps)
new_token = await auth.refresh_token()

# Get current token with metadata
token = await auth.get_token()
print(f"Token expires at: {token.expires_at}")
```

## Client Configuration

Configure client behavior with `GitHubClientConfig`:

```python
from src.github.client import GitHubClientConfig

# Custom configuration
config = GitHubClientConfig(
    base_url="https://api.github.com",        # GitHub API base URL
    timeout=30,                               # Request timeout in seconds
    max_retries=3,                           # Maximum retry attempts
    retry_backoff_factor=2.0,                # Exponential backoff factor
    rate_limit_buffer=100,                   # Rate limit buffer (requests)
    user_agent="MyApp/1.0",                  # Custom User-Agent header
    max_concurrent_requests=10               # Concurrent request limit
)

client = GitHubClient(auth=auth, config=config)
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `base_url` | `"https://api.github.com"` | GitHub API base URL (for GitHub Enterprise) |
| `timeout` | `30` | HTTP request timeout in seconds |
| `max_retries` | `3` | Maximum number of retry attempts |
| `retry_backoff_factor` | `2.0` | Exponential backoff multiplier |
| `rate_limit_buffer` | `100` | Buffer to maintain before rate limit |
| `user_agent` | `"PR-Monitor-Worker/1.0"` | User-Agent header for requests |
| `max_concurrent_requests` | `10` | Maximum concurrent requests |

### GitHub Enterprise Configuration

For GitHub Enterprise Server:

```python
config = GitHubClientConfig(
    base_url="https://github.company.com/api/v3",
    timeout=60,  # Longer timeout for enterprise
    rate_limit_buffer=50  # Lower buffer for enterprise
)
```

## Core Operations

The client provides convenient methods for common GitHub API operations.

### HTTP Methods

Direct HTTP method access for any GitHub API endpoint:

```python
# GET requests
user = await client.get("user")
repos = await client.get("user/repos", params={"type": "owner"})

# POST requests
issue = await client.post("repos/owner/repo/issues", data={
    "title": "Bug report",
    "body": "Description of the bug"
})

# PUT requests
await client.put("repos/owner/repo/subscription", data={
    "subscribed": True,
    "ignored": False
})

# DELETE requests
await client.delete("repos/owner/repo/subscription")

# PATCH requests
updated_issue = await client.patch("repos/owner/repo/issues/1", data={
    "state": "closed"
})
```

### Convenience Methods

High-level methods for common operations:

```python
# User operations
user = await client.get_user("username")
current_user = await client.get_user()  # Current authenticated user

# Repository operations
repo = await client.get_repo("owner/repo")
repos = await client.get_user_repos("username")
org_repos = await client.get_org_repos("organization")

# Pull request operations
pull = await client.get_pull("owner/repo", 123)
pulls = await client.get_pulls("owner/repo", state="open")

# Issue operations
issue = await client.get_issue("owner/repo", 456)
issues = await client.get_issues("owner/repo", state="open")
```

### Request Parameters

All methods support query parameters and request customization:

```python
# Query parameters
repos = await client.get("user/repos", params={
    "type": "owner",
    "sort": "updated",
    "direction": "desc",
    "per_page": 50
})

# Custom headers
response = await client.get("user", headers={
    "Accept": "application/vnd.github.v3+json",
    "X-Custom-Header": "value"
})

# Request body data
issue = await client.post("repos/owner/repo/issues", data={
    "title": "New feature request",
    "body": "Detailed description",
    "labels": ["enhancement", "feature"]
})
```

## Pagination

Handle large datasets efficiently with automatic pagination.

### Async Pagination

```python
from src.github.pagination import AsyncPaginator

# Paginate through all repositories
async for repo in client.paginate("user/repos"):
    print(f"Repository: {repo['name']}")

# Paginate with parameters
params = {"type": "owner", "sort": "updated"}
async for repo in client.paginate("user/repos", params=params):
    print(f"Updated: {repo['updated_at']}")
```

### Manual Pagination Control

```python
# Get paginated response with metadata
response = await client.get_paginated("user/repos", per_page=50)

print(f"Total pages: {response.total_pages}")
print(f"Current page: {response.current_page}")
print(f"Has next page: {response.has_next}")

# Process current page
for repo in response.data:
    print(f"Repository: {repo['name']}")

# Get next page
if response.has_next:
    next_response = await client.get_paginated(response.next_url)
```

### Pagination Utilities

```python
# Collect all results into a list
all_repos = []
async for repo in client.paginate("user/repos"):
    all_repos.append(repo)

# Or use list comprehension
all_repos = [repo async for repo in client.paginate("user/repos")]

# Limit pagination
count = 0
async for repo in client.paginate("user/repos"):
    if count >= 100:  # Only process first 100
        break
    print(repo['name'])
    count += 1
```

## Rate Limiting

Automatic rate limit management with intelligent handling.

### Rate Limit Information

```python
# Get current rate limit status
rate_limit = await client.get_rate_limit()
print(f"Remaining: {rate_limit['rate']['remaining']}")
print(f"Limit: {rate_limit['rate']['limit']}")
print(f"Reset: {rate_limit['rate']['reset']}")

# Check specific rate limit category
core_limit = rate_limit['rate']
search_limit = rate_limit['search']
graphql_limit = rate_limit['graphql']
```

### Automatic Rate Limit Handling

The client automatically handles rate limits:

```python
# Client automatically waits when approaching rate limit
for i in range(1000):  # Will automatically throttle
    try:
        user = await client.get(f"users/user{i}")
        print(f"User: {user['login']}")
    except GitHubRateLimitError as e:
        # This exception is rare due to automatic handling
        print(f"Rate limited, retry after: {e.retry_after} seconds")
        await asyncio.sleep(e.retry_after)
```

### Rate Limit Configuration

```python
# Configure rate limit behavior
config = GitHubClientConfig(
    rate_limit_buffer=50,  # Wait when 50 requests remain
    max_retries=5,         # Retry on rate limit errors
    retry_backoff_factor=2.0  # Exponential backoff
)

client = GitHubClient(auth=auth, config=config)
```

### Circuit Breaker

Prevent cascading failures during API issues:

```python
# Circuit breaker automatically opens on repeated failures
try:
    for i in range(100):
        await client.get("user")
except GitHubConnectionError:
    # Circuit breaker may be open
    print("Circuit breaker may be protecting against API issues")
    
    # Wait for circuit breaker reset
    await asyncio.sleep(60)  # Circuit breaker timeout
```

## Error Handling

Comprehensive exception hierarchy for robust error handling.

### Exception Types

```python
from src.github.exceptions import (
    GitHubError,                 # Base exception for all GitHub API errors
    GitHubAuthenticationError,   # 401 Unauthorized
    GitHubRateLimitError,       # 429 Too Many Requests
    GitHubNotFoundError,        # 404 Not Found
    GitHubValidationError,      # 422 Validation Failed
    GitHubServerError,          # 5xx Server Errors
    GitHubTimeoutError,         # Request timeout
    GitHubConnectionError       # Network/connection issues
)
```

### Error Handling Patterns

```python
async def robust_github_operation():
    try:
        user = await client.get_user("username")
        return user
        
    except GitHubAuthenticationError:
        # Handle authentication issues
        print("Authentication failed - check token")
        # Re-authenticate or refresh token
        
    except GitHubRateLimitError as e:
        # Handle rate limiting
        print(f"Rate limited, retry after {e.retry_after} seconds")
        await asyncio.sleep(e.retry_after)
        return await robust_github_operation()  # Retry
        
    except GitHubNotFoundError:
        # Handle missing resources
        print("User not found")
        return None
        
    except GitHubValidationError as e:
        # Handle validation errors
        print(f"Validation failed: {e.errors}")
        return None
        
    except GitHubServerError as e:
        # Handle server errors with exponential backoff
        print(f"Server error: {e.status_code}")
        await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
    except GitHubTimeoutError:
        # Handle timeout errors
        print("Request timed out")
        # Consider increasing timeout or reducing request size
        
    except GitHubConnectionError:
        # Handle connection issues
        print("Connection failed")
        # Check network connectivity
        
    except GitHubError as e:
        # Handle any other GitHub errors
        print(f"GitHub API error: {e}")
```

### Error Response Details

Exceptions include detailed information:

```python
try:
    await client.post("repos/owner/repo/issues", data={"title": ""})
except GitHubValidationError as e:
    print(f"Status: {e.status_code}")
    print(f"Message: {e.message}")
    print(f"Errors: {e.errors}")
    print(f"Documentation: {e.documentation_url}")
    
    # Example error details:
    # Status: 422
    # Message: Validation Failed
    # Errors: [{'field': 'title', 'code': 'missing'}]
    # Documentation: https://docs.github.com/rest/issues/issues#create-an-issue
```

## Advanced Features

### Correlation IDs

Track requests across the system with correlation IDs:

```python
import uuid

# Add correlation ID to requests
correlation_id = str(uuid.uuid4())
user = await client.get("user", headers={
    "X-Correlation-ID": correlation_id
})

# Correlation ID is automatically logged for debugging
```

### Request Middleware

Customize request processing:

```python
# Custom request headers
async def add_custom_headers(request):
    request.headers["X-App-Version"] = "1.0.0"
    request.headers["X-Request-ID"] = str(uuid.uuid4())
    return request

# Apply middleware (if implemented)
client.add_middleware(add_custom_headers)
```

### Response Caching

Cache responses to improve performance:

```python
# Enable response caching for GET requests
config = GitHubClientConfig(
    cache_enabled=True,      # Enable caching
    cache_ttl=300,          # 5-minute TTL
    cache_max_size=1000     # Max 1000 cached responses
)

client = GitHubClient(auth=auth, config=config)

# Subsequent identical requests served from cache
user1 = await client.get("user")  # API call
user2 = await client.get("user")  # Served from cache
```

### Concurrent Request Management

Handle multiple requests efficiently:

```python
import asyncio

# Process multiple repositories concurrently
repo_names = ["repo1", "repo2", "repo3", "repo4", "repo5"]

async def get_repo_info(repo_name):
    return await client.get_repo(f"owner/{repo_name}")

# Concurrent requests (respects max_concurrent_requests)
results = await asyncio.gather(*[
    get_repo_info(repo) for repo in repo_names
])

for result in results:
    print(f"Repository: {result['full_name']}")
```

### Custom User-Agent

Identify your application in GitHub logs:

```python
config = GitHubClientConfig(
    user_agent="MyApp/2.1.0 (contact@company.com)"
)
client = GitHubClient(auth=auth, config=config)
```

## Performance Optimization

### Connection Pooling

The client automatically manages HTTP connections:

```python
# Connection pool is managed automatically
# Configure pool size if needed
config = GitHubClientConfig(
    max_concurrent_requests=20,  # Increase for high-throughput applications
    timeout=60                   # Longer timeout for slow responses
)
```

### Request Batching

Batch operations when possible:

```python
# Instead of multiple individual requests
users = []
for username in usernames:
    user = await client.get_user(username)  # Individual requests
    users.append(user)

# Use concurrent requests
async def get_user_safe(username):
    try:
        return await client.get_user(username)
    except GitHubNotFoundError:
        return None

users = await asyncio.gather(*[
    get_user_safe(username) for username in usernames
])
users = [user for user in users if user is not None]
```

### Memory Management

Handle large datasets efficiently:

```python
# For large pagination, process items as they arrive
async def process_large_dataset():
    async for repo in client.paginate("user/repos"):
        # Process each repository immediately
        await process_repository(repo)
        # Don't accumulate all results in memory

# Instead of loading everything into memory:
# all_repos = [repo async for repo in client.paginate("user/repos")]  # Memory intensive
```

## Best Practices

### Authentication Security

```python
# ✅ Store tokens securely
import os
token = os.getenv("GITHUB_TOKEN")  # From environment
auth = PersonalAccessTokenAuth(token=token)

# ❌ Don't hardcode tokens
# auth = PersonalAccessTokenAuth(token="ghp_hardcoded_token")  # Insecure
```

### Error Handling

```python
# ✅ Handle specific exceptions
try:
    user = await client.get_user("username")
except GitHubNotFoundError:
    user = None  # Handle gracefully
except GitHubRateLimitError as e:
    await asyncio.sleep(e.retry_after)  # Respect rate limits

# ❌ Don't ignore errors
# user = await client.get_user("username")  # May raise unhandled exceptions
```

### Rate Limiting

```python
# ✅ Configure appropriate buffer
config = GitHubClientConfig(
    rate_limit_buffer=100  # Conservative buffer
)

# ✅ Monitor rate limit usage
rate_limit = await client.get_rate_limit()
if rate_limit['rate']['remaining'] < 100:
    print("Approaching rate limit")

# ❌ Don't ignore rate limits
# config = GitHubClientConfig(rate_limit_buffer=0)  # Risky
```

### Resource Management

```python
# ✅ Use async context manager when available
async with client:
    user = await client.get_user("username")
# Connection automatically closed

# ✅ Explicitly close when done
client = GitHubClient(auth=auth)
try:
    user = await client.get_user("username")
finally:
    await client.close()
```

### Performance

```python
# ✅ Use pagination for large datasets
async for repo in client.paginate("user/repos"):
    process_repo(repo)

# ✅ Use concurrent requests for multiple operations
results = await asyncio.gather(*[
    client.get_repo(repo) for repo in repo_list
])

# ❌ Don't make sequential requests when concurrent is possible
# for repo in repo_list:
#     result = await client.get_repo(repo)  # Sequential, slower
```

---

**Next Steps:**
- 📖 **Examples**: Check [GitHub Client Examples](examples/github-client-usage.py) for complete working code
- ⚙️ **Configuration**: See [Configuration Management API](configuration-api.md) for config integration
- 🧪 **Testing**: Review [Testing Guide](../developer/testing-guide.md) for testing patterns