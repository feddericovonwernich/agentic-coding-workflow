# Code Review Guidelines

This guide provides comprehensive guidelines for conducting effective code reviews in the Agentic Coding Workflow project, ensuring code quality, knowledge sharing, and team collaboration.

## Table of Contents

- [Code Review Philosophy](#code-review-philosophy)
- [Review Process](#review-process)
- [Review Standards](#review-standards)
- [Reviewer Guidelines](#reviewer-guidelines)
- [Author Guidelines](#author-guidelines)
- [Review Checklist](#review-checklist)
- [Common Review Scenarios](#common-review-scenarios)
- [Review Tools and Automation](#review-tools-and-automation)
- [Handling Review Conflicts](#handling-review-conflicts)

## Code Review Philosophy

### Core Principles

1. **Code Quality**: Ensure code meets our high standards for maintainability, performance, and security
2. **Knowledge Sharing**: Reviews are opportunities for learning and knowledge transfer
3. **Constructive Feedback**: Focus on improving the code, not criticizing the author
4. **Collaborative Improvement**: Work together to find the best solution
5. **Continuous Learning**: Both reviewers and authors should learn from every review

### Goals of Code Reviews

- **Quality Assurance**: Catch bugs, design issues, and maintainability problems
- **Knowledge Transfer**: Share domain knowledge and best practices
- **Code Consistency**: Ensure adherence to project standards and patterns
- **Security Review**: Identify potential security vulnerabilities
- **Performance Optimization**: Spot performance issues and improvement opportunities
- **Documentation**: Ensure code is properly documented and testable

## Review Process

### 1. Pre-Review Preparation

#### Author Checklist (Before Requesting Review)

- [ ] **Self-Review**: Review your own code first, checking for obvious issues
- [ ] **Testing**: All tests pass locally, including new tests for added functionality
- [ ] **Code Quality**: Pre-commit hooks pass (formatting, linting, type checking)
- [ ] **Documentation**: Code is properly documented with docstrings and comments
- [ ] **Scope**: PR has a clear, focused scope and single responsibility
- [ ] **Description**: PR description clearly explains what was changed and why

#### Creating Effective Pull Requests

```markdown
## Pull Request Template

### Summary
Brief description of what this PR accomplishes and why it's needed.

### Changes Made
- Specific change 1
- Specific change 2
- Specific change 3

### Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed (describe scenarios)

### Review Focus Areas
Please pay special attention to:
- Performance implications of the new caching layer
- Security of the new authentication flow
- Database migration safety

### Screenshots/Examples
(If applicable, add screenshots or code examples)

### Related Issues
Closes #123, Related to #456
```

### 2. Review Workflow

#### Timeline Expectations

- **Small PRs** (< 100 lines): 24 hours for initial review
- **Medium PRs** (100-500 lines): 48 hours for initial review
- **Large PRs** (> 500 lines): Should be broken down if possible, 72 hours for review

#### Review States

1. **Draft**: PR is work in progress, not ready for formal review
2. **Ready for Review**: Author has completed development and testing
3. **In Review**: Actively being reviewed by team members
4. **Changes Requested**: Reviewer has requested specific changes
5. **Approved**: Code meets standards and is ready to merge
6. **Merged**: Changes have been integrated into the main branch

### 3. Review Assignment

#### Automatic Assignment Rules

- **Core Team**: All PRs reviewed by at least one core team member
- **Security Changes**: Security-sensitive code reviewed by security-focused developer
- **Database Changes**: Database schema changes reviewed by database expert
- **Performance Critical**: Performance-sensitive code reviewed by performance expert

#### Manual Assignment

Authors should request specific reviewers when:
- Changes affect reviewer's area of expertise
- Complex architectural decisions need domain expert input
- Cross-team collaboration requires stakeholder review

## Review Standards

### 1. Correctness and Functionality

#### Code Logic
```python
# ✅ Good: Clear logic with error handling
async def process_pull_request(pr_id: uuid.UUID) -> ProcessingResult:
    """Process a pull request through the analysis pipeline."""
    try:
        pr = await pr_repository.get_by_id(pr_id)
        if not pr:
            raise PullRequestNotFoundError(f"PR not found: {pr_id}")
        
        # Validate PR is in correct state for processing
        if pr.status not in [PRStatus.OPEN, PRStatus.CHECKS_FAILED]:
            logger.info("Skipping PR not ready for processing", pr_id=pr_id, status=pr.status)
            return ProcessingResult.skipped(pr_id, reason="Not ready for processing")
        
        analysis = await analyze_pr_failures(pr)
        return await apply_fixes_if_needed(pr, analysis)
        
    except Exception as e:
        logger.error("Failed to process PR", pr_id=pr_id, error=str(e))
        raise

# ❌ Bad: Unclear logic, poor error handling
async def process_pr(pr_id):
    pr = await get_pr(pr_id)
    if pr and pr.status == "open":
        analysis = await analyze(pr)
        return await fix(pr, analysis)
    return None
```

**Review Questions:**
- Does the code do what it's supposed to do?
- Are edge cases handled appropriately?
- Is error handling comprehensive and appropriate?
- Are there any obvious bugs or logical errors?

#### Input Validation
```python
# ✅ Good: Comprehensive input validation
from pydantic import BaseModel, Field, validator

class CreatePullRequestRequest(BaseModel):
    """Request to create a new pull request record."""
    
    repository_id: uuid.UUID = Field(..., description="Repository UUID")
    pr_number: int = Field(..., gt=0, le=99999, description="GitHub PR number")
    title: str = Field(..., min_length=1, max_length=500, description="PR title")
    author: str = Field(..., min_length=1, max_length=100, description="GitHub username")
    
    @validator('title')
    def validate_title(cls, v):
        if not v.strip():
            raise ValueError("Title cannot be empty or whitespace only")
        return v.strip()
    
    @validator('author')
    def validate_github_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$', v):
            raise ValueError("Invalid GitHub username format")
        return v

# ❌ Bad: No input validation
def create_pr(repo_id, pr_number, title, author):
    # Direct database insertion without validation
    pass
```

### 2. Code Quality and Maintainability

#### Readability and Structure
```python
# ✅ Good: Clear structure and naming
class GitHubCheckAnalyzer:
    """Analyzes GitHub check runs to determine failure categories and fix strategies."""
    
    def __init__(self, llm_provider: LLMProvider, confidence_threshold: float = 0.8):
        self.llm_provider = llm_provider
        self.confidence_threshold = confidence_threshold
        self.logger = structlog.get_logger()
    
    async def analyze_failed_check(self, check_run: CheckRun) -> AnalysisResult:
        """Analyze a failed check run to determine root cause and fix strategy."""
        check_logs = await self._extract_check_logs(check_run)
        analysis_context = self._build_analysis_context(check_run)
        
        llm_analysis = await self.llm_provider.analyze_failure(check_logs, analysis_context)
        
        return AnalysisResult(
            check_run_id=check_run.id,
            category=llm_analysis.category,
            confidence=llm_analysis.confidence,
            fix_strategy=llm_analysis.fix_strategy,
            requires_human_review=llm_analysis.confidence < self.confidence_threshold
        )

# ❌ Bad: Poor structure and naming
class Analyzer:
    def __init__(self, llm, thresh=0.8):
        self.llm = llm
        self.thresh = thresh
    
    async def analyze(self, check):
        logs = await get_logs(check)
        ctx = make_context(check)
        result = await self.llm.analyze(logs, ctx)
        return make_result(check, result, result.conf < self.thresh)
```

**Review Questions:**
- Are function and variable names descriptive and self-documenting?
- Is the code structure logical and easy to follow?
- Are functions appropriately sized (single responsibility)?
- Is the code DRY (Don't Repeat Yourself)?

### 3. Security Review

#### Authentication and Authorization
```python
# ✅ Good: Proper authentication and authorization
@require_authentication
@require_permissions(['pr:read', 'repository:access'])
async def get_pull_request(
    pr_id: uuid.UUID, 
    current_user: User = Depends(get_current_user)
) -> PullRequest:
    """Get pull request with proper authorization checks."""
    
    pr = await pr_repository.get_by_id(pr_id)
    if not pr:
        raise HTTPException(status_code=404, detail="Pull request not found")
    
    # Verify user has access to the repository
    if not await user_has_repository_access(current_user, pr.repository_id):
        raise HTTPException(status_code=403, detail="Access denied to repository")
    
    # Don't expose sensitive internal data
    return PullRequestResponse.from_orm(pr)

# ❌ Bad: No authorization checks
async def get_pull_request(pr_id: uuid.UUID):
    return await pr_repository.get_by_id(pr_id)
```

#### Input Sanitization
```python
# ✅ Good: Proper input sanitization
def sanitize_log_content(log_content: str) -> str:
    """Sanitize log content before sending to LLM or storing."""
    
    # Remove potential API keys, tokens, and secrets
    sanitized = re.sub(
        r'(?i)(token|key|secret|password)\s*[:=]\s*["\']?([a-zA-Z0-9+/=]{20,})["\']?',
        r'\1: ***',
        log_content
    )
    
    # Remove email addresses that might be sensitive
    sanitized = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        '***@***.***',
        sanitized
    )
    
    return sanitized

# ❌ Bad: No sanitization
def process_logs(log_content: str):
    # Directly process without sanitization
    return log_content
```

**Security Review Questions:**
- Are all inputs properly validated and sanitized?
- Is authentication and authorization implemented correctly?
- Are secrets and sensitive data properly protected?
- Are there any potential injection vulnerabilities?

### 4. Performance Review

#### Database Queries
```python
# ✅ Good: Efficient database queries
async def get_failed_checks_batch(
    repository_ids: List[uuid.UUID], 
    limit: int = 100
) -> List[CheckRun]:
    """Efficiently fetch failed checks for multiple repositories."""
    
    # Single query with proper indexes
    query = (
        select(CheckRun)
        .join(PullRequest)
        .where(
            PullRequest.repository_id.in_(repository_ids),
            CheckRun.conclusion == 'failure',
            CheckRun.analyzed_at.is_(None)
        )
        .order_by(CheckRun.created_at.desc())
        .limit(limit)
    )
    
    result = await session.execute(query)
    return result.scalars().all()

# ❌ Bad: N+1 query problem
async def get_failed_checks_slow(repository_ids: List[uuid.UUID]):
    all_checks = []
    for repo_id in repository_ids:  # N+1 queries
        prs = await get_prs_for_repository(repo_id)
        for pr in prs:
            checks = await get_failed_checks_for_pr(pr.id)
            all_checks.extend(checks)
    return all_checks
```

#### Async/Await Usage
```python
# ✅ Good: Proper concurrency
async def process_multiple_repositories(repository_ids: List[uuid.UUID]) -> List[ProcessingResult]:
    """Process multiple repositories concurrently."""
    
    # Process repositories concurrently, but limit concurrency
    semaphore = asyncio.Semaphore(5)  # Max 5 concurrent operations
    
    async def process_with_semaphore(repo_id):
        async with semaphore:
            return await process_repository(repo_id)
    
    tasks = [process_with_semaphore(repo_id) for repo_id in repository_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle any exceptions in results
    return [r for r in results if isinstance(r, ProcessingResult)]

# ❌ Bad: Sequential processing
async def process_multiple_repositories_slow(repository_ids: List[uuid.UUID]):
    results = []
    for repo_id in repository_ids:
        result = await process_repository(repo_id)
        results.append(result)
    return results
```

**Performance Review Questions:**
- Are database queries efficient and using proper indexes?
- Is async/await used appropriately for I/O operations?
- Are there any obvious performance bottlenecks?
- Is caching used where appropriate?

## Reviewer Guidelines

### 1. Providing Effective Feedback

#### Types of Feedback

**Critical Issues** (Must be fixed before merge):
```markdown
**🚨 Critical**: This function doesn't handle the case where `pr` is None, 
which will cause a runtime error. Please add null checking.

```python
if not pr:
    raise PullRequestNotFoundError(f"PR not found: {pr_id}")
```

**Suggestions** (Improvements but not blocking):
```markdown
**💡 Suggestion**: Consider using a more descriptive variable name here. 
`failed_checks_needing_analysis` would be clearer than `fc`.
```

**Questions** (Seeking clarification):
```markdown
**❓ Question**: Why do we use a 30-second timeout here? Is this based on 
typical LLM response times? Could you add a comment explaining the reasoning?
```

**Praise** (Positive reinforcement):
```markdown
**✨ Nice**: Excellent error handling here! The structured logging will make 
debugging much easier.
```

#### Effective Feedback Examples

```markdown
# ✅ Good feedback: Specific, actionable, constructive
**Issue**: The `analyze_failure` method could fail if the logs are too large for the LLM context window.

**Suggestion**: Consider truncating logs or implementing chunking:
```python
def truncate_logs_for_llm(logs: str, max_tokens: int = 3000) -> str:
    # Implementation that safely truncates while preserving important parts
    pass
```

**Rationale**: LLM providers have token limits, and large log files could cause API errors.

# ❌ Bad feedback: Vague, non-actionable
This code might have issues with large inputs.
```

### 2. Review Priorities

#### High Priority (Always Review)
1. **Security vulnerabilities**
2. **Correctness bugs**
3. **Performance issues**
4. **Breaking changes**
5. **Data safety concerns**

#### Medium Priority (Review When Time Permits)
1. **Code style and consistency**
2. **Documentation quality**
3. **Test coverage**
4. **Refactoring opportunities**

#### Low Priority (Optional)
1. **Minor style preferences**
2. **Non-critical optimizations**
3. **Alternative implementation approaches**

## Author Guidelines

### 1. Responding to Review Comments

#### Acknowledging Feedback
```markdown
# ✅ Good response: Acknowledges and explains action taken
Thanks for catching this! You're absolutely right about the null check. 
I've added proper validation and also included a test case for this scenario 
in commit abc123.

# ✅ Good response: Acknowledges but explains different approach
Good point about the variable naming. I chose `fc` to match the pattern used 
in similar functions throughout the codebase (like `pr` for pull requests). 
What do you think about keeping consistency vs. more descriptive names?

# ❌ Bad response: Dismissive or defensive
That's not really an issue in practice.
```

#### Requesting Clarification
```markdown
# ✅ Good clarification request
Could you help me understand the security concern here? I'm not seeing how 
this could be exploited. Are you thinking about the case where an attacker 
could manipulate the input logs?

# ❌ Bad clarification request
I don't see the problem.
```

### 2. Making Changes Based on Feedback

#### Iterative Improvement
1. **Address Critical Issues First**: Fix bugs and security issues immediately
2. **Group Related Changes**: Make logical commits that group related fixes
3. **Test Changes**: Ensure fixes don't break existing functionality
4. **Update Documentation**: Update docs if behavior changes
5. **Respond to Comments**: Let reviewers know what was changed

#### Commit Messages for Review Changes
```bash
# ✅ Good: Clear commit messages referencing review
git commit -m "fix: add null check for PR lookup (addresses review comment)"
git commit -m "refactor: improve variable naming for clarity (review feedback)"

# ❌ Bad: Vague commit messages
git commit -m "fix review comments"
git commit -m "updates"
```

## Review Checklist

### Technical Review Checklist

#### Functionality
- [ ] Code does what it's supposed to do
- [ ] Edge cases are handled appropriately
- [ ] Error handling is comprehensive
- [ ] No obvious bugs or logical errors

#### Code Quality
- [ ] Code is readable and well-structured
- [ ] Functions have single responsibility
- [ ] Variable and function names are descriptive
- [ ] Code follows project conventions
- [ ] No code duplication without good reason

#### Security
- [ ] Input validation is implemented
- [ ] Authentication and authorization are correct
- [ ] No secrets in code or logs
- [ ] No injection vulnerabilities

#### Performance
- [ ] Database queries are efficient
- [ ] Appropriate use of async/await
- [ ] No obvious performance bottlenecks
- [ ] Proper resource management

#### Testing
- [ ] Adequate test coverage for new code
- [ ] Tests follow Why/What/How documentation standard
- [ ] Tests are reliable and not flaky
- [ ] Integration tests for complex interactions

#### Documentation
- [ ] Public functions have docstrings
- [ ] Complex logic is commented
- [ ] API changes are documented
- [ ] Breaking changes are noted

### Process Review Checklist

#### PR Quality
- [ ] PR has clear description and scope
- [ ] Commits are logical and well-messaged
- [ ] PR size is reasonable for review
- [ ] Related issues are referenced

#### Review Process
- [ ] Appropriate reviewers are assigned
- [ ] Review comments are constructive
- [ ] Author responses are timely
- [ ] All discussions are resolved

## Common Review Scenarios

### 1. Large Pull Requests

**Problem**: PR is too large to review effectively (>500 lines)

**Solutions**:
- **Request Breakdown**: Ask author to split into smaller, logical PRs
- **Staged Review**: Review in multiple passes, focusing on different aspects
- **Architecture Review**: Start with high-level design review before detailed code review

**Review Approach**:
```markdown
This PR is quite large (1200 lines). Could we break this down into smaller chunks? 
I suggest:

1. Database schema changes (migrations + models)
2. Core service implementation 
3. API endpoints
4. Tests

This would make review more effective and reduce risk.
```

### 2. Performance-Critical Changes

**Special Focus Areas**:
- Database query efficiency
- Caching strategies
- Async/await usage
- Memory usage patterns
- API call optimization

**Review Questions**:
- How does this change affect system performance?
- Are there benchmarks or performance tests?
- Could this cause bottlenecks under load?
- Are database indexes appropriate?

### 3. Security-Sensitive Changes

**Required Reviews**:
- Security team member review
- Extra scrutiny for input validation
- Authentication/authorization checks
- Data privacy compliance

**Security Checklist**:
- [ ] Input sanitization implemented
- [ ] Output encoding appropriate
- [ ] Authentication required where needed
- [ ] Authorization checks in place
- [ ] No secrets exposed in logs or code
- [ ] SQL injection prevention
- [ ] XSS prevention (if applicable)

### 4. Database Schema Changes

**Special Requirements**:
- Database expert review
- Migration safety review
- Backward compatibility check
- Performance impact assessment

**Migration Review**:
```sql
-- ✅ Good: Safe migration with proper checks
ALTER TABLE pull_requests 
ADD COLUMN priority INTEGER DEFAULT 1 NOT NULL;

-- Add index concurrently to avoid locks
CREATE INDEX CONCURRENTLY idx_pull_requests_priority 
ON pull_requests (priority, created_at);

-- ❌ Bad: Potentially dangerous migration
ALTER TABLE pull_requests 
DROP COLUMN status;  -- This could cause data loss!
```

## Review Tools and Automation

### 1. Automated Checks

#### Pre-Review Automation
- **Code Formatting**: ruff format validation
- **Linting**: ruff check for code quality
- **Type Checking**: mypy validation
- **Security Scanning**: bandit security linting
- **Test Execution**: Automated test runs
- **Coverage Reporting**: Test coverage analysis

#### GitHub Integration
```yaml
# .github/workflows/pr-checks.yml
name: PR Quality Checks
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  quality-checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
          
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
          
      - name: Run formatting check
        run: ruff format --check .
        
      - name: Run linting
        run: ruff check .
        
      - name: Run type checking
        run: mypy src/
        
      - name: Run security scan
        run: bandit -r src/
        
      - name: Run tests
        run: pytest tests/ --cov=src --cov-report=xml
        
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### 2. Review Templates

#### GitHub PR Template
```markdown
<!-- .github/pull_request_template.md -->
## Summary
Brief description of changes and motivation.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Review Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review performed
- [ ] Code is commented, particularly in hard-to-understand areas
- [ ] Documentation updated if needed
- [ ] No breaking changes without version bump

## Additional Notes
Any additional information for reviewers.
```

## Handling Review Conflicts

### 1. Technical Disagreements

#### Resolution Process
1. **Clarify Positions**: Ensure both sides understand the disagreement
2. **Present Evidence**: Use benchmarks, examples, or documentation
3. **Seek Third Opinion**: Involve a neutral team member
4. **Escalate if Needed**: Involve team lead or architect
5. **Document Decision**: Record the reasoning for future reference

#### Example Resolution
```markdown
**Disagreement**: Whether to use Redis or database for caching

**Resolution Process**:
1. Both sides presented performance benchmarks
2. Security team provided input on data sensitivity
3. Team architect made final decision based on system architecture
4. Decision documented in ADR (Architecture Decision Record)

**Outcome**: Use Redis for non-sensitive cache, database for sensitive data
```

### 2. Process Conflicts

#### Common Issues
- Review taking too long
- Reviewer being too nitpicky
- Author not addressing feedback
- Scope creep during review

#### Resolution Strategies
```markdown
# For slow reviews:
If review is taking longer than expected, consider:
- Breaking down the PR
- Requesting specific reviewer assignment
- Escalating to team lead if blocking critical work

# For excessive nitpicking:
Focus feedback on:
- Critical issues first
- Maintainability concerns
- Security and correctness
- Save style preferences for linting automation

# For unresponsive authors:
- Send gentle reminder after 48 hours
- Offer to pair program on complex feedback
- Consider if PR is still relevant/needed
```

### 3. Escalation Guidelines

#### When to Escalate
- Technical disagreement cannot be resolved
- Review process is blocking critical work
- Interpersonal conflicts affecting collaboration
- Security concerns need expert review

#### Escalation Process
1. **Document Issue**: Clearly describe the disagreement
2. **Involve Team Lead**: Get neutral perspective
3. **Technical Escalation**: Involve architect for design decisions
4. **Time-bound Decision**: Set deadline for resolution
5. **Document Resolution**: Record decision and reasoning

---

Effective code reviews are essential for maintaining code quality and fostering team collaboration. These guidelines ensure that our review process is thorough, constructive, and efficient while maintaining the high standards expected in the Agentic Coding Workflow project.