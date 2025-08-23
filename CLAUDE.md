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

## Development Workflow with Specialized Agents

**IMPORTANT**: Use specialized agents for efficient development:

1. **Architecture Planning** (`architecture-planner` agent)
   - Use BEFORE implementing any new feature or significant refactoring
   - Creates comprehensive technical plans in `scratch-pad/` directory
   - Defines interfaces, coordination strategies, and implementation tasks

2. **Implementation coordination**
   - You will act as the coordinator for the plan laid out by the `architecture-planner` agent.
   - Read the plan carefully
   - Ensure understanding of the overall architecture and individual tasks
   - List out tasks you need to execute to fulfill the plan clearly in the scratch pad for tracking in a file named `tasks.md`
   - Mark tasks as complete in `tasks.md` as the sub agents complete them.
   - If you need to clarify or adjust the plan, you can re-engage the `architecture-planner` agent and update the tasks accordingly.
   - Make sure to keep the scratch pad updated with progress and any issues encountered.

2. **Implementation execution**
   - **ALWAYS run these agents IN PARALLEL when indicated by the plan**
     - **Code Implementation** (`code-implementer` agent): Use this agent to write the actual code based on the plan.
       - `code-implementer` agent will have knowledge of coding best practices of the project, it should ONLY be used to write code.
     - **Test Writing** (`test-implementor` agent): Use this agent to create comprehensive tests for the code being implemented.
       - `test-implementor` agent will have knowledge of testing best practices of the project, it should ONLY be used to write tests.
   - Maximize development efficiency through parallel execution
   - **CRITICAL**: Make sure to instruct these agents to read relevant files for the task given from the scratch pad.

3. **Documentation** (`code-documentator` agent)
   - Use AFTER code and tests are complete.
   - This agent will have knowledge of the project's documentation standards.
   - Updates or creates documentation according to project standards.
   - Ensures all changes are properly documented.

4 - **Code Quality** (`Code Quality Enforcer` agent)
   - Use AFTER implementation and documentation are complete.
   - This agent will have knowledge of the project's code quality standards.

5 - Commit and Push
   - After all agents have completed their tasks, review the changes.
   - Make sure that all tasks in `tasks.md` are marked as complete.
   - **CRITICAL**: Run a final check to ensure everything is working as expected.
     - Run all tests
     - Run code quality tools
     - If anything fails, categorize the issues, split into manageable tasks, and re-engage the appropriate agents to fix them.
       - Engage agents in parallel work where possible to maximize efficiency.
   - **IMPORTANT**: Once everything is verified: Clear scratch pad of all temporary files and notes.
     - Make sure the plan we've followed is detailed in the PR description.
   - Commit the changes with a clear message summarizing the work done.
   - Push the changes to the appropriate branch in the repository.
   - Create a Pull Request if necessary, following the project's PR guidelines.