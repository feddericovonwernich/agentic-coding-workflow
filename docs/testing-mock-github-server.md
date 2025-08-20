# Mock GitHub API Server for Testing

This document explains how to use the Mock GitHub API Server for testing GitHub API integrations without requiring real GitHub tokens.

## Overview

The Mock GitHub API Server provides realistic GitHub API responses using real data collected from the GitHub API. This enables:

- **Token-free testing**: No need for real GitHub authentication tokens
- **Reliable tests**: Tests don't depend on external GitHub service availability  
- **Fast execution**: Local mock server responds much faster than real GitHub API
- **Reproducible results**: Consistent test data across all environments
- **Offline testing**: Tests can run without internet connectivity

## Architecture

```
┌─────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│                     │    │                      │    │                     │
│   Integration       │───▶│  Mock GitHub API     │───▶│   Real GitHub       │
│   Tests             │    │  Server (Flask)      │    │   Response Data     │
│                     │    │                      │    │   (JSON Files)      │
└─────────────────────┘    └──────────────────────┘    └─────────────────────┘
         │                            │                           │
         │                            │                           │
         ▼                            ▼                           ▼
   Uses GitHub Client        Serves realistic responses    Collected via gh CLI
   (no token required)       on standard endpoints         (one-time setup)
```

## Quick Start

### 1. Start the Mock Server

#### Option A: Using Docker Compose (Recommended)
```bash
# Start the mock server and other test services
docker-compose -f docker-compose.test.yml up github-mock

# Or start all test services
docker-compose -f docker-compose.test.yml up
```

#### Option B: Direct Python Execution
```bash
# Install dependencies
pip install Flask==3.0.3

# Start the server
python tests/fixtures/github/mock_server.py --port 8080
```

### 2. Run Tests

#### Run Mock Server Tests
```bash
# Run only the mock server integration tests
pytest tests/integration/github/test_github_integration_mock.py -v

# Run with specific mock server URL
MOCK_GITHUB_URL=http://localhost:8080 pytest tests/integration/github/test_github_integration_mock.py -v
```

#### Compare with Real GitHub Tests
```bash
# Run real GitHub tests (requires GITHUB_TOKEN)
GITHUB_TOKEN=your_token pytest tests/integration/github/test_github_integration.py -v

# Run both test suites
pytest tests/integration/github/ -v
```

## Server Endpoints

The mock server implements the following GitHub API endpoints:

### Authentication & User
- `GET /user` - Get authenticated user information
- `GET /rate_limit` - Get API rate limit information

### Repository Operations  
- `GET /repos/{owner}/{repo}` - Get repository details
- `GET /repos/{owner}/{repo}/pulls` - List pull requests
- `GET /users/{username}/repos` - List user repositories

### Check Runs
- `GET /repos/{owner}/{repo}/commits/{ref}/check-runs` - Get check runs for commits

### Error Responses
- Returns realistic 404 responses for nonexistent resources
- Includes proper GitHub API error message format

## Response Data

### Static Responses (Real GitHub Data)
The following endpoints serve real GitHub API responses collected using `gh api`:

| Endpoint | Data Source | Description |
|----------|-------------|-------------|
| `/user` | Real authenticated user | Your actual GitHub user data |
| `/rate_limit` | Real rate limits | Current API rate limit status |
| `/repos/octocat/Hello-World` | Real repository | Famous GitHub test repository |
| `/repos/microsoft/vscode/pulls` | Real pull requests | Actual VS Code pull requests |
| `/repos/microsoft/vscode/commits/main/check-runs` | Real check runs | VS Code CI/CD check runs |

### Dynamic Responses (Generated)
For endpoints not in the static data, the server generates realistic responses:

- **Any repository**: `GET /repos/{owner}/{repo}` generates a realistic repo structure
- **User repositories**: `GET /users/{username}/repos` generates paginated repository lists  
- **Empty responses**: Unknown endpoints return appropriate empty arrays/objects

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MOCK_GITHUB_URL` | `http://localhost:8080` | Base URL for mock server in tests |
| `FLASK_ENV` | `production` | Flask environment mode |

