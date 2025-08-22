# Development Best Practices

> **📚 Authoritative Reference**: This guide provides a focused overview of development practices. For comprehensive development standards and detailed technical patterns, see **[DEVELOPMENT_GUIDELINES.md](../../DEVELOPMENT_GUIDELINES.md)** - the authoritative source for all development standards.

## Purpose

This guide serves as a **quick reference and practical overview** of development practices for daily development work. It consolidates key practices from the comprehensive development guidelines for easy reference during development workflows.

## Table of Contents

- [Code Quality Standards](#code-quality-standards)
- [Development Workflow](#development-workflow)
- [Architecture Principles](#architecture-principles)
- [Testing Requirements](#testing-requirements)
- [Documentation Standards](#documentation-standards)
- [Security Practices](#security-practices)
- [Performance Guidelines](#performance-guidelines)

## Code Quality Standards

### Python Coding Conventions

We follow PEP 8 with project-specific adaptations enforced by automated tools.

#### Type Hints (MANDATORY)

All functions and methods must have complete type annotations:

```python
# ✅ Good: Complete type annotations
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

# ❌ Bad: Missing type annotations  
def create_pull_request(repository_id, pr_number, title, author, body=None):
    # Missing all type information
```

#### Variable Naming Conventions

Use descriptive, self-documenting names:

```python
# ✅ Good: Clear, descriptive names
repository_health_score = calculate_repository_health_score(repository)
failed_checks_count = len([check for check in checks if check.failed])
github_api_rate_limit_remaining = client.rate_limiter.get_remaining()

# ❌ Bad: Abbreviated or unclear names
repo_score = calc_score(repo)
failed_cnt = len([c for c in checks if c.failed])
api_remaining = client.rate_limiter.get_remaining()
```

#### Function Design

Keep functions focused and small with single responsibility:

```python
# ✅ Good: Single responsibility, clear purpose
def calculate_repository_health_score(repository: Repository) -> float:
    """Calculate health score based on recent PR success rate."""
    recent_prs = get_recent_pull_requests(repository.id, days=30)
    if not recent_prs:
        return 1.0  # Default to healthy for new repos
    
    successful_prs = [pr for pr in recent_prs if pr.all_checks_passed()]
    return len(successful_prs) / len(recent_prs)

# ❌ Bad: Multiple responsibilities in one function
def analyze_repository(repository):
    # Mixing data fetching, calculation, and formatting
    # ... (see DEVELOPMENT_GUIDELINES.md for full example)
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

## Development Workflow

### Git Workflow

1. **Branch Naming**: Use descriptive names with prefixes
   ```bash
   feature/add-user-authentication
   fix/database-connection-timeout  
   docs/update-api-documentation
   refactor/extract-notification-service
   ```

2. **Commit Messages**: Follow conventional commits format
   ```bash
   feat: add user authentication to PR monitor
   fix: resolve database connection timeout issue
   docs: update API documentation for GitHub client
   refactor: extract notification service into separate module
   test: add integration tests for fix applicator worker
   ```

3. **Pull Request Process**:
   - Create feature branch from `main`
   - Make incremental commits with clear messages
   - Ensure all tests pass and code quality checks pass
   - Create PR with comprehensive description
   - Address review feedback promptly
   - Squash commits before merge if needed

### Development Commands

```bash
# Setup and dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
pre-commit install

# Code quality (run before committing)
ruff format .                    # Format code
ruff check . --fix              # Lint and fix issues
mypy src/                       # Type checking
bandit -r src/                  # Security scanning
safety check                   # Dependency vulnerabilities

# Testing
pytest tests/ -v                # Run all tests
pytest tests/unit/ -v           # Unit tests only
pytest tests/integration/ -v    # Integration tests only
pytest tests/ --cov=src --cov-report=html  # With coverage

# Development environment
docker-compose up               # Start all services
python -m workers.monitor       # Run individual workers
python -m workers.analyzer
python -m workers.fixer

# Database operations
alembic upgrade head            # Apply migrations
alembic revision -m "message"   # Create migration
```

## Architecture Principles

### 1. Human Readability First

Code should be optimized for human understanding:

```python
# ✅ Good: Clear intent and flow
async def process_failed_check(check_run: CheckRun) -> FixAttempt:
    """Process a failed check and attempt automated fix."""
    analysis = await analyze_check_failure(check_run)
    
    if analysis.is_automatically_fixable():
        fix_strategy = select_fix_strategy(analysis)
        return await apply_fix_strategy(check_run, fix_strategy)
    else:
        await escalate_to_human_review(check_run, analysis)
        return FixAttempt.create_escalated(check_run.id)
```

### 2. Strong Interface Design

Use abstract base classes to define clear contracts:

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def analyze_failure(
        self, 
        check_logs: str, 
        context: AnalysisContext
    ) -> FailureAnalysis:
        """Analyze check failure logs to determine fix strategy."""
        pass
    
    @abstractmethod
    async def generate_fix(
        self, 
        analysis: FailureAnalysis
    ) -> Optional[FixSuggestion]:
        """Generate a fix suggestion based on failure analysis."""
        pass
```

### 3. Design Patterns

#### Provider Pattern
Use for all external integrations:

```python
class NotificationProvider(ABC):
    @abstractmethod
    async def send_notification(
        self, 
        message: str, 
        severity: NotificationSeverity
    ) -> bool:
        pass

class TelegramNotificationProvider(NotificationProvider):
    async def send_notification(self, message: str, severity: NotificationSeverity) -> bool:
        # Telegram-specific implementation
        pass
```

#### Repository Pattern
Abstract database operations:

```python
class BaseRepository(ABC):
    def __init__(self, session: AsyncSession):
        self.session = session
    
    @abstractmethod
    async def get_by_id(self, id: uuid.UUID) -> Optional[T]:
        pass
    
    @abstractmethod
    async def create(self, **kwargs) -> T:
        pass
```

#### Worker Pattern
Separate workers for each workflow step:

```python
class BaseWorker(ABC):
    @abstractmethod
    async def process_message(self, message: WorkerMessage) -> None:
        pass
    
    async def run(self) -> None:
        while True:
            message = await self.queue.get_message()
            try:
                await self.process_message(message)
                await self.queue.acknowledge_message(message)
            except Exception as e:
                await self.handle_processing_error(message, e)
```

## Testing Requirements

### Test Documentation Standard

Every test must include Why/What/How documentation:

```python
def test_analyzer_categorizes_lint_failures():
    """
    Why: Ensure the analyzer correctly identifies lint failures to route them
         for automatic fixing rather than human escalation
    
    What: Tests that CheckAnalyzer.analyze() returns category='lint' for
          eslint failure logs
    
    How: Provides sample eslint failure logs and verifies the returned
         analysis has the correct category and confidence score
    """
    # Test implementation
```

### Test Types and Coverage

- **Unit Tests**: Test individual functions and classes in isolation
- **Integration Tests**: Test component interactions
- **End-to-End Tests**: Test complete workflows
- **Performance Tests**: Verify performance requirements
- **Security Tests**: Validate security controls

See [Testing Guide](testing-guide.md) for comprehensive testing documentation.

## Documentation Standards

### Code Comments

Explain "why", not "what":

```python
# ✅ Good: Explains reasoning
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

# ❌ Bad: Explains obvious code
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

Document all public interfaces with examples:

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

## Security Practices

### Secret Management

Never log or expose sensitive data:

```python
# ✅ Good: Mask sensitive data in logs
def get_config_summary(config: Config) -> Dict[str, Any]:
    """Get configuration summary safe for logging."""
    return {
        "database_host": config.database.host,
        "database_port": config.database.port,
        "github_token": "***" if config.github.token else None,
        "anthropic_api_key": "***" if config.anthropic.api_key else None,
    }

# ❌ Bad: Exposing secrets in logs
def log_config(config):
    logger.info(f"Config: {config}")  # May contain API keys
```

### Input Validation

Validate all inputs with Pydantic:

```python
from pydantic import BaseModel, Field, validator

class PullRequestCreateRequest(BaseModel):
    repository_id: uuid.UUID = Field(..., description="Repository ID")
    pr_number: int = Field(..., gt=0, description="PR number (must be positive)")
    title: str = Field(..., min_length=1, max_length=500, description="PR title")
    author: str = Field(..., min_length=1, max_length=100, description="PR author")
    
    @validator('title')
    def validate_title(cls, v):
        if not v.strip():
            raise ValueError("Title cannot be empty or whitespace only")
        return v.strip()
```

### Error Handling

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
```

## Performance Guidelines

### Async/Await Patterns

Use async for I/O operations:

```python
# ✅ Good: Proper async usage for I/O
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

# ❌ Bad: Sequential processing
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
# ✅ Good: Efficient bulk operations
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

# ❌ Bad: Individual queries in loop
async def mark_prs_processed_slow(pr_ids, processed_at):
    for pr_id in pr_ids:
        pr = await self.session.get(PullRequest, pr_id)
        pr.processed_at = processed_at
        pr.updated_at = datetime.utcnow()
    await self.session.commit()
```

### Structured Logging

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

## Development Tools

### Required Tools Configuration

```bash
# Install all development tools
pip install ruff mypy bandit safety pytest pytest-asyncio pytest-cov pre-commit

# Configure pre-commit hooks
pre-commit install
```

### Pre-commit Configuration

`.pre-commit-config.yaml`:
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

### IDE Configuration

**VS Code**: Install recommended extensions
- Python
- Pylance (type checking)
- Ruff (linting and formatting)
- GitLens (git integration)

**PyCharm**: Enable built-in inspections
- Enable all Python inspections
- Configure external tools for ruff, mypy, bandit

## Quality Assurance Checklist

Before submitting any code:

- [ ] Type hints are complete and accurate
- [ ] Docstrings follow Google style and include examples
- [ ] Error handling is appropriate and informative
- [ ] No secrets or sensitive data are logged or exposed
- [ ] Async/await is used correctly for I/O operations
- [ ] Database queries are efficient and properly indexed
- [ ] Tests follow the Why/What/How pattern
- [ ] Public interfaces are well-documented
- [ ] Code follows the established architecture patterns
- [ ] All pre-commit hooks pass
- [ ] Test coverage is adequate (>80% for new code)

---

## Quick Reference Navigation

### 📖 **For Comprehensive Standards**
- **[DEVELOPMENT_GUIDELINES.md](../../DEVELOPMENT_GUIDELINES.md)** - Complete development standards (849 lines)
- **[TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md)** - Complete testing standards (856 lines)

### 🚀 **For Practical Workflows**  
- **[Local Development Setup](local-development.md)** - Environment setup and workflows
- **[Testing Guide](testing-guide.md)** - Testing overview and entry point
- **[Code Review Guidelines](code-review.md)** - Review process and standards
- **[Debugging Guide](debugging.md)** - Troubleshooting and debugging techniques

---

Following these best practices ensures that all code contributions maintain the high quality and consistency expected in this project. **For detailed technical patterns, advanced topics, and comprehensive standards, always refer to [DEVELOPMENT_GUIDELINES.md](../../DEVELOPMENT_GUIDELINES.md)**.