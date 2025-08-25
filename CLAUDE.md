# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An automated system for monitoring, analyzing, and fixing failed GitHub pull request checks using LLM-powered analysis and the Claude Code SDK. The system orchestrates multiple workers to handle PR monitoring, failure analysis, automated fixing, and multi-agent code reviews.

## Architecture

### Core Components
- **PR Monitor Worker**: Comprehensive PR discovery and processing system (Issue #48)
  - **Discovery Engines**: PRDiscoveryEngine and CheckRunDiscoveryEngine for GitHub API interactions
  - **State Change Detection**: StateChangeDetector for efficient O(1) PR and check run state comparison
  - **Data Synchronization**: DataSynchronizer with bulk operations and transaction management
  - **Main Orchestrator**: PRProcessor coordinating the entire workflow with resource management
  - **Performance Capabilities**: Handle 100,000+ PRs across repositories with <2s response time
- **Check Analyzer Worker**: Analyzes failed check logs using configurable LLMs
- **Fix Applicator Worker**: Applies automated fixes using Claude Code SDK
- **Review Orchestrator Worker**: Coordinates multi-agent PR reviews
- **Notification Service**: Handles escalations to humans via Telegram/Slack

### PR Monitor Worker Architecture (Implemented)

#### Data Models and Interfaces (`src/workers/monitor/models.py`)
- **ProcessingMetrics**: Performance tracking with API usage, timing, and resource monitoring
- **DiscoveryResult**: Immutable PR discovery data with validation and serialization
- **CheckRunDiscovery**: Check run data with actionable failure detection
- **StateChangeEvent**: State change tracking with severity levels and change categorization
- **SyncOperation**: Database synchronization operations with rollback capabilities
- **Abstract Interfaces**: PRDiscoveryInterface, CheckRunDiscoveryInterface, StateDetectorInterface, DataSynchronizerInterface

#### Discovery System (`src/workers/monitor/discovery.py`)
- **PRDiscoveryEngine**: 
  - Fetches PRs from GitHub with intelligent caching and pagination
  - Rate limiting with backoff strategies
  - Repository-level parallelization support
- **CheckRunDiscoveryEngine**: 
  - Discovers check runs with suite management and categorization
  - Failed check run identification and routing
  - Performance optimization with concurrent discovery

#### Change Detection (`src/workers/monitor/change_detection.py`)
- **StateChangeDetector**: 
  - Efficient O(1) comparison of PR and check run states
  - Prioritized change event generation with severity analysis
  - Actionable change filtering for immediate processing

#### Data Synchronization (`src/workers/monitor/synchronization.py`)
- **DataSynchronizer**: 
  - Bulk database operations with transaction management
  - Conflict resolution strategies and rollback capabilities
  - ACID compliance with comprehensive error handling

#### Main Processor (`src/workers/monitor/processor.py`)
- **PRProcessor**: 
  - Orchestrates entire workflow with repository-level parallelization
  - Supports full/incremental/dry-run processing modes
  - Resource management with memory and CPU monitoring
  - Comprehensive metrics collection and performance monitoring
  - Graceful shutdown and error recovery mechanisms