# Quick Start Guide

Get the Agentic Coding Workflow system running in under 15 minutes! This guide will help you set up automated PR monitoring and fixing for your GitHub repositories.

> **📚 Navigation**: This is the **quick start guide** for new users. For production deployment, see [Installation Guide](installation.md). For user configuration scenarios, see [User Configuration Guide](../user-guide/configuration.md). For development setup, see [Developer Onboarding](../developer/onboarding.md).

## What You'll Achieve

By the end of this guide, you'll have:
- ✅ The system monitoring your GitHub repository
- ✅ Automatic detection of failed PR checks
- ✅ AI-powered analysis of failures 
- ✅ Automated fixes for common issues (linting, formatting)
- ✅ Smart notifications when human review is needed

## Prerequisites (2 minutes)

Before starting, ensure you have:

- **GitHub repository** with CI/CD checks (GitHub Actions, etc.)
- **GitHub Personal Access Token** with repo access
- **LLM API key** (Anthropic Claude or OpenAI)
- **Docker** installed (for database)
- **Python 3.11+** installed

## Quick Setup Steps

### Step 1: Clone and Install (3 minutes)

```bash
# Clone the repository
git clone https://github.com/feddericovonwernich/agentic-coding-workflow.git
cd agentic-coding-workflow

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Environment Setup (2 minutes)

Create a `.env` file with your credentials:

```bash
# Copy the example environment file
cp .env.example .env

# Edit with your values
nano .env
```

Add these essential variables:

```bash
# GitHub Integration
GITHUB_TOKEN=ghp_your_github_token_here

# LLM Provider (choose one)
ANTHROPIC_API_KEY=sk-ant-your_key_here
# OR
OPENAI_API_KEY=sk-your_openai_key_here

# Database (SQLite for quick start)
DATABASE_URL=sqlite:///./agentic.db

# Notification (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Step 3: Configuration (3 minutes)

Create your `config.yaml`:

```bash
cp config.example.yaml config.yaml
```

Update the configuration with your repository:

```yaml
# config.yaml - Minimal quick start configuration
repositories:
  - url: "https://github.com/your-org/your-repo"
    name: "your-repo"
    polling_interval: 300  # Check every 5 minutes

llm:
  anthropic:  # or openai
    provider: anthropic
    api_key: "${ANTHROPIC_API_KEY}"
    model: claude-3-sonnet-20240229

default_llm_provider: anthropic

database:
  url: "${DATABASE_URL}"

queue:
  provider: memory  # Simple in-memory queue for quick start

notification:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
```

### Step 4: Database Setup (1 minute)

```bash
# Run database migrations
alembic upgrade head
```

### Step 5: Start the System (1 minute)

```bash
# Start the monitoring system
python -m src.workers.monitor
```

You should see:
```
✅ Configuration loaded successfully
✅ Database connected
✅ Starting PR monitor for your-org/your-repo
🔍 Checking for pull requests...
```

### Step 6: Test with a PR (3 minutes)

1. **Create a test PR** in your repository with a simple linting issue:

```python
# Add this to a Python file (missing semicolon for JS, etc.)
def test_function():
    x=1+2    # Poor formatting - will trigger linting
    return x
```

2. **Watch the system work**:
   - Monitor logs show PR detection
   - Failed checks are analyzed
   - Automatic fixes are applied (for linting issues)
   - Notifications sent for complex issues

3. **Check results**:
   - Look for automatic fix commits
   - Check PR status updates
   - Verify notifications received

## Next Steps

🎉 **Congratulations!** Your automated PR monitoring system is running.

### For Production Use

- **[Installation Guide](installation.md)** - Production deployment with PostgreSQL
- **[First Deployment Guide](first-deployment.md)** - Complete production setup
- **[User Guide](../user-guide/README.md)** - Configuration, monitoring, and troubleshooting

### For Development & Integration

- **[Development Guidelines](../../DEVELOPMENT_GUIDELINES.md)** - Contributing to the project
- **[API Documentation](../api/README.md)** - Complete API reference for custom integrations
- **[Configuration Reference](../config/reference.md)** - Advanced configuration options

## Troubleshooting Quick Fixes

### "Configuration file not found"
```bash
# Ensure config.yaml exists in project root
ls -la config.yaml
```

### "Database connection failed"
```bash
# For SQLite, ensure directory is writable
touch agentic.db
```

### "GitHub API rate limit"
```bash
# Check your token has correct permissions
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit
```

### "No PRs detected"
```bash
# Verify repository URL and ensure it has open PRs with failed checks
# Check GitHub token has access to the repository
```

## Support

- **🛠️ Issues**: [Troubleshooting Hub](../troubleshooting-hub.md) - **Navigation center** to find the right troubleshooting guide
- **Quick Operational Issues**: [User Troubleshooting Guide](../user-guide/troubleshooting.md)
- **Installation Issues**: [Installation Troubleshooting](installation.md#troubleshooting)
- **Configuration Help**: [User Configuration Guide](../user-guide/configuration.md)
- **Bugs/Features**: [Create an issue](https://github.com/feddericovonwernich/agentic-coding-workflow/issues)

---

**Time to Success**: Target completion in 15 minutes | **Difficulty**: Beginner | **Prerequisites**: GitHub repo with CI/CD