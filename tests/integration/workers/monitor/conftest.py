"""
Test fixtures and configuration for PR monitoring integration tests.

Provides fixtures for testcontainers, GitHub API mocking, and shared test data
for integration testing of the PR monitoring workflow.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

from src.database.config import DatabaseConfig, DatabasePoolConfig, reset_database_config
from src.database.connection import DatabaseConnectionManager, reset_connection_manager
from src.database.health import reset_health_checker
from src.github.client import GitHubClient
from src.models import CheckRun, PullRequest, Repository as RepoModel, RepositoryStatus
from src.models.enums import CheckConclusion, CheckStatus, PRState
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.workers.monitor.models import CheckRunData, PRData


@pytest.fixture(scope="module")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """
    Why: Need real PostgreSQL instance for integration testing database operations
    What: Spins up PostgreSQL container using testcontainers
    How: Uses PostgreSQL 15 alpine image with test credentials
    """
    with PostgresContainer(
        image="postgres:15-alpine",
        username="test_user",
        password="test_password",
        dbname="test_monitor_integration",
    ) as postgres:
        postgres.get_connection_url()
        yield postgres


@pytest.fixture(scope="module")
def database_config(postgres_container: PostgresContainer) -> DatabaseConfig:
    """
    Why: Need database configuration pointing to test container
    What: Creates DatabaseConfig with testcontainer connection details
    How: Converts container URL to asyncpg and configures connection pool
    """
    reset_database_config()
    reset_connection_manager()
    reset_health_checker()

    connection_url = postgres_container.get_connection_url()
    async_url = connection_url.replace("postgresql+psycopg2", "postgresql+asyncpg")

    pool_config = DatabasePoolConfig(
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
    )

    return DatabaseConfig(database_url=async_url, pool=pool_config)


@pytest_asyncio.fixture
async def connection_manager(
    database_config: DatabaseConfig,
) -> AsyncGenerator[DatabaseConnectionManager, None]:
    """
    Why: Need connection manager for database operations in tests
    What: Creates DatabaseConnectionManager connected to test database
    How: Manages lifecycle of database connection manager
    """
    manager = DatabaseConnectionManager(database_config)
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def database_session(connection_manager: DatabaseConnectionManager):
    """
    Why: Need database session for repository operations
    What: Provides database session from connection manager
    How: Uses connection manager's get_session context manager
    """
    async with connection_manager.get_session() as session:
        yield session


@pytest_asyncio.fixture
async def setup_database_schema(database_session):
    """
    Why: Need database tables for testing repository operations
    What: Creates necessary database tables for PR monitoring
    How: Executes DDL statements to create required tables
    """
    # Create repositories table
    await database_session.execute(
        text("""
        CREATE TABLE IF NOT EXISTS repositories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            url VARCHAR(512) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            full_name VARCHAR(300),
            status VARCHAR(20) DEFAULT 'active',
            last_polled_at TIMESTAMP WITH TIME ZONE,
            failure_count INTEGER DEFAULT 0,
            last_failure_reason TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT repositories_status_check 
            CHECK (status IN ('active', 'inactive', 'archived', 'error'))
        )
        """)
    )

    # Create pull_requests table
    await database_session.execute(
        text("""
        CREATE TABLE IF NOT EXISTS pull_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            repository_id UUID NOT NULL,
            pr_number INTEGER NOT NULL,
            title VARCHAR(512) NOT NULL,
            author VARCHAR(255) NOT NULL,
            state VARCHAR(20) NOT NULL DEFAULT 'opened',
            draft BOOLEAN DEFAULT FALSE,
            base_branch VARCHAR(255) NOT NULL,
            head_branch VARCHAR(255) NOT NULL,
            base_sha VARCHAR(40) NOT NULL,
            head_sha VARCHAR(40) NOT NULL,
            url VARCHAR(512) NOT NULL,
            body TEXT,
            pr_metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(repository_id, pr_number),
            CONSTRAINT pr_state_check 
            CHECK (state IN ('opened', 'closed', 'merged'))
        )
        """)
    )

    # Create check_runs table
    await database_session.execute(
        text("""
        CREATE TABLE IF NOT EXISTS check_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pr_id UUID NOT NULL,
            external_id VARCHAR(255) NOT NULL UNIQUE,
            check_name VARCHAR(255) NOT NULL,
            check_suite_id VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            conclusion VARCHAR(20),
            details_url VARCHAR(512),
            logs_url VARCHAR(512),
            output_summary TEXT,
            output_text TEXT,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            check_metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT check_status_check 
            CHECK (status IN ('queued', 'in_progress', 'completed', 'cancelled')),
            CONSTRAINT check_conclusion_check 
            CHECK (conclusion IN ('success', 'failure', 'neutral', 'cancelled', 
                                'timed_out', 'action_required') OR conclusion IS NULL)
        )
        """)
    )

    # Create pr_state_history table
    await database_session.execute(
        text("""
        CREATE TABLE IF NOT EXISTS pr_state_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pr_id UUID NOT NULL,
            old_state VARCHAR(20),
            new_state VARCHAR(20) NOT NULL,
            trigger_event VARCHAR(50) NOT NULL,
            triggered_by VARCHAR(255) NOT NULL DEFAULT 'system',
            transition_metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT pr_history_old_state_check 
            CHECK (old_state IN ('opened', 'closed', 'merged') OR old_state IS NULL),
            CONSTRAINT pr_history_new_state_check 
            CHECK (new_state IN ('opened', 'closed', 'merged'))
        )
        """)
    )

    await database_session.commit()
    yield
    
    # Cleanup tables after tests
    await database_session.execute(text("DROP TABLE IF EXISTS pr_state_history"))
    await database_session.execute(text("DROP TABLE IF EXISTS check_runs"))
    await database_session.execute(text("DROP TABLE IF EXISTS pull_requests"))
    await database_session.execute(text("DROP TABLE IF EXISTS repositories"))
    await database_session.commit()


@pytest.fixture
def mock_github_client():
    """
    Why: Need controlled GitHub API responses for integration testing
    What: Creates mock GitHubClient with realistic response patterns
    How: Uses MagicMock with pre-configured response methods
    """
    mock = MagicMock(spec=GitHubClient)
    
    # Mock paginate method to return async generator
    async def mock_paginate(*args, **kwargs):
        # Return sample PR data for pagination
        if "/pulls" in args[0]:
            for item in _get_sample_github_prs():
                yield item
        elif "/check-runs" in args[0]:
            for item in _get_sample_github_check_runs():
                yield item
    
    mock.paginate = mock_paginate
    return mock


@pytest.fixture
def test_repository() -> RepoModel:
    """
    Why: Need consistent repository model for testing
    What: Creates test Repository instance with realistic data
    How: Uses Repository model with GitHub-like configuration
    """
    repo = RepoModel()
    repo.id = uuid.uuid4()
    repo.url = "https://github.com/test-org/test-repo"
    repo.name = "test-repo"
    repo.full_name = "test-org/test-repo"
    repo.status = RepositoryStatus.ACTIVE
    repo.failure_count = 0
    return repo


@pytest_asyncio.fixture
async def test_repository_in_db(
    database_session, setup_database_schema, test_repository: RepoModel
) -> RepoModel:
    """
    Why: Need repository persisted in database for relationship testing
    What: Creates and persists test repository in database
    How: Inserts repository record and returns the instance
    """
    await database_session.execute(
        text("""
        INSERT INTO repositories 
        (id, url, name, full_name, status, failure_count, created_at, updated_at)
        VALUES (:id, :url, :name, :full_name, :status, :failure_count, 
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """),
        {
            "id": test_repository.id,
            "url": test_repository.url,
            "name": test_repository.name,
            "full_name": test_repository.full_name,
            "status": test_repository.status.value,
            "failure_count": test_repository.failure_count,
        },
    )
    await database_session.commit()
    return test_repository


@pytest.fixture
def sample_pr_data() -> list[PRData]:
    """
    Why: Need realistic PR data for testing change detection and synchronization
    What: Creates sample PRData instances with various states
    How: Returns list of PRData with different scenarios (open, closed, draft)
    """
    return [
        PRData(
            number=123,
            title="Add new feature",
            author="developer1",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/new-feature",
            base_sha="abc123def456",
            head_sha="def456ghi789",
            url="https://github.com/test-org/test-repo/pull/123",
            body="This PR adds a new feature",
            labels=["feature", "enhancement"],
            assignees=["developer1"],
            milestone="v2.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            raw_data={"repository_id": str(uuid.uuid4())},
        ),
        PRData(
            number=124,
            title="Fix critical bug",
            author="developer2",
            state="open",
            draft=True,
            base_branch="main",
            head_branch="bugfix/critical-fix",
            base_sha="abc123def456",
            head_sha="ghi789jkl012",
            url="https://github.com/test-org/test-repo/pull/124",
            body="Fixes critical production bug",
            labels=["bug", "critical"],
            assignees=["developer2", "lead-dev"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            raw_data={"repository_id": str(uuid.uuid4())},
        ),
        PRData(
            number=125,
            title="Update documentation",
            author="tech-writer",
            state="closed",
            draft=False,
            merged=True,
            base_branch="main",
            head_branch="docs/update-readme",
            base_sha="abc123def456",
            head_sha="jkl012mno345",
            url="https://github.com/test-org/test-repo/pull/125",
            body="Updates README with new installation instructions",
            labels=["documentation"],
            assignees=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            merged_at=datetime.now(timezone.utc),
            raw_data={"repository_id": str(uuid.uuid4())},
        ),
    ]


@pytest.fixture
def sample_check_run_data() -> list[CheckRunData]:
    """
    Why: Need realistic check run data for testing synchronization
    What: Creates sample CheckRunData instances with various statuses
    How: Returns list of CheckRunData with different scenarios
    """
    return [
        CheckRunData(
            external_id="12345678901",
            check_name="CI Build",
            status="completed",
            conclusion="success",
            check_suite_id="87654321098",
            details_url="https://github.com/test-org/test-repo/actions/runs/123",
            output_summary="Build completed successfully",
            output_text="All tests passed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            raw_data={"app": {"name": "GitHub Actions"}},
        ),
        CheckRunData(
            external_id="12345678902",
            check_name="Code Quality",
            status="completed",
            conclusion="failure",
            check_suite_id="87654321098",
            details_url="https://github.com/test-org/test-repo/actions/runs/124",
            output_summary="Code quality checks failed",
            output_text="Found 3 linting errors",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            raw_data={"app": {"name": "SonarCloud"}},
        ),
        CheckRunData(
            external_id="12345678903",
            check_name="Security Scan",
            status="in_progress",
            conclusion=None,
            check_suite_id="87654321098",
            details_url="https://github.com/test-org/test-repo/actions/runs/125",
            started_at=datetime.now(timezone.utc),
            raw_data={"app": {"name": "Snyk"}},
        ),
    ]


@pytest_asyncio.fixture
async def pr_repository(database_session) -> PullRequestRepository:
    """
    Why: Need PR repository for database operations in integration tests
    What: Creates PullRequestRepository instance with test database session
    How: Instantiates repository with active database session
    """
    return PullRequestRepository(database_session)


@pytest_asyncio.fixture
async def check_run_repository(database_session) -> CheckRunRepository:
    """
    Why: Need check run repository for database operations in integration tests
    What: Creates CheckRunRepository instance with test database session
    How: Instantiates repository with active database session
    """
    return CheckRunRepository(database_session)


@pytest.fixture
def performance_test_data() -> dict[str, Any]:
    """
    Why: Need large datasets for performance testing
    What: Creates large amounts of test data for performance benchmarks
    How: Generates realistic volumes of PRs and check runs
    """
    base_time = datetime.now(timezone.utc)
    
    # Generate 100 PRs with different states
    prs = []
    for i in range(100):
        pr = PRData(
            number=1000 + i,
            title=f"Test PR #{i}",
            author=f"developer{i % 10}",
            state="open" if i % 3 != 0 else "closed",
            draft=i % 5 == 0,
            base_branch="main",
            head_branch=f"feature/test-{i}",
            base_sha=f"abc{i:06d}",
            head_sha=f"def{i:06d}",
            url=f"https://github.com/test-org/test-repo/pull/{1000 + i}",
            labels=[f"label-{i % 3}"],
            assignees=[f"dev-{i % 5}"] if i % 2 == 0 else [],
            created_at=base_time,
            updated_at=base_time,
            raw_data={"repository_id": str(uuid.uuid4())},
        )
        prs.append(pr)
    
    # Generate 500 check runs (5 per PR on average)
    check_runs = []
    for pr_idx in range(100):
        for check_idx in range(5):
            check_run = CheckRunData(
                external_id=f"check_{pr_idx:03d}_{check_idx}",
                check_name=f"Check {check_idx + 1}",
                status="completed" if check_idx < 4 else "in_progress",
                conclusion="success" if check_idx % 2 == 0 else "failure" if check_idx < 4 else None,
                check_suite_id=f"suite_{pr_idx:03d}",
                details_url=f"https://example.com/check/{pr_idx}/{check_idx}",
                started_at=base_time,
                completed_at=base_time if check_idx < 4 else None,
                raw_data={"pr_number": 1000 + pr_idx},
            )
            check_runs.append(check_run)
    
    return {"prs": prs, "check_runs": check_runs}


def _get_sample_github_prs() -> list[dict[str, Any]]:
    """Helper function to generate sample GitHub PR API responses."""
    return [
        {
            "number": 123,
            "title": "Add new feature",
            "user": {"login": "developer1"},
            "state": "open",
            "draft": False,
            "base": {"ref": "main", "sha": "abc123def456"},
            "head": {"ref": "feature/new-feature", "sha": "def456ghi789"},
            "html_url": "https://github.com/test-org/test-repo/pull/123",
            "body": "This PR adds a new feature",
            "labels": [{"name": "feature"}, {"name": "enhancement"}],
            "assignees": [{"login": "developer1"}],
            "milestone": {"title": "v2.0"},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "merged": False,
        }
    ]


def _get_sample_github_check_runs() -> list[dict[str, Any]]:
    """Helper function to generate sample GitHub check run API responses."""
    return [
        {
            "id": 12345678901,
            "name": "CI Build",
            "status": "completed",
            "conclusion": "success",
            "check_suite": {"id": 87654321098},
            "details_url": "https://github.com/test-org/test-repo/actions/runs/123",
            "html_url": "https://github.com/test-org/test-repo/actions/runs/123",
            "output": {
                "title": "Build Success",
                "summary": "Build completed successfully",
                "text": "All tests passed",
            },
            "started_at": "2024-01-01T00:00:00Z",
            "completed_at": "2024-01-01T00:05:00Z",
        }
    ]