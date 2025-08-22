# New Developer Onboarding

> **📋 Document Purpose**: This guide provides a **structured 30-day onboarding program** for new developers, with clear milestones, checklists, and progressive goals to become productive within the first week.

## Welcome to the Team

Welcome to the Agentic Coding Workflow project! This comprehensive onboarding guide will help you become a productive contributor through a structured 30-day journey.

## Prerequisites Checklist

### Required Tools and Software

- [ ] **Python 3.9+** installed with pip
- [ ] **Git** configured with your name and email
- [ ] **Docker** and Docker Compose for local development
- [ ] **PostgreSQL** client tools (optional, for database debugging)
- [ ] **Redis CLI** (optional, for queue debugging)

### Development Environment

- [ ] **Code Editor**: VS Code, PyCharm, or your preferred Python IDE
- [ ] **Terminal**: Command line access (bash, zsh, or equivalent)
- [ ] **Browser**: For accessing GitHub, documentation, and development tools

### Account Setup

- [ ] **GitHub Account** with access to the repository
- [ ] **API Keys**: Obtain required API keys (see [Environment Variables](#environment-variables))
- [ ] **Development Tools**: GitHub CLI (`gh`) for PR management (optional but recommended)

### Environment Variables

> **📚 Complete Environment Setup**: For complete environment variable setup instructions, API key creation, and configuration, see the **[Installation Guide - Environment Setup](../getting-started/installation.md#environment-setup)**.

Quick validation that your environment is set up correctly:

```bash
# Verify required environment variables are set
python -c "import os; print('✓' if os.getenv('GITHUB_TOKEN') else '✗ Missing GITHUB_TOKEN')"
python -c "import os; print('✓' if os.getenv('ANTHROPIC_API_KEY') else '✗ Missing ANTHROPIC_API_KEY')"
python -c "import os; print('✓' if os.getenv('DATABASE_URL') else '✗ Missing DATABASE_URL')"
```

## First Day Tasks

### 1. Repository Setup

```bash
# Clone the repository
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development tools
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install
```

### 2. Environment Verification

```bash
# Verify Python environment
python --version  # Should be 3.9+
pip list | grep -E "(fastapi|sqlalchemy|anthropic|openai)"

# Verify development tools
ruff --version
mypy --version
pytest --version

# Verify environment variables
python -c "import os; print('✓' if os.getenv('GITHUB_TOKEN') else '✗ Missing GITHUB_TOKEN')"
```

### 3. Database Setup

```bash
# Start local services
docker-compose up -d postgres redis

# Wait for services to be ready
docker-compose ps

# Run database migrations
alembic upgrade head

# Verify database connection
python -c "from src.database import get_session; print('✓ Database connected')"
```

### 4. First Successful Test Run

```bash
# Run all tests to verify setup
pytest tests/ -v

# Run specific test suites
pytest tests/unit/ -v          # Unit tests
pytest tests/integration/ -v   # Integration tests

# Check test coverage
pytest tests/ --cov=src --cov-report=html
```

### 5. First Successful Build

```bash
# Code quality checks
ruff format .        # Format code
ruff check . --fix   # Lint and fix issues
mypy src/           # Type checking

# Security checks
bandit -r src/      # Security linting
safety check        # Dependency vulnerability check

# All checks should pass
pre-commit run --all-files
```

### 6. Development Server Verification

```bash
# Start individual workers (in separate terminals)
python -m workers.monitor
python -m workers.analyzer
python -m workers.fixer

# Or start all services
docker-compose up

# Verify services are running
curl http://localhost:8000/health  # API health check
redis-cli ping                     # Redis connectivity
```

## First Week Goals

### Days 2-3: Understanding the System

#### Read Core Documentation
- [ ] **[System Architecture](architecture.md)** - Understand overall system design
- [ ] **[Development Best Practices](best-practices.md)** - Learn coding standards
- [ ] **[API Documentation](../api/README.md)** - Familiarize with interfaces

#### Explore the Codebase
- [ ] **Workers**: Examine `src/workers/` to understand the processing pipeline
- [ ] **Models**: Review `src/models/` for data structures
- [ ] **Services**: Study `src/services/` for external integrations
- [ ] **Tests**: Look at `tests/` to understand testing patterns

#### Development Environment Mastery
- [ ] **IDE Setup**: Configure your editor with Python plugins, type checking
- [ ] **Debugging**: Set up debugger configurations for workers and tests
- [ ] **Git Workflow**: Understand branching strategy and commit conventions

### Days 4-5: First Contribution

#### Choose a Starter Task
Look for issues labeled with:
- `good first issue` - Simple, well-defined tasks
- `documentation` - Documentation improvements
- `enhancement` - Small feature additions

#### Development Workflow
1. **Create Branch**: `git checkout -b feature/your-feature-name`
2. **Make Changes**: Follow [best practices](best-practices.md)
3. **Write Tests**: Include unit tests for new functionality
4. **Code Review**: Self-review using [checklist](code-review.md#review-checklist)
5. **Submit PR**: Create pull request with clear description

#### Success Criteria
- [ ] Code follows project conventions
- [ ] Tests pass and provide adequate coverage
- [ ] Documentation is updated if needed
- [ ] Pre-commit hooks pass
- [ ] PR receives approval and is merged

### Days 6-7: Team Integration

#### Code Review Participation
- [ ] **Review Others' PRs**: Practice using [review guidelines](code-review.md)
- [ ] **Respond to Feedback**: Learn to incorporate review suggestions
- [ ] **Ask Questions**: Engage with the team for clarification

#### Understanding Team Practices
- [ ] **Communication**: Learn team communication channels and conventions
- [ ] **Planning**: Understand how features are planned and prioritized
- [ ] **Deployment**: Learn deployment process and rollback procedures

## 30-Day Milestones

### Week 2: Independent Development
- [ ] **Feature Development**: Work on medium-complexity features independently
- [ ] **System Understanding**: Understand all major system components
- [ ] **Testing Proficiency**: Write comprehensive tests without guidance
- [ ] **Debug Effectively**: Resolve issues using project debugging tools

### Week 3: Advanced Contributions
- [ ] **Architecture Input**: Contribute to architectural discussions
- [ ] **Performance Optimization**: Identify and address performance issues
- [ ] **Security Awareness**: Apply security best practices consistently
- [ ] **Mentoring**: Help newer developers with onboarding

### Week 4: Full Integration
- [ ] **Process Improvement**: Suggest improvements to development practices
- [ ] **Documentation**: Contribute to documentation and knowledge sharing
- [ ] **Quality Assurance**: Help maintain code quality standards
- [ ] **Project Leadership**: Take ownership of features or components

## Common First-Week Issues

### Development Environment
**Issue**: Import errors or missing dependencies
```bash
# Solution: Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

**Issue**: Database connection failures
```bash
# Solution: Verify Docker services
docker-compose ps
docker-compose logs postgres
```

**Issue**: Tests failing on setup
```bash
# Solution: Check environment variables
python -c "import os; print({k:v for k,v in os.environ.items() if 'TOKEN' in k or 'KEY' in k})"
```

### Code Quality
**Issue**: Pre-commit hooks failing
```bash
# Solution: Run individual tools to identify issues
ruff check .
mypy src/
bandit -r src/
```

**Issue**: Type checking errors
```bash
# Solution: Add missing type hints
mypy src/ --show-error-codes
```

### Git Workflow
**Issue**: Merge conflicts
```bash
# Solution: Rebase against main
git fetch origin
git rebase origin/main
```

**Issue**: Commit message format
```bash
# Follow conventional commits format
git commit -m "feat: add user authentication to PR monitor"
git commit -m "fix: resolve database connection timeout issue"
git commit -m "docs: update API documentation for GitHub client"
```

## Getting Help

### Internal Resources
- **Architecture Questions**: [architecture.md](architecture.md)
- **Development Setup**: [local-development.md](local-development.md)
- **Development Issues**: [debugging.md](debugging.md)
- **Testing Issues**: [testing-guide.md](testing-guide.md)
- **Code Reviews**: [code-review.md](code-review.md)

### Team Communication
- **GitHub Issues**: For bug reports and feature requests
- **Pull Request Reviews**: For code-specific questions
- **Project Discussions**: For architectural and design questions

### Self-Help Resources
- **Documentation**: Start with [Developer Guide](README.md)
- **Error Messages**: Check [debugging guide](debugging.md)
- **Code Examples**: Look at existing implementations in `src/`

## Success Indicators

### Technical Proficiency
- [ ] Can set up development environment independently
- [ ] Understands and follows project coding standards
- [ ] Writes effective tests for new functionality
- [ ] Can debug issues using project tools and documentation

### Process Integration
- [ ] Follows git workflow and branching conventions
- [ ] Participates effectively in code reviews
- [ ] Communicates clearly about technical issues
- [ ] Contributes to documentation and knowledge sharing

### System Understanding
- [ ] Understands overall system architecture
- [ ] Can explain data flow between components
- [ ] Knows when and how to use different services
- [ ] Understands security and performance considerations

## Next Steps

After completing onboarding:
1. **Regular Development**: Use [Developer Guide](README.md) for ongoing work
2. **Advanced Topics**: Explore [API Documentation](../api/README.md) for deep dives
3. **Specialization**: Focus on specific areas (workers, integrations, testing)
4. **Leadership**: Mentor new developers and contribute to project direction

---

**Welcome to the team!** Remember that becoming productive takes time. Don't hesitate to ask questions and seek help as you learn the system.