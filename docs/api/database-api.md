# Database API Documentation

The Database API provides comprehensive data persistence through SQLAlchemy models and repository patterns, with support for async operations, transactions, and performance optimization.

## Table of Contents

- [Quick Start](#quick-start)
- [Database Models](#database-models)
- [Repository Pattern](#repository-pattern)
- [Database Connection](#database-connection)
- [Transactions](#transactions)
- [Query Patterns](#query-patterns)
- [Performance Optimization](#performance-optimization)
- [Migrations](#migrations)
- [Testing Support](#testing-support)
- [Best Practices](#best-practices)

## Quick Start

### Basic Database Usage

```python
import asyncio
from src.database.connection import get_connection_manager
from src.config.loader import load_config
from src.repositories.pull_request import PullRequestRepository
from src.models.pull_request import PullRequest

async def main():
    # Load configuration
    config = load_config()
    
    # Get database connection
    manager = get_connection_manager(config.database)
    
    # Use repository
    async with manager.get_session() as session:
        pr_repo = PullRequestRepository(session)
        
        # Create a pull request
        pr = await pr_repo.create(
            repository_id=uuid.uuid4(),
            pr_number=123,
            title="Feature: Add new API endpoint",
            author="developer"
        )
        
        print(f"Created PR: {pr.title}")
        
        # Query pull requests
        open_prs = await pr_repo.get_by_status("open")
        print(f"Open PRs: {len(open_prs)}")

asyncio.run(main())
```

### Connection Setup

```python
from src.database.connection import DatabaseConnectionManager
from src.config.models import DatabaseConfig

# Create connection manager
db_config = DatabaseConfig(
    url="postgresql://user:password@localhost:5432/agentic",
    pool_size=20,
    max_overflow=30,
    pool_timeout=30
)

manager = DatabaseConnectionManager(db_config)

# Initialize database
await manager.initialize()

# Use session
async with manager.get_session() as session:
    # Database operations
    pass

# Cleanup
await manager.close()
```

## Database Models

### Base Model

All models inherit from `BaseModel` which provides common functionality:

```python
from src.models.base import BaseModel
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class CustomModel(BaseModel):
    """Custom model example."""
    
    __tablename__ = "custom_table"
    
    # BaseModel provides:
    # - id: UUID primary key
    # - created_at: Timestamp with timezone
    # - updated_at: Timestamp with timezone (auto-updated)
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    
    def __repr__(self) -> str:
        return f"<CustomModel(id={self.id}, name='{self.name}')>"
```

### Core Models

#### Repository Model

```python
from src.models.repository import Repository

# Repository represents a GitHub repository
class Repository(BaseModel):
    __tablename__ = "repositories"
    
    name: Mapped[str]                    # Repository name
    full_name: Mapped[str]               # owner/repo format
    url: Mapped[str]                     # GitHub URL
    default_branch: Mapped[str]          # Default branch name
    is_private: Mapped[bool]             # Private repository flag
    is_active: Mapped[bool]              # Active monitoring flag
    
    # Relationships
    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="repository")
    check_runs: Mapped[list["CheckRun"]] = relationship(back_populates="repository")
```

#### Pull Request Model

```python
from src.models.pull_request import PullRequest
from src.models.enums import PRState

class PullRequest(BaseModel):
    __tablename__ = "pull_requests"
    
    # Basic information
    repository_id: Mapped[uuid.UUID]     # Foreign key to Repository
    pr_number: Mapped[int]               # PR number in repository
    title: Mapped[str]                   # PR title
    body: Mapped[str | None]             # PR description
    author: Mapped[str]                  # Author username
    
    # State management
    state: Mapped[PRState]               # open, closed, merged
    is_draft: Mapped[bool]               # Draft PR flag
    
    # GitHub metadata
    github_id: Mapped[int]               # GitHub PR ID
    head_sha: Mapped[str]                # HEAD commit SHA
    base_branch: Mapped[str]             # Target branch
    head_branch: Mapped[str]             # Source branch
    
    # Relationships
    repository: Mapped["Repository"] = relationship(back_populates="pull_requests")
    check_runs: Mapped[list["CheckRun"]] = relationship(back_populates="pull_request")
    fix_attempts: Mapped[list["FixAttempt"]] = relationship(back_populates="pull_request")
```

#### Check Run Model

```python
from src.models.check_run import CheckRun
from src.models.enums import CheckRunStatus, CheckRunConclusion

class CheckRun(BaseModel):
    __tablename__ = "check_runs"
    
    # Relationships
    repository_id: Mapped[uuid.UUID]     # Foreign key to Repository
    pull_request_id: Mapped[uuid.UUID]   # Foreign key to PullRequest
    
    # GitHub check run data
    github_id: Mapped[int]               # GitHub check run ID
    name: Mapped[str]                    # Check name (e.g., "CI", "Tests")
    head_sha: Mapped[str]                # Commit SHA
    
    # Status and results
    status: Mapped[CheckRunStatus]       # queued, in_progress, completed
    conclusion: Mapped[CheckRunConclusion | None]  # success, failure, cancelled
    
    # Timing
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    
    # Output
    output_title: Mapped[str | None]
    output_summary: Mapped[str | None]
    output_text: Mapped[str | None]      # Full log output
    
    # Relationships
    repository: Mapped["Repository"] = relationship(back_populates="check_runs")
    pull_request: Mapped["PullRequest"] = relationship(back_populates="check_runs")
```

### Model Enums

Type-safe enums for model fields:

```python
from src.models.enums import PRState, CheckRunStatus, CheckRunConclusion

# Pull Request states
class PRState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"

# Check run status
class CheckRunStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

# Check run conclusion
class CheckRunConclusion(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
```

### Model Utilities

Built-in model utilities:

```python
# Convert model to dictionary
pr = await pr_repo.get_by_id(pr_id)
pr_data = pr.to_dict()
print(pr_data)
# Output: {'id': UUID('...'), 'title': 'Feature: ...', 'created_at': datetime(...)}

# String representation
print(repr(pr))
# Output: <PullRequest(id=123e4567-e89b-12d3-a456-426614174000)>

# Access timestamps
print(f"Created: {pr.created_at}")
print(f"Updated: {pr.updated_at}")
```

## Repository Pattern

### Base Repository

All repositories inherit from `BaseRepository` with common CRUD operations:

```python
from src.repositories.base import BaseRepository

class CustomRepository(BaseRepository[CustomModel]):
    """Custom repository with additional methods."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, CustomModel)
    
    async def get_by_name(self, name: str) -> CustomModel | None:
        """Get entity by name."""
        stmt = select(CustomModel).where(CustomModel.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_active_entities(self) -> list[CustomModel]:
        """Get all active entities."""
        stmt = select(CustomModel).where(CustomModel.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
```

### CRUD Operations

Standard CRUD operations available on all repositories:

```python
# Create
new_pr = await pr_repo.create(
    repository_id=repo_id,
    pr_number=123,
    title="New feature",
    author="developer"
)

# Read
pr = await pr_repo.get_by_id(pr_id)
pr = await pr_repo.get_by_id_or_raise(pr_id)  # Raises exception if not found

# Update
updated_pr = await pr_repo.update(pr, title="Updated title", state=PRState.CLOSED)

# Delete
await pr_repo.delete(pr)

# List with pagination
prs = await pr_repo.list(limit=50, offset=0)

# Count
total_prs = await pr_repo.count()
```

### Specialized Repositories

#### Pull Request Repository

```python
from src.repositories.pull_request import PullRequestRepository

pr_repo = PullRequestRepository(session)

# Get by PR number
pr = await pr_repo.get_by_number(repository_id, pr_number=123)

# Get by status
open_prs = await pr_repo.get_by_status("open")
merged_prs = await pr_repo.get_by_status("merged")

# Get with failed checks
prs_with_failures = await pr_repo.get_prs_with_failed_checks(repository_id)

# Get recent PRs
recent_prs = await pr_repo.get_recent(limit=10, days=7)

# Search by title or author
search_results = await pr_repo.search(query="bug fix", author="developer")
```

#### Repository Repository

```python
from src.repositories.repository import RepositoryRepository

repo_repo = RepositoryRepository(session)

# Get by full name
repo = await repo_repo.get_by_full_name("owner/repo")

# Get active repositories
active_repos = await repo_repo.get_active_repositories()

# Get repositories with recent activity
active_repos = await repo_repo.get_with_recent_activity(hours=24)
```

#### Check Run Repository

```python
from src.repositories.check_run import CheckRunRepository

check_repo = CheckRunRepository(session)

# Get failed check runs
failed_checks = await check_repo.get_failed_checks(pull_request_id)

# Get by commit SHA
checks = await check_repo.get_by_commit_sha(repository_id, sha="abc123")

# Get recent check runs
recent_checks = await check_repo.get_recent(repository_id, limit=50)
```

## Database Connection

### Connection Manager

Manage database connections with pooling and health monitoring:

```python
from src.database.connection import DatabaseConnectionManager, get_connection_manager
from src.config.models import DatabaseConfig

# Create connection manager
db_config = DatabaseConfig(
    url="postgresql://user:password@localhost:5432/agentic",
    pool_size=20,                # Connection pool size
    max_overflow=30,             # Additional connections allowed
    pool_timeout=30,             # Connection timeout
    pool_recycle=3600,           # Recycle connections after 1 hour
    pool_pre_ping=True,          # Validate connections before use
    echo_sql=False               # Log SQL queries (development only)
)

manager = get_connection_manager(db_config)

# Initialize database
await manager.initialize()

# Get session
async with manager.get_session() as session:
    # Database operations
    pass

# Health check
is_healthy = await manager.health_check()
```

### Session Management

Use sessions for database operations:

```python
# Context manager (recommended)
async with manager.get_session() as session:
    pr_repo = PullRequestRepository(session)
    pr = await pr_repo.create(repository_id=repo_id, pr_number=123)
    # Session automatically committed and closed

# Manual session management
session = manager.get_session()
try:
    pr_repo = PullRequestRepository(session)
    pr = await pr_repo.create(repository_id=repo_id, pr_number=123)
    await session.commit()
finally:
    await session.close()

# Session with transaction
async with manager.get_session() as session:
    async with session.begin():
        # Multiple operations in transaction
        pr = await pr_repo.create(...)
        check = await check_repo.create(...)
        # Automatically committed or rolled back
```

## Transactions

### Automatic Transactions

Use context managers for automatic transaction management:

```python
# Transaction with session context manager
async with manager.get_session() as session:
    # Transaction automatically started
    pr_repo = PullRequestRepository(session)
    check_repo = CheckRunRepository(session)
    
    # Multiple operations
    pr = await pr_repo.create(repository_id=repo_id, pr_number=123)
    check = await check_repo.create(pull_request_id=pr.id, name="CI")
    
    # Automatically committed on successful exit
    # Automatically rolled back on exception

# Explicit transaction control
async with manager.get_session() as session:
    async with session.begin():
        # Explicit transaction
        pr = await pr_repo.create(...)
        check = await check_repo.create(...)
        # Committed on successful exit
```

### Manual Transaction Control

```python
async with manager.get_session() as session:
    try:
        # Start transaction
        await session.begin()
        
        # Operations
        pr = await pr_repo.create(...)
        check = await check_repo.create(...)
        
        # Commit transaction
        await session.commit()
    except Exception:
        # Rollback on error
        await session.rollback()
        raise
```

### Savepoints

Use savepoints for nested transactions:

```python
async with manager.get_session() as session:
    async with session.begin():
        # Main transaction
        pr = await pr_repo.create(...)
        
        # Savepoint for risky operation
        savepoint = await session.begin_nested()
        try:
            risky_operation = await check_repo.create(...)
            await savepoint.commit()
        except Exception:
            await savepoint.rollback()
            # Continue with main transaction
        
        # Main transaction continues
        another_operation = await pr_repo.update(pr, state="closed")
```

## Query Patterns

### Basic Queries

```python
from sqlalchemy import select, and_, or_, func
from src.models.pull_request import PullRequest

# Simple select
stmt = select(PullRequest).where(PullRequest.state == "open")
result = await session.execute(stmt)
open_prs = list(result.scalars().all())

# Select with multiple conditions
stmt = select(PullRequest).where(
    and_(
        PullRequest.state == "open",
        PullRequest.is_draft == False
    )
)
result = await session.execute(stmt)
open_non_draft_prs = list(result.scalars().all())

# Select single result
stmt = select(PullRequest).where(PullRequest.pr_number == 123)
result = await session.execute(stmt)
pr = result.scalar_one_or_none()
```

### Joins and Relationships

```python
from sqlalchemy.orm import selectinload, joinedload

# Eager loading with selectinload (separate query)
stmt = select(PullRequest).options(
    selectinload(PullRequest.check_runs),
    selectinload(PullRequest.repository)
).where(PullRequest.state == "open")
result = await session.execute(stmt)
prs_with_relations = list(result.scalars().all())

# Eager loading with joinedload (single query)
stmt = select(PullRequest).options(
    joinedload(PullRequest.repository)
).where(PullRequest.state == "open")
result = await session.execute(stmt)
prs_with_repos = list(result.scalars().all())

# Join queries
stmt = (
    select(PullRequest, Repository)
    .join(Repository)
    .where(Repository.is_active == True)
)
result = await session.execute(stmt)
for pr, repo in result:
    print(f"PR {pr.title} in {repo.name}")
```

### Aggregations

```python
# Count queries
stmt = select(func.count(PullRequest.id)).where(PullRequest.state == "open")
result = await session.execute(stmt)
open_pr_count = result.scalar()

# Group by
stmt = (
    select(PullRequest.state, func.count(PullRequest.id))
    .group_by(PullRequest.state)
)
result = await session.execute(stmt)
for state, count in result:
    print(f"{state}: {count}")

# Complex aggregation
stmt = (
    select(
        Repository.name,
        func.count(PullRequest.id).label("pr_count"),
        func.max(PullRequest.created_at).label("latest_pr")
    )
    .join(Repository)
    .group_by(Repository.name)
    .having(func.count(PullRequest.id) > 5)
)
```

### Pagination

```python
# Offset-based pagination
def paginate_query(stmt, page: int, per_page: int):
    offset = (page - 1) * per_page
    return stmt.offset(offset).limit(per_page)

# Usage
stmt = select(PullRequest).where(PullRequest.state == "open")
page_1 = paginate_query(stmt, page=1, per_page=20)
result = await session.execute(page_1)
prs = list(result.scalars().all())

# Cursor-based pagination (more efficient for large datasets)
def cursor_paginate(stmt, cursor_field, cursor_value, per_page: int):
    return (
        stmt.where(cursor_field > cursor_value)
        .order_by(cursor_field)
        .limit(per_page)
    )

# Usage
stmt = select(PullRequest).where(PullRequest.state == "open")
page = cursor_paginate(stmt, PullRequest.created_at, last_created_at, 20)
```

## Performance Optimization

### Connection Pooling

Optimize connection pool settings:

```python
# Production configuration
db_config = DatabaseConfig(
    url="postgresql://user:password@localhost:5432/agentic",
    pool_size=20,                # Base pool size
    max_overflow=50,             # Additional connections
    pool_timeout=30,             # Connection timeout
    pool_recycle=3600,           # Recycle after 1 hour
    pool_pre_ping=True,          # Validate before use
    pool_reset_on_return="commit"  # Reset behavior
)
```

### Query Optimization

```python
# Use indexes effectively
stmt = select(PullRequest).where(
    PullRequest.repository_id == repo_id,  # Indexed
    PullRequest.state == "open"            # Indexed
).order_by(PullRequest.created_at.desc())  # Indexed

# Eager load relationships to avoid N+1 queries
stmt = select(PullRequest).options(
    selectinload(PullRequest.check_runs),
    selectinload(PullRequest.repository)
)

# Use specific columns when possible
stmt = select(
    PullRequest.id,
    PullRequest.title,
    PullRequest.state
).where(PullRequest.state == "open")

# Batch operations
await session.execute(
    insert(PullRequest),
    [
        {"repository_id": repo_id, "pr_number": 1, "title": "PR 1"},
        {"repository_id": repo_id, "pr_number": 2, "title": "PR 2"},
        # ... more PRs
    ]
)
```

### Monitoring

Monitor database performance:

```python
from src.database.monitoring import DatabaseMonitor

monitor = DatabaseMonitor(manager)

# Get performance metrics
metrics = await monitor.get_metrics()
print(f"Active connections: {metrics.active_connections}")
print(f"Query count: {metrics.query_count}")
print(f"Average response time: {metrics.avg_response_time_ms}ms")

# Monitor slow queries
slow_queries = await monitor.get_slow_queries(threshold_ms=1000)
for query in slow_queries:
    print(f"Slow query: {query.sql} ({query.duration_ms}ms)")
```

## Migrations

### Creating Migrations

Use Alembic for database schema management:

```bash
# Create new migration
alembic revision --autogenerate -m "Add check_runs table"

# Create empty migration
alembic revision -m "Add custom index"

# Apply migrations
alembic upgrade head

# Downgrade migrations
alembic downgrade -1
```

### Migration Best Practices

```python
"""Add check_runs table

Revision ID: abc123
Revises: def456
Create Date: 2024-01-15 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'abc123'
down_revision = 'def456'
branch_labels = None
depends_on = None

def upgrade():
    """Add check_runs table with proper indexes."""
    # Create table
    op.create_table(
        'check_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('repository_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pull_request_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('github_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    
    # Add indexes
    op.create_index('ix_check_runs_repository_id', 'check_runs', ['repository_id'])
    op.create_index('ix_check_runs_pull_request_id', 'check_runs', ['pull_request_id'])
    op.create_index('ix_check_runs_github_id', 'check_runs', ['github_id'])
    op.create_index('ix_check_runs_status', 'check_runs', ['status'])
    
    # Add foreign keys
    op.create_foreign_key(
        'fk_check_runs_repository_id',
        'check_runs', 'repositories',
        ['repository_id'], ['id'],
        ondelete='CASCADE'
    )

def downgrade():
    """Remove check_runs table."""
    op.drop_table('check_runs')
```

## Testing Support

### Test Database Setup

```python
import pytest
from src.database.connection import DatabaseConnectionManager
from src.config.models import DatabaseConfig

@pytest.fixture
async def db_manager():
    """Provide test database manager."""
    config = DatabaseConfig(url="sqlite:///:memory:")
    manager = DatabaseConnectionManager(config)
    await manager.initialize()
    yield manager
    await manager.close()

@pytest.fixture
async def session(db_manager):
    """Provide test database session."""
    async with db_manager.get_session() as session:
        yield session

@pytest.fixture
async def pr_repo(session):
    """Provide pull request repository."""
    from src.repositories.pull_request import PullRequestRepository
    return PullRequestRepository(session)
```

### Model Testing

```python
import pytest
from src.models.pull_request import PullRequest

@pytest.mark.asyncio
async def test_pull_request_creation(session, pr_repo):
    """Test pull request creation."""
    pr = await pr_repo.create(
        repository_id=uuid.uuid4(),
        pr_number=123,
        title="Test PR",
        author="testuser"
    )
    
    assert pr.id is not None
    assert pr.pr_number == 123
    assert pr.title == "Test PR"
    assert pr.created_at is not None
    assert pr.updated_at is not None

@pytest.mark.asyncio
async def test_pull_request_relationships(session, pr_repo):
    """Test pull request relationships."""
    # Create repository first
    repo = await repo_repo.create(name="test-repo", full_name="user/test-repo")
    
    # Create pull request
    pr = await pr_repo.create(
        repository_id=repo.id,
        pr_number=123,
        title="Test PR"
    )
    
    # Load with relationships
    pr_with_repo = await pr_repo.get_with_repository(pr.id)
    assert pr_with_repo.repository.name == "test-repo"
```

## Best Practices

### Repository Design

```python
# ✅ Use repository pattern for data access
class PullRequestService:
    def __init__(self, pr_repo: PullRequestRepository):
        self.pr_repo = pr_repo
    
    async def create_pr(self, data: dict) -> PullRequest:
        return await self.pr_repo.create(**data)

# ❌ Don't access models directly in business logic
# class PullRequestService:
#     async def create_pr(self, session: AsyncSession, data: dict):
#         pr = PullRequest(**data)  # Direct model access
#         session.add(pr)
```

### Session Management

```python
# ✅ Use context managers for sessions
async with manager.get_session() as session:
    result = await pr_repo.create(...)
    # Session automatically closed

# ✅ Use transactions for multiple operations
async with manager.get_session() as session:
    async with session.begin():
        pr = await pr_repo.create(...)
        check = await check_repo.create(...)
        # Automatically committed or rolled back

# ❌ Don't forget to close sessions
# session = manager.get_session()
# result = await pr_repo.create(...)
# # Session never closed - memory leak
```

### Performance

```python
# ✅ Use eager loading for relationships
stmt = select(PullRequest).options(
    selectinload(PullRequest.check_runs)
)

# ✅ Use specific columns when possible
stmt = select(PullRequest.id, PullRequest.title)

# ✅ Use pagination for large datasets
stmt = select(PullRequest).limit(100).offset(page * 100)

# ❌ Don't load all data at once
# all_prs = await pr_repo.list()  # Could be thousands of records
```

### Error Handling

```python
# ✅ Handle database errors appropriately
try:
    pr = await pr_repo.create(...)
except IntegrityError as e:
    if "duplicate key" in str(e):
        raise ValueError("PR already exists")
    raise
except DatabaseError:
    logger.error("Database error creating PR")
    raise

# ✅ Use get_by_id_or_raise for required entities
pr = await pr_repo.get_by_id_or_raise(pr_id)  # Raises if not found
```

---

**Next Steps:**
- 📖 **Examples**: Check [Database Examples](examples/database-queries.py) for complete working code
- ⚙️ **Configuration**: See [Configuration API](configuration-api.md) for database configuration
- 🧪 **Testing**: Review [Testing Guide](../developer/testing-guide.md) for database testing patterns