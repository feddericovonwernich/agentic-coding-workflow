# System Behavior Diagrams

This file has been reorganized into detailed individual diagram files. For comprehensive documentation with explanations, please visit:

## 📋 [Complete Diagrams Documentation](docs/diagrams/README.md)

The diagrams are now organized by category with detailed explanations:

### 🏗️ Architecture Diagrams
- **[System Overview](docs/diagrams/architecture/system-overview.md)** - Complete system architecture
- **[Component Interactions](docs/diagrams/architecture/component-interactions.md)** - Detailed interaction patterns

### 🔄 Workflow Diagrams  
- **[PR Monitoring](docs/diagrams/workflows/pr-monitoring.md)** - PR discovery and tracking
- **[Check Analysis & Fixing](docs/diagrams/workflows/check-analysis-fixing.md)** - Failure analysis and automated fixes
- **[PR Review Process](docs/diagrams/workflows/pr-review.md)** - Multi-agent code review
- **[PR State Machine](docs/diagrams/workflows/pr-state-machine.md)** - Complete PR lifecycle

### 📊 Sequence Diagrams
- **[Failed Check to Fix](docs/diagrams/sequences/failed-check-to-fix.md)** - Step-by-step fix process
- **[PR Review Process](docs/diagrams/sequences/pr-review-process.md)** - Review coordination sequence

### ⚙️ Operational Diagrams
- **[Decision Logic](docs/diagrams/operational/decision-logic.md)** - Fix vs escalate decision tree
- **[Error Handling](docs/diagrams/operational/error-handling.md)** - Comprehensive error recovery
- **[Monitoring Dashboard](docs/diagrams/operational/monitoring-dashboard.md)** - Observability and alerting

Each diagram file includes:
- **Purpose**: What the diagram shows and why it's important
- **Detailed Explanations**: Step-by-step breakdowns of processes
- **Configuration Examples**: Real-world implementation guidance
- **Code Samples**: Practical implementation snippets
- **Monitoring Considerations**: Operational insights

## Quick Reference

### For Developers
Start with [System Overview](docs/diagrams/architecture/system-overview.md) → [Workflow Diagrams](docs/diagrams/workflows/) → [Sequence Diagrams](docs/diagrams/sequences/)

### For Operations Teams  
Focus on [Error Handling](docs/diagrams/operational/error-handling.md) → [Monitoring Dashboard](docs/diagrams/operational/monitoring-dashboard.md) → [Component Interactions](docs/diagrams/architecture/component-interactions.md)

### For Implementation
Use [Decision Logic](docs/diagrams/operational/decision-logic.md) → [Check Analysis & Fixing](docs/diagrams/workflows/check-analysis-fixing.md) → [Failed Check to Fix](docs/diagrams/sequences/failed-check-to-fix.md)