# Configuration Documentation Hub

> **📚 Navigation Hub**: This is the **central navigation point** for all configuration documentation. Choose the guide that matches your needs and experience level.

## Configuration Documentation Hierarchy

### 🚀 **Quick Start** (Choose Your Path)
- **New User?** → **[Installation Guide](../getting-started/installation.md)** - Complete environment setup with API keys
- **Setting up team scenarios?** → **[User Configuration Guide](../user-guide/configuration.md)** - Ready-to-use templates 
- **Developer/Technical setup?** → **[Configuration Technical Guide](getting-started.md)** - System internals and validation
- **Programmatic access?** → **[Configuration API Reference](../api/configuration-api.md)** - Complete API documentation

### 📋 **Complete Guide Navigation**

#### 🔧 **For Users** (Team Setup & Scenarios)
- **[User Configuration Guide](../user-guide/configuration.md)** - Configuration templates for teams and use cases
- **[Installation Guide](../getting-started/installation.md)** - Environment variables and API key setup 
- **[User Troubleshooting](../user-guide/troubleshooting.md)** - Common configuration issues and solutions

#### 🛠️ **For Developers** (Technical Implementation)  
- **[Configuration Technical Guide](getting-started.md)** - Technical setup and system internals
- **[Configuration Reference](reference.md)** - Complete field documentation and technical details
- **[Configuration API Reference](../api/configuration-api.md)** - Programmatic configuration management
- **[Tools & Utilities](tools.md)** - Validation, comparison, and management tools

#### 🔒 **For Security & Operations**
- **[Security Guide](security.md)** - Security best practices and credential management
- **[Configuration Troubleshooting](troubleshooting.md)** - Technical configuration issues and debugging

## Documentation Types Explained

### 📖 **What Each Guide Provides**

#### **User Guides** (Practical Scenarios)
- **Focus**: Ready-to-use configuration templates and real-world scenarios
- **Audience**: Users setting up teams, choosing between small/enterprise configurations
- **Content**: YAML templates, team workflows, performance tuning examples
- **When to use**: You want to quickly configure the system for your specific team size or use case

#### **Technical Guides** (System Understanding) 
- **Focus**: How the configuration system works internally
- **Audience**: Developers who need to understand system behavior, validation, debugging
- **Content**: Configuration loading, validation APIs, programmatic usage, troubleshooting
- **When to use**: You're developing against the system or need to debug configuration issues

#### **API References** (Programmatic Integration)
- **Focus**: Complete API documentation for programmatic configuration management
- **Audience**: Developers writing code that interacts with the configuration system
- **Content**: Function signatures, class hierarchies, code examples, parameter options
- **When to use**: You're writing code that loads, modifies, or validates configuration

## Configuration System Features

### 🔧 **Core Capabilities**
- Type-safe configuration with Pydantic models
- Environment variable substitution for secrets
- Multi-file configuration with inheritance
- Runtime validation and hot reload

### ⚡ **Performance & Reliability**
- In-memory caching with LRU eviction
- Thread-safe concurrent access
- Configuration metrics and monitoring
- Graceful error handling and recovery
- Automatic sensitive value masking in logs
- Configuration validation and security scanning

## Architecture Overview

```
┌─────────────────┬─────────────────┬─────────────────┐
│   Application   │   Configuration │    Storage      │
│   Components    │    Manager      │   & Sources     │
├─────────────────┼─────────────────┼─────────────────┤
│ • Workers       │ • Type Safety   │ • YAML Files    │
│ • Services      │ • Validation    │ • Env Variables │
│ • Controllers   │ • Caching       │ • Remote Config │
│ • Models        │ • Metrics       │ • Key Vaults    │
│ • Repositories  │ • Hot Reload    │ • Databases     │
└─────────────────┴─────────────────┴─────────────────┘
          ▲                 ▲                 ▲
          │                 │                 │
    Config Access      Management API    Config Sources
```

## Configuration Flow

1. **Load**: Configuration loaded from YAML files with env variable substitution
2. **Validate**: Schema validation, business rule checks, connectivity tests
3. **Cache**: Critical paths warmed into high-performance cache
4. **Monitor**: Access patterns, performance metrics, and health tracked
5. **Serve**: Type-safe configuration access throughout application
6. **Reload**: Hot reload capability with cache invalidation

## Supported Environments

- **Development** - Local development with minimal dependencies
- **Testing** - Isolated test configurations with mocking
- **Staging** - Production-like environment for integration testing  
- **Production** - Full production configuration with security hardening

## Configuration Sources

The system supports loading configuration from multiple sources in priority order:

1. **Explicit Path** - Direct file path specification
2. **Environment Variable** - `AGENTIC_CONFIG_PATH`
3. **Current Directory** - `./config.yaml`
4. **User Directory** - `~/.agentic/config.yaml`
5. **System Directory** - `/etc/agentic/config.yaml`

## Quick Configuration Workflows

### 🎯 **Common User Journeys** 

#### **"I'm setting up a new team"**
1. **[Installation Guide](../getting-started/installation.md)** → Set up environment variables and API keys
2. **[User Configuration Guide](../user-guide/configuration.md)** → Choose team template (small/enterprise)
3. **[User Troubleshooting](../user-guide/troubleshooting.md)** → If you encounter issues

#### **"I'm developing against the config system"**
1. **[Configuration Technical Guide](getting-started.md)** → Understand system internals
2. **[Configuration API Reference](../api/configuration-api.md)** → Programmatic usage
3. **[Tools & Utilities](tools.md)** → Validation and debugging tools

#### **"I'm implementing security/operations"**
1. **[Security Guide](security.md)** → Security best practices and credential management
2. **[Configuration Reference](reference.md)** → Complete technical reference
3. **[Configuration Troubleshooting](troubleshooting.md)** → Advanced debugging

## Configuration Documentation Maintenance

This hub is maintained to provide clear navigation between the different types of configuration documentation. Each guide serves a specific purpose:

- **No duplication**: Each guide has a distinct focus and audience
- **Clear cross-references**: Guides reference each other appropriately
- **Progressive disclosure**: Start simple, dive deeper as needed
- **Audience-specific**: Content matches the user's immediate needs

## Getting Help

- **🛠️ Not sure which troubleshooting guide to use?**: Visit the [**Troubleshooting Hub**](../troubleshooting-hub.md) to find the right guide for your issue type
- **User configuration issues**: Start with [User Troubleshooting](../user-guide/troubleshooting.md)
- **Technical configuration problems**: See [Configuration Troubleshooting](troubleshooting.md)
- **Environment setup issues**: Check [Installation Troubleshooting](../getting-started/installation.md#troubleshooting)
- **Documentation gaps**: File an issue in the repository