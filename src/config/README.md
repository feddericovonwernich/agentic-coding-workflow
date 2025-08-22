# Configuration System

The configuration documentation has been consolidated into the main documentation directory.

## 📚 Complete Configuration Documentation

Please visit **[docs/config/README.md](../../docs/config/README.md)** for the complete configuration system documentation.

### Quick Links

- **[Getting Started](../../docs/config/getting-started.md)** - Set up configuration in < 15 minutes
- **[Configuration Reference](../../docs/config/reference.md)** - Complete field documentation and API reference
- **[Tools & Utilities](../../docs/config/tools.md)** - Validation and comparison tools
- **[Security Guide](../../docs/config/security.md)** - Best practices for credential management
- **[Troubleshooting](../../docs/config/troubleshooting.md)** - Common issues and solutions

## Quick Start

For immediate usage, here's the basic pattern:

```python
from src.config import load_config

# Load configuration (auto-discovers config.yaml)
config = load_config()

# Access configuration sections
database_url = config.database.url
llm_provider = config.llm[config.default_llm_provider]
```

For detailed usage examples, configuration options, and advanced features, see the [complete documentation](../../docs/config/README.md).