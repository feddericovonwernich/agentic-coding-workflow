# Security Policy

## Supported Versions

We release patches for security vulnerabilities. Currently supported versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take the security of the Agentic Coding Workflow project seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please DO NOT:

- **Do not** create a public GitHub issue for security vulnerabilities
- **Do not** post about the vulnerability in public forums or social media
- **Do not** exploit the vulnerability beyond what is necessary to demonstrate the issue

### Please DO:

**Email us directly at**: security@[domain] *(Note: Replace with actual security email)*

**Or use GitHub's private vulnerability reporting**:
1. Go to the Security tab of our repository
2. Click on "Report a vulnerability"
3. Fill out the form with details

### What to Include in Your Report

Please include the following information to help us understand and resolve the issue quickly:

1. **Type of vulnerability** (e.g., SQL injection, XSS, authentication bypass)
2. **Affected component** (e.g., specific module, API endpoint, configuration)
3. **Steps to reproduce**:
   - Environment details (OS, Python version, dependencies)
   - Detailed steps to trigger the vulnerability
   - Proof-of-concept code if available
4. **Impact assessment**:
   - What can an attacker achieve?
   - What data or functionality is at risk?
5. **Suggested fix** (if you have recommendations)

### What to Expect

**Initial Response**: We will acknowledge receipt of your report within 48 hours.

**Investigation**: We will investigate the issue and may contact you for additional information.

**Resolution Timeline**:
- Critical vulnerabilities: 7 days
- High severity: 14 days
- Medium severity: 30 days
- Low severity: 60 days

**Communication**: We will keep you informed about our progress and expected resolution timeline.

**Recognition**: With your permission, we will acknowledge your contribution in the security advisory.

## Security Best Practices for Users

### Environment Variables and Secrets

1. **Never commit secrets**:
   - Use `.env` files (already in `.gitignore`)
   - Store sensitive data in environment variables
   - Use secret management systems in production

2. **Required secrets**:
   ```bash
   # Critical secrets that must be protected
   GITHUB_TOKEN          # GitHub API access
   DATABASE_URL          # Database credentials
   ANTHROPIC_API_KEY     # LLM provider keys
   OPENAI_API_KEY
   TELEGRAM_BOT_TOKEN    # Notification credentials
   ```

3. **Rotate regularly**:
   - Change API keys and tokens periodically
   - Update database passwords regularly
   - Revoke unused access tokens

### GitHub Token Security

1. **Use minimal permissions**:
   - Only grant necessary repository permissions
   - Use fine-grained personal access tokens
   - Prefer GitHub Apps over PATs when possible

2. **Token scopes for this project**:
   ```
   repo:status       # Access commit status
   public_repo       # Access public repositories
   write:packages    # Write packages (if using GitHub Packages)
   read:org          # Read org and team membership
   ```

### Database Security

1. **Connection security**:
   - Use SSL/TLS for database connections
   - Implement connection pooling limits
   - Use read-only credentials where possible

2. **Query safety**:
   - Project uses SQLAlchemy ORM (prevents SQL injection)
   - All inputs are parameterized
   - Validation happens at multiple layers

### API Security

1. **Rate limiting**:
   - Implement rate limiting for all external APIs
   - Use circuit breakers for failure scenarios
   - Monitor for unusual activity patterns

2. **Authentication**:
   - Validate all webhook signatures
   - Use strong authentication for admin endpoints
   - Implement proper session management

### Container Security

1. **Docker best practices**:
   - Don't run containers as root
   - Use official base images
   - Scan images for vulnerabilities
   - Keep base images updated

2. **Secrets in containers**:
   - Never build secrets into images
   - Use environment variables or mounted secrets
   - Implement secret rotation

## Security Features

### Built-in Security Measures

1. **Input Validation**:
   - Pydantic models validate all configuration
   - Strong typing throughout the codebase
   - Sanitization of user inputs

2. **Error Handling**:
   - Sensitive data masked in logs
   - Generic error messages to users
   - Detailed errors only in debug mode

3. **Dependencies**:
   - Regular dependency updates
   - Security scanning with `safety` and `bandit`
   - Automated vulnerability alerts from GitHub

### Security Checklist for Contributors

Before submitting code, ensure:

- [ ] No secrets or credentials in code
- [ ] All user inputs are validated
- [ ] Error messages don't leak sensitive information
- [ ] Dependencies are up to date
- [ ] Security tests pass
- [ ] Documentation updated for security-relevant changes

## Vulnerability Disclosure Policy

### Responsible Disclosure

We follow a responsible disclosure model:

1. **Private disclosure period**: 90 days from initial report
2. **Patch development**: Create and test fixes privately
3. **Coordinated release**: Release patch with security advisory
4. **Public disclosure**: Full details after patches are available

### Security Advisories

Security advisories will be published through:
- GitHub Security Advisories
- Project changelog
- Direct notification to affected users (if contact information available)

## Security Tools and Commands

### Running Security Checks

```bash
# Scan for known vulnerabilities in dependencies
safety check

# Static security analysis
bandit -r src/

# Check for outdated dependencies
pip list --outdated

# Audit dependencies for known vulnerabilities
pip-audit
```

### Pre-commit Security Hooks

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/PyCQA/bandit
    rev: '1.7.5'
    hooks:
      - id: bandit
        args: ['-r', 'src/']
  
  - repo: https://github.com/pyupio/safety
    rev: v2.3.5
    hooks:
      - id: safety
```

## Contact

For security concerns, contact:
- **Email**: security@[domain] *(Note: Update with actual email)*
- **GitHub Security**: Use private vulnerability reporting

For general questions:
- Create a [GitHub issue](https://github.com/feddericovonwernich/agentic-coding-workflow/issues)
- Check our [Contributing Guidelines](CONTRIBUTING.md)

## Acknowledgments

We thank the security researchers who have responsibly disclosed vulnerabilities and helped improve the security of this project.

## Updates

This security policy is regularly reviewed and updated. Last update: December 2024

---

*This security policy is adapted from best practices recommended by the [GitHub Security Lab](https://securitylab.github.com/) and the [Open Source Security Foundation](https://openssf.org/).*