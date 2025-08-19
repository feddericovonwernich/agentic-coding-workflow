# Database Testing Methodology

This document outlines our comprehensive methodology for testing database operations in the agentic coding workflow project.

## Table of Contents

- [Testing Philosophy](#testing-philosophy)
- [Testing Strategy](#testing-strategy)
- [Test Categories](#test-categories)
- [Database Test Environments](#database-test-environments)
- [Testing Patterns](#testing-patterns)
- [Data Management](#data-management)
- [Integration Testing Approach](#integration-testing-approach)
- [Performance Testing Strategy](#performance-testing-strategy)
- [Error Scenario Testing](#error-scenario-testing)
- [Test Lifecycle Management](#test-lifecycle-management)

## Testing Philosophy

### Core Principles

Our database testing methodology is built on these fundamental principles:

1. **Test Behavior, Not Implementation**
   - Focus on what the database layer should do, not how it does it
   - Test contracts and interfaces, not internal SQL details
   - Validate business rules and constraints

2. **Realistic Test Scenarios**
   - Use data patterns that mirror production usage
   - Test with realistic data volumes and relationships
   - Include edge cases and boundary conditions

3. **Fast Feedback Loop**
   - Unit tests provide immediate feedback (< 1 second)
   - Integration tests validate real behavior (< 10 seconds)
   - Comprehensive coverage without sacrificing speed

4. **Isolation and Independence**
   - Each test is completely independent
   - Tests can run in any order
   - No shared state between tests

5. **Comprehensive Error Coverage**
   - Test both success and failure paths
   - Validate error handling and recovery
   - Ensure graceful degradation

## Testing Strategy

### Testing Pyramid for Database Operations

```
     Integration Tests (30%)
          Real Database
        Complex Scenarios
         E2E Workflows
    /                     \
   /                       \
  Unit Tests (70%)
  Mocked Sessions
  Business Logic
  Error Handling
 Fast & Isolated
```

### Strategic Test Distribution

**Unit Tests (70% of tests)**: Fast, isolated testing of business logic
- Repository methods with mocked database sessions
- Model validation and business rules
- Query construction logic
- Error handling paths

**Integration Tests (30% of tests)**: Realistic database scenarios
- Real PostgreSQL with testcontainers
- Complex queries with actual data
- Transaction behavior
- Migration testing

## Test Categories

### 1. Model Testing

**Purpose**: Validate SQLAlchemy models, relationships, and business logic

```python
class TestPullRequestModel:
    """Test PullRequest model functionality."""
    
    def test_pull_request_creation(self):
        """
        Why: Ensure PR model can be created with valid data
        What: Tests model instantiation and field assignment
        How: Creates PR with required fields and validates attributes
        """
        pr = PullRequest(
            repository_id=uuid.uuid4(),
            pr_number=123,
            title="Test PR",
            author="testuser",
            state=PRState.OPENED
        )
        
        assert pr.pr_number == 123
        assert pr.state == PRState.OPENED
        assert pr.title == "Test PR"
    
    def test_state_transition_validation(self):
        """
        Why: Validate business rules for PR state transitions
        What: Tests can_transition_to method with various states
        How: Creates PR in different states and tests transition rules
        """
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

**What We Test:**
- ✅ Model field definitions and types
- ✅ Relationship configurations
- ✅ Business logic methods
- ✅ Validation rules and constraints
- ✅ Enum handling and serialization

### 2. Repository Unit Testing

**Purpose**: Test repository logic in isolation with mocked database sessions

```python
class TestPullRequestRepository:
    """Test PullRequestRepository functionality."""
    
    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Provide mock session for isolated testing."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.get = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        return session
    
    async def test_create_pull_request(self, repository, mock_session):
        """
        Why: Ensure repository create method properly manages database session
        What: Tests that create method calls appropriate session methods
        How: Mocks session and verifies method calls and return values
        """
        # Execute
        result = await repository.create(
            repository_id=uuid.uuid4(),
            pr_number=123,
            title="Test PR",
            author="user"
        )
        
        # Verify session interactions
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once_with(result)
        assert isinstance(result, PullRequest)
```

**What We Test:**
- ✅ CRUD operations (Create, Read, Update, Delete)
- ✅ Domain-specific query methods
- ✅ Session management (flush, commit, rollback)
- ✅ Query construction and parameters
- ✅ Error handling and exception paths

### 3. Integration Testing

**Purpose**: Validate database operations with real PostgreSQL instances

```python
class TestPullRequestIntegration:
    """Test PR operations with real database."""
    
    async def test_pr_lifecycle_integration(self, async_session_factory):
        """
        Why: Validate complete PR lifecycle with real database persistence
        What: Tests create, read, update, delete cycle with data validation
        How: Uses real PostgreSQL via testcontainers for authentic testing
        """
        async with async_session_factory() as session:
            repo = PullRequestRepository(session)
            
            # Create PR
            pr = await repo.create(
                repository_id=uuid.uuid4(),
                pr_number=123,
                title="Integration Test PR",
                author="testuser"
            )
            await session.commit()
            
            # Verify persistence
            found_pr = await repo.get_by_id(pr.id)
            assert found_pr is not None
            assert found_pr.title == "Integration Test PR"
            
            # Update PR
            updated_pr = await repo.update(found_pr, title="Updated Title")
            await session.commit()
            
            # Verify update persistence
            refetched_pr = await repo.get_by_id(pr.id)
            assert refetched_pr.title == "Updated Title"
```

**What We Test:**
- ✅ Real database persistence
- ✅ Complex queries with joins
- ✅ Transaction behavior
- ✅ Concurrent access patterns
- ✅ Migration testing

### 4. Migration Testing

**Purpose**: Ensure database schema changes work correctly

```python
class TestDatabaseMigration:
    """Test database migration functionality."""
    
    async def test_migration_creates_all_tables(self, postgres_container):
        """
        Why: Ensure migration scripts create complete database schema
        What: Tests that all expected tables, indexes, and constraints exist
        How: Runs migration and queries system catalogs for schema validation
        """
        # Apply migrations
        await run_migrations(postgres_container.get_connection_url())
        
        # Verify table creation
        async with async_session_factory() as session:
            # Check for all expected tables
            result = await session.execute(text("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY tablename
            """))
            tables = [row[0] for row in result.fetchall()]
            
            expected_tables = [
                'repositories', 'pull_requests', 'check_runs',
                'analysis_results', 'fix_attempts', 'pr_state_history', 'reviews'
            ]
            
            for table in expected_tables:
                assert table in tables, f"Table {table} not created by migration"
```

**What We Test:**
- ✅ Schema creation and modification
- ✅ Index creation and performance
- ✅ Constraint enforcement
- ✅ Migration rollback functionality
- ✅ Data preservation during schema changes

## Database Test Environments

### Test Database Setup

We use **testcontainers** for real PostgreSQL instances in integration tests:

```python
# conftest.py - Test environment configuration
import pytest
import asyncio
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture(scope="session")
def postgres_container():
    """Provide PostgreSQL container for integration tests."""
    postgres = PostgresContainer("postgres:15")
    postgres.start()
    yield postgres
    postgres.stop()

@pytest.fixture(scope="session")
async def async_engine(postgres_container):
    """Create async engine for test database."""
    database_url = postgres_container.get_connection_url().replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(database_url)
    
    # Run migrations
    await run_migrations(database_url)
    
    yield engine
    await engine.dispose()

@pytest.fixture
async def async_session_factory(async_engine):
    """Provide session factory for tests."""
    return async_sessionmaker(async_engine, class_=AsyncSession)
```

### Test Data Isolation

Each test gets a clean database state:

```python
@pytest.fixture(autouse=True)
async def cleanup_database(async_session_factory):
    """Ensure clean database state for each test."""
    yield  # Run the test
    
    # Cleanup after test
    async with async_session_factory() as session:
        # Truncate all tables in dependency order
        await session.execute(text("TRUNCATE TABLE fix_attempts CASCADE"))
        await session.execute(text("TRUNCATE TABLE analysis_results CASCADE"))
        await session.execute(text("TRUNCATE TABLE check_runs CASCADE"))
        await session.execute(text("TRUNCATE TABLE pr_state_history CASCADE"))
        await session.execute(text("TRUNCATE TABLE reviews CASCADE"))
        await session.execute(text("TRUNCATE TABLE pull_requests CASCADE"))
        await session.execute(text("TRUNCATE TABLE repositories CASCADE"))
        await session.commit()
```

## Testing Patterns

### Pattern 1: Factory-Based Test Data

```python
class TestDataFactory:
    """Factory for creating consistent test data."""
    
    @staticmethod
    def create_repository(**overrides):
        """Create repository with realistic default data."""
        defaults = {
            "url": f"https://github.com/test/repo-{uuid.uuid4().hex[:8]}",
            "name": f"repo-{uuid.uuid4().hex[:8]}",
            "full_name": f"test/repo-{uuid.uuid4().hex[:8]}",
            "status": RepositoryStatus.ACTIVE,
            "polling_interval_minutes": 15,
            "failure_count": 0
        }
        defaults.update(overrides)
        return defaults
    
    @staticmethod
    def create_pull_request(repository_id, **overrides):
        """Create PR with realistic default data."""
        defaults = {
            "repository_id": repository_id,
            "pr_number": random.randint(1, 9999),
            "title": f"Fix: Handle edge case in {uuid.uuid4().hex[:8]}",
            "body": "This PR addresses a critical issue where...",
            "author": f"developer{random.randint(1, 100)}",
            "head_sha": uuid.uuid4().hex[:7],
            "base_sha": uuid.uuid4().hex[:7],
            "state": PRState.OPENED,
            "draft": False
        }
        defaults.update(overrides)
        return defaults
```

### Pattern 2: Scenario-Based Testing

```python
async def test_pr_with_failed_checks_scenario(async_session_factory):
    """
    Why: Test realistic scenario of PR with failed CI checks
    What: Creates PR with multiple check runs and queries for failed PRs
    How: Sets up complete scenario data and validates query behavior
    """
    async with async_session_factory() as session:
        pr_repo = PullRequestRepository(session)
        check_repo = CheckRunRepository(session)
        
        # Scenario setup: PR with mixed check results
        repository_id = uuid.uuid4()
        pr = await pr_repo.create(**TestDataFactory.create_pull_request(repository_id))
        
        # Passing checks
        await check_repo.create(
            pr_id=pr.id,
            external_id="check-1",
            check_name="unit-tests",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS
        )
        
        # Failed check
        await check_repo.create(
            pr_id=pr.id,
            external_id="check-2", 
            check_name="lint-check",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.FAILURE,
            check_metadata={"error_count": 3, "warnings": 12}
        )
        
        await session.commit()
        
        # Test the scenario
        failed_prs = await pr_repo.get_prs_with_failed_checks(repository_id)
        assert len(failed_prs) == 1
        assert failed_prs[0].id == pr.id
```

### Pattern 3: Error Scenario Testing

```python
async def test_concurrent_pr_state_update_handling(async_session_factory):
    """
    Why: Ensure repository handles concurrent state updates gracefully
    What: Tests concurrent update scenarios and conflict resolution
    How: Simulates concurrent updates and validates handling
    """
    async with async_session_factory() as session:
        repo = PullRequestRepository(session)
        
        # Create PR
        pr = await repo.create(**TestDataFactory.create_pull_request(uuid.uuid4()))
        await session.commit()
        
        # Simulate concurrent update scenario
        # In a real concurrent scenario, this would be more complex
        # but we test the conflict resolution mechanism
        
        try:
            # This would typically involve separate sessions
            # and transaction isolation testing
            await repo.update_state(
                pr.id,
                PRState.MERGED,
                TriggerEvent.MANUAL_CHECK,
                {"merged_by": "user1"}
            )
            await session.commit()
        except Exception as e:
            # Verify proper error handling
            assert "state transition" in str(e).lower()
            await session.rollback()
```

## Data Management

### Test Data Strategies

1. **Unique Data Generation**
   ```python
   # Ensure unique test data to avoid conflicts
   unique_id = uuid.uuid4().hex[:8]
   repository_name = f"test-repo-{unique_id}"
   pr_title = f"Test PR {unique_id}"
   ```

2. **Realistic Data Patterns**
   ```python
   # Use patterns that mirror production data
   github_urls = [
       "https://github.com/microsoft/vscode",
       "https://github.com/python/cpython", 
       "https://github.com/nodejs/node"
   ]
   realistic_pr_titles = [
       "Fix: Handle null pointer exception in analyzer",
       "Feature: Add support for new GitHub API",
       "Refactor: Improve error handling in DB layer"
   ]
   ```

3. **Test Data Relationships**
   ```python
   # Maintain proper relationships in test data
   async def create_complete_pr_scenario(session):
       """Create PR with all related entities."""
       # Create repository
       repo = await repo_repository.create(**TestDataFactory.create_repository())
       
       # Create PR
       pr = await pr_repository.create(**TestDataFactory.create_pull_request(repo.id))
       
       # Create related check runs
       check = await check_repository.create(
           pr_id=pr.id,
           external_id=f"check-{uuid.uuid4().hex[:8]}",
           check_name="ci-tests",
           status=CheckStatus.COMPLETED
       )
       
       await session.commit()
       return repo, pr, check
   ```

## Integration Testing Approach

### Multi-Component Integration

```python
async def test_complete_pr_analysis_workflow(async_session_factory):
    """
    Why: Validate complete workflow from PR creation to analysis completion
    What: Tests integration between repositories, models, and business logic
    How: Executes complete workflow and validates state at each step
    """
    async with async_session_factory() as session:
        # Setup repositories
        pr_repo = PullRequestRepository(session)
        check_repo = CheckRunRepository(session)
        analysis_repo = AnalysisResultRepository(session)
        
        # Step 1: Create PR
        pr = await pr_repo.create(**TestDataFactory.create_pull_request(uuid.uuid4()))
        await session.commit()
        
        # Step 2: Add check run
        check = await check_repo.create(
            pr_id=pr.id,
            external_id="workflow-123",
            check_name="ci-pipeline",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.FAILURE,
            check_metadata={"build_url": "https://github.com/actions/runs/123"}
        )
        await session.commit()
        
        # Step 3: Create analysis
        analysis = await analysis_repo.create(
            check_run_id=check.id,
            category="build_failure",
            confidence_score=0.92,
            analysis_data={"error_type": "dependency_conflict", "fix_complexity": "medium"}
        )
        await session.commit()
        
        # Step 4: Validate complete workflow
        # Verify PR has associated failed checks
        failed_prs = await pr_repo.get_prs_with_failed_checks(pr.repository_id)
        assert len(failed_prs) == 1
        
        # Verify analysis exists
        check_analyses = await analysis_repo.get_by_check_run(check.id)
        assert len(check_analyses) == 1
        assert check_analyses[0].category == "build_failure"
        
        # Verify relationships work
        loaded_pr = await pr_repo.get_by_id(pr.id)
        assert loaded_pr is not None
        # Test would continue with relationship loading...
```

### Transaction Testing

```python
async def test_transaction_rollback_on_constraint_violation(async_session_factory):
    """
    Why: Ensure transaction rollback works correctly for constraint violations
    What: Tests that failed operations don't leave partial data
    How: Attempts operations that violate constraints and verifies cleanup
    """
    async with async_session_factory() as session:
        repo = PullRequestRepository(session)
        
        # Create initial PR
        repository_id = uuid.uuid4()
        pr1 = await repo.create(**TestDataFactory.create_pull_request(
            repository_id, pr_number=123
        ))
        await session.commit()
        
        # Verify PR exists
        found_pr = await repo.get_by_id(pr1.id)
        assert found_pr is not None
        
        # Attempt to create duplicate (should fail)
        try:
            pr2 = await repo.create(**TestDataFactory.create_pull_request(
                repository_id, pr_number=123  # Same number - constraint violation
            ))
            await session.commit()
            assert False, "Expected constraint violation"
        except IntegrityError:
            await session.rollback()
        
        # Verify original data is intact
        found_pr = await repo.get_by_id(pr1.id)
        assert found_pr is not None
        assert found_pr.pr_number == 123
        
        # Verify no partial data exists
        all_prs = await repo.list_all()
        assert len(all_prs) == 1  # Only original PR exists
```

## Performance Testing Strategy

### Basic Performance Validation

```python
import time

async def test_repository_operation_performance(async_session_factory):
    """
    Why: Ensure repository operations meet performance requirements
    What: Tests that common operations complete within acceptable time
    How: Measures execution time and validates against thresholds
    """
    async with async_session_factory() as session:
        repo = PullRequestRepository(session)
        
        # Setup test data
        pr = await repo.create(**TestDataFactory.create_pull_request(uuid.uuid4()))
        await session.commit()
        
        # Test read performance
        start_time = time.perf_counter()
        found_pr = await repo.get_by_id(pr.id)
        end_time = time.perf_counter()
        
        assert found_pr is not None
        # Should complete within 50ms for integration tests
        assert (end_time - start_time) < 0.050
        
        # Test query performance
        start_time = time.perf_counter()
        active_prs = await repo.get_active_prs_for_repo(pr.repository_id)
        end_time = time.perf_counter()
        
        assert len(active_prs) == 1
        # Complex queries should complete within 100ms
        assert (end_time - start_time) < 0.100
```

Note: Comprehensive performance testing is planned for [Performance Testing Infrastructure (#32)](https://github.com/feddericovonwernich/agentic-coding-workflow/issues/32).

## Error Scenario Testing

### Database Connection Errors

```python
async def test_repository_handles_connection_failure():
    """
    Why: Ensure repository handles database connection failures gracefully
    What: Tests repository behavior when database is unavailable
    How: Simulates connection failures and validates error handling
    """
    # Mock session that raises connection errors
    mock_session = AsyncMock()
    mock_session.execute.side_effect = DatabaseError("Connection failed", None, None)
    
    repo = PullRequestRepository(mock_session)
    
    with pytest.raises(DatabaseError, match="Connection failed"):
        await repo.get_by_id(uuid.uuid4())
    
    # Verify session cleanup was attempted
    mock_session.rollback.assert_called_once()
```

### Constraint Violation Testing

```python
async def test_unique_constraint_violations(async_session_factory):
    """
    Why: Ensure unique constraints are properly enforced
    What: Tests that duplicate data raises appropriate exceptions
    How: Creates duplicate records and validates constraint enforcement
    """
    async with async_session_factory() as session:
        repo = PullRequestRepository(session)
        repository_id = uuid.uuid4()
        
        # Create first PR
        pr1 = await repo.create(**TestDataFactory.create_pull_request(
            repository_id, pr_number=100
        ))
        await session.commit()
        
        # Attempt duplicate
        with pytest.raises(IntegrityError) as exc_info:
            pr2 = await repo.create(**TestDataFactory.create_pull_request(
                repository_id, pr_number=100  # Duplicate number
            ))
            await session.commit()
        
        # Verify specific constraint was violated
        assert "unique constraint" in str(exc_info.value).lower()
        assert "pr_number" in str(exc_info.value).lower()
```

## Test Lifecycle Management

### Test Setup and Teardown

```python
# Global test configuration
@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup global test environment."""
    # Configure logging for tests
    logging.basicConfig(level=logging.INFO)
    
    # Set test-specific environment variables
    os.environ["TESTING"] = "true"
    os.environ["LOG_LEVEL"] = "DEBUG"
    
    yield
    
    # Global cleanup
    # Clear any global state if needed

# Per-test cleanup
@pytest.fixture(autouse=True)
async def test_cleanup(async_session_factory):
    """Ensure clean state for each test."""
    yield  # Run the test
    
    # Cleanup database state
    async with async_session_factory() as session:
        # Truncate tables in dependency order
        tables = [
            "fix_attempts", "analysis_results", "check_runs",
            "pr_state_history", "reviews", "pull_requests", "repositories"
        ]
        
        for table in tables:
            await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        
        await session.commit()
```

### Test Data Management

```python
class TestDataManager:
    """Manages test data lifecycle."""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._cleanup_tasks = []
    
    async def create_test_repository(self, **overrides):
        """Create repository and register for cleanup."""
        async with self.session_factory() as session:
            repo = RepositoryRepository(session)
            test_repo = await repo.create(**TestDataFactory.create_repository(**overrides))
            await session.commit()
            
            # Register for cleanup
            self._cleanup_tasks.append(("repositories", test_repo.id))
            return test_repo
    
    async def cleanup(self):
        """Clean up all created test data."""
        async with self.session_factory() as session:
            for table, entity_id in reversed(self._cleanup_tasks):
                await session.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": entity_id})
            await session.commit()
            self._cleanup_tasks.clear()

# Usage in tests
@pytest.fixture
async def test_data_manager(async_session_factory):
    """Provide test data manager."""
    manager = TestDataManager(async_session_factory)
    yield manager
    await manager.cleanup()
```

## Summary

Our database testing methodology provides:

### Comprehensive Coverage
- ✅ **Model testing** for business logic validation
- ✅ **Repository unit testing** with mocked sessions  
- ✅ **Integration testing** with real PostgreSQL
- ✅ **Migration testing** for schema changes
- ✅ **Error scenario coverage** for reliability

### Quality Assurance
- ✅ **Test data factories** for consistent, realistic data
- ✅ **Isolation mechanisms** ensuring test independence
- ✅ **Performance validation** with timing thresholds
- ✅ **Comprehensive documentation** with Why/What/How pattern

### Scalable Framework
- ✅ **170 test methods** across comprehensive scenarios
- ✅ **5,182 lines** of quality test code
- ✅ **Multi-environment support** (unit, integration, CI)
- ✅ **Automated cleanup** and state management

### Future Enhancements
- 🚀 **Performance testing infrastructure** (Issue #32)
- 🚀 **Advanced testing features** (Issue #33)
- 🚀 **Property-based testing** integration
- 🚀 **Mutation testing** for test quality validation

This methodology ensures reliable, maintainable, and comprehensive testing of our database layer, providing confidence in data operations and business logic implementation.

For specific implementation guidance, see [Testing Best Practices](./best-practices.md) and [Coverage Analysis](./coverage.md).