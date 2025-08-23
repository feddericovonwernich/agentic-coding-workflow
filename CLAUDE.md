# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An automated system for monitoring, analyzing, and fixing failed GitHub pull request checks using LLM-powered analysis and the Claude Code SDK. The system orchestrates multiple workers to handle PR monitoring, failure analysis, automated fixing, and multi-agent code reviews.

## Architecture

### Core Components
- **PR Monitor Worker**: Fetches PRs from GitHub repositories on a schedule
- **Check Analyzer Worker**: Analyzes failed check logs using configurable LLMs
- **Fix Applicator Worker**: Applies automated fixes using Claude Code SDK
- **Review Orchestrator Worker**: Coordinates multi-agent PR reviews
- **Notification Service**: Handles escalations to humans via Telegram/Slack

### Data Flow
```
GitHub → Monitor → Queue → Analyzer → Router → Fix/Review/Notify → GitHub
                     ↓        ↓         ↓
                  Database (PostgreSQL/MySQL)
```

## Development Guidelines

**For comprehensive development guidance, see [Developer Documentation](docs/developer/README.md)**

### Development Workflow with Specialized Agents

**IMPORTANT**: Use these specialized agents for efficient development:

1. **Architecture Planning** (`architecture-planner` agent)
   - Use BEFORE implementing any new feature or significant refactoring
   - Creates comprehensive technical plans in `scratch-pad/` directory
   - Defines interfaces, coordination strategies, and implementation tasks

2. **Parallel Implementation Phase**
   - **ALWAYS run these agents IN PARALLEL when the plan allows:**
     - **Code Implementation** (`code-implementer` agent): Reads plans from `scratch-pad/` and implements the code
     - **Test Writing** (`test-implementor` agent): Creates comprehensive test suites based on the plan
   - Both agents work independently from the same architectural plan
   - Maximizes development efficiency through parallel execution

3. **Documentation** (`code-documentator` agent)
   - Use AFTER code and tests are complete
   - Updates or creates documentation according to project standards
   - Ensures all changes are properly documented

### Quick Reference

**Code Quality**: Follow [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md) (authoritative) and [Development Best Practices](docs/developer/best-practices.md) (practical guide)
- Human readability first
- Strong interface design using abstract base classes
- Comprehensive type hints and documentation
- Single responsibility principle

**Testing**: Follow [TESTING_GUIDELINES.md](TESTING_GUIDELINES.md) (authoritative) and [Testing Guide](docs/developer/testing-guide.md) (daily workflows)
- Every test must include Why/What/How documentation
- Use appropriate test types (unit vs integration)
- Follow testing best practices and patterns

**Code Review**: Follow [Code Review Guidelines](docs/developer/code-review.md)
- Constructive, specific feedback
- Focus on correctness, security, and maintainability
- Use provided checklists and templates

### Essential Patterns

1. **Interface Design Example**
   ```python
   class NotificationProvider(ABC):
       """Abstract base class for notification providers."""
       
       @abstractmethod
       def send(self, message: Message, priority: Priority) -> bool:
           """Send a notification message."""
           pass
   ```

2. **Test Documentation Standard**
   ```python
   def test_function_name():
       """
       Why: [Business/technical reason for this test]
       What: [Specific functionality being tested]  
       How: [Methodology and approach used]
       """
       # Test implementation
   ```

## Development Commands

```bash
# Install dependencies (when package.json/requirements.txt exists)
pip install -r requirements.txt  # Python
npm install                       # Node.js

# Run tests
pytest tests/ -v                  # Python tests
npm test                          # Node.js tests

# Code quality checks
ruff format .                    # Python formatter
ruff check .                     # Python linter and import sorting
mypy .                           # Python type checking
npm run lint                     # JavaScript/TypeScript linter

# Database operations
alembic upgrade head             # Apply migrations
alembic revision -m "message"   # Create migration

# Local development
python -m workers.monitor        # Run monitor worker
python -m workers.analyzer       # Run analyzer worker
docker-compose up                # Start all services
```

## Configuration

The system uses a YAML configuration file (`config.yaml`) with environment variable substitution:

```yaml
repositories:
  - url: "https://github.com/org/repo"
    auth_token: "${GITHUB_TOKEN}"
    
llm_providers:
  default: "anthropic"
  providers:
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
```

## Project Structure

```
/
├── workers/              # Worker implementations
│   ├── monitor.py       # PR monitoring worker
│   ├── analyzer.py      # Check analysis worker
│   ├── fixer.py        # Fix application worker
│   └── reviewer.py     # Review orchestration worker
├── services/            # Shared services
│   ├── notification/    # Notification provider implementations
│   ├── database/        # Database models and queries
│   └── queue/          # Queue abstractions
├── interfaces/          # Abstract base classes and protocols
├── config/             # Configuration schemas and loaders
├── tests/              # Test suites
└── migrations/         # Database migrations
```

## Key Design Patterns

1. **Provider Pattern**: All external integrations (LLMs, notifications) use provider interfaces
2. **Worker Pattern**: Each workflow step is a separate worker consuming from queues
3. **Repository Pattern**: Database access is abstracted through repository classes
4. **Strategy Pattern**: Different fix strategies based on failure categories

## Environment Variables

Required environment variables:
- `GITHUB_TOKEN`: GitHub API authentication
- `DATABASE_URL`: PostgreSQL/MySQL connection string
- `REDIS_URL`: Redis connection for queues
- `ANTHROPIC_API_KEY`: Claude API key
- `OPENAI_API_KEY`: OpenAI API key (if using)
- `TELEGRAM_BOT_TOKEN`: Telegram notification bot
- `TELEGRAM_CHAT_ID`: Telegram chat for notifications

## Common Tasks

### Adding a New LLM Provider
1. Create provider class implementing `LLMProvider` interface in `services/llm/`
2. Register provider in `config/providers.py`
3. Add configuration schema in `config/schemas.py`
4. Write tests with clear Why/What/How comments

### Adding a New Notification Channel
1. Implement `NotificationProvider` interface in `services/notification/`
2. Update configuration schema
3. Add provider-specific environment variables
4. Document the new channel in README.md

### Debugging Failed Checks
1. Check logs: `docker-compose logs analyzer`
2. Verify check logs are accessible via GitHub API
3. Review analysis results in database
4. Test LLM prompts manually if needed

## Security Considerations

- Never log API keys or sensitive data
- Use least-privilege GitHub tokens
- Validate all LLM responses before applying fixes
- Implement rate limiting for all external APIs
- Store secrets in environment variables only