# Database Testing Best Practices

This guide provides comprehensive best practices for testing database operations in the agentic coding workflow project.

## Table of Contents

- [General Testing Principles](#general-testing-principles)
- [Database Testing Strategy](#database-testing-strategy)
- [Unit Testing Guidelines](#unit-testing-guidelines)
- [Integration Testing Guidelines](#integration-testing-guidelines)
- [Test Data Management](#test-data-management)
- [Performance Testing Considerations](#performance-testing-considerations)
- [Error Testing Best Practices](#error-testing-best-practices)
- [Code Quality Standards](#code-quality-standards)

## General Testing Principles

### 1. Test Documentation Standard

Every test must include comprehensive docstring documentation following our **Why/What/How** pattern:

```python
def test_repository_handles_constraint_violation():
    """
    Why: Ensure repository gracefully handles database constraint violations
         and provides meaningful error messages for debugging
    What: Tests that duplicate key insertion raises appropriate exception
         with clear error information
    How: Creates duplicate records and verifies exception type and message
    """
    # Test implementation
```

### 2. Test Naming Convention

Use descriptive names that clearly indicate the scenario being tested:

```python
# Good: Describes the exact scenario
def test_get_prs_by_repo_excludes_drafts_by_default()
def test_update_state_raises_error_for_invalid_transition()
def test_bulk_update_returns_zero_for_empty_list()

# Bad: Vague or unclear purpose  
def test_get_prs()
def test_update()
def test_bulk_stuff()
```

### 3. Test Independence

Each test must be completely independent and isolated:

```python
# Good: Each test sets up its own data
def test_create_pull_request():
    repository_id = uuid.uuid4()  # Fresh data for this test
    pr = PullRequest(repository_id=repository_id, ...)
    
# Bad: Relying on global state or other tests
def test_create_pull_request():
    # Assumes repository_id exists from previous test
    pr = PullRequest(repository_id=GLOBAL_REPO_ID, ...)
```

## Database Testing Strategy

### Testing Pyramid

Our database testing follows a structured approach:

```
    Integration Tests (Fewer)
         /             \
        /    Real DB    \
       /   Testcontainers \
      /                   \
     Unit Tests (More)
    /   Mocked Sessions   \
   /     Fast & Isolated   \
  /_______________________\
```

### When to Use Each Type

**Unit Tests**: Use for testing business logic, validation, and repository methods in isolation
- ✅ Repository CRUD operations
- ✅ Model validation and business rules
- ✅ Query construction logic
- ✅ Error handling scenarios

**Integration Tests**: Use for testing actual database interactions and data persistence
- ✅ Complex queries with real data
- ✅ Transaction behavior
- ✅ Migration testing
- ✅ Performance validation

## Unit Testing Guidelines

### 1. Repository Unit Testing

Mock the database session and test repository logic:

```python
@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide mock AsyncSession for testing repository operations."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session

async def test_create_pull_request(repository: PullRequestRepository):
    """Test PR creation calls correct session methods."""
    # Execute
    result = await repository.create(
        repository_id=uuid.uuid4(),
        pr_number=123,
        title="Test PR",
        author="user"
    )
    
    # Verify session interactions
    repository.session.add.assert_called_once()
    repository.session.flush.assert_called_once()
    repository.session.refresh.assert_called_once_with(result)
```

### 2. Model Unit Testing

Test model business logic without database persistence:

```python
def test_pull_request_state_transitions():
    """Test PR state transition validation."""
    pr = PullRequest(
        repository_id=uuid.uuid4(),
        pr_number=1,
        title="Test",
        author="user",
        state=PRState.OPENED
    )
    
    # Valid transitions
    assert pr.can_transition_to(PRState.CLOSED) is True
    assert pr.can_transition_to(PRState.MERGED) is True
    
    # Invalid transitions after merge
    pr.state = PRState.MERGED
    assert pr.can_transition_to(PRState.OPENED) is False
```

### 3. Mock Setup Patterns

Use consistent patterns for mock setup:

```python
def setup_mock_query_result(session: AsyncMock, return_value: Any) -> None:
    """Helper to setup consistent mock query results."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = return_value
    session.execute.return_value = mock_result

def setup_mock_list_result(session: AsyncMock, return_list: list[Any]) -> None:
    """Helper to setup mock list query results."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = return_list
    mock_result.scalars.return_value = mock_scalars
    session.execute.return_value = mock_result
```

## Integration Testing Guidelines

### 1. Real Database Testing

Use testcontainers for integration tests requiring real database:

```python
@pytest.mark.asyncio
async def test_pull_request_crud_operations(async_session_factory):
    """Test complete PR CRUD lifecycle with real database."""
    async with async_session_factory() as session:
        repo = PullRequestRepository(session)
        
        # Create
        pr = await repo.create(
            repository_id=uuid.uuid4(),
            pr_number=123,
            title="Integration Test PR",
            author="testuser"
        )
        assert pr.id is not None
        
        # Read
        found_pr = await repo.get_by_id(pr.id)
        assert found_pr is not None
        assert found_pr.title == "Integration Test PR"
        
        # Update
        updated_pr = await repo.update(found_pr, title="Updated Title")
        assert updated_pr.title == "Updated Title"
        
        # Delete
        success = await repo.delete_by_id(pr.id)
        assert success is True
        
        # Verify deletion
        deleted_pr = await repo.get_by_id(pr.id)
        assert deleted_pr is None
```

### 2. Transaction Testing

Test transaction behavior and rollback scenarios:

```python
async def test_transaction_rollback_on_error(async_session_factory):
    """Test that failed operations trigger proper rollback."""
    async with async_session_factory() as session:
        repo = PullRequestRepository(session)
        
        # Create initial PR
        pr = await repo.create(
            repository_id=uuid.uuid4(),
            pr_number=123,
            title="Test PR",
            author="user"
        )
        await session.commit()
        
        try:
            # Attempt operation that will fail
            await repo.create(
                repository_id=pr.repository_id,
                pr_number=123,  # Duplicate number - should fail
                title="Duplicate",
                author="user"
            )
            await session.commit()
        except Exception:
            await session.rollback()
            
        # Verify original data is intact
        found_pr = await repo.get_by_id(pr.id)
        assert found_pr.title == "Test PR"
```

### 3. Complex Query Testing

Test complex queries with realistic data sets:

```python
async def test_get_prs_with_failed_checks_query(async_session_factory):
    """Test complex query for PRs with failed checks."""
    async with async_session_factory() as session:
        pr_repo = PullRequestRepository(session)
        check_repo = CheckRunRepository(session)
        
        # Setup test data
        pr = await pr_repo.create(
            repository_id=uuid.uuid4(),
            pr_number=123,
            title="PR with Failed Checks",
            author="user"
        )
        
        failed_check = await check_repo.create(
            pr_id=pr.id,
            external_id="check-123",
            check_name="lint",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.FAILURE
        )
        
        await session.commit()
        
        # Test the query
        prs_with_failures = await pr_repo.get_prs_with_failed_checks(
            pr.repository_id,
            limit=10
        )
        
        assert len(prs_with_failures) == 1
        assert prs_with_failures[0].id == pr.id
```

## Test Data Management

### 1. Use Factory Patterns

Create reusable factory functions for test data:

```python
def create_test_repository(**kwargs) -> dict:
    """Factory for test repository data."""
    defaults = {
        "url": "https://github.com/test/repo",
        "name": "repo",
        "full_name": "test/repo",
        "status": RepositoryStatus.ACTIVE,
        "polling_interval_minutes": 15,
        "failure_count": 0
    }
    defaults.update(kwargs)
    return defaults

def create_test_pull_request(repository_id: uuid.UUID, **kwargs) -> dict:
    """Factory for test pull request data."""
    defaults = {
        "repository_id": repository_id,
        "pr_number": random.randint(1, 9999),
        "title": f"Test PR {uuid.uuid4().hex[:8]}",
        "author": "testuser",
        "state": PRState.OPENED,
        "draft": False
    }
    defaults.update(kwargs)
    return defaults
```

### 2. Unique Test Data

Ensure test data is unique to avoid conflicts:

```python
def test_create_multiple_prs():
    """Test creating multiple PRs with unique data."""
    repository_id = uuid.uuid4()
    
    for i in range(3):
        pr_data = create_test_pull_request(
            repository_id=repository_id,
            pr_number=i + 1,  # Unique PR numbers
            title=f"PR {i + 1} - {uuid.uuid4().hex[:8]}"  # Unique titles
        )
        # Test PR creation
```

### 3. Realistic Test Data

Use realistic data that matches production patterns:

```python
# Good: Realistic GitHub-style data
pr = PullRequest(
    repository_id=uuid.uuid4(),
    pr_number=1547,
    title="Fix: Handle null pointer exception in PR analyzer",
    body="This PR fixes a critical bug where the PR analyzer crashes when...",
    author="developer123",
    head_sha="abc123def456",
    base_sha="789xyz012",
    state=PRState.OPENED
)

# Bad: Artificial test data
pr = PullRequest(
    repository_id=uuid.uuid4(),
    pr_number=1,
    title="test",
    author="user"
)
```

## Performance Testing Considerations

### 1. Basic Performance Validation

Include basic timing validation in integration tests:

```python
import time

async def test_pr_lookup_performance(async_session_factory):
    """Test that PR lookup meets performance requirements."""
    async with async_session_factory() as session:
        repo = PullRequestRepository(session)
        
        # Setup test data
        pr = await repo.create(**create_test_pull_request(uuid.uuid4()))
        await session.commit()
        
        # Measure lookup performance
        start_time = time.perf_counter()
        found_pr = await repo.get_by_id(pr.id)
        end_time = time.perf_counter()
        
        assert found_pr is not None
        # Should complete within reasonable time for integration tests
        assert (end_time - start_time) < 0.050  # 50ms threshold
```

### 2. Bulk Operation Efficiency

Test bulk operations for efficiency patterns:

```python
async def test_bulk_update_efficiency(async_session_factory):
    """Test that bulk operations scale efficiently."""
    async with async_session_factory() as session:
        repo = PullRequestRepository(session)
        
        # Create multiple PRs
        pr_ids = []
        for i in range(10):
            pr = await repo.create(**create_test_pull_request(uuid.uuid4()))
            pr_ids.append(pr.id)
        
        await session.commit()
        
        # Test bulk update
        start_time = time.perf_counter()
        rows_updated = await repo.bulk_update_last_checked(pr_ids)
        end_time = time.perf_counter()
        
        assert rows_updated == 10
        # Bulk operation should be faster than individual updates
        assert (end_time - start_time) < 0.100  # 100ms for 10 records
```

Note: For comprehensive performance testing, see [Performance Testing Infrastructure (#32)](https://github.com/feddericovonwernich/agentic-coding-workflow/issues/32).

## Error Testing Best Practices

### 1. Test Expected Exceptions

Test that operations fail appropriately for invalid inputs:

```python
async def test_get_by_id_or_raise_with_invalid_id(repository):
    """Test that get_by_id_or_raise raises ValueError for non-existent ID."""
    repository.session.get.return_value = None
    
    with pytest.raises(ValueError, match="PullRequest with id .* not found"):
        await repository.get_by_id_or_raise(uuid.uuid4())
```

### 2. Test Constraint Violations

Test database constraint handling:

```python
async def test_duplicate_pr_number_constraint(async_session_factory):
    """Test that duplicate PR numbers within same repo raise constraint error."""
    async with async_session_factory() as session:
        repo = PullRequestRepository(session)
        repository_id = uuid.uuid4()
        
        # Create first PR
        await repo.create(
            repository_id=repository_id,
            pr_number=123,
            title="First PR",
            author="user"
        )
        await session.commit()
        
        # Attempt to create duplicate
        with pytest.raises(IntegrityError):
            await repo.create(
                repository_id=repository_id,
                pr_number=123,  # Same number, same repo
                title="Duplicate PR",
                author="user"
            )
            await session.commit()
```

### 3. Test Connection Errors

Test repository behavior under connection failures:

```python
async def test_repository_handles_connection_error(mock_session):
    """Test repository handles database connection errors gracefully."""
    mock_session.execute.side_effect = SQLAlchemyError("Connection lost")
    
    repo = PullRequestRepository(mock_session)
    
    with pytest.raises(SQLAlchemyError, match="Connection lost"):
        await repo.get_by_id(uuid.uuid4())
```

## Code Quality Standards

### 1. Type Annotations

All test code must have proper type annotations:

```python
@pytest.fixture
def repository(mock_session: AsyncMock) -> PullRequestRepository:
    """Create repository instance for testing."""
    return PullRequestRepository(mock_session)

async def test_create_pull_request(
    repository: PullRequestRepository,
    sample_pr_data: dict[str, Any]
) -> None:
    """Test PR creation with typed parameters."""
    result: PullRequest = await repository.create(**sample_pr_data)
    assert isinstance(result, PullRequest)
```

### 2. Clear Assertions

Use specific assertions with helpful error messages:

```python
# Good: Specific assertions
assert result.state == PRState.OPENED
assert len(results) == 3
assert result.created_at is not None

# Bad: Generic assertions
assert result
assert results
assert result.created_at
```

### 3. Test Organization

Group related tests in classes with descriptive names:

```python
class TestPullRequestCreation:
    """Tests for PR creation scenarios."""
    
    async def test_create_with_minimal_data(self):
        """Test creating PR with only required fields."""
        
    async def test_create_with_full_data(self):
        """Test creating PR with all optional fields."""
        
    async def test_create_with_invalid_data(self):
        """Test PR creation validation errors."""

class TestPullRequestQueries:
    """Tests for PR query methods."""
    
    async def test_get_by_repo_and_number(self):
        """Test finding PR by repository and number."""
```

### 4. Test Maintenance

Keep tests maintainable and easy to understand:

- Use descriptive variable names
- Extract common setup into fixtures
- Keep test methods focused on single scenarios  
- Avoid complex logic in test code
- Update tests when requirements change

## Summary

Following these best practices ensures:
- **Reliable tests** that catch real issues
- **Maintainable test code** that evolves with the system
- **Clear test intent** through documentation and naming
- **Comprehensive coverage** of both success and failure scenarios
- **Efficient test execution** with proper isolation and data management

For specific guidance on database testing methodology, see [Database Testing Guide](./database-testing.md).