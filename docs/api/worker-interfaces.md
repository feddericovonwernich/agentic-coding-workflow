# Worker Interfaces Documentation

The Worker Interfaces provide extensible patterns for implementing background workers, message queue integration, and event-driven processing in the Agentic Coding Workflow system.

## Table of Contents

- [Quick Start](#quick-start)
- [Worker Architecture](#worker-architecture)
- [Message Queue Integration](#message-queue-integration)
- [Worker Base Classes](#worker-base-classes)
- [Message Formats](#message-formats)
- [Event Handling](#event-handling)
- [Custom Worker Implementation](#custom-worker-implementation)
- [Error Handling](#error-handling)
- [Monitoring and Health Checks](#monitoring-and-health-checks)
- [Performance Optimization](#performance-optimization)
- [Best Practices](#best-practices)

## Quick Start

### Basic Worker Implementation

```python
import asyncio
from abc import ABC, abstractmethod
from typing import Any
from dataclasses import dataclass

@dataclass
class WorkerMessage:
    """Base message format for worker communication."""
    id: str
    type: str
    payload: dict[str, Any]
    priority: int = 1
    retry_count: int = 0
    max_retries: int = 3

class BaseWorker(ABC):
    """Abstract base class for all workers."""
    
    def __init__(self, name: str, queue_manager: QueueManager):
        self.name = name
        self.queue_manager = queue_manager
        self.is_running = False
    
    @abstractmethod
    async def process_message(self, message: WorkerMessage) -> bool:
        """Process a single message. Return True if successful."""
        pass
    
    async def start(self):
        """Start the worker."""
        self.is_running = True
        while self.is_running:
            try:
                message = await self.queue_manager.get_message(self.name)
                if message:
                    success = await self.process_message(message)
                    if success:
                        await self.queue_manager.ack_message(message.id)
                    else:
                        await self.queue_manager.nack_message(message.id)
                await asyncio.sleep(0.1)  # Prevent tight loop
            except Exception as e:
                logger.error(f"Worker {self.name} error: {e}")
                await asyncio.sleep(1)  # Backoff on error

# Example implementation
class PRMonitorWorker(BaseWorker):
    """Worker for monitoring pull requests."""
    
    async def process_message(self, message: WorkerMessage) -> bool:
        if message.type == "monitor_repository":
            return await self.monitor_repository(message.payload)
        elif message.type == "check_pull_request":
            return await self.check_pull_request(message.payload)
        return False
    
    async def monitor_repository(self, payload: dict) -> bool:
        repository_id = payload["repository_id"]
        # Monitor repository for new PRs
        return True

# Advanced Implementation - PR Monitor Worker (Issue #48 - Implemented)
class AdvancedPRMonitorWorker(BaseWorker):
    """Advanced PR monitoring with comprehensive discovery and processing."""
    
    def __init__(self, name: str, queue_manager: QueueManager, 
                 github_client: GitHubClient, cache_manager: CacheManager):
        super().__init__(name, queue_manager)
        self.pr_processor = PRProcessor(
            github_client=github_client,
            session=session,
            cache_manager=cache_manager,
            config=ProcessorConfig()
        )
    
    async def process_message(self, message: WorkerMessage) -> bool:
        """Process repository monitoring with full orchestration."""
        try:
            if message.type == "process_repositories":
                repositories = message.payload.get("repository_ids")
                mode = ProcessingMode(message.payload.get("mode", "incremental"))
                
                session = await self.pr_processor.process_repositories(
                    repositories=repositories,
                    mode=mode
                )
                
                return session.success_rate > 90  # Success if >90% repositories processed
                
            elif message.type == "process_single_repository":
                repository_id = UUID(message.payload["repository_id"])
                since = message.payload.get("since")
                
                result = await self.pr_processor.process_single_repository(
                    repository_id=repository_id,
                    since=datetime.fromisoformat(since) if since else None
                )
                
                return result.success
                
            else:
                logger.warning(f"Unknown message type: {message.type}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return False

# Usage
async def main():
    queue_manager = RedisQueueManager(redis_url="redis://localhost:6379")
    worker = PRMonitorWorker("pr_monitor", queue_manager)
    await worker.start()

asyncio.run(main())
```

## Worker Architecture

### System Overview

The worker system follows an event-driven architecture:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Event Source  │───▶│  Message Queue  │───▶│     Worker      │
│                 │    │                 │    │                 │
│ • GitHub API    │    │ • Redis/Memory  │    │ • PR Monitor    │
│ • Webhooks      │    │ • Priorities    │    │ • Check Analyzer│
│ • Scheduled     │    │ • Persistence   │    │ • Fix Applicator│
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         │                        │                        │
         ▼                        ▼                        ▼
   Event Generation        Message Routing        Task Processing
```

### Core Components

#### Worker Manager

```python
from typing import Dict, List
from src.workers.manager import WorkerManager

class WorkerManager:
    """Manages multiple workers and their lifecycle."""
    
    def __init__(self, queue_manager: QueueManager):
        self.queue_manager = queue_manager
        self.workers: Dict[str, BaseWorker] = {}
        self.running_tasks: List[asyncio.Task] = []
    
    def register_worker(self, worker: BaseWorker):
        """Register a worker with the manager."""
        self.workers[worker.name] = worker
    
    async def start_all_workers(self):
        """Start all registered workers."""
        for worker in self.workers.values():
            task = asyncio.create_task(worker.start())
            self.running_tasks.append(task)
    
    async def stop_all_workers(self):
        """Stop all workers gracefully."""
        for worker in self.workers.values():
            worker.is_running = False
        
        # Wait for workers to finish current tasks
        await asyncio.gather(*self.running_tasks, return_exceptions=True)
    
    async def get_worker_status(self) -> Dict[str, Dict]:
        """Get status of all workers."""
        status = {}
        for name, worker in self.workers.items():
            status[name] = {
                "running": worker.is_running,
                "queue_size": await self.queue_manager.get_queue_size(name),
                "processed_count": getattr(worker, 'processed_count', 0),
                "error_count": getattr(worker, 'error_count', 0)
            }
        return status

# Usage
manager = WorkerManager(queue_manager)
manager.register_worker(PRMonitorWorker("pr_monitor", queue_manager))
manager.register_worker(CheckAnalyzerWorker("check_analyzer", queue_manager))
await manager.start_all_workers()
```

## Message Queue Integration

### Queue Manager Interface

```python
from abc import ABC, abstractmethod
from typing import Optional, List

class QueueManager(ABC):
    """Abstract interface for message queue management."""
    
    @abstractmethod
    async def send_message(self, queue_name: str, message: WorkerMessage) -> bool:
        """Send message to queue."""
        pass
    
    @abstractmethod
    async def get_message(self, queue_name: str) -> Optional[WorkerMessage]:
        """Get next message from queue."""
        pass
    
    @abstractmethod
    async def ack_message(self, message_id: str) -> bool:
        """Acknowledge message processing."""
        pass
    
    @abstractmethod
    async def nack_message(self, message_id: str) -> bool:
        """Negative acknowledge - requeue message."""
        pass
    
    @abstractmethod
    async def get_queue_size(self, queue_name: str) -> int:
        """Get number of messages in queue."""
        pass
```

### Redis Queue Implementation

```python
import json
import redis.asyncio as redis
from src.workers.queue.redis_queue import RedisQueueManager

class RedisQueueManager(QueueManager):
    """Redis-based queue manager implementation."""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis = None
    
    async def connect(self):
        """Connect to Redis."""
        self.redis = redis.from_url(self.redis_url)
    
    async def send_message(self, queue_name: str, message: WorkerMessage) -> bool:
        """Send message to Redis queue."""
        try:
            message_data = {
                "id": message.id,
                "type": message.type,
                "payload": message.payload,
                "priority": message.priority,
                "retry_count": message.retry_count,
                "max_retries": message.max_retries
            }
            
            # Use Redis sorted set for priority queue
            score = -message.priority  # Higher priority = lower score
            await self.redis.zadd(
                f"queue:{queue_name}",
                {json.dumps(message_data): score}
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def get_message(self, queue_name: str) -> Optional[WorkerMessage]:
        """Get highest priority message from queue."""
        try:
            # Get message with lowest score (highest priority)
            result = await self.redis.zpopmin(f"queue:{queue_name}")
            if not result:
                return None
            
            message_json, _ = result[0]
            message_data = json.loads(message_json)
            
            return WorkerMessage(
                id=message_data["id"],
                type=message_data["type"],
                payload=message_data["payload"],
                priority=message_data["priority"],
                retry_count=message_data["retry_count"],
                max_retries=message_data["max_retries"]
            )
        except Exception as e:
            logger.error(f"Failed to get message: {e}")
            return None
```

### Memory Queue Implementation

```python
import asyncio
import heapq
from collections import defaultdict
from src.workers.queue.memory_queue import MemoryQueueManager

class MemoryQueueManager(QueueManager):
    """In-memory queue manager for development and testing."""
    
    def __init__(self):
        self.queues = defaultdict(list)  # Priority heaps
        self.processing = set()          # Processing message IDs
        self.lock = asyncio.Lock()
    
    async def send_message(self, queue_name: str, message: WorkerMessage) -> bool:
        """Send message to memory queue."""
        async with self.lock:
            # Use negative priority for min-heap behavior
            heapq.heappush(
                self.queues[queue_name],
                (-message.priority, message)
            )
        return True
    
    async def get_message(self, queue_name: str) -> Optional[WorkerMessage]:
        """Get highest priority message from queue."""
        async with self.lock:
            if not self.queues[queue_name]:
                return None
            
            _, message = heapq.heappop(self.queues[queue_name])
            self.processing.add(message.id)
            return message
    
    async def ack_message(self, message_id: str) -> bool:
        """Remove message from processing set."""
        async with self.lock:
            self.processing.discard(message_id)
        return True
    
    async def nack_message(self, message_id: str) -> bool:
        """Requeue message with incremented retry count."""
        # Implementation would requeue the message
        async with self.lock:
            self.processing.discard(message_id)
        return True
```

## Worker Base Classes

### Specialized Worker Types

#### Event-Driven Worker

```python
from src.workers.base.event_worker import EventWorker

class EventWorker(BaseWorker):
    """Worker that processes events in real-time."""
    
    def __init__(self, name: str, queue_manager: QueueManager):
        super().__init__(name, queue_manager)
        self.event_handlers = {}
    
    def register_handler(self, event_type: str, handler: callable):
        """Register handler for specific event type."""
        self.event_handlers[event_type] = handler
    
    async def process_message(self, message: WorkerMessage) -> bool:
        """Process event message using registered handlers."""
        handler = self.event_handlers.get(message.type)
        if not handler:
            logger.warning(f"No handler for event type: {message.type}")
            return False
        
        try:
            await handler(message.payload)
            return True
        except Exception as e:
            logger.error(f"Handler error for {message.type}: {e}")
            return False

# Usage
github_worker = EventWorker("github_events", queue_manager)

async def handle_pr_opened(payload: dict):
    pr_id = payload["pull_request"]["id"]
    # Process new PR
    
async def handle_check_completed(payload: dict):
    check_run_id = payload["check_run"]["id"]
    # Process completed check

github_worker.register_handler("pull_request.opened", handle_pr_opened)
github_worker.register_handler("check_run.completed", handle_check_completed)
```

#### Scheduled Worker

```python
from src.workers.base.scheduled_worker import ScheduledWorker
import asyncio

class ScheduledWorker(BaseWorker):
    """Worker that runs on a schedule."""
    
    def __init__(self, name: str, interval_seconds: int):
        self.name = name
        self.interval_seconds = interval_seconds
        self.is_running = False
    
    @abstractmethod
    async def execute_task(self) -> bool:
        """Execute the scheduled task."""
        pass
    
    async def start(self):
        """Start scheduled execution."""
        self.is_running = True
        while self.is_running:
            try:
                await self.execute_task()
                await asyncio.sleep(self.interval_seconds)
            except Exception as e:
                logger.error(f"Scheduled worker {self.name} error: {e}")
                await asyncio.sleep(self.interval_seconds)

# Example implementation
class RepositoryMonitorWorker(ScheduledWorker):
    """Periodically monitor repositories for new PRs."""
    
    def __init__(self, github_client: GitHubClient, interval_seconds: int = 300):
        super().__init__("repository_monitor", interval_seconds)
        self.github_client = github_client
    
    async def execute_task(self) -> bool:
        """Check all active repositories for new PRs."""
        repositories = await self.get_active_repositories()
        
        for repo in repositories:
            try:
                await self.check_repository_prs(repo)
            except Exception as e:
                logger.error(f"Error checking repository {repo.name}: {e}")
        
        return True
    
    async def check_repository_prs(self, repository):
        """Check a single repository for new PRs."""
        prs = await self.github_client.get_pulls(repository.full_name)
        for pr_data in prs:
            await self.process_pr_data(repository, pr_data)
```

#### Batch Worker

```python
from src.workers.base.batch_worker import BatchWorker

class BatchWorker(BaseWorker):
    """Worker that processes messages in batches."""
    
    def __init__(self, name: str, queue_manager: QueueManager, batch_size: int = 10):
        super().__init__(name, queue_manager)
        self.batch_size = batch_size
    
    @abstractmethod
    async def process_batch(self, messages: List[WorkerMessage]) -> List[bool]:
        """Process a batch of messages. Return success status for each."""
        pass
    
    async def start(self):
        """Start batch processing."""
        self.is_running = True
        while self.is_running:
            try:
                batch = await self.collect_batch()
                if batch:
                    results = await self.process_batch(batch)
                    await self.handle_batch_results(batch, results)
                else:
                    await asyncio.sleep(1)  # No messages available
            except Exception as e:
                logger.error(f"Batch worker {self.name} error: {e}")
                await asyncio.sleep(1)
    
    async def collect_batch(self) -> List[WorkerMessage]:
        """Collect messages for batch processing."""
        batch = []
        for _ in range(self.batch_size):
            message = await self.queue_manager.get_message(self.name)
            if message:
                batch.append(message)
            else:
                break  # No more messages
        return batch

# Example implementation
class CheckAnalyzerBatchWorker(BatchWorker):
    """Analyze multiple check runs in batches."""
    
    async def process_batch(self, messages: List[WorkerMessage]) -> List[bool]:
        """Analyze check runs in batch for efficiency."""
        check_runs = [msg.payload for msg in messages]
        
        # Batch analysis
        results = await self.analyze_check_runs_batch(check_runs)
        
        return [result.success for result in results]
```

## Message Formats

### Standard Message Types

```python
from dataclasses import dataclass
from typing import Any, Optional
from datetime import datetime

@dataclass
class PRMonitorMessage:
    """Message for PR monitoring tasks."""
    repository_id: str
    pr_number: Optional[int] = None
    force_refresh: bool = False
    
    def to_worker_message(self) -> WorkerMessage:
        return WorkerMessage(
            id=f"pr_monitor_{self.repository_id}_{int(datetime.now().timestamp())}",
            type="monitor_repository",
            payload=self.__dict__,
            priority=1
        )

@dataclass
class CheckAnalysisMessage:
    """Message for check run analysis."""
    check_run_id: str
    repository_id: str
    pull_request_id: str
    failure_logs: str
    
    def to_worker_message(self) -> WorkerMessage:
        return WorkerMessage(
            id=f"check_analysis_{self.check_run_id}",
            type="analyze_check_failure",
            payload=self.__dict__,
            priority=2  # Higher priority for failures
        )

@dataclass
class FixApplicationMessage:
    """Message for applying automated fixes."""
    pull_request_id: str
    fix_strategy: str
    fix_content: str
    confidence_score: float
    
    def to_worker_message(self) -> WorkerMessage:
        return WorkerMessage(
            id=f"fix_application_{self.pull_request_id}",
            type="apply_fix",
            payload=self.__dict__,
            priority=3  # Highest priority for fixes
        )
```

### Message Serialization

```python
import json
from datetime import datetime
from typing import Any

class MessageSerializer:
    """Handles serialization/deserialization of messages."""
    
    @staticmethod
    def serialize(message: WorkerMessage) -> str:
        """Serialize message to JSON string."""
        data = {
            "id": message.id,
            "type": message.type,
            "payload": message.payload,
            "priority": message.priority,
            "retry_count": message.retry_count,
            "max_retries": message.max_retries,
            "timestamp": datetime.utcnow().isoformat()
        }
        return json.dumps(data, default=str)
    
    @staticmethod
    def deserialize(message_json: str) -> WorkerMessage:
        """Deserialize JSON string to message."""
        data = json.loads(message_json)
        return WorkerMessage(
            id=data["id"],
            type=data["type"],
            payload=data["payload"],
            priority=data["priority"],
            retry_count=data["retry_count"],
            max_retries=data["max_retries"]
        )
```

## Event Handling

### Event System

```python
from typing import Callable, Dict, List
from src.workers.events import EventBus

class EventBus:
    """Central event bus for worker communication."""
    
    def __init__(self):
        self.handlers: Dict[str, List[Callable]] = {}
    
    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe to an event type."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable):
        """Unsubscribe from an event type."""
        if event_type in self.handlers:
            self.handlers[event_type].remove(handler)
    
    async def publish(self, event_type: str, data: Any):
        """Publish an event to all subscribers."""
        if event_type in self.handlers:
            for handler in self.handlers[event_type]:
                try:
                    await handler(data)
                except Exception as e:
                    logger.error(f"Event handler error: {e}")

# Usage
event_bus = EventBus()

# Subscribe to events
async def on_pr_created(pr_data):
    # Send message to check analyzer
    message = CheckAnalysisMessage(
        check_run_id=pr_data["check_run_id"],
        repository_id=pr_data["repository_id"],
        pull_request_id=pr_data["id"],
        failure_logs=""
    )
    await queue_manager.send_message("check_analyzer", message.to_worker_message())

event_bus.subscribe("pr.created", on_pr_created)

# Publish events
await event_bus.publish("pr.created", {"id": "123", "repository_id": "repo-1"})
```

### Event Patterns

```python
# Observer Pattern
class WorkerObserver:
    """Observer for worker events."""
    
    async def on_worker_started(self, worker_name: str):
        logger.info(f"Worker {worker_name} started")
    
    async def on_worker_stopped(self, worker_name: str):
        logger.info(f"Worker {worker_name} stopped")
    
    async def on_message_processed(self, worker_name: str, message_id: str, success: bool):
        if success:
            logger.info(f"Worker {worker_name} processed message {message_id}")
        else:
            logger.error(f"Worker {worker_name} failed to process message {message_id}")

# Chain of Responsibility Pattern
class MessageProcessor:
    """Chain of message processors."""
    
    def __init__(self):
        self.processors = []
    
    def add_processor(self, processor: Callable):
        self.processors.append(processor)
    
    async def process(self, message: WorkerMessage) -> bool:
        for processor in self.processors:
            if await processor(message):
                return True
        return False
```

## Custom Worker Implementation

### Creating Custom Workers

```python
from src.workers.base import BaseWorker
from src.github.client import GitHubClient
from src.database.connection import DatabaseConnectionManager

class CustomAnalysisWorker(BaseWorker):
    """Custom worker for advanced PR analysis."""
    
    def __init__(
        self,
        name: str,
        queue_manager: QueueManager,
        github_client: GitHubClient,
        db_manager: DatabaseConnectionManager
    ):
        super().__init__(name, queue_manager)
        self.github_client = github_client
        self.db_manager = db_manager
        self.processed_count = 0
        self.error_count = 0
    
    async def process_message(self, message: WorkerMessage) -> bool:
        """Process custom analysis message."""
        try:
            if message.type == "analyze_pr_complexity":
                return await self.analyze_pr_complexity(message.payload)
            elif message.type == "analyze_code_quality":
                return await self.analyze_code_quality(message.payload)
            else:
                logger.warning(f"Unknown message type: {message.type}")
                return False
        except Exception as e:
            logger.error(f"Error processing message {message.id}: {e}")
            self.error_count += 1
            return False
        finally:
            self.processed_count += 1
    
    async def analyze_pr_complexity(self, payload: dict) -> bool:
        """Analyze pull request complexity."""
        pr_id = payload["pull_request_id"]
        
        # Get PR data from GitHub
        pr_data = await self.github_client.get_pull(
            payload["repository"], 
            payload["pr_number"]
        )
        
        # Analyze complexity
        complexity_score = await self.calculate_complexity(pr_data)
        
        # Store results in database
        async with self.db_manager.get_session() as session:
            analysis_repo = AnalysisRepository(session)
            await analysis_repo.create(
                pull_request_id=pr_id,
                analysis_type="complexity",
                score=complexity_score,
                metadata={"files_changed": len(pr_data["files"])}
            )
        
        return True
    
    async def calculate_complexity(self, pr_data: dict) -> float:
        """Calculate complexity score for a PR."""
        # Custom complexity calculation logic
        files_changed = len(pr_data.get("files", []))
        lines_changed = pr_data.get("additions", 0) + pr_data.get("deletions", 0)
        
        # Simple complexity formula
        complexity = (files_changed * 0.3) + (lines_changed * 0.001)
        return min(complexity, 10.0)  # Cap at 10.0
```

### Worker Configuration

```python
from src.workers.config import WorkerConfig

@dataclass
class WorkerConfig:
    """Configuration for worker behavior."""
    
    max_concurrent_messages: int = 1
    retry_delay_seconds: int = 60
    health_check_interval: int = 30
    graceful_shutdown_timeout: int = 30
    dead_letter_queue: bool = True
    metrics_enabled: bool = True

class ConfigurableWorker(BaseWorker):
    """Worker with configurable behavior."""
    
    def __init__(self, name: str, queue_manager: QueueManager, config: WorkerConfig):
        super().__init__(name, queue_manager)
        self.config = config
        self.semaphore = asyncio.Semaphore(config.max_concurrent_messages)
    
    async def process_message_with_config(self, message: WorkerMessage) -> bool:
        """Process message with configuration constraints."""
        async with self.semaphore:  # Limit concurrent processing
            return await self.process_message(message)
    
    async def start(self):
        """Start worker with configuration."""
        # Start health check task
        health_task = asyncio.create_task(self.health_check_loop())
        
        # Start main processing loop
        await super().start()
        
        # Cancel health check
        health_task.cancel()
    
    async def health_check_loop(self):
        """Periodic health check."""
        while self.is_running:
            try:
                await self.perform_health_check()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
```

## Error Handling

### Retry Mechanisms

```python
from src.workers.retry import RetryPolicy, ExponentialBackoff

class RetryPolicy:
    """Policy for message retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: int = 60,
        max_delay: int = 3600,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def should_retry(self, message: WorkerMessage, error: Exception) -> bool:
        """Determine if message should be retried."""
        if message.retry_count >= self.max_retries:
            return False
        
        # Don't retry certain error types
        if isinstance(error, (ValueError, TypeError)):
            return False
        
        return True
    
    def get_retry_delay(self, retry_count: int) -> int:
        """Calculate delay before retry."""
        delay = self.base_delay * (self.backoff_factor ** retry_count)
        return min(delay, self.max_delay)

class RetryableWorker(BaseWorker):
    """Worker with retry capabilities."""
    
    def __init__(self, name: str, queue_manager: QueueManager, retry_policy: RetryPolicy):
        super().__init__(name, queue_manager)
        self.retry_policy = retry_policy
    
    async def process_message(self, message: WorkerMessage) -> bool:
        """Process message with retry logic."""
        try:
            return await self.do_process_message(message)
        except Exception as e:
            if self.retry_policy.should_retry(message, e):
                await self.schedule_retry(message, e)
                return True  # Handled by retry
            else:
                await self.send_to_dead_letter_queue(message, e)
                return False
    
    async def schedule_retry(self, message: WorkerMessage, error: Exception):
        """Schedule message for retry."""
        retry_delay = self.retry_policy.get_retry_delay(message.retry_count)
        
        # Create retry message
        retry_message = WorkerMessage(
            id=message.id,
            type=message.type,
            payload=message.payload,
            priority=message.priority,
            retry_count=message.retry_count + 1,
            max_retries=message.max_retries
        )
        
        # Schedule for later processing
        await asyncio.sleep(retry_delay)
        await self.queue_manager.send_message(self.name, retry_message)
```

### Dead Letter Queue

```python
class DeadLetterQueue:
    """Handles messages that cannot be processed."""
    
    def __init__(self, queue_manager: QueueManager):
        self.queue_manager = queue_manager
        self.dlq_name = "dead_letter_queue"
    
    async def send_to_dlq(self, message: WorkerMessage, error: Exception):
        """Send failed message to dead letter queue."""
        dlq_message = WorkerMessage(
            id=f"dlq_{message.id}",
            type="dead_letter",
            payload={
                "original_message": message.__dict__,
                "error": str(error),
                "error_type": type(error).__name__,
                "failed_at": datetime.utcnow().isoformat()
            },
            priority=0  # Lowest priority
        )
        
        await self.queue_manager.send_message(self.dlq_name, dlq_message)
        logger.error(f"Message {message.id} sent to dead letter queue: {error}")
    
    async def process_dead_letters(self):
        """Process messages in dead letter queue for analysis."""
        while True:
            message = await self.queue_manager.get_message(self.dlq_name)
            if not message:
                await asyncio.sleep(60)  # Check every minute
                continue
            
            # Analyze failed message
            await self.analyze_failure(message)
            await self.queue_manager.ack_message(message.id)
```

## Monitoring and Health Checks

### Worker Metrics

```python
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class WorkerMetrics:
    """Metrics for worker monitoring."""
    
    worker_name: str
    processed_count: int = 0
    error_count: int = 0
    average_processing_time: float = 0.0
    queue_size: int = 0
    last_processed_at: datetime | None = None
    uptime_seconds: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.processed_count + self.error_count
        if total == 0:
            return 1.0
        return self.processed_count / total
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        return 1.0 - self.success_rate

class MetricsCollector:
    """Collects metrics from workers."""
    
    def __init__(self):
        self.metrics: Dict[str, WorkerMetrics] = {}
        self.start_time = datetime.utcnow()
    
    def record_message_processed(self, worker_name: str, processing_time: float):
        """Record successful message processing."""
        if worker_name not in self.metrics:
            self.metrics[worker_name] = WorkerMetrics(worker_name=worker_name)
        
        metrics = self.metrics[worker_name]
        metrics.processed_count += 1
        metrics.last_processed_at = datetime.utcnow()
        
        # Update average processing time
        total_time = metrics.average_processing_time * (metrics.processed_count - 1)
        metrics.average_processing_time = (total_time + processing_time) / metrics.processed_count
    
    def record_message_error(self, worker_name: str):
        """Record message processing error."""
        if worker_name not in self.metrics:
            self.metrics[worker_name] = WorkerMetrics(worker_name=worker_name)
        
        self.metrics[worker_name].error_count += 1
    
    def get_metrics(self, worker_name: str) -> WorkerMetrics:
        """Get metrics for a specific worker."""
        if worker_name not in self.metrics:
            return WorkerMetrics(worker_name=worker_name)
        
        metrics = self.metrics[worker_name]
        metrics.uptime_seconds = int((datetime.utcnow() - self.start_time).total_seconds())
        return metrics
```

### Health Checks

```python
class HealthChecker:
    """Performs health checks on workers."""
    
    def __init__(self, worker_manager: WorkerManager, metrics_collector: MetricsCollector):
        self.worker_manager = worker_manager
        self.metrics_collector = metrics_collector
    
    async def check_worker_health(self, worker_name: str) -> Dict[str, Any]:
        """Check health of a specific worker."""
        metrics = self.metrics_collector.get_metrics(worker_name)
        
        health_status = {
            "worker_name": worker_name,
            "healthy": True,
            "checks": {}
        }
        
        # Check if worker is running
        worker_status = await self.worker_manager.get_worker_status()
        is_running = worker_status.get(worker_name, {}).get("running", False)
        health_status["checks"]["running"] = is_running
        
        # Check recent activity
        if metrics.last_processed_at:
            time_since_last = datetime.utcnow() - metrics.last_processed_at
            inactive_too_long = time_since_last > timedelta(minutes=30)
            health_status["checks"]["recent_activity"] = not inactive_too_long
        else:
            health_status["checks"]["recent_activity"] = True  # New worker
        
        # Check error rate
        high_error_rate = metrics.error_rate > 0.1  # 10% error rate threshold
        health_status["checks"]["error_rate"] = not high_error_rate
        
        # Check queue size
        queue_size = worker_status.get(worker_name, {}).get("queue_size", 0)
        queue_too_large = queue_size > 1000
        health_status["checks"]["queue_size"] = not queue_too_large
        
        # Overall health
        health_status["healthy"] = all(health_status["checks"].values())
        
        return health_status
    
    async def check_all_workers(self) -> Dict[str, Dict[str, Any]]:
        """Check health of all workers."""
        worker_status = await self.worker_manager.get_worker_status()
        health_results = {}
        
        for worker_name in worker_status.keys():
            health_results[worker_name] = await self.check_worker_health(worker_name)
        
        return health_results
```

## Performance Optimization

### Concurrent Processing

```python
class ConcurrentWorker(BaseWorker):
    """Worker that processes multiple messages concurrently."""
    
    def __init__(self, name: str, queue_manager: QueueManager, concurrency: int = 5):
        super().__init__(name, queue_manager)
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.processing_tasks = set()
    
    async def start(self):
        """Start concurrent processing."""
        self.is_running = True
        
        # Start multiple consumer tasks
        consumers = [
            asyncio.create_task(self.consumer_loop())
            for _ in range(self.concurrency)
        ]
        
        try:
            await asyncio.gather(*consumers)
        finally:
            # Cancel any remaining processing tasks
            for task in self.processing_tasks:
                task.cancel()
            await asyncio.gather(*self.processing_tasks, return_exceptions=True)
    
    async def consumer_loop(self):
        """Individual consumer loop."""
        while self.is_running:
            try:
                message = await self.queue_manager.get_message(self.name)
                if message:
                    # Process message concurrently
                    task = asyncio.create_task(self.process_message_tracked(message))
                    self.processing_tasks.add(task)
                    task.add_done_callback(self.processing_tasks.discard)
                else:
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Consumer error: {e}")
                await asyncio.sleep(1)
    
    async def process_message_tracked(self, message: WorkerMessage):
        """Process message with tracking."""
        async with self.semaphore:
            try:
                success = await self.process_message(message)
                if success:
                    await self.queue_manager.ack_message(message.id)
                else:
                    await self.queue_manager.nack_message(message.id)
            except Exception as e:
                logger.error(f"Error processing message {message.id}: {e}")
                await self.queue_manager.nack_message(message.id)
```

### Batch Processing Optimization

```python
class OptimizedBatchWorker(BatchWorker):
    """Optimized batch worker with dynamic batch sizing."""
    
    def __init__(self, name: str, queue_manager: QueueManager):
        super().__init__(name, queue_manager, batch_size=10)
        self.processing_times = []
        self.optimal_batch_size = 10
    
    async def collect_batch(self) -> List[WorkerMessage]:
        """Collect optimal batch size based on performance."""
        batch = []
        for _ in range(self.optimal_batch_size):
            message = await self.queue_manager.get_message(self.name)
            if message:
                batch.append(message)
            else:
                break
        return batch
    
    async def process_batch(self, messages: List[WorkerMessage]) -> List[bool]:
        """Process batch and optimize batch size."""
        start_time = time.time()
        
        # Process the batch
        results = await self.do_process_batch(messages)
        
        # Record timing
        processing_time = time.time() - start_time
        self.processing_times.append(processing_time)
        
        # Keep only recent timing data
        if len(self.processing_times) > 50:
            self.processing_times = self.processing_times[-50:]
        
        # Adjust batch size based on performance
        await self.adjust_batch_size()
        
        return results
    
    async def adjust_batch_size(self):
        """Dynamically adjust batch size for optimal performance."""
        if len(self.processing_times) < 10:
            return
        
        avg_time = sum(self.processing_times[-10:]) / 10
        
        # If processing too slow, reduce batch size
        if avg_time > 5.0 and self.optimal_batch_size > 5:
            self.optimal_batch_size -= 1
        # If processing fast, increase batch size
        elif avg_time < 2.0 and self.optimal_batch_size < 50:
            self.optimal_batch_size += 1
```

## PR Monitor Worker Patterns (Issue #48 - Implemented)

### Data-Driven Processing

The PR Monitor Worker implementation provides advanced patterns for high-volume data processing with performance optimization:

```python
from src.workers.monitor import (
    PRProcessor, ProcessorConfig, ProcessingMode,
    DiscoveryResult, CheckRunDiscovery, StateChangeEvent
)

class ProductionPRMonitorWorker(BaseWorker):
    """Production-ready PR monitor with comprehensive capabilities."""
    
    def __init__(self, name: str, queue_manager: QueueManager, config: dict):
        super().__init__(name, queue_manager)
        
        # Initialize processor with optimized configuration
        processor_config = ProcessorConfig(
            max_concurrent_repos=config.get("max_concurrent_repos", 10),
            batch_size=config.get("batch_size", 25),
            memory_limit_mb=config.get("memory_limit_mb", 2048),
            enable_metrics=True,
            enable_recovery_mode=True
        )
        
        self.pr_processor = PRProcessor(
            github_client=github_client,
            session=database_session,
            cache_manager=cache_manager,
            config=processor_config
        )
    
    async def process_message(self, message: WorkerMessage) -> bool:
        """Process with comprehensive error handling and metrics."""
        message_type = message.type
        payload = message.payload
        
        try:
            if message_type == "bulk_repository_processing":
                return await self._handle_bulk_processing(payload)
            elif message_type == "single_repository_processing":
                return await self._handle_single_repository(payload)
            elif message_type == "dry_run_processing":
                return await self._handle_dry_run(payload)
            else:
                logger.warning(f"Unsupported message type: {message_type}")
                return False
                
        except Exception as e:
            logger.error(f"Processing failed for {message_type}: {e}", exc_info=True)
            
            # Send failure notification
            await self._notify_processing_failure(message, e)
            return False
    
    async def _handle_bulk_processing(self, payload: dict) -> bool:
        """Handle bulk repository processing with monitoring."""
        repository_ids = [UUID(rid) for rid in payload.get("repository_ids", [])]
        mode = ProcessingMode(payload.get("mode", "incremental"))
        
        # Process repositories with full orchestration
        session = await self.pr_processor.process_repositories(
            repositories=repository_ids,
            mode=mode
        )
        
        # Log comprehensive results
        logger.info(
            f"Bulk processing completed: "
            f"success_rate={session.success_rate:.1f}%, "
            f"repositories_processed={session.processed_repositories}, "
            f"prs_discovered={session.total_prs_discovered}, "
            f"duration={session.duration_seconds:.1f}s"
        )
        
        # Consider successful if >80% repositories processed
        success = session.success_rate >= 80.0
        
        # Send metrics to monitoring system
        await self._send_processing_metrics(session)
        
        return success
    
    async def _handle_single_repository(self, payload: dict) -> bool:
        """Handle single repository processing with detailed logging."""
        repository_id = UUID(payload["repository_id"])
        since_iso = payload.get("since")
        since = datetime.fromisoformat(since_iso) if since_iso else None
        
        result = await self.pr_processor.process_single_repository(
            repository_id=repository_id,
            since=since
        )
        
        logger.info(
            f"Repository processing: {result.repository_name} - "
            f"{'SUCCESS' if result.success else 'FAILED'}, "
            f"PRs={result.prs_discovered}, "
            f"Checks={result.check_runs_discovered}, "
            f"Changes={result.state_changes_detected}, "
            f"Time={result.processing_time_seconds:.2f}s"
        )
        
        return result.success
    
    async def _send_processing_metrics(self, session: ProcessingSession) -> None:
        """Send metrics to monitoring system."""
        metrics = {
            "session_id": session.session_id,
            "mode": session.mode.value,
            "success_rate": session.success_rate,
            "repositories_processed": session.processed_repositories,
            "prs_discovered": session.total_prs_discovered,
            "check_runs_discovered": session.total_check_runs_discovered,
            "duration_seconds": session.duration_seconds,
            "memory_usage_mb": session.memory_usage_mb
        }
        
        # Send to metrics collection system
        await self.queue_manager.send_message(
            "metrics_collector",
            WorkerMessage(
                id=f"metrics_{session.session_id}",
                type="processing_metrics",
                payload=metrics,
                priority=1
            )
        )
```

### High-Performance Message Formats

```python
@dataclass
class BulkRepositoryProcessingMessage:
    """Optimized message for bulk repository processing."""
    repository_ids: List[str]
    mode: str = "incremental"  # full, incremental, dry_run
    priority_repositories: List[str] = field(default_factory=list)
    performance_config: Dict[str, Any] = field(default_factory=dict)
    
    def to_worker_message(self) -> WorkerMessage:
        return WorkerMessage(
            id=f"bulk_processing_{int(datetime.now().timestamp())}",
            type="bulk_repository_processing",
            payload=asdict(self),
            priority=2  # High priority for bulk operations
        )

@dataclass
class RepositoryProcessingResultMessage:
    """Result message with comprehensive metrics."""
    session_id: str
    repository_results: List[Dict[str, Any]]
    processing_metrics: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    
    def to_worker_message(self) -> WorkerMessage:
        return WorkerMessage(
            id=f"processing_result_{self.session_id}",
            type="processing_result",
            payload=asdict(self),
            priority=1
        )
```

### Performance Monitoring Integration

```python
class MonitoringPRWorker(BaseWorker):
    """PR Worker with integrated performance monitoring."""
    
    def __init__(self, name: str, queue_manager: QueueManager, 
                 metrics_collector: MetricsCollector):
        super().__init__(name, queue_manager)
        self.metrics = metrics_collector
        self.processing_times = []
    
    async def process_message(self, message: WorkerMessage) -> bool:
        """Process with performance tracking."""
        start_time = time.time()
        
        try:
            # Process the message
            result = await self._process_pr_message(message)
            
            # Record success metrics
            processing_time = time.time() - start_time
            self.metrics.record_message_processed(self.name, processing_time)
            
            # Update processing time history
            self.processing_times.append(processing_time)
            if len(self.processing_times) > 100:
                self.processing_times = self.processing_times[-100:]
            
            return result
            
        except Exception as e:
            # Record error metrics
            processing_time = time.time() - start_time
            self.metrics.record_message_error(self.name)
            
            logger.error(f"Processing error after {processing_time:.2f}s: {e}")
            return False
    
    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics."""
        if not self.processing_times:
            return {"status": "no_data"}
        
        times = self.processing_times
        return {
            "average_processing_time": sum(times) / len(times),
            "min_processing_time": min(times),
            "max_processing_time": max(times),
            "recent_processing_times": times[-10:],
            "total_processed": len(times)
        }
```

## Best Practices

### Worker Design

```python
# ✅ Use dependency injection for testability
class GoodWorker(BaseWorker):
    def __init__(self, name: str, queue_manager: QueueManager, github_client: GitHubClient):
        super().__init__(name, queue_manager)
        self.github_client = github_client

# ❌ Don't create dependencies inside worker
# class BadWorker(BaseWorker):
#     def __init__(self, name: str, queue_manager: QueueManager):
#         super().__init__(name, queue_manager)
#         self.github_client = GitHubClient(...)  # Hard to test

# ✅ Handle errors gracefully
async def process_message(self, message: WorkerMessage) -> bool:
    try:
        return await self.do_work(message)
    except SpecificError as e:
        logger.warning(f"Expected error: {e}")
        return False  # Don't retry
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise  # Let retry mechanism handle it

# ❌ Don't let errors crash the worker
# async def process_message(self, message: WorkerMessage) -> bool:
#     return await self.do_work(message)  # Unhandled exceptions
```

### Message Design

```python
# ✅ Use structured message formats
@dataclass
class ProcessPRMessage:
    repository_id: str
    pr_number: int
    force_refresh: bool = False

# ✅ Include correlation IDs for tracing
message = WorkerMessage(
    id=f"process_pr_{pr_id}_{uuid.uuid4()}",
    type="process_pr",
    payload={"correlation_id": correlation_id, **data}
)

# ❌ Don't use generic message formats
# message = WorkerMessage(
#     id="msg",
#     type="work",
#     payload={"stuff": "things"}  # Unclear structure
# )
```

### Resource Management

```python
# ✅ Use connection pooling
class DatabaseWorker(BaseWorker):
    def __init__(self, name: str, queue_manager: QueueManager, db_manager: DatabaseConnectionManager):
        super().__init__(name, queue_manager)
        self.db_manager = db_manager  # Reuse connection pool
    
    async def process_message(self, message: WorkerMessage) -> bool:
        async with self.db_manager.get_session() as session:
            # Use pooled connection
            pass

# ✅ Implement graceful shutdown
async def shutdown(self):
    self.is_running = False
    # Wait for current messages to finish
    await asyncio.sleep(5)
    # Close resources
    await self.cleanup_resources()
```

### Monitoring

```python
# ✅ Include comprehensive logging
logger.info(f"Processing message {message.id} of type {message.type}")
logger.debug(f"Message payload: {message.payload}")

# ✅ Track metrics
self.metrics.record_message_processed(processing_time)

# ✅ Implement health checks
async def health_check(self) -> bool:
    # Check dependencies are accessible
    return await self.github_client.health_check()
```

---

**Next Steps:**
- 📖 **Examples**: Check [Worker Examples](examples/worker-implementations.py) for complete working code
- 🔧 **Configuration**: See [Configuration API](configuration-api.md) for worker configuration
- 📬 **Webhooks**: Review [Webhook Interfaces](webhooks.md) for event-driven patterns