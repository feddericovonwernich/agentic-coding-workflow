# Testing Best Practices

This document provides comprehensive testing guidelines for the Agentic Coding Workflow project. These practices ensure reliable, maintainable tests that provide meaningful coverage and feedback for both human developers and AI testing subagents.

## Table of Contents

- [Testing Philosophy](#testing-philosophy)
- [Test Structure and Organization](#test-structure-and-organization)
- [Documentation Requirements](#documentation-requirements)
- [Unit Testing Guidelines](#unit-testing-guidelines)
- [Integration Testing Guidelines](#integration-testing-guidelines)
- [Test Data Management](#test-data-management)
- [Assertion Standards](#assertion-standards)
- [Coverage Requirements](#coverage-requirements)
- [Testing Tools and Configuration](#testing-tools-and-configuration)
- [Performance Testing](#performance-testing)
- [Error Scenario Testing](#error-scenario-testing)

## Testing Philosophy

### Core Principles

1. **Test Behavior, Not Implementation**
   - Focus on what the code should do, not how it does it
   - Test public interfaces and contracts
   - Avoid testing internal implementation details

2. **Comprehensive Documentation**
   - Every test MUST include Why/What/How documentation
   - Tests serve as living documentation of expected behavior
   - Clear test names that describe scenarios

3. **Independence and Isolation**
   - Each test is completely independent
   - Tests can run in any order
   - No shared state between tests
   - Clean setup and teardown

4. **Fast Feedback Loop**
   - Unit tests provide immediate feedback (< 1 second)
   - Integration tests validate real behavior (< 10 seconds)
   - Quick test execution enables rapid development

5. **Comprehensive Error Coverage**
   - Test both success and failure paths
   - Validate error handling and recovery
   - Test edge cases and boundary conditions

### Testing Pyramid Strategy

```
    Integration Tests (30%)
      Real Database
    Complex Scenarios
     E2E Workflows
  /                     \
 /                       \
Unit Tests (70%)
Mocked Dependencies
Business Logic Testing
Fast & Isolated
```

**Distribution Guidelines:**
- **70% Unit Tests**: Fast, isolated testing with mocked dependencies
- **30% Integration Tests**: Real service testing with actual database

## Test Structure and Organization

### Naming Conventions

Use descriptive names that clearly indicate the scenario:

```python
# Good: Describes the exact scenario being tested
def test_get_prs_by_repository_excludes_draft_prs_by_default()
def test_create_pull_request_raises_error_for_duplicate_number()
def test_analyze_check_failure_categorizes_lint_errors_correctly()
def test_github_client_retries_on_rate_limit_with_backoff()

# Bad: Vague or unclear purpose
def test_get_prs()
def test_create_pr()
def test_analyze()
def test_client_retry()
```

### Test Organization by Feature

Organize tests in classes by feature or component:

```python
class TestPullRequestCreation:
    """Tests for pull request creation scenarios."""
    
    async def test_create_with_minimal_required_data(self):
        """Test creating PR with only required fields."""
        
    async def test_create_with_full_optional_data(self):
        """Test creating PR with all optional fields."""
        
    async def test_create_validates_pr_number_uniqueness(self):
        """Test that duplicate PR numbers are rejected."""

class TestPullRequestQueries:
    """Tests for pull request query operations."""
    
    async def test_get_by_repository_filters_by_state(self):
        """Test filtering PRs by state (open/closed/merged)."""
        
    async def test_get_recent_prs_respects_time_boundaries(self):
        """Test that recent PR queries use correct date ranges."""
```

## Documentation Requirements

### Mandatory Why/What/How Pattern

Every test MUST include comprehensive docstring documentation:

```python
def test_analyzer_categorizes_lint_failures():
    """
    Why: Ensure the analyzer correctly identifies lint failures to route them
         for automatic fixing rather than human escalation. Proper categorization
         is critical for determining the appropriate fix strategy.
    
    What: Tests that CheckAnalyzer.analyze() returns category='lint' for
          eslint failure logs and includes confidence score above threshold.
    
    How: Provides sample eslint failure logs with typical error patterns,
         calls the analyzer, and verifies the returned analysis has correct
         category, confidence score >= 0.8, and suggested fix strategy.
    """
    # Test implementation here
```

### Documentation Template

Use this template for all tests:

```python
def test_feature_scenario_condition():
    """
    Why: [Business reason why this test exists - what problem does it prevent?
         What confidence does it provide? Why is this behavior important?]
    
    What: [Specific functionality being tested - exact inputs and expected outputs.
          What methods/functions are called? What state changes are expected?]
    
    How: [Testing approach and methodology - how is the test structured?
         What test data is used? How are assertions validated?]
    """
    # Test implementation
```

## Unit Testing Guidelines

### When to Use Unit Tests (70% of tests)

- Testing business logic and validation rules
- Repository methods with mocked database sessions
- Model behavior and state transitions
- Error handling and edge cases
- Pure functions and calculations

### Mocking Strategies

Use consistent patterns for mocking dependencies:

```python
@pytest.fixture
def mock_github_client() -> AsyncMock:
    """Provide mock GitHub client for testing."""
    client = AsyncMock()
    client.get_pull_request = AsyncMock()
    client.list_check_runs = AsyncMock()
    client.rate_limiter = AsyncMock()
    return client

@pytest.fixture
def mock_database_session() -> AsyncMock:
    """Provide mock database session for repository testing."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    session.add = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session

# Helper functions for consistent mock setup
def setup_mock_query_result(session: AsyncMock, return_value: Any) -> None:
    """Setup mock session to return specific query result."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = return_value
    session.execute.return_value = mock_result

def setup_mock_list_result(session: AsyncMock, return_list: List[Any]) -> None:
    """Setup mock session to return list of results."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = return_list
    mock_result.scalars.return_value = mock_scalars
    session.execute.return_value = mock_result
```

### Unit Test Example

```python
async def test_pull_request_repository_creates_with_valid_data():
    """
    Why: Ensure the repository correctly creates PR records with valid data
         and properly handles database session operations for consistency.
    
    What: Tests that PullRequestRepository.create() successfully creates a PR
          with required fields and returns the created instance with ID.
    
    How: Mocks database session, calls create with valid PR data, verifies
         session methods are called correctly and returned PR has expected values.
    """
    # Arrange
    mock_session = AsyncMock()
    repository = PullRequestRepository(mock_session)
    
    pr_data = create_test_pull_request_data(
        repository_id=uuid.uuid4(),
        pr_number=123,
        title="Test PR",
        author="testuser"
    )
    
    # Mock the created PR that would be returned from database
    created_pr = PullRequest(id=uuid.uuid4(), **pr_data)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    
    # Act
    result = await repository.create(**pr_data)
    
    # Assert
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()
    mock_session.refresh.assert_called_once()
    
    # Verify the created PR has expected properties
    assert result.pr_number == 123
    assert result.title == "Test PR"
    assert result.author == "testuser"
    assert result.state == PRState.OPENED  # Default state
```

## Integration Testing Guidelines

### When to Use Integration Tests (30% of tests)

- Testing with real database using testcontainers
- Complex queries with actual data relationships
- Transaction behavior and rollback scenarios
- End-to-end workflow testing
- Performance validation with realistic data

### Real Database Testing

Use testcontainers for integration tests:

```python
@pytest.mark.asyncio
async def test_pull_request_crud_operations_with_real_database():
    """
    Why: Verify that PR CRUD operations work correctly with real PostgreSQL
         database including constraints, triggers, and transaction handling.
    
    What: Tests complete lifecycle of creating, reading, updating, and deleting
          a pull request using actual database operations.
    
    How: Uses testcontainer PostgreSQL, creates real PR record, performs CRUD
         operations, and verifies data persistence and constraint enforcement.
    """
    async with async_session_factory() as session:
        repository = PullRequestRepository(session)
        
        # Create
        original_pr = await repository.create(
            repository_id=uuid.uuid4(),
            pr_number=123,
            title="Integration Test PR",
            author="testuser",
            body="Test description"
        )
        await session.commit()
        
        assert original_pr.id is not None
        assert original_pr.created_at is not None
        
        # Read
        found_pr = await repository.get_by_id(original_pr.id)
        assert found_pr is not None
        assert found_pr.title == "Integration Test PR"
        assert found_pr.pr_number == 123
        
        # Update
        updated_pr = await repository.update(
            found_pr, 
            title="Updated Integration Test PR",
            body="Updated description"
        )
        await session.commit()
        
        assert updated_pr.title == "Updated Integration Test PR"
        assert updated_pr.body == "Updated description"
        assert updated_pr.updated_at > updated_pr.created_at
        
        # Delete
        success = await repository.delete_by_id(original_pr.id)
        await session.commit()
        
        assert success is True
        
        # Verify deletion
        deleted_pr = await repository.get_by_id(original_pr.id)
        assert deleted_pr is None
```

### Transaction Testing

Test rollback and transaction boundaries:

```python
async def test_transaction_rollback_on_constraint_violation():
    """
    Why: Ensure database transactions are properly rolled back when constraint
         violations occur, maintaining data consistency and preventing partial updates.
    
    What: Tests that attempting to create duplicate PR numbers triggers rollback
          and leaves database in consistent state with original data intact.
    
    How: Creates initial PR, commits, then attempts duplicate creation in new
         transaction, verifies exception is raised and original data is preserved.
    """
    async with async_session_factory() as session:
        repository = PullRequestRepository(session)
        repository_id = uuid.uuid4()
        
        # Create initial PR
        original_pr = await repository.create(
            repository_id=repository_id,
            pr_number=123,
            title="Original PR",
            author="user1"
        )
        await session.commit()
        
        # Attempt to create duplicate in new session
        async with async_session_factory() as new_session:
            new_repository = PullRequestRepository(new_session)
            
            with pytest.raises(IntegrityError):
                await new_repository.create(
                    repository_id=repository_id,
                    pr_number=123,  # Duplicate number
                    title="Duplicate PR",
                    author="user2"
                )
                await new_session.commit()
        
        # Verify original data is intact
        async with async_session_factory() as verify_session:
            verify_repository = PullRequestRepository(verify_session)
            found_pr = await verify_repository.get_by_id(original_pr.id)
            
            assert found_pr is not None
            assert found_pr.title == "Original PR"
            assert found_pr.author == "user1"
```

## Test Data Management

### Factory Patterns

Create reusable factories for consistent test data:

```python
def create_test_repository_data(**overrides) -> Dict[str, Any]:
    """Factory for test repository data.
    
    Provides realistic default values that can be overridden for specific tests.
    """
    defaults = {
        "url": f"https://github.com/test-org/test-repo-{uuid.uuid4().hex[:8]}",
        "name": f"test-repo-{uuid.uuid4().hex[:8]}",
        "full_name": f"test-org/test-repo-{uuid.uuid4().hex[:8]}",
        "status": RepositoryStatus.ACTIVE,
        "polling_interval_minutes": 15,
        "failure_count": 0,
        "last_checked_at": datetime.utcnow() - timedelta(minutes=5)
    }
    defaults.update(overrides)
    return defaults

def create_test_pull_request_data(repository_id: uuid.UUID, **overrides) -> Dict[str, Any]:
    """Factory for test pull request data."""
    defaults = {
        "repository_id": repository_id,
        "pr_number": random.randint(1, 9999),
        "title": f"Test PR {uuid.uuid4().hex[:8]}",
        "body": f"Test PR description {uuid.uuid4().hex[:8]}",
        "author": f"testuser{random.randint(1, 999)}",
        "head_sha": f"abc{uuid.uuid4().hex[:8]}def",
        "base_sha": f"xyz{uuid.uuid4().hex[:8]}123",
        "state": PRState.OPENED,
        "draft": False
    }
    defaults.update(overrides)
    return defaults

def create_test_check_run_data(pr_id: uuid.UUID, **overrides) -> Dict[str, Any]:
    """Factory for test check run data."""
    defaults = {
        "pr_id": pr_id,
        "external_id": f"check-{uuid.uuid4().hex[:12]}",
        "check_name": f"test-check-{random.choice(['lint', 'test', 'build'])}",
        "status": CheckStatus.COMPLETED,
        "conclusion": random.choice(list(CheckConclusion)),
        "started_at": datetime.utcnow() - timedelta(minutes=2),
        "completed_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    return defaults
```

### Unique Test Data

Ensure test data uniqueness to prevent conflicts:

```python
def test_create_multiple_pull_requests_with_unique_data():
    """
    Why: Verify that multiple PRs can be created within the same repository
         without conflicts when using unique PR numbers.
    
    What: Tests creating 3 different PRs in the same repository with
          unique PR numbers and validates all are stored correctly.
    
    How: Uses factory pattern to generate unique data for each PR,
         creates them sequentially, and verifies all have distinct IDs.
    """
    repository_id = uuid.uuid4()
    created_prs = []
    
    for i in range(3):
        pr_data = create_test_pull_request_data(
            repository_id=repository_id,
            pr_number=i + 100,  # Ensure unique PR numbers
            title=f"PR {i + 1} - {uuid.uuid4().hex[:8]}"  # Unique titles
        )
        
        pr = await repository.create(**pr_data)
        created_prs.append(pr)
    
    # Verify all PRs were created with unique IDs
    pr_ids = [pr.id for pr in created_prs]
    assert len(set(pr_ids)) == 3  # All IDs are unique
    
    # Verify PR numbers are as expected
    pr_numbers = [pr.pr_number for pr in created_prs]
    assert pr_numbers == [100, 101, 102]
```

### Realistic Test Data

Use realistic data that matches production patterns:

```python
# Good: Realistic GitHub-style data
def create_realistic_pull_request():
    return create_test_pull_request_data(
        repository_id=uuid.uuid4(),
        pr_number=1547,
        title="Fix: Handle null pointer exception in PR analyzer (#1540)",
        body="""This PR fixes a critical bug where the PR analyzer crashes when 
        encountering null values in check run metadata.
        
        Changes:
        - Add null checks in CheckRunAnalyzer.analyze()
        - Update error handling to log context information
        - Add regression tests for null metadata scenarios
        
        Fixes #1540""",
        author="developer123",
        head_sha="a1b2c3d4e5f6789",
        base_sha="z9y8x7w6v5u4321",
        state=PRState.OPENED
    )

# Bad: Artificial, unrealistic test data
def create_artificial_pull_request():
    return create_test_pull_request_data(
        repository_id=uuid.uuid4(),
        pr_number=1,
        title="test",
        body="test description",
        author="user"
    )
```

## Assertion Standards

### Specific Assertions

Use specific assertions with helpful error messages:

```python
# Good: Specific assertions that provide clear feedback
def test_pull_request_state_transitions():
    """Test valid and invalid PR state transitions."""
    
    pr = create_test_pull_request(state=PRState.OPENED)
    
    # Test valid transitions
    assert pr.can_transition_to(PRState.CLOSED) is True, \
        "Open PR should be able to transition to closed"
    assert pr.can_transition_to(PRState.MERGED) is True, \
        "Open PR should be able to transition to merged"
    
    # Test state after transition
    pr.state = PRState.MERGED
    assert pr.state == PRState.MERGED, \
        "PR state should be updated to merged"
    
    # Test invalid transitions after merge
    assert pr.can_transition_to(PRState.OPENED) is False, \
        "Merged PR should not be able to reopen"
    assert pr.can_transition_to(PRState.CLOSED) is False, \
        "Merged PR should not be able to transition to closed"

# Bad: Generic assertions without context
def test_pr_transitions():
    pr = create_test_pull_request()
    assert pr.can_transition_to(PRState.CLOSED)  # No context
    assert pr.state  # Too generic
    pr.state = PRState.MERGED
    assert not pr.can_transition_to(PRState.OPENED)  # Unclear why
```

### Multiple Assertion Strategies

Test multiple aspects with clear grouping:

```python
def test_github_client_rate_limit_handling():
    """
    Why: Ensure GitHub client properly handles rate limit responses and
         implements appropriate backoff strategies to prevent API abuse.
    
    What: Tests that rate limit errors trigger exponential backoff,
          rate limit information is tracked, and requests succeed after reset.
    
    How: Mocks GitHub API responses with rate limit headers, verifies
         client behavior matches expected backoff patterns and tracking.
    """
    # Setup rate limit scenario
    mock_response = create_rate_limit_response(
        limit=5000,
        remaining=0,
        reset_time=int(time.time()) + 60
    )
    
    with pytest.raises(GitHubRateLimitError) as exc_info:
        await github_client.get_pull_request("owner", "repo", 123)
    
    # Verify exception details
    error = exc_info.value
    assert error.status_code == 429, "Rate limit error should have 429 status"
    assert error.reset_time > time.time(), "Reset time should be in the future"
    assert "rate limit exceeded" in str(error).lower(), \
        "Error message should mention rate limiting"
    
    # Verify rate limit tracking
    rate_limit_info = github_client.rate_limiter.get_rate_limit("core")
    assert rate_limit_info is not None, "Rate limit info should be tracked"
    assert rate_limit_info.limit == 5000, "Limit should match API response"
    assert rate_limit_info.remaining == 0, "Remaining should be zero"
    assert rate_limit_info.reset == mock_response.reset_time, \
        "Reset time should match API response"
```

## Coverage Requirements

### Minimum Coverage Thresholds

- **Overall project coverage**: 80% minimum
- **New code coverage**: 90% minimum
- **Critical path coverage**: 95% minimum

### Coverage Configuration

Configure pytest-cov for meaningful coverage reporting:

```python
# pyproject.toml
[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/migrations/*", 
    "*/__pycache__/*",
    "*/venv/*",
    "*/.venv/*"
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if self.debug:",
    "if settings.DEBUG",
    "raise AssertionError",
    "raise NotImplementedError",
    "if 0:",
    "if __name__ == .__main__.:",
    "class .*\\bProtocol\\):",
    "@(abc\\.)?abstractmethod",
]
precision = 2
show_missing = true
fail_under = 80
```

### Critical Path Coverage

Ensure critical functionality has comprehensive coverage:

```python
# Example: Critical path testing for PR processing
def test_complete_pr_processing_workflow():
    """
    Why: Verify the entire PR processing workflow functions correctly
         from detection through analysis to fix application.
    
    What: Tests the complete flow: detect new PR -> analyze checks ->
          categorize failures -> apply fixes -> update status.
    
    How: Creates realistic PR with failed checks, processes through
         each workflow stage, and validates state transitions and outputs.
    """
    # This test covers the critical path and should have comprehensive coverage
    pass
```

## Testing Tools and Configuration

### Required Testing Dependencies

```bash
# Core testing framework
pip install pytest pytest-asyncio

# Coverage reporting
pip install pytest-cov

# Integration testing
pip install testcontainers

# Test fixtures and mocking
pip install pytest-mock

# Property-based testing (for complex scenarios)
pip install hypothesis
```

### Pytest Configuration

```python
# pyproject.toml
[tool.pytest.ini_options]
minversion = "7.0"
addopts = [
    "-ra",                    # Show summary of all test results
    "--strict-markers",       # Require explicit marker registration
    "--strict-config",        # Strict configuration validation
    "--disable-warnings",     # Reduce noise in test output
    "--cov=src",             # Enable coverage for src directory
    "--cov-report=html",     # Generate HTML coverage report
    "--cov-report=term-missing",  # Show missing coverage in terminal
]
testpaths = ["tests"]
markers = [
    "unit: Unit tests with mocked dependencies",
    "integration: Integration tests with real services", 
    "real_database: Tests requiring actual PostgreSQL database",
    "slow: Tests that take a long time to run",
    "performance: Performance benchmark tests",
]
asyncio_mode = "auto"  # Automatically handle async tests
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run only unit tests (fast)
pytest tests/unit/ -v -m unit

# Run integration tests
pytest tests/integration/ -v -m integration

# Run with coverage
pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# Run tests in parallel (with pytest-xdist)
pytest tests/ -n auto

# Run only failed tests from last run
pytest tests/ --lf

# Run specific test patterns
pytest tests/ -k "test_pull_request"

# Generate coverage report
pytest tests/ --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

## Performance Testing

### Basic Performance Validation

Include timing validation in integration tests:

```python
import time

async def test_repository_query_performance():
    """
    Why: Ensure repository queries meet performance requirements
         to maintain responsive user experience and prevent timeouts.
    
    What: Tests that common repository queries complete within acceptable
          time limits under normal load conditions.
    
    How: Measures execution time for typical query operations and
         validates against established performance thresholds.
    """
    # Setup test data
    repository_id = uuid.uuid4() 
    for i in range(50):  # Create realistic data volume
        await pr_repository.create(**create_test_pull_request_data(repository_id))
    
    # Measure query performance
    start_time = time.perf_counter()
    results = await pr_repository.get_by_repository(
        repository_id, 
        limit=20,
        state=PRState.OPENED
    )
    end_time = time.perf_counter()
    
    query_time = end_time - start_time
    
    # Validate performance
    assert len(results) <= 20, "Should respect limit parameter"
    assert query_time < 0.100, f"Query took {query_time:.3f}s, should be < 100ms"
    
    # Validate results are correct
    assert all(pr.state == PRState.OPENED for pr in results), \
        "All returned PRs should be in opened state"
```

## Error Scenario Testing

### Exception Testing Patterns

Test expected exceptions with proper validation:

```python
async def test_repository_handles_constraint_violations():
    """
    Why: Ensure repository gracefully handles database constraint violations
         and provides meaningful error information for debugging and recovery.
    
    What: Tests that unique constraint violations raise appropriate exceptions
          with clear error messages and proper error categorization.
    
    How: Creates conflicting data that violates unique constraints,
         attempts database operations, and validates exception handling.
    """
    repository_id = uuid.uuid4()
    
    # Create initial PR
    await pr_repository.create(
        repository_id=repository_id,
        pr_number=123,
        title="Original PR",
        author="user1"
    )
    
    # Attempt to create duplicate
    with pytest.raises(IntegrityError) as exc_info:
        await pr_repository.create(
            repository_id=repository_id,
            pr_number=123,  # Duplicate number
            title="Duplicate PR", 
            author="user2"
        )
    
    # Validate exception details
    error = exc_info.value
    assert "unique constraint" in str(error).lower(), \
        "Error should mention constraint violation"
    assert "pr_number" in str(error).lower(), \
        "Error should indicate which field caused the violation"
```

### Error Recovery Testing

Test system behavior under failure conditions:

```python
async def test_github_client_recovers_from_network_errors():
    """
    Why: Ensure GitHub client can recover from transient network failures
         without losing data or leaving the system in an inconsistent state.
    
    What: Tests that network timeouts and connection errors trigger proper
          retry logic with exponential backoff and eventual success.
    
    How: Simulates network failures using mock exceptions, verifies retry
         attempts follow expected patterns, and validates final success.
    """
    # Setup mock to fail twice then succeed
    mock_responses = [
        aiohttp.ClientError("Connection timeout"),
        aiohttp.ClientError("Connection reset"),
        {"id": 123, "title": "Test PR"}  # Success on third attempt
    ]
    
    github_client._session.get.side_effect = mock_responses
    
    # Should succeed after retries
    result = await github_client.get_pull_request("owner", "repo", 123)
    
    # Verify result
    assert result["id"] == 123
    assert result["title"] == "Test PR"
    
    # Verify retry attempts
    assert github_client._session.get.call_count == 3, \
        "Should have made 3 attempts (2 failures + 1 success)"
```

---

This document serves as the canonical reference for testing practices. All tests, whether written by humans or AI testing subagents, must follow these guidelines to ensure consistent, reliable, and maintainable test coverage across the project.