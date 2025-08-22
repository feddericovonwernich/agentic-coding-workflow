# Development Guidelines (Authoritative)

> **📋 Document Purpose**: This is the **authoritative source** for all development standards, coding practices, and technical patterns in the Agentic Coding Workflow project. For practical daily development guidance, see [docs/developer/best-practices.md](docs/developer/best-practices.md).

## Purpose

This document provides **comprehensive development guidelines** that ensure code quality, maintainability, and consistency across all contributions. It serves as the definitive reference for all development standards and detailed technical patterns.

## Table of Contents

- [Code Style and Standards](#code-style-and-standards)
- [Architecture Principles](#architecture-principles)
- [Module Structure](#module-structure)
- [Error Handling](#error-handling)
- [Security Practices](#security-practices)
- [Performance Considerations](#performance-considerations)
- [Documentation Requirements](#documentation-requirements)
- [Code Review Standards](#code-review-standards)
- [Development Tools](#development-tools)

## Code Style and Standards

### Python Coding Conventions

We follow PEP 8 with project-specific adaptations enforced by automated tools.

#### Type Hints (MANDATORY)

All functions and methods must have complete type annotations:

```python
# Good: Complete type annotations
from typing import Optional, List, Dict, Any
import uuid

async def create_pull_request(
    repository_id: uuid.UUID,
    pr_number: int,
    title: str,
    author: str,
    body: Optional[str] = None
) -> PullRequest:
    """Create a new pull request record."""
    # Implementation

# Bad: Missing or incomplete type annotations  
def create_pull_request(repository_id, pr_number, title, author, body=None):
    # Missing all type information
```

#### Variable Naming Conventions

Use descriptive, self-documenting names:

```python
# Good: Clear, descriptive names
repository_health_score = calculate_repository_health_score(repository)
failed_checks_count = len([check for check in checks if check.failed])
github_api_rate_limit_remaining = client.rate_limiter.get_remaining()

# Bad: Abbreviated or unclear names
repo_score = calc_score(repo)
failed_cnt = len([c for c in checks if c.failed])
api_remaining = client.rate_limiter.get_remaining()
```

#### Function Design

Keep functions focused and small:

```python
# Good: Single responsibility, clear purpose
def calculate_repository_health_score(repository: Repository) -> float:
    """Calculate health score based on recent PR success rate."""
    recent_prs = get_recent_pull_requests(repository.id, days=30)
    if not recent_prs:
        return 1.0  # Default to healthy for new repos
    
    successful_prs = [pr for pr in recent_prs if pr.all_checks_passed()]
    return len(successful_prs) / len(recent_prs)

def get_recent_pull_requests(repository_id: uuid.UUID, days: int) -> List[PullRequest]:
    """Fetch pull requests from the last N days."""
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    return repository.get_prs_since(cutoff_date)

# Bad: Multiple responsibilities in one function
def analyze_repository(repository):
    # Mixing data fetching, calculation, and formatting
    recent_prs = []
    for pr in repository.prs:
        if pr.created_at > datetime.utcnow() - timedelta(days=30):
            recent_prs.append(pr)
    
    if len(recent_prs) == 0:
        score = 1.0
    else:
        successful = 0
        for pr in recent_prs:
            if all(check.conclusion == "success" for check in pr.checks):
                successful += 1
        score = successful / len(recent_prs)
    
    return f"Repository health: {score * 100:.1f}%"
```

#### Import Organization

Use `ruff` configuration for consistent import ordering:

```python
# Standard library imports
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

# Third-party imports
import aiohttp
import structlog
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from src.models import PullRequest, Repository, CheckRun
from src.repositories import PullRequestRepository
from src.github import GitHubClient
from src.config import get_config
```

### Docstring Standards

Use Google-style docstrings for all public functions and classes:

```python
class GitHubClient:
    """Client for interacting with the GitHub API.
    
    Provides authentication, rate limiting, and error handling for GitHub API
    operations. Supports both Personal Access Token and GitHub App authentication.
    
    Attributes:
        auth: Authentication provider instance
        config: Client configuration settings
        rate_limiter: Rate limiting manager
        
    Example:
        ```python
        auth = PersonalAccessTokenAuth("ghp_token")
        client = GitHubClient(auth=auth)
        
        async with client:
            user = await client.get_user()
            print(f"Authenticated as: {user['login']}")
        ```
    """
    
    async def get_pull_request(
        self, 
        owner: str, 
        repo: str, 
        pr_number: int
    ) -> Dict[str, Any]:
        """Fetch a specific pull request.
        
        Args:
            owner: Repository owner (user or organization)
            repo: Repository name
            pr_number: Pull request number
            
        Returns:
            Pull request data as returned by GitHub API
            
        Raises:
            GitHubNotFoundError: If the pull request doesn't exist
            GitHubAuthenticationError: If authentication fails
            GitHubRateLimitError: If rate limit is exceeded
            
        Example:
            ```python
            pr = await client.get_pull_request("owner", "repo", 123)
            print(f"PR title: {pr['title']}")
            ```
        """
```

## Architecture Principles

### 1. Human Readability First

Code should be optimized for human understanding, not just machine execution:

```python
# Good: Clear intent and flow
async def process_failed_check(check_run: CheckRun) -> FixAttempt:
    """Process a failed check and attempt automated fix."""
    analysis = await analyze_check_failure(check_run)
    
    if analysis.is_automatically_fixable():
        fix_strategy = select_fix_strategy(analysis)
        return await apply_fix_strategy(check_run, fix_strategy)
    else:
        await escalate_to_human_review(check_run, analysis)
        return FixAttempt.create_escalated(check_run.id)

# Bad: Unclear flow and purpose
async def process_check(check):
    analysis = await analyze(check)
    if analysis.fixable:
        strategy = get_strategy(analysis)
        return await apply_fix(check, strategy)
    else:
        await escalate(check, analysis)
        return FixAttempt.escalated(check.id)
```

### 2. Strong Interface Design

Use abstract base classes to define clear contracts:

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    """Abstract base class for LLM providers.
    
    All LLM providers must implement this interface to ensure compatibility
    with the analysis and fix generation systems.
    """
    
    @abstractmethod
    async def analyze_failure(
        self, 
        check_logs: str, 
        context: AnalysisContext
    ) -> FailureAnalysis:
        """Analyze check failure logs to determine fix strategy.
        
        Args:
            check_logs: Raw log output from failed check
            context: Additional context about the repository and PR
            
        Returns:
            Analysis with categorization and fix recommendations
        """
        pass
    
    @abstractmethod
    async def generate_fix(
        self, 
        analysis: FailureAnalysis
    ) -> Optional[FixSuggestion]:
        """Generate a fix suggestion based on failure analysis.
        
        Args:
            analysis: Previous analysis of the failure
            
        Returns:
            Fix suggestion or None if unable to generate fix
        """
        pass

# Concrete implementation
class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider implementation."""
    
    async def analyze_failure(
        self, 
        check_logs: str, 
        context: AnalysisContext
    ) -> FailureAnalysis:
        # Implementation specific to Anthropic API
        pass
```

### 3. Design Patterns

#### Provider Pattern
Use for all external integrations (LLMs, notifications, databases):

```python
class NotificationProvider(ABC):
    """Abstract notification provider."""
    
    @abstractmethod
    async def send_notification(
        self, 
        message: str, 
        severity: NotificationSeverity
    ) -> bool:
        """Send notification through this provider."""
        pass

class TelegramNotificationProvider(NotificationProvider):
    """Telegram notification implementation."""
    
    async def send_notification(
        self, 
        message: str, 
        severity: NotificationSeverity
    ) -> bool:
        # Telegram-specific implementation
        pass
```

#### Repository Pattern
Abstract database operations:

```python
class BaseRepository(ABC):
    """Base repository with common database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    @abstractmethod
    async def get_by_id(self, id: uuid.UUID) -> Optional[T]:
        """Get entity by ID."""
        pass
    
    @abstractmethod
    async def create(self, **kwargs) -> T:
        """Create new entity."""
        pass

class PullRequestRepository(BaseRepository[PullRequest]):
    """Repository for pull request operations."""
    
    async def get_by_id(self, id: uuid.UUID) -> Optional[PullRequest]:
        result = await self.session.get(PullRequest, id)
        return result
```

#### Worker Pattern
Separate workers for each workflow step:

```python
class BaseWorker(ABC):
    """Base class for all worker implementations."""
    
    @abstractmethod
    async def process_message(self, message: WorkerMessage) -> None:
        """Process a single message from the queue."""
        pass
    
    async def run(self) -> None:
        """Main worker loop."""
        while True:
            message = await self.queue.get_message()
            try:
                await self.process_message(message)
                await self.queue.acknowledge_message(message)
            except Exception as e:
                await self.handle_processing_error(message, e)

class PRMonitorWorker(BaseWorker):
    """Worker that monitors repositories for new pull requests."""
    
    async def process_message(self, message: WorkerMessage) -> None:
        repository_id = message.data["repository_id"]
        await self.check_repository_for_new_prs(repository_id)
```

## Module Structure

### Public vs Private API

Clearly separate public interfaces from implementation details:

```python
# src/github/__init__.py - Public API
"""GitHub integration module.

This module provides the public API for GitHub operations.
"""

# Public exports
from .client import GitHubClient, GitHubClientConfig
from .auth import PersonalAccessTokenAuth, GitHubAppAuth
from .exceptions import (
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubAuthenticationError
)

# Internal modules (not exported)
# .rate_limiting - Internal rate limiting implementation
# .pagination - Internal pagination logic
# ._http_client - Private HTTP client wrapper

__all__ = [
    "GitHubClient",
    "GitHubClientConfig", 
    "PersonalAccessTokenAuth",
    "GitHubAppAuth",
    "GitHubError",
    "GitHubNotFoundError",
    "GitHubRateLimitError",
    "GitHubAuthenticationError",
]
```

### Module Organization

Organize code by domain, not by type:

```python
# Good: Domain-based organization
src/
├── github/           # GitHub API integration
│   ├── client.py     # Main client
│   ├── auth.py       # Authentication
│   └── exceptions.py # GitHub-specific exceptions
├── analysis/         # Check failure analysis
│   ├── analyzer.py   # Main analyzer
│   ├── patterns.py   # Failure patterns
│   └── llm/         # LLM integration
└── notifications/    # Notification system
    ├── providers/    # Provider implementations
    ├── router.py     # Notification routing
    └── templates.py  # Message templates

# Bad: Type-based organization  
src/
├── models/          # All models mixed together
├── services/        # All services mixed together
├── exceptions/      # All exceptions mixed together
└── utils/          # Miscellaneous utilities
```

## Error Handling

### Exception Hierarchy

Create clear, domain-specific exceptions:

```python
class AgenticWorkflowError(Exception):
    """Base exception for all workflow errors."""
    pass

class GitHubError(AgenticWorkflowError):
    """Base exception for GitHub API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code

class GitHubRateLimitError(GitHubError):
    """Raised when GitHub rate limit is exceeded."""
    
    def __init__(self, reset_time: int, message: str = "Rate limit exceeded"):
        super().__init__(message, status_code=429)
        self.reset_time = reset_time

class GitHubNotFoundError(GitHubError):
    """Raised when GitHub resource is not found."""
    
    def __init__(self, resource: str, message: Optional[str] = None):
        if message is None:
            message = f"GitHub resource not found: {resource}"
        super().__init__(message, status_code=404)
        self.resource = resource
```

### Error Handling Patterns

Handle errors at the appropriate level:

```python
# Good: Handle errors where they can be meaningfully addressed
async def fetch_pull_request_with_retry(
    client: GitHubClient, 
    owner: str, 
    repo: str, 
    pr_number: int,
    max_retries: int = 3
) -> Optional[Dict[str, Any]]:
    """Fetch PR with automatic retry on rate limit errors."""
    
    for attempt in range(max_retries):
        try:
            return await client.get_pull_request(owner, repo, pr_number)
            
        except GitHubRateLimitError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(e.reset_time - time.time())
                continue
            raise
            
        except GitHubNotFoundError:
            # PR doesn't exist, return None rather than raising
            return None
            
        except GitHubError as e:
            # Log error for debugging but don't retry
            logger.error(
                "Failed to fetch pull request",
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                error=str(e),
                status_code=e.status_code
            )
            raise

# Bad: Catching and re-raising without adding value
async def fetch_pull_request(client, owner, repo, pr_number):
    try:
        return await client.get_pull_request(owner, repo, pr_number)
    except Exception as e:
        logger.error(f"Error: {e}")
        raise  # No value added
```

### Logging Standards

Use structured logging with context:

```python
import structlog

logger = structlog.get_logger()

async def process_repository(repository: Repository) -> None:
    """Process a repository for new pull requests."""
    
    logger.info(
        "Starting repository processing",
        repository_id=str(repository.id),
        repository_name=repository.full_name,
        last_checked=repository.last_checked_at.isoformat()
    )
    
    try:
        new_prs = await fetch_new_pull_requests(repository)
        
        logger.info(
            "Found new pull requests",
            repository_id=str(repository.id),
            new_pr_count=len(new_prs),
            pr_numbers=[pr.number for pr in new_prs]
        )
        
        for pr in new_prs:
            await process_pull_request(pr)
            
    except Exception as e:
        logger.error(
            "Repository processing failed",
            repository_id=str(repository.id),
            repository_name=repository.full_name,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True  # Include traceback in debug mode
        )
        raise
```

## Security Practices

### Secret Management

Never log or expose sensitive data:

```python
# Good: Mask sensitive data in logs
def get_config_summary(config: Config) -> Dict[str, Any]:
    """Get configuration summary safe for logging."""
    return {
        "database_host": config.database.host,
        "database_port": config.database.port,
        "github_token": "***" if config.github.token else None,
        "anthropic_api_key": "***" if config.anthropic.api_key else None,
    }

# Bad: Exposing secrets in logs
def log_config(config):
    logger.info(f"Config: {config}")  # May contain API keys
```

### Input Validation

Validate all inputs with Pydantic:

```python
from pydantic import BaseModel, Field, validator

class PullRequestCreateRequest(BaseModel):
    """Request model for creating pull requests."""
    
    repository_id: uuid.UUID = Field(..., description="Repository ID")
    pr_number: int = Field(..., gt=0, description="PR number (must be positive)")
    title: str = Field(..., min_length=1, max_length=500, description="PR title")
    author: str = Field(..., min_length=1, max_length=100, description="PR author")
    body: Optional[str] = Field(None, max_length=10000, description="PR description")
    
    @validator('title')
    def validate_title(cls, v):
        if not v.strip():
            raise ValueError("Title cannot be empty or whitespace only")
        return v.strip()
    
    @validator('author')
    def validate_author(cls, v):
        # Basic validation for GitHub username pattern
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError("Invalid GitHub username format")
        return v
```

## Performance Considerations

### Async/Await Patterns

Use async for I/O operations:

```python
# Good: Proper async usage for I/O
async def analyze_multiple_repositories(
    repository_ids: List[uuid.UUID]
) -> List[RepositoryAnalysis]:
    """Analyze multiple repositories concurrently."""
    
    # Fetch repositories concurrently
    repositories = await asyncio.gather(*[
        repository_repo.get_by_id(repo_id) 
        for repo_id in repository_ids
    ])
    
    # Process each repository concurrently
    analyses = await asyncio.gather(*[
        analyze_repository(repo) 
        for repo in repositories 
        if repo is not None
    ])
    
    return analyses

# Bad: Sequential processing
async def analyze_multiple_repositories_slow(repository_ids):
    analyses = []
    for repo_id in repository_ids:
        repo = await repository_repo.get_by_id(repo_id)
        if repo:
            analysis = await analyze_repository(repo)
            analyses.append(analysis)
    return analyses
```

### Database Optimization

Use efficient query patterns:

```python
# Good: Efficient bulk operations
async def mark_multiple_prs_as_processed(
    pr_ids: List[uuid.UUID],
    processed_at: datetime
) -> int:
    """Mark multiple PRs as processed in a single query."""
    
    stmt = (
        update(PullRequest)
        .where(PullRequest.id.in_(pr_ids))
        .values(
            processed_at=processed_at,
            updated_at=datetime.utcnow()
        )
    )
    
    result = await self.session.execute(stmt)
    await self.session.commit()
    return result.rowcount

# Bad: Individual queries in loop
async def mark_prs_processed_slow(pr_ids, processed_at):
    for pr_id in pr_ids:
        pr = await self.session.get(PullRequest, pr_id)
        pr.processed_at = processed_at
        pr.updated_at = datetime.utcnow()
    await self.session.commit()
```

## Documentation Requirements

### Code Comments

Explain "why", not "what":

```python
# Good: Explains reasoning
async def retry_failed_check(check_run: CheckRun) -> bool:
    """Retry a failed check run."""
    
    # GitHub API requires a 30-second delay between check run retries
    # to prevent overwhelming the CI system
    await asyncio.sleep(30)
    
    # Use the original check run configuration to ensure consistency
    # with the initial run parameters
    return await github_client.retry_check_run(
        check_run.external_id,
        config=check_run.original_config
    )

# Bad: Explains obvious code
async def retry_failed_check(check_run):
    # Sleep for 30 seconds
    await asyncio.sleep(30)
    
    # Call retry_check_run method
    return await github_client.retry_check_run(
        check_run.external_id,
        config=check_run.original_config
    )
```

### API Documentation

Document all public interfaces:

```python
def calculate_fix_success_rate(
    repository: Repository,
    days_back: int = 30
) -> float:
    """Calculate the success rate of automated fixes.
    
    This metric helps evaluate the effectiveness of our automated fix
    strategies and can be used to adjust confidence thresholds.
    
    Args:
        repository: Repository to analyze
        days_back: Number of days to look back for fix attempts
        
    Returns:
        Success rate as a float between 0.0 and 1.0, where 1.0 means
        all automated fixes were successful. Returns 1.0 if no fix
        attempts were made (assuming optimistically that fixes would work).
        
    Example:
        ```python
        repo = await repository_repo.get_by_name("owner/repo")
        success_rate = calculate_fix_success_rate(repo, days_back=7)
        print(f"Fix success rate: {success_rate:.2%}")
        ```
    """
```

## Code Review Standards

### What to Check During Reviews

1. **Correctness**: Does the code do what it's supposed to do?
2. **Readability**: Can other developers understand the code?
3. **Maintainability**: Will this code be easy to modify later?
4. **Performance**: Are there obvious performance issues?
5. **Security**: Are there potential security vulnerabilities?
6. **Testing**: Is the code adequately tested?
7. **Documentation**: Is the code properly documented?

### Review Checklist

- [ ] Type hints are complete and accurate
- [ ] Docstrings follow Google style and include examples
- [ ] Error handling is appropriate and informative
- [ ] No secrets or sensitive data are logged or exposed
- [ ] Async/await is used correctly for I/O operations
- [ ] Database queries are efficient and properly indexed
- [ ] Tests follow the Why/What/How pattern
- [ ] Public interfaces are well-documented
- [ ] Code follows the established architecture patterns

## Development Tools

### Required Tools

Configure your development environment with:

```bash
# Code formatting and linting
pip install ruff black

# Type checking
pip install mypy

# Security scanning
pip install bandit safety

# Testing
pip install pytest pytest-asyncio pytest-cov

# Development dependencies
pip install pre-commit
```

### Pre-commit Configuration

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests, types-redis]

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: [-r, src/]
```

### Development Commands

```bash
# Format code
ruff format .

# Lint and fix issues
ruff check . --fix

# Type checking
mypy src/

# Security scanning
bandit -r src/
safety check

# Run tests
pytest tests/ -v

# Test with coverage
pytest tests/ --cov=src --cov-report=html

# Run pre-commit hooks manually
pre-commit run --all-files
```

---

This document serves as the canonical reference for development practices. All code contributions, whether from humans or AI subagents, must follow these guidelines to ensure consistency and quality across the project.