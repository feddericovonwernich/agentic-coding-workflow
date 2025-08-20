# Contributing to Agentic Coding Workflow

Thank you for your interest in contributing to the Agentic Coding Workflow project! This document provides guidelines and instructions for contributing to this repository.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Process](#development-process)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)
- [Documentation](#documentation)
- [Issue Reporting](#issue-reporting)
- [Community](#community)

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- Python 3.11 or higher
- Docker (for running tests with testcontainers)
- Git configured with your GitHub account
- A fork of this repository

### Setting Up Your Development Environment

1. **Fork and Clone the Repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/agentic-coding-workflow.git
   cd agentic-coding-workflow
   ```

2. **Create a Virtual Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # Development dependencies
   ```

4. **Set Up Pre-commit Hooks**
   ```bash
   pre-commit install
   ```

5. **Run Tests to Verify Setup**
   ```bash
   pytest tests/unit/ -v  # Quick unit tests
   pytest tests/ -v       # All tests (requires Docker)
   ```

## Development Process

### 1. Find or Create an Issue

- Check existing [issues](https://github.com/feddericovonwernich/agentic-coding-workflow/issues) for something you'd like to work on
- If you have a new idea, create an issue first to discuss it
- Comment on the issue to indicate you're working on it

### 2. Create a Feature Branch

```bash
git checkout -b feature/issue-number-brief-description
# Example: git checkout -b feature/42-add-github-webhook-support
```

### 3. Make Your Changes

- Write clean, readable code following our [Development Guidelines](DEVELOPMENT.md)
- Add tests for new functionality following our [Testing Guidelines](TESTING.md)
- Update documentation as needed
- Keep commits focused and atomic

### 4. Test Your Changes

```bash
# Run formatters
ruff format .
ruff check . --fix

# Run type checking
mypy src/

# Run tests
pytest tests/ -v

# Check test coverage
pytest tests/ --cov=src --cov-report=html
```

### 5. Commit Your Changes

Follow our commit message convention:

```
type: Brief description (max 50 chars)

Longer explanation if needed (wrap at 72 chars).
Explain the problem this commit solves and why
this approach was chosen.

Fixes #42
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions or changes
- `chore`: Maintenance tasks
- `perf`: Performance improvements

## Submitting Changes

### Pull Request Process

1. **Push Your Branch**
   ```bash
   git push origin feature/issue-number-brief-description
   ```

2. **Create a Pull Request**
   - Use a clear, descriptive title
   - Reference the issue number (e.g., "Fixes #42")
   - Provide a comprehensive description of changes
   - Include screenshots for UI changes
   - List any breaking changes

3. **Pull Request Template**
   ```markdown
   ## Summary
   Brief description of changes

   ## Motivation and Context
   Why is this change required? What problem does it solve?
   Fixes #(issue number)

   ## Changes Made
   - Change 1
   - Change 2
   - Change 3

   ## Testing
   - [ ] Unit tests pass
   - [ ] Integration tests pass
   - [ ] Manual testing completed

   ## Checklist
   - [ ] My code follows the project's style guidelines
   - [ ] I have performed a self-review of my code
   - [ ] I have commented my code where necessary
   - [ ] I have updated the documentation
   - [ ] My changes generate no new warnings
   - [ ] I have added tests that prove my fix/feature works
   - [ ] New and existing unit tests pass locally
   - [ ] Any dependent changes have been merged
   ```

4. **Code Review**
   - Address reviewer feedback promptly
   - Keep discussions professional and constructive
   - Be open to suggestions and alternative approaches
   - Update your PR based on feedback

5. **Merging**
   - PRs require at least one approval
   - All CI checks must pass
   - Maintainers will merge approved PRs

## Coding Standards

### Python Code Style

We use automated tools to ensure consistent code style:

- **Formatter**: `ruff format` (Black-compatible)
- **Linter**: `ruff check` (includes flake8, isort, and more)
- **Type Checker**: `mypy` with strict settings

### Key Guidelines

1. **Type Hints**: All functions must have type annotations
2. **Docstrings**: All public functions and classes need comprehensive docstrings
3. **Comments**: Explain "why" not "what" - code should be self-documenting
4. **Naming**: Use descriptive names (prefer `calculate_repository_health_score` over `calc_score`)
5. **Functions**: Keep functions small and focused on a single responsibility
6. **Error Handling**: Use custom exceptions and provide helpful error messages

For detailed guidelines, see [DEVELOPMENT.md](DEVELOPMENT.md).

## Testing Requirements

### Test Coverage

- New features must include comprehensive tests
- Bug fixes must include regression tests
- Maintain or improve overall test coverage (minimum 80%)

### Test Structure

Every test must include the Why/What/How documentation pattern:

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

For detailed testing guidelines, see [TESTING.md](TESTING.md).

## Documentation

### When to Update Documentation

Update documentation when you:
- Add new features or functionality
- Change existing behavior
- Add new configuration options
- Discover unclear or missing documentation
- Fix documentation errors

### Documentation Standards

- Use clear, concise language
- Include code examples where helpful
- Keep documentation close to code (docstrings for API docs)
- Update both user and developer documentation as needed
- Ensure all links work and references are valid

### Documentation Locations

- `README.md`: Project overview and quick start
- `DEVELOPMENT.md`: Development guidelines and best practices
- `TESTING.md`: Testing guidelines and patterns
- `docs/`: Detailed technical documentation
- Code docstrings: API documentation

## Issue Reporting

### Creating Good Issues

When creating an issue, include:

1. **Clear Title**: Summarize the issue in one line
2. **Description**: Detailed explanation of the problem or feature
3. **Steps to Reproduce** (for bugs):
   - Environment details (OS, Python version, etc.)
   - Minimal code example
   - Expected vs actual behavior
4. **Possible Solution**: If you have ideas on how to fix/implement
5. **Additional Context**: Screenshots, logs, related issues

### Issue Labels

- `bug`: Something isn't working
- `enhancement`: New feature or request
- `documentation`: Documentation improvements
- `good first issue`: Good for newcomers
- `help wanted`: Extra attention needed
- `question`: Further information requested

## Community

### Getting Help

- Check existing documentation and issues first
- Ask questions in issue discussions
- Be patient and respectful when seeking help

### Helping Others

- Answer questions in issues when you can
- Review pull requests
- Improve documentation based on common questions
- Share your experience with the project

## Recognition

Contributors are recognized in several ways:
- Listed in pull request history
- Mentioned in release notes for significant contributions
- Added to CONTRIBUTORS.md for ongoing contributions

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

## Questions?

If you have questions about contributing, please:
1. Check existing documentation
2. Search closed issues for similar questions
3. Create a new issue with the `question` label

Thank you for contributing to Agentic Coding Workflow!