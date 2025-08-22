# Contributing to Agentic Coding Workflow

> **📚 Developer Resources**: For comprehensive development guidance, see **[docs/developer/README.md](docs/developer/README.md)** - the complete developer documentation hub including onboarding, setup, and best practices.

Thank you for your interest in contributing to the Agentic Coding Workflow project! This document focuses on the **contribution process and community guidelines**. For development setup, coding standards, and daily development workflows, see our comprehensive developer documentation.

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

### 🚀 **New to the Project?**

**Complete Developer Onboarding**: Follow our structured **[30-day onboarding guide](docs/developer/onboarding.md)** which includes:
- Prerequisites and setup checklist
- Development environment configuration
- First week goals and milestones
- Integration with team practices

### ⚡ **Quick Start for Contributors**

1. **Fork the repository**
2. **Setup**: Follow [Local Development Setup](docs/developer/local-development.md)
3. **Standards**: Review [Development Best Practices](docs/developer/best-practices.md)
4. **Verify**: Run `pytest tests/unit/ -v` to ensure setup works

**Essential Resources:**
- **[Developer Guide Hub](docs/developer/README.md)** - Complete navigation
- **[Local Development Setup](docs/developer/local-development.md)** - Environment configuration
- **[Testing Guide](docs/developer/testing-guide.md)** - Testing overview and requirements

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

- **Code Quality**: Follow [Development Best Practices](docs/developer/best-practices.md) and [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md)
- **Testing**: Add tests following [Testing Guide](docs/developer/testing-guide.md) and [TESTING_GUIDELINES.md](TESTING_GUIDELINES.md)
- **Documentation**: Update relevant documentation
- **Commits**: Keep commits focused and atomic

### 4. Test Your Changes

**Quick Commands**: See [Local Development Setup](docs/developer/local-development.md) for complete development workflows.

```bash
# Code quality checks
ruff format . && ruff check . --fix && mypy src/

# Run tests
pytest tests/ -v --cov=src
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
   - Follow our [Code Review Guidelines](docs/developer/code-review.md)
   - Address reviewer feedback promptly
   - Keep discussions professional and constructive
   - Be open to suggestions and alternative approaches

5. **Merging**
   - PRs require at least one approval
   - All CI checks must pass
   - Maintainers will merge approved PRs

## Coding Standards

> **📚 Complete Standards**: See [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md) for comprehensive development standards and [Development Best Practices](docs/developer/best-practices.md) for practical guidance.

### Quick Reference

**Code Quality Tools:**
- **Formatter**: `ruff format` 
- **Linter**: `ruff check`
- **Type Checker**: `mypy`

**Key Requirements:**
- Type hints for all functions
- Comprehensive docstrings for public APIs
- Descriptive naming conventions
- Single responsibility functions
- Proper error handling

**Daily Workflow**: Follow [Local Development Setup](docs/developer/local-development.md) for complete development commands and workflows.

## Testing Requirements

> **📚 Complete Testing Standards**: See [TESTING_GUIDELINES.md](TESTING_GUIDELINES.md) for comprehensive testing methodology and [Testing Guide](docs/developer/testing-guide.md) for daily testing workflows.

### Essential Requirements

**Test Coverage:**
- New features must include comprehensive tests
- Bug fixes must include regression tests
- Maintain minimum 80% test coverage

**Test Documentation Pattern:**
All tests must include Why/What/How documentation as defined in [TESTING_GUIDELINES.md](TESTING_GUIDELINES.md).

**Testing Workflow**: Follow [Testing Guide](docs/developer/testing-guide.md) for test types, tools, and daily testing commands.

## Documentation

### When to Update Documentation

Update documentation when you:
- Add new features or functionality
- Change existing behavior
- Add new configuration options
- Discover unclear or missing documentation
- Fix documentation errors

### Documentation Standards

> **📚 Complete Documentation Standards**: See [DOCUMENTATION_GUIDELINES.md](DOCUMENTATION_GUIDELINES.md) for comprehensive guidelines.

**Key Requirements:**
- Clear, concise language with runnable examples
- Why/What/How pattern for complex explanations
- Update both user and developer documentation
- Ensure all links work and references are valid

### Documentation Structure

**Developer Documentation**: [docs/developer/README.md](docs/developer/README.md) - Complete navigation
**User Documentation**: [docs/user-guide/README.md](docs/user-guide/README.md) - User workflows
**API Documentation**: [docs/api/README.md](docs/api/README.md) - Technical reference
**Standards**: Root-level .md files (DEVELOPMENT_GUIDELINES.md, TESTING_GUIDELINES.md, etc.)

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