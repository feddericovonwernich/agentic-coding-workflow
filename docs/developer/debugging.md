# Developer Troubleshooting and Debugging Guide

> **📚 Navigation**: This guide covers **development workflow troubleshooting and debugging**. For testing issues, see **[Testing Troubleshooting](../testing/troubleshooting.md)**. For configuration problems, see **[Configuration Troubleshooting](../config/troubleshooting.md)**. For environment setup, see **[Installation Troubleshooting](../getting-started/installation.md#troubleshooting)**.

This guide helps developers troubleshoot issues specific to the development workflow, IDE setup, debugging tools, and local development environment problems.

## Table of Contents

- [Development Environment Issues](#development-environment-issues)
- [IDE Configuration Problems](#ide-configuration-problems)
- [Debugging Setup Issues](#debugging-setup-issues)
- [Local Development Workflow](#local-development-workflow)
- [Code Quality Tool Issues](#code-quality-tool-issues)
- [Development Server Problems](#development-server-problems)
- [Git Workflow Issues](#git-workflow-issues)
- [Getting Help](#getting-help)

## Development Environment Issues

### Issue: Python Path and Import Problems

**Symptoms:**
- `ImportError: No module named 'src'` in development
- IDE can't find modules that exist
- Code completion not working for project modules

**Solutions:**

1. **Install in development mode:**
   ```bash
   # This adds the project to Python path
   pip install -e .
   
   # Verify it's installed
   pip show agentic-coding-workflow | grep Location
   ```

2. **Configure IDE Python path:**
   ```json
   // For VS Code - add to .vscode/settings.json
   {
     "python.autoComplete.extraPaths": ["./src"],
     "python.analysis.extraPaths": ["./src"]
   }
   ```

3. **Set PYTHONPATH for development:**
   ```bash
   # Add to development environment
   export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
   ```

### Issue: Virtual Environment Problems

**Symptoms:**
- Wrong Python interpreter being used
- Packages installed globally instead of in venv
- IDE not detecting virtual environment

**Solutions:**

1. **Recreate virtual environment:**
   ```bash
   # Remove existing environment
   deactivate 2>/dev/null || true
   rm -rf .venv
   
   # Create new environment
   python -m venv .venv
   source .venv/bin/activate
   
   # Reinstall dependencies
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   pip install -e .
   ```

## IDE Configuration Problems

### Issue: VS Code Python Extension Issues

**Symptoms:**
- No code completion or IntelliSense
- Linting not working
- Debugging not available

**Solutions:**

1. **Configure VS Code workspace settings:**
   ```json
   // .vscode/settings.json
   {
     "python.defaultInterpreterPath": "./.venv/bin/python",
     "python.terminal.activateEnvironment": true,
     "python.linting.enabled": true,
     "python.linting.ruffEnabled": true,
     "python.formatting.provider": "black",
     "python.testing.pytestEnabled": true,
     "python.testing.pytestArgs": ["tests/"]
   }
   ```

## Debugging Setup Issues

### Issue: Python Debugger Not Working

**Symptoms:**
- Breakpoints not being hit
- Debugger fails to attach
- No debug output or variables

**Solutions:**

1. **VS Code debug configuration:**
   ```json
   // .vscode/launch.json
   {
     "version": "0.2.0",
     "configurations": [
       {
         "name": "Debug Worker",
         "type": "python",
         "request": "launch",
         "module": "workers.monitor",
         "env": {
           "PYTHONPATH": "${workspaceFolder}/src"
         },
         "envFile": "${workspaceFolder}/.env",
         "console": "integratedTerminal"
       }
     ]
   }
   ```

2. **Add debugging to Python code:**
   ```python
   # Add breakpoint in code
   import pdb; pdb.set_trace()
   
   # Or use built-in breakpoint() (Python 3.7+)
   breakpoint()
   ```

## Local Development Workflow

### Issue: Hot Reload Not Working

**Symptoms:**
- Changes not reflected without restart
- Workers not reloading on code changes
- Development server needs manual restart

**Solutions:**

1. **Use development server with auto-reload:**
   ```bash
   # For FastAPI development
   uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
   
   # For workers with auto-restart
   watchdog --patterns="*.py" --recursive src/ python -m workers.monitor
   ```

### Issue: Database Reset for Development

**Symptoms:**
- Need to reset database frequently
- Schema changes not applied
- Test data conflicts with development

**Solutions:**

1. **Quick database reset script:**
   ```bash
   #!/bin/bash
   # scripts/reset_dev_db.sh
   
   echo "Resetting development database..."
   
   # Drop and recreate database
   python -c "
   from src.database import engine, Base
   import asyncio
   
   async def reset_db():
       async with engine.begin() as conn:
           await conn.run_sync(Base.metadata.drop_all)
           await conn.run_sync(Base.metadata.create_all)
       print('Database reset complete')
   
   asyncio.run(reset_db())
   "
   
   echo "Database reset complete"
   ```

## Code Quality Tool Issues

### Issue: Ruff Configuration Problems

**Symptoms:**
- Inconsistent formatting between developers
- Ruff rules conflicts with existing code
- IDE and command line showing different results

**Solutions:**

1. **Configure ruff properly:**
   ```toml
   # pyproject.toml
   [tool.ruff]
   line-length = 88
   target-version = "py311"
   exclude = [
       ".git",
       "__pycache__",
       "migrations/",
       ".venv"
   ]
   
   [tool.ruff.lint]
   select = [
       "E",  # pycodestyle errors
       "W",  # pycodestyle warnings
       "F",  # Pyflakes
       "I",  # isort
   ]
   ```

2. **Fix common ruff issues:**
   ```bash
   # Format all code
   ruff format .
   
   # Fix auto-fixable issues
   ruff check . --fix
   ```

### Issue: MyPy Type Checking Problems

**Symptoms:**
- Type errors that seem incorrect
- Missing type stubs for dependencies
- Inconsistent type checking results

**Solutions:**

1. **Install type stubs:**
   ```bash
   # Install missing stubs
   pip install types-requests
   pip install types-redis
   pip install types-PyYAML
   
   # Check what stubs are needed
   mypy src/ --install-types
   ```

## Development Server Problems

### Issue: Port Conflicts During Development

**Symptoms:**
- `Address already in use` errors
- Services failing to start
- Conflicts between development instances

**Solutions:**

1. **Use different ports for development:**
   ```yaml
   # config/development.yaml
   monitoring:
     metrics:
       port: 8080
     health_checks:
       port: 8081
   
   api:
     port: 8000
   ```

2. **Kill conflicting processes:**
   ```bash
   # Find and kill processes using ports
   lsof -ti:8080 | xargs kill -9
   lsof -ti:8081 | xargs kill -9
   ```

## Git Workflow Issues

### Issue: Commit Hooks Failing

**Symptoms:**
- Pre-commit hooks prevent commits
- Formatting changes not applied automatically
- Different results between developers

**Solutions:**

1. **Install and configure pre-commit:**
   ```yaml
   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/pre-commit/pre-commit-hooks
       rev: v4.4.0
       hooks:
         - id: trailing-whitespace
         - id: end-of-file-fixer
         - id: check-yaml
     
     - repo: https://github.com/astral-sh/ruff-pre-commit
       rev: v0.1.6
       hooks:
         - id: ruff
           args: [--fix, --exit-non-zero-on-fix]
         - id: ruff-format
   ```

2. **Fix pre-commit issues:**
   ```bash
   # Install pre-commit hooks
   pre-commit install
   
   # Run on all files
   pre-commit run --all-files
   
   # Skip hooks temporarily (if needed)
   git commit -m "message" --no-verify
   ```

## Getting Help

### Development Environment Diagnostic

```bash
#!/bin/bash
# scripts/dev_diagnostic.sh

echo "=== Development Environment Diagnostic ==="
echo "Generated: $(date)"
echo

echo "--- Python Environment ---"
which python
python --version
echo "Virtual env: $VIRTUAL_ENV"

echo -e "\n--- Project Setup ---"
pip show agentic-coding-workflow || echo "Project not installed in development mode"
ls -la src/ | head -5

echo -e "\n--- Development Tools ---"
ruff --version 2>/dev/null || echo "ruff not installed"
mypy --version 2>/dev/null || echo "mypy not installed"
pytest --version 2>/dev/null || echo "pytest not installed"

echo -e "\n--- Git Configuration ---"
git config user.name
git config user.email

echo -e "\n=== End Diagnostic ==="
```

### Development Support Resources

#### For Development Setup Issues
- **[Local Development Guide](local-development.md)** - Complete setup instructions
- **[Installation Troubleshooting](../getting-started/installation.md#troubleshooting)** - Environment setup problems
- **[Development Guidelines](../../DEVELOPMENT_GUIDELINES.md)** - Complete development standards

#### For Testing Issues  
- **[Testing Troubleshooting](../testing/troubleshooting.md)** - Test execution and setup problems
- **[Testing Guide](testing-guide.md)** - Testing workflows and patterns

#### For Configuration Issues
- **[Configuration Troubleshooting](../config/troubleshooting.md)** - Configuration validation and setup
- **[Troubleshooting Hub](../troubleshooting-hub.md)** - Find the right guide for your issue

### Common Development Commands

```bash
# Daily development workflow
source .venv/bin/activate
pip install -e .
ruff format . && ruff check . --fix
mypy src/
pytest tests/ -v

# Reset development environment  
deactivate; rm -rf .venv; python -m venv .venv; source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .

# Start development server
python -m uvicorn src.api.main:app --reload --port 8000

# Run workers for development
python -m workers.monitor &
python -m workers.analyzer &
```

---

**Development tip:** Most development issues are environment-related. When in doubt, recreate your virtual environment and reinstall dependencies to get a clean slate.