# Documentation Best Practices

This guide defines the documentation standards and best practices for the Agentic Coding Workflow project. It serves as a reference for both human developers and AI agents when creating, modifying, or reviewing documentation.

## Table of Contents

- [Core Principles](#core-principles)
- [Documentation Types](#documentation-types)
- [Writing Standards](#writing-standards)
- [Code Documentation](#code-documentation)
- [API Documentation](#api-documentation)
- [Architecture Documentation](#architecture-documentation)
- [User Documentation](#user-documentation)
- [Documentation Maintenance](#documentation-maintenance)
- [AI Agent Guidelines](#ai-agent-guidelines)
- [Review Checklist](#review-checklist)

## Core Principles

### 1. Documentation as Code

- **Version Control**: All documentation lives in the repository alongside code
- **Review Process**: Documentation changes go through the same PR review process
- **Testing**: Documentation examples should be tested when possible
- **Automation**: Generate documentation from code where appropriate

### 2. Audience-First Approach

Documentation should be written for its intended audience:

- **End Users**: Focus on task completion, avoid technical jargon
- **Developers**: Include technical details, architectural decisions
- **AI Agents**: Provide structured, unambiguous instructions
- **Operators**: Emphasize deployment, monitoring, troubleshooting

### 3. Progressive Disclosure

- Start with the most common use case
- Layer complexity gradually
- Provide links to detailed information
- Keep introductory sections concise

### 4. Single Source of Truth

- Avoid duplicating information across files
- Use references and links instead of copying
- Centralize configuration documentation
- Keep README focused on overview and quick start

## Documentation Types

### README.md

**Purpose**: Project overview and quick start guide

**Must Include**:
- Project description (1-2 paragraphs)
- Key features list
- Installation instructions
- Quick start example
- Links to detailed documentation
- License and contribution info

**Must NOT Include**:
- Detailed API documentation
- Complex configuration options
- Internal implementation details
- Lengthy tutorials

### CONTRIBUTING.md

**Purpose**: Guide for potential contributors

**Must Include**:
- Development environment setup
- Code style guidelines
- Testing requirements
- PR process and standards
- Issue reporting guidelines
- Communication channels

### API Documentation

**Purpose**: Complete reference for all public interfaces

**Must Include**:
- Function/method signatures with types
- Parameter descriptions and constraints
- Return value specifications
- Error conditions and exceptions
- Usage examples for each endpoint
- Authentication requirements

### Architecture Documentation

**Purpose**: System design and technical decisions

**Must Include**:
- High-level system overview
- Component interactions
- Data flow diagrams
- Technology choices and rationale
- Scaling considerations
- Security model

## Writing Standards

### Language and Tone

1. **Clarity Over Cleverness**
   - Use simple, direct language
   - Avoid idioms and cultural references
   - Define technical terms on first use
   - Write for non-native English speakers

2. **Active Voice**
   ```markdown
   ✅ Good: The system validates input before processing
   ❌ Avoid: Input is validated by the system before being processed
   ```

3. **Present Tense**
   ```markdown
   ✅ Good: The function returns an error if validation fails
   ❌ Avoid: The function will return an error if validation fails
   ```

### Structure and Formatting

1. **Headings Hierarchy**
   - Use descriptive headings
   - Maintain consistent hierarchy (don't skip levels)
   - Keep headings concise (< 60 characters)
   - Use sentence case, not Title Case

2. **Lists and Tables**
   - Use bullet points for unordered information
   - Use numbered lists for sequential steps
   - Use tables for comparing options or presenting data
   - Keep list items parallel in structure

3. **Code Examples**
   - Always specify the language in code blocks
   - Include imports and context
   - Show both successful and error cases
   - Keep examples runnable and self-contained

   ```python
   # ✅ Good: Complete, runnable example
   from workers.analyzer import CheckAnalyzer
   from models import CheckResult
   
   analyzer = CheckAnalyzer(config={'timeout': 30})
   result = analyzer.analyze(check_log="ESLint failed: Missing semicolon")
   
   if result.category == 'lint':
       print(f"Lint issue detected with {result.confidence}% confidence")
   ```

   ```python
   # ❌ Avoid: Incomplete example without context
   result = analyze(log)  # What is analyze? What is log?
   ```

### Visual Elements

1. **Diagrams**
   - Use Mermaid for version-controlled diagrams
   - Include ASCII diagrams for simple flows
   - Provide alt text for accessibility
   - Keep diagrams focused on one concept

2. **Screenshots**
   - Only include when absolutely necessary
   - Annotate with callouts for key areas
   - Provide text alternatives
   - Update when UI changes

## Code Documentation

### Python Docstrings

Follow Google-style docstrings with type hints:

```python
def analyze_check_failure(
    log_content: str,
    check_type: CheckType,
    context: Optional[Dict[str, Any]] = None
) -> AnalysisResult:
    """Analyze a failed CI check and categorize the failure.
    
    Processes the check log to identify failure patterns and determine
    whether the issue can be automatically fixed or requires human review.
    
    Args:
        log_content: Raw log output from the failed check
        check_type: Type of check that failed (lint, test, build, etc.)
        context: Additional context about the PR and repository
        
    Returns:
        AnalysisResult containing:
            - category: Failure category (lint, test, build, config)
            - confidence: Confidence score (0-100)
            - suggested_fix: Optional fix recommendation
            - requires_human: Whether human intervention is needed
            
    Raises:
        InvalidLogFormatError: If log_content cannot be parsed
        AnalysisTimeoutError: If analysis exceeds timeout threshold
        
    Example:
        >>> result = analyze_check_failure(
        ...     log_content="ESLint: Missing semicolon at line 42",
        ...     check_type=CheckType.LINT
        ... )
        >>> print(result.category)
        'lint'
        >>> print(result.confidence)
        95
    """
    # Implementation
```

### Inline Comments

```python
# ✅ Good: Explains WHY, not WHAT
# Use exponential backoff to avoid overwhelming the API during outages
retry_delay = min(2 ** attempt * base_delay, max_delay)

# ❌ Avoid: Explains what the code already says
# Multiply 2 to the power of attempt by base_delay
retry_delay = min(2 ** attempt * base_delay, max_delay)
```

### Type Hints and Annotations

Always include type hints for:
- Function parameters
- Return values
- Class attributes
- Complex data structures

```python
from typing import Dict, List, Optional, Union, Tuple
from dataclasses import dataclass

@dataclass
class CheckAnalysis:
    """Result of analyzing a failed check."""
    category: str
    confidence: float
    fixes: List[Fix]
    metadata: Dict[str, Any]
    
def process_checks(
    checks: List[Check],
    strategy: Optional[Strategy] = None
) -> Tuple[List[CheckAnalysis], List[str]]:
    """Process multiple checks and return analyses and errors."""
    pass
```

## API Documentation

### REST API Endpoints

Document each endpoint with:

```markdown
### Get Pull Request Analysis

Retrieve the analysis results for a specific pull request.

**Endpoint**: `GET /api/v1/pulls/{owner}/{repo}/{pull_number}/analysis`

**Authentication**: Required (Bearer token)

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| owner | string | Yes | Repository owner |
| repo | string | Yes | Repository name |
| pull_number | integer | Yes | Pull request number |
| include_history | boolean | No | Include historical analyses (default: false) |

**Response**:
```json
{
  "pull_number": 123,
  "analyses": [
    {
      "check_name": "eslint",
      "status": "failed",
      "category": "lint",
      "confidence": 95,
      "fixable": true,
      "suggested_fix": {
        "type": "auto_fix",
        "description": "Add missing semicolons"
      }
    }
  ],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid or missing authentication token
- `404 Not Found`: Repository or pull request not found
- `429 Too Many Requests`: Rate limit exceeded

**Example**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.example.com/api/v1/pulls/myorg/myrepo/123/analysis"
```
```

### GraphQL Schema

```graphql
"""
Represents a pull request analysis result.
"""
type PullRequestAnalysis {
  """Unique identifier for the analysis."""
  id: ID!
  
  """The pull request being analyzed."""
  pullRequest: PullRequest!
  
  """List of check analyses."""
  checkAnalyses: [CheckAnalysis!]!
  
  """Whether all checks can be automatically fixed."""
  fullyFixable: Boolean!
  
  """Timestamp when analysis was performed."""
  analyzedAt: DateTime!
}
```

## Architecture Documentation

### System Design Documents

Structure architecture docs with:

1. **Overview**
   - Problem statement
   - Solution approach
   - Key design decisions

2. **Components**
   - Component responsibilities
   - Interfaces and contracts
   - Dependencies

3. **Data Flow**
   - Input sources
   - Processing stages
   - Output destinations

4. **Diagrams**
   ```mermaid
   graph LR
       A[GitHub Webhook] --> B[PR Monitor]
       B --> C[Message Queue]
       C --> D[Check Analyzer]
       D --> E{Fixable?}
       E -->|Yes| F[Fix Applicator]
       E -->|No| G[Human Review]
       F --> H[Create Fix PR]
       G --> I[Send Notification]
   ```

5. **Trade-offs**
   - Alternatives considered
   - Pros and cons
   - Decision rationale

### Decision Records (ADRs)

```markdown
# ADR-001: Use Event-Driven Architecture for Worker Communication

## Status
Accepted

## Context
Workers need to communicate analysis results and trigger downstream processes.
Options include direct API calls, shared database, or message queues.

## Decision
Use message queues (Redis/RabbitMQ) for worker communication.

## Consequences
### Positive
- Decoupled components
- Better fault tolerance
- Easy to scale workers independently

### Negative
- Additional infrastructure complexity
- Potential message ordering issues
- Need for dead letter queue handling

## Alternatives Considered
1. **Direct API Calls**: Rejected due to tight coupling
2. **Shared Database**: Rejected due to polling overhead
```

## User Documentation

### Tutorials and Guides

Structure tutorials with:

1. **Learning Objectives**
   - What users will learn
   - Prerequisites
   - Time estimate

2. **Step-by-Step Instructions**
   ```markdown
   ## Setting Up Automated PR Fixes
   
   This tutorial shows you how to configure automatic fixing for lint issues.
   
   **Prerequisites**:
   - GitHub repository with CI/CD configured
   - Admin access to repository settings
   - Claude API key
   
   **Time**: 15 minutes
   
   ### Step 1: Install the GitHub App
   
   1. Navigate to the [GitHub Marketplace](https://github.com/marketplace)
   2. Search for "Agentic Coding Workflow"
   3. Click "Install" and select your repository
   
   ### Step 2: Configure Webhooks
   
   1. Go to Settings → Webhooks in your repository
   2. Add webhook URL: `https://api.example.com/webhooks/github`
   3. Select events: "Pull requests" and "Check runs"
   ```

3. **Troubleshooting**
   - Common issues and solutions
   - Debug commands
   - Where to find logs

### Configuration Reference

```yaml
# config.yaml - Complete configuration reference

# Repository configuration
repositories:
  - url: "https://github.com/org/repo"  # Required: Repository URL
    auth_token: "${GITHUB_TOKEN}"        # Required: GitHub PAT or App token
    
    # Check configuration (optional)
    checks:
      enabled: true                       # Enable check monitoring (default: true)
      include_patterns:                   # Check names to include (default: all)
        - "eslint"
        - "pytest"
      exclude_patterns:                   # Check names to exclude
        - "security-scan"
      
    # Auto-fix configuration (optional)
    auto_fix:
      enabled: true                       # Enable automatic fixes (default: false)
      categories:                         # Categories to auto-fix
        - "lint"
        - "formatting"
      confidence_threshold: 80           # Min confidence for auto-fix (0-100)
      max_attempts: 3                    # Max fix attempts per PR

# LLM provider configuration
llm_providers:
  default: "anthropic"                   # Default provider to use
  
  providers:
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"    # Required: API key
      model: "claude-3-opus-20240229"    # Model to use
      max_tokens: 4096                   # Max response tokens
      temperature: 0.2                   # Response randomness (0-1)
```

## Documentation Maintenance

### Regular Reviews

1. **Quarterly Reviews**
   - Check for outdated information
   - Update version-specific content
   - Review and incorporate feedback
   - Verify all links still work

2. **On Each Release**
   - Update CHANGELOG.md
   - Review README quickstart
   - Update API documentation
   - Check example code still works

### Documentation Testing

```python
# tests/test_documentation.py
import doctest
import os
import markdown
from pathlib import Path

def test_code_examples():
    """
    Why: Ensure documentation code examples remain valid and runnable
    
    What: Tests all Python code blocks in markdown files can be executed
    
    How: Extracts code blocks from .md files and attempts execution
    """
    for md_file in Path(".").glob("**/*.md"):
        with open(md_file) as f:
            content = f.read()
            
        # Extract and test Python code blocks
        code_blocks = extract_python_blocks(content)
        for block in code_blocks:
            try:
                compile(block, md_file, 'exec')
            except SyntaxError as e:
                pytest.fail(f"Invalid Python in {md_file}: {e}")

def test_links():
    """
    Why: Broken links frustrate users and damage documentation credibility
    
    What: Verifies all internal links in documentation are valid
    
    How: Parses markdown files and checks that linked files exist
    """
    # Implementation
```

## AI Agent Guidelines

### When Creating Documentation

1. **Analyze Existing Patterns**
   ```python
   # Before creating new documentation:
   # 1. Review existing documentation structure
   # 2. Match the style and format
   # 3. Use consistent terminology
   # 4. Follow established patterns
   ```

2. **Include Concrete Examples**
   - Every concept needs an example
   - Examples should be complete and runnable
   - Include both success and failure cases
   - Test examples before committing

3. **Structure for Scannability**
   - Use descriptive headings
   - Include table of contents for long documents
   - Put most important information first
   - Use formatting to highlight key points

### When Modifying Documentation

1. **Preserve Existing Structure**
   - Don't reorganize without explicit request
   - Maintain heading hierarchy
   - Keep formatting consistent
   - Update table of contents if present

2. **Update Cross-References**
   - Check for references to modified sections
   - Update links if paths change
   - Maintain bidirectional links
   - Update index/overview pages

3. **Version-Specific Changes**
   ```markdown
   <!-- Mark version-specific content -->
   > **Note**: This feature requires version 2.0 or later
   
   <!-- Or use compatibility tables -->
   | Feature | v1.x | v2.x | v3.x |
   |---------|------|------|------|
   | Auto-fix | ❌ | ✅ | ✅ |
   | Multi-repo | ❌ | ❌ | ✅ |
   ```

### When Reviewing Documentation

Check for:

1. **Completeness**
   - All parameters documented
   - All error conditions listed
   - Examples provided
   - Prerequisites stated

2. **Accuracy**
   - Code examples work
   - Configuration is valid
   - Links are not broken
   - Version info is current

3. **Clarity**
   - Unambiguous instructions
   - Technical terms defined
   - Logical flow
   - Appropriate detail level

## Review Checklist

### Before Committing Documentation

- [ ] **Accuracy**
  - [ ] All technical information is correct
  - [ ] Code examples are tested and working
  - [ ] Configuration samples are valid
  - [ ] Version numbers are current

- [ ] **Completeness**
  - [ ] All new features are documented
  - [ ] All parameters have descriptions
  - [ ] Error conditions are documented
  - [ ] Examples cover common use cases

- [ ] **Consistency**
  - [ ] Terminology matches project conventions
  - [ ] Formatting follows project standards
  - [ ] Style matches existing documentation
  - [ ] Cross-references are updated

- [ ] **Clarity**
  - [ ] Language is clear and simple
  - [ ] Structure is logical
  - [ ] Headers are descriptive
  - [ ] Examples illustrate concepts well

- [ ] **Maintenance**
  - [ ] No duplicate information
  - [ ] Links to detailed docs where appropriate
  - [ ] Automated generation where possible
  - [ ] Update tracking in CHANGELOG.md

### Documentation Quality Metrics

Track these metrics to improve documentation:

1. **Completeness Score**
   - Public APIs documented: __%
   - Configuration options documented: __%
   - Error messages documented: __%

2. **Freshness Score**
   - Days since last update: __
   - Outdated version references: __
   - Broken links: __

3. **Usability Score**
   - Time to first successful API call: __ minutes
   - Support tickets about documentation: __ per month
   - Documentation-related PRs: __ per quarter

## Examples of Excellence

### Great Function Documentation

```python
def apply_fix(
    pr: PullRequest,
    fix: Fix,
    strategy: FixStrategy = FixStrategy.CONSERVATIVE,
    dry_run: bool = False
) -> FixResult:
    """Apply an automated fix to a pull request.
    
    Attempts to automatically fix issues identified in PR checks by creating
    a new commit with the necessary changes. The fix is applied according to
    the specified strategy, with safeguards to prevent breaking changes.
    
    The function performs these steps:
    1. Validates the fix is applicable to the current PR state
    2. Creates a working branch from the PR head
    3. Applies the fix changes
    4. Runs validation checks on the fixed code
    5. Commits and pushes if validation passes
    
    Args:
        pr: Pull request to fix, must be open and have failed checks
        fix: Fix to apply, generated by CheckAnalyzer
        strategy: How aggressively to apply fixes
            - CONSERVATIVE: Only apply high-confidence fixes (default)
            - BALANCED: Apply medium and high confidence fixes
            - AGGRESSIVE: Apply all suggested fixes
        dry_run: If True, simulate the fix without making changes
        
    Returns:
        FixResult with:
            - success: Whether the fix was applied successfully
            - commit_sha: SHA of the fix commit (if success=True)
            - validation_results: Output from post-fix validation
            - error: Error message if fix failed
            
    Raises:
        PRNotOpenError: If the PR is closed or merged
        FixNotApplicableError: If the fix cannot be applied to current code
        ValidationFailedError: If the fixed code fails validation
        GitHubAPIError: If GitHub API calls fail
        
    Example:
        >>> # Fix lint issues in a PR
        >>> pr = github.get_pull(owner="myorg", repo="myrepo", number=123)
        >>> fix = analyzer.suggest_fix(pr.failed_checks[0])
        >>> result = apply_fix(pr, fix, strategy=FixStrategy.CONSERVATIVE)
        >>> if result.success:
        ...     print(f"Fixed in commit {result.commit_sha}")
        ... else:
        ...     print(f"Fix failed: {result.error}")
        
    Note:
        This function requires write access to the repository. The GitHub
        token must have 'repo' scope for private repositories or 'public_repo'
        scope for public repositories.
        
    See Also:
        - :func:`analyze_check`: Generates fixes from check failures
        - :class:`FixStrategy`: Available fix strategies
        - :doc:`/guides/auto-fixing`: Tutorial on setting up auto-fixing
    """
    # Implementation
```

### Great README Structure

```markdown
# Agentic Coding Workflow

Automated system for monitoring, analyzing, and fixing failed GitHub pull request checks using LLM-powered analysis and the Claude Code SDK.

## ✨ Key Features

- 🔍 **Automatic PR Monitoring** - Continuously monitors repositories for failed checks
- 🤖 **Intelligent Analysis** - Uses LLMs to understand failure root causes
- 🔧 **Automated Fixes** - Applies fixes for common issues like linting and formatting
- 👥 **Multi-Agent Reviews** - Orchestrates multiple AI agents for code review
- 📢 **Smart Notifications** - Escalates to humans only when necessary

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/agentic-coding-workflow
cd agentic-coding-workflow

# Install dependencies
pip install -r requirements.txt

# Configure (see Configuration section)
cp config.example.yaml config.yaml
# Edit config.yaml with your settings

# Run the system
docker-compose up
```

## 📖 Documentation

- [Installation Guide](docs/installation.md) - Detailed setup instructions
- [Configuration Reference](docs/configuration.md) - All configuration options
- [API Documentation](docs/api.md) - REST API reference
- [Development Guide](DEVELOPMENT.md) - Contributing and development setup
- [Architecture Overview](docs/architecture.md) - System design and components

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## 📜 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.
```

## Conclusion

Good documentation is essential for project success. It should be:

- **Accurate**: Technically correct and up-to-date
- **Complete**: Covers all necessary information
- **Clear**: Easy to understand for the target audience
- **Maintainable**: Easy to update as the project evolves
- **Discoverable**: Well-organized and searchable

Remember: Documentation is written once but read many times. Invest the time to make it excellent.

When in doubt, ask yourself:
1. Would a new developer understand this?
2. Would an AI agent be able to follow these instructions?
3. Will this still be clear in six months?
4. Can someone use this without asking questions?

If the answer to any of these is "no", the documentation needs improvement.