### Docker Configuration

The mock server runs in a Docker container with:
- **Base image**: `python:3.12-slim`
- **Port**: 8080 (configurable)
- **Health check**: HTTP GET to `/`
- **Network**: `test-network` (for integration with other test services)

## Development

### Adding New Endpoints

1. **Collect real response data**:
   ```bash
   # Use GitHub CLI to collect response
   gh api /new/endpoint > tests/fixtures/github/responses/new_endpoint.json
   ```

2. **Add route to mock server**:
   ```python
   @self.app.route("/new/endpoint")
   def get_new_endpoint():
       """Get new endpoint data."""
       return self._serve_response("new_endpoint.json")
   ```

3. **Update tests**:
   ```python
   @pytest.mark.asyncio
   async def test_new_endpoint_mock(self, mock_github_client):
       async with mock_github_client:
           result = await mock_github_client.get("/new/endpoint")
       assert "expected_field" in result
   ```

### Updating Response Data

To refresh the GitHub API response data:

```bash
# Recreate all response files
./scripts/collect_github_responses.sh

# Or collect specific endpoints
gh api /user > tests/fixtures/github/responses/user.json
gh api /rate_limit > tests/fixtures/github/responses/rate_limit.json
```

### Mock Server Development

The mock server is a Flask application located at `tests/fixtures/github/mock_server.py`:

```python
class MockGitHubServer:
    def __init__(self, responses_dir: Path):
        self.app = Flask(__name__)
        self.responses_dir = responses_dir
        self._setup_routes()
    
    def _serve_response(self, filename: str) -> Response:
        """Serve a cached JSON response with realistic headers."""
        # Implementation details...
```

Key features:
- **Response caching**: JSON files are loaded once and cached
- **Pagination support**: Handles `per_page` and `page` parameters
- **Realistic headers**: Adds GitHub API headers for rate limiting
- **Error simulation**: Proper 404 responses with GitHub error format

## Testing Strategies

### Integration Test Patterns

#### 1. Direct Mock Server Tests
Test GitHub client behavior using the mock server:

```python
@pytest.mark.asyncio
async def test_repository_access_mock(self, mock_github_client):
    """Test repository access without real tokens."""
    async with mock_github_client:
        repo = await mock_github_client.get_repo("octocat", "Hello-World")
    
    assert repo["name"] == "Hello-World"
    assert repo["private"] is False
```

#### 2. Comparative Testing
Run the same test logic against both real and mock servers:

```python
@pytest.mark.parametrize("client_fixture", [
    "mock_github_client",  # Uses mock server
    "real_github_client"   # Uses real GitHub (requires token)
])
async def test_user_info(self, request, client_fixture):
    client = request.getfixturevalue(client_fixture)
    async with client:
        user = await client.get_user()
    assert "login" in user
```

#### 3. Performance Testing
Compare mock server performance vs real GitHub API:

```python
@pytest.mark.asyncio
async def test_request_performance_comparison():
    # Mock server should be much faster
    mock_time = await time_request(mock_client.get_user())
    real_time = await time_request(real_client.get_user())
    
    assert mock_time < real_time / 10  # At least 10x faster
```

### CI/CD Integration

#### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test-with-mock:
    runs-on: ubuntu-latest
    
    services:
      github-mock:
        image: ghcr.io/your-org/github-mock-server:latest
        ports:
          - 8080:8080
        options: --health-cmd "curl -f http://localhost:8080/" --health-interval 10s
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run mock integration tests
        env:
          MOCK_GITHUB_URL: http://localhost:8080
        run: pytest tests/integration/github/test_github_integration_mock.py -v
      
      - name: Run real GitHub tests (if token available)
        if: env.GITHUB_TOKEN != null
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: pytest tests/integration/github/test_github_integration.py -v
```

## Troubleshooting

### Common Issues

#### Mock Server Not Starting
```bash
# Check if port is already in use
lsof -i :8080

