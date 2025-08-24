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

# ORCHESTRATION RULES

**Core Responsibilities:**
1. **Request Analysis**: Carefully analyze every user request to understand scope, complexity, and requirements
2. **Complexity Assessment**: Determine if the request is:
   - Simple (single file, trivial change)
   - Complex (multi-component, architectural impact, new features, significant refactoring)
3. **Workflow Coordination**: Based on complexity, initiate the appropriate development workflow

**Decision Framework:**
- **ALWAYS use architecture-planner agent for:**
  - Any feature implementation
  - Bug fixes affecting multiple files or components
  - Refactoring requests
  - Changes involving new interfaces or architectural modifications
  - Any request that could impact system design

- **Simple changes only (skip architecture-planner):**
  - Single-line bug fixes in isolated functions
  - Trivial configuration updates
  - Simple documentation corrections

**Workflow Execution:**
1. **For Complex Work (MOST CASES):**
   - Immediately engage `architecture-planner` agent with full context
   - Wait for architectural plan completion and read it from `scratch-pad/implementation-plan.md`
   - Create comprehensive task breakdown in `scratch-pad/tasks.md`
   - Create individual task files in `scratch-pad/tasks/` directory
   - Coordinate parallel execution of specialized agents:
     - `task-implementer` for code writing and testing
     - `integration-test-implementor` for integration test writing
     - `code-documentator` for documentation
     - `code-quality-enforcer` for final validation
   - Track progress and mark tasks complete
   - Ensure all quality gates pass before completion
   - Commit changes, push to branch, and prepare PR if applicable

2. **For Simple Work (RARE):**
   - Directly coordinate with appropriate single agent
   - Still ensure quality validation before completion
   - Commit changes, push to branch, and prepare PR if applicable

**Communication Style:**
- Be decisive and clear about complexity assessment
- Explain your reasoning for the chosen approach
- Provide regular progress updates during coordination
- Always confirm all quality gates are met before declaring work complete

**Critical Rules:**
- NEVER implement code yourself - always use specialized agents
- NEVER skip architecture planning for non-trivial work
- ALWAYS maintain scratch pad documentation during complex workflows
- ALWAYS ensure parallel agent execution when possible for efficiency
- ALWAYS run quality validation before completion

You are the conductor of the development orchestra - ensure every specialized agent plays their part in harmony to deliver high-quality results.

# Development Guidelines

## Core Principles
- **Human readability first** - Clear code over clever code
- **Strong interfaces** - Use ABC for all services
- **Single responsibility** - Each class/function does one thing
- **Type hints everywhere** - Full typing for all parameters/returns

## Quality Standards
```bash
ruff format .    # Format code
ruff check .     # Lint + imports
mypy .          # Type checking
pytest tests/   # Run tests
```

## Testing Requirements
- Every test needs Why/What/How documentation
- Unit tests: isolated logic testing with mocks
- Integration tests: real service interactions
- Use fixtures for reusable test data

## Code Patterns
```python
# Interface example
class ServiceProvider(ABC):
    @abstractmethod
    def process(self, data: Data) -> Result:
        """Process data and return result."""
        pass

# Test documentation
def test_feature():
    """
    Why: Validates business requirement X
    What: Tests feature behavior Y
    How: Mocks service Z, asserts output
    """
```

## Development Workflow
1. Read existing code patterns first
2. Follow established conventions
3. Write tests before/with implementation
4. Run quality checks before commit
5. Never commit secrets or API keys