# Start with different port
python tests/fixtures/github/mock_server.py --port 8081
```

#### Tests Can't Connect to Mock Server
```bash
# Verify server is running
curl http://localhost:8080/

# Check if server is binding to correct interface
python tests/fixtures/github/mock_server.py --host 0.0.0.0 --port 8080
```

#### Missing Response Data
```bash
# Check if response files exist
ls tests/fixtures/github/responses/

# Regenerate response data
gh api /user > tests/fixtures/github/responses/user.json
```

#### Docker Issues
```bash
# Check container logs
docker-compose -f docker-compose.test.yml logs github-mock

# Rebuild container
docker-compose -f docker-compose.test.yml build --no-cache github-mock

# Check container health
docker-compose -f docker-compose.test.yml ps
```

### Integration with Project Test Suite

The mock server integrates seamlessly with the project's existing test infrastructure:

```python
# Test file: tests/integration/github/test_github_integration_mock.py
class TestGitHubIntegrationMock:
    """Integration tests for GitHub client using mock server."""
    
    @pytest.mark.asyncio
    async def test_complete_workflow_mock(self, mock_github_client: GitHubClient) -> None:
        """
        Why: Validate complete GitHub API workflow without external dependencies.
        What: Tests authentication, repository access, and rate limit tracking.
        How: Makes sequential API calls and validates each response component.
        """
        # Implementation following project standards...
```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Direct execution with debug
python tests/fixtures/github/mock_server.py --debug

# Docker with debug
docker-compose -f docker-compose.test.yml up github-mock -e FLASK_ENV=development
```

### Verification Steps

1. **Server Health Check**:
   ```bash
   curl http://localhost:8080/ | jq
   ```

2. **Test Endpoint**:
   ```bash
   curl http://localhost:8080/user | jq
   curl http://localhost:8080/rate_limit | jq
   ```

3. **Test Pagination**:
   ```bash
   curl "http://localhost:8080/users/torvalds/repos?per_page=5&page=1" | jq length
   ```

4. **Test Error Handling**:
   ```bash
   curl -i http://localhost:8080/repos/nonexistent-user/nonexistent-repo
   ```

## Benefits

### For Development
- **Fast feedback**: Tests run in seconds instead of minutes
- **No API limits**: No concern about hitting GitHub API rate limits
- **Offline development**: Work without internet connectivity
- **Predictable data**: Consistent test data across all environments

### For CI/CD
- **No secrets management**: No need to manage GitHub tokens in CI
- **Parallel execution**: Multiple test jobs can run simultaneously  
- **Cost effective**: No API usage costs
- **Reliable builds**: No dependency on GitHub API availability

### For Testing
- **Complete coverage**: Test both success and failure scenarios
- **Edge cases**: Test pagination, rate limiting, and error conditions
- **Reproducible**: Same results every time
- **Isolated**: Tests don't interfere with each other

## Best Practices

### Server Configuration
1. **Keep response data fresh**: Periodically update response files with latest GitHub data
2. **Test both paths**: Run tests against both mock and real GitHub when possible
3. **Version control**: Include response data in version control for consistency
4. **Document endpoints**: Clearly document which endpoints are mocked vs dynamic
5. **Error scenarios**: Include various error response scenarios in your test data
6. **Performance baseline**: Use mock server performance as baseline for optimization

### Test Writing Standards

When writing tests that use the mock server, follow the project's testing best practices:

#### 1. Test Documentation (Why/What/How Pattern)
Every test must include comprehensive docstring documentation:

```python
@pytest.mark.asyncio
async def test_get_repository_mock(self, mock_github_client: GitHubClient) -> None:
    """
    Why: Ensure mock server returns accurate repository data that matches real GitHub API
         response format for integration testing without external dependencies.
    What: Tests retrieving public repository information from mock server.
    How: Requests specific repository and validates response fields match expected values.
    """
    async with mock_github_client:
        repo = await mock_github_client.get_repo("octocat", "Hello-World")

    # Validate repository structure and expected values
    assert repo["name"] == "Hello-World", "Repository name must match requested name"
    assert repo["full_name"] == "octocat/Hello-World", "Full name must match owner/name format"
    assert "id" in repo, "Repository must have an ID field"
```

#### 2. Type Annotations
All test functions must include proper type annotations:

```python
@pytest.fixture
def mock_github_client(
    mock_github_server_url: str, ensure_mock_server_running: str
) -> GitHubClient:
    """Create GitHub client configured to use the mock server."""
    # Implementation...

@pytest.mark.asyncio
async def test_pagination_mock(self, mock_github_client: GitHubClient) -> None:
    """Test pagination functionality with mock server."""
    # Implementation...
```

#### 3. Descriptive Test Names
Use clear, descriptive test names that indicate the exact scenario:

```python
# Good: Specific scenario description
def test_get_authenticated_user_returns_valid_data_mock()
def test_pagination_respects_per_page_limit_mock()
def test_error_handling_returns_404_for_nonexistent_repo_mock()

# Bad: Vague or unclear
def test_user_mock()
def test_pagination_mock()
def test_error_mock()
```

#### 4. Comprehensive Assertions
Use specific assertions with helpful error messages:

```python
# Good: Specific assertions with context
assert repo["name"] == "Hello-World", "Repository name must match requested name"
assert isinstance(user["id"], int), "User ID must be an integer"
assert len(pulls) <= 10, f"Should not exceed per_page limit of 10, got {len(pulls)}"

# Bad: Generic assertions
assert repo["name"]
assert user["id"]
assert pulls
```

#### 5. Test Independence
Each test must be completely independent:

```python
# Good: Each test uses fresh client and data
@pytest.mark.asyncio
async def test_concurrent_requests_mock(self, mock_github_client: GitHubClient) -> None:
    async def fetch_user() -> dict:
        async with mock_github_client:  # Fresh context
            return await mock_github_client.get_user()
    
    # Test implementation using isolated data
```

#### 6. Performance Validation
Include basic performance validation for mock server tests:

```python
@pytest.mark.asyncio
async def test_request_timing_mock(self, mock_github_client: GitHubClient) -> None:
    import time

    async with mock_github_client:
        start_time = time.perf_counter()  # Use precise timing
        await mock_github_client.get_user()
        end_time = time.perf_counter()

        request_time = end_time - start_time

    # Mock server should be very fast
    assert request_time < 0.5, f"Mock server should be fast, took {request_time:.3f}s"
```

#### 7. Error Testing
Test both success and failure scenarios:

```python
@pytest.mark.asyncio
async def test_error_handling_not_found_mock(self, mock_github_client: GitHubClient) -> None:
    from src.github.exceptions import GitHubNotFoundError

    async with mock_github_client:
        with pytest.raises(GitHubNotFoundError) as exc_info:
            await mock_github_client.get_repo("nonexistent-user", "nonexistent-repo")
        
        # Validate exception details
        assert "nonexistent-user" in str(exc_info.value), "Exception should mention the user"
```

#### 8. Fixture Documentation
Document fixtures with Why/What/How pattern:

```python
@pytest.fixture(scope="session")
def ensure_mock_server_running(mock_github_server_url: str) -> str:
    """
    Why: Ensure mock server availability before running tests to prevent
         test failures due to infrastructure issues.
    What: Verifies the mock GitHub server is running and accessible.
    How: Attempts connection with retries, skips tests if server unavailable.
    """
    # Implementation...
```

This mock server infrastructure provides a robust foundation for testing GitHub API integrations reliably and efficiently, while following the project's established testing standards.