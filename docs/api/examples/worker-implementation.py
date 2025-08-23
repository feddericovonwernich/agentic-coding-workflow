#!/usr/bin/env python3
"""
Worker Implementation Examples

This module demonstrates comprehensive usage of the worker interfaces
for building custom workers and processing systems.
"""

import asyncio
import contextlib
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    """Message priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class WorkerMessage:
    """Base message structure for worker communication."""

    id: str
    type: str
    payload: dict[str, Any]
    priority: MessagePriority
    created_at: datetime
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["priority"] = self.priority.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkerMessage":
        """Create from dictionary."""
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["priority"] = MessagePriority(data["priority"])
        return cls(**data)


class QueueManager(ABC):
    """Abstract base class for queue management."""

    @abstractmethod
    async def enqueue(
        self, message: WorkerMessage, queue_name: str = "default"
    ) -> bool:
        """Add message to queue."""
        pass

    @abstractmethod
    async def dequeue(self, queue_name: str = "default") -> WorkerMessage | None:
        """Get message from queue."""
        pass

    @abstractmethod
    async def get_queue_size(self, queue_name: str = "default") -> int:
        """Get current queue size."""
        pass

    @abstractmethod
    async def ack_message(
        self, message: WorkerMessage, queue_name: str = "default"
    ) -> bool:
        """Acknowledge message processing."""
        pass

    @abstractmethod
    async def nack_message(
        self, message: WorkerMessage, queue_name: str = "default"
    ) -> bool:
        """Negative acknowledge (retry) message."""
        pass


class MemoryQueueManager(QueueManager):
    """In-memory queue manager for testing and development."""

    def __init__(self):
        self.queues: dict[str, list[WorkerMessage]] = {}
        self.processing: dict[str, list[WorkerMessage]] = {}

    async def enqueue(
        self, message: WorkerMessage, queue_name: str = "default"
    ) -> bool:
        """Add message to queue."""
        if queue_name not in self.queues:
            self.queues[queue_name] = []

        # Insert based on priority
        self.queues[queue_name].append(message)
        self.queues[queue_name].sort(
            key=lambda m: list(MessagePriority).index(m.priority)
        )

        logger.debug(f"Enqueued message {message.id} to {queue_name}")
        return True

    async def dequeue(self, queue_name: str = "default") -> WorkerMessage | None:
        """Get message from queue."""
        if queue_name not in self.queues or not self.queues[queue_name]:
            return None

        message = self.queues[queue_name].pop(0)

        # Move to processing
        if queue_name not in self.processing:
            self.processing[queue_name] = []
        self.processing[queue_name].append(message)

        logger.debug(f"Dequeued message {message.id} from {queue_name}")
        return message

    async def get_queue_size(self, queue_name: str = "default") -> int:
        """Get current queue size."""
        return len(self.queues.get(queue_name, []))

    async def ack_message(
        self, message: WorkerMessage, queue_name: str = "default"
    ) -> bool:
        """Acknowledge message processing."""
        if queue_name in self.processing:
            self.processing[queue_name] = [
                m for m in self.processing[queue_name] if m.id != message.id
            ]
        logger.debug(f"Acknowledged message {message.id}")
        return True

    async def nack_message(
        self, message: WorkerMessage, queue_name: str = "default"
    ) -> bool:
        """Negative acknowledge (retry) message."""
        if queue_name in self.processing:
            self.processing[queue_name] = [
                m for m in self.processing[queue_name] if m.id != message.id
            ]

        # Retry if under limit
        if message.retry_count < message.max_retries:
            message.retry_count += 1
            await self.enqueue(message, queue_name)
            logger.debug(
                f"Retrying message {message.id} (attempt {message.retry_count})"
            )
        else:
            logger.warning(f"Message {message.id} exceeded max retries")

        return True


class BaseWorker(ABC):
    """Abstract base class for workers."""

    def __init__(
        self,
        name: str,
        queue_manager: QueueManager,
        input_queue: str = "default",
        output_queue: str | None = None,
        batch_size: int = 1,
        poll_interval: float = 1.0,
    ):
        self.name = name
        self.queue_manager = queue_manager
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.running = False
        self.processed_count = 0
        self.error_count = 0
        self.start_time: datetime | None = None

    @abstractmethod
    async def process_message(self, message: WorkerMessage) -> bool:
        """Process a single message. Return True if successful."""
        pass

    async def process_batch(self, messages: list[WorkerMessage]) -> list[bool]:
        """Process a batch of messages. Override for batch optimization."""
        results = []
        for message in messages:
            result = await self.process_message(message)
            results.append(result)
        return results

    async def start(self):
        """Start the worker."""
        self.running = True
        self.start_time = datetime.utcnow()
        logger.info(f"Starting worker: {self.name}")

        try:
            while self.running:
                await self._process_cycle()
                await asyncio.sleep(self.poll_interval)

        except Exception as e:
            logger.error(f"Worker {self.name} crashed: {e}")
            raise

        finally:
            logger.info(f"Worker {self.name} stopped")

    async def stop(self):
        """Stop the worker."""
        self.running = False
        logger.info(f"Stopping worker: {self.name}")

    async def _process_cycle(self):
        """Single processing cycle."""
        # Get messages from queue
        messages = []
        for _ in range(self.batch_size):
            message = await self.queue_manager.dequeue(self.input_queue)
            if message:
                messages.append(message)
            else:
                break

        if not messages:
            return

        # Process messages
        if len(messages) == 1:
            # Single message processing
            message = messages[0]
            try:
                success = await self.process_message(message)
                await self._handle_result(message, success)
            except Exception as e:
                logger.error(f"Error processing message {message.id}: {e}")
                await self._handle_result(message, False)
        else:
            # Batch processing
            try:
                results = await self.process_batch(messages)
                for message, success in zip(messages, results, strict=False):
                    await self._handle_result(message, success)
            except Exception as e:
                logger.error(f"Error processing batch: {e}")
                for message in messages:
                    await self._handle_result(message, False)

    async def _handle_result(self, message: WorkerMessage, success: bool):
        """Handle processing result."""
        if success:
            await self.queue_manager.ack_message(message, self.input_queue)
            self.processed_count += 1

            # Send to output queue if configured
            if self.output_queue:
                result_message = WorkerMessage(
                    id=str(uuid.uuid4()),
                    type=f"{message.type}_result",
                    payload={
                        "original_message_id": message.id,
                        "processed_by": self.name,
                        "result": "success",
                    },
                    priority=message.priority,
                    created_at=datetime.utcnow(),
                )
                await self.queue_manager.enqueue(result_message, self.output_queue)
        else:
            await self.queue_manager.nack_message(message, self.input_queue)
            self.error_count += 1

    def get_stats(self) -> dict[str, Any]:
        """Get worker statistics."""
        uptime = (
            datetime.utcnow() - self.start_time if self.start_time else timedelta(0)
        )

        return {
            "name": self.name,
            "running": self.running,
            "uptime_seconds": uptime.total_seconds(),
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "success_rate": (
                self.processed_count / (self.processed_count + self.error_count)
                if (self.processed_count + self.error_count) > 0
                else 0
            ),
        }


class PRAnalyzerWorker(BaseWorker):
    """Example worker for analyzing pull requests."""

    async def process_message(self, message: WorkerMessage) -> bool:
        """Analyze a pull request."""
        if message.type != "pr_analysis":
            logger.warning(f"Unexpected message type: {message.type}")
            return False

        payload = message.payload
        pr_id = payload.get("pr_id")
        repository = payload.get("repository")
        head_sha = payload.get("head_sha")

        logger.info(f"Analyzing PR {pr_id} in {repository} (SHA: {head_sha})")

        try:
            # Simulate analysis work
            await asyncio.sleep(0.5)  # Simulate processing time

            # Simulate different outcomes
            import random

            if random.random() < 0.8:  # 80% success rate
                analysis_result = {
                    "pr_id": pr_id,
                    "repository": repository,
                    "head_sha": head_sha,
                    "issues_found": random.randint(0, 5),
                    "severity": random.choice(["low", "medium", "high"]),
                    "recommendations": [
                        "Fix linting issues",
                        "Add missing tests",
                        "Update documentation",
                    ][: random.randint(1, 3)],
                }

                issues_count = analysis_result["issues_found"]
                logger.info(f"Analysis complete for PR {pr_id}: {issues_count} issues")
                return True
            else:
                logger.warning(f"Analysis failed for PR {pr_id}")
                return False

        except Exception as e:
            logger.error(f"Error analyzing PR {pr_id}: {e}")
            return False


class FixApplicatorWorker(BaseWorker):
    """Example worker for applying fixes to pull requests."""

    async def process_message(self, message: WorkerMessage) -> bool:
        """Apply fixes to a pull request."""
        if message.type != "apply_fixes":
            logger.warning(f"Unexpected message type: {message.type}")
            return False

        payload = message.payload
        pr_id = payload.get("pr_id")
        fixes = payload.get("fixes", [])

        logger.info(f"Applying {len(fixes)} fixes to PR {pr_id}")

        try:
            # Simulate fix application
            for i, fix in enumerate(fixes, 1):
                logger.info(f"Applying fix {i}/{len(fixes)}: {fix}")
                await asyncio.sleep(0.2)  # Simulate processing time

            # Simulate success/failure
            import random

            if random.random() < 0.9:  # 90% success rate
                logger.info(f"Successfully applied all fixes to PR {pr_id}")
                return True
            else:
                logger.warning(f"Failed to apply fixes to PR {pr_id}")
                return False

        except Exception as e:
            logger.error(f"Error applying fixes to PR {pr_id}: {e}")
            return False


class NotificationWorker(BaseWorker):
    """Example worker for sending notifications."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.notification_channels = {
            "email": self._send_email,
            "slack": self._send_slack,
            "telegram": self._send_telegram,
        }

    async def process_message(self, message: WorkerMessage) -> bool:
        """Send a notification."""
        if message.type != "notification":
            logger.warning(f"Unexpected message type: {message.type}")
            return False

        payload = message.payload
        channel = payload.get("channel")
        recipient = payload.get("recipient")
        content = payload.get("content")

        logger.info(f"Sending {channel} notification to {recipient}")

        try:
            if channel in self.notification_channels:
                return await self.notification_channels[channel](recipient, content)
            else:
                logger.error(f"Unknown notification channel: {channel}")
                return False

        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False

    async def _send_email(self, recipient: str, content: str) -> bool:
        """Simulate sending email."""
        await asyncio.sleep(0.1)
        logger.info(f"Email sent to {recipient}: {content[:50]}...")
        return True

    async def _send_slack(self, recipient: str, content: str) -> bool:
        """Simulate sending Slack message."""
        await asyncio.sleep(0.1)
        logger.info(f"Slack message sent to {recipient}: {content[:50]}...")
        return True

    async def _send_telegram(self, recipient: str, content: str) -> bool:
        """Simulate sending Telegram message."""
        await asyncio.sleep(0.1)
        logger.info(f"Telegram message sent to {recipient}: {content[:50]}...")
        return True


class BatchProcessingWorker(BaseWorker):
    """Example worker demonstrating batch processing optimization."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, batch_size=5, **kwargs)  # Process 5 messages at once

    async def process_batch(self, messages: list[WorkerMessage]) -> list[bool]:
        """Process messages in batch for better efficiency."""
        logger.info(f"Processing batch of {len(messages)} messages")

        # Simulate batch processing (e.g., bulk database operations)
        await asyncio.sleep(0.5)  # Simulate batch work

        # Group messages by type for more efficient processing
        grouped = {}
        for message in messages:
            msg_type = message.type
            if msg_type not in grouped:
                grouped[msg_type] = []
            grouped[msg_type].append(message)

        results = []
        for msg_type, group in grouped.items():
            logger.info(f"Processing {len(group)} messages of type {msg_type}")

            # Simulate type-specific batch processing
            for _message in group:
                # Simulate 95% success rate
                import random

                success = random.random() < 0.95
                results.append(success)

        logger.info(
            f"Batch processing complete: {sum(results)}/{len(results)} successful"
        )
        return results


class WorkerManager:
    """Manage multiple workers."""

    def __init__(self, queue_manager: QueueManager):
        self.queue_manager = queue_manager
        self.workers: dict[str, BaseWorker] = {}
        self.worker_tasks: dict[str, asyncio.Task] = {}

    def register_worker(self, worker: BaseWorker):
        """Register a worker."""
        self.workers[worker.name] = worker
        logger.info(f"Registered worker: {worker.name}")

    async def start_worker(self, worker_name: str):
        """Start a specific worker."""
        if worker_name not in self.workers:
            raise ValueError(f"Worker {worker_name} not found")

        worker = self.workers[worker_name]
        task = asyncio.create_task(worker.start())
        self.worker_tasks[worker_name] = task

        logger.info(f"Started worker: {worker_name}")

    async def stop_worker(self, worker_name: str):
        """Stop a specific worker."""
        if worker_name in self.workers:
            await self.workers[worker_name].stop()

        if worker_name in self.worker_tasks:
            self.worker_tasks[worker_name].cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.worker_tasks[worker_name]
            del self.worker_tasks[worker_name]

        logger.info(f"Stopped worker: {worker_name}")

    async def start_all_workers(self):
        """Start all registered workers."""
        for worker_name in self.workers:
            await self.start_worker(worker_name)

    async def stop_all_workers(self):
        """Stop all workers."""
        for worker_name in list(self.worker_tasks.keys()):
            await self.stop_worker(worker_name)

    def get_worker_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all workers."""
        return {
            worker_name: worker.get_stats()
            for worker_name, worker in self.workers.items()
        }

    async def get_queue_stats(self) -> dict[str, int]:
        """Get queue statistics."""
        queues = ["analysis", "fixes", "notifications", "results"]
        stats = {}
        for queue_name in queues:
            stats[queue_name] = await self.queue_manager.get_queue_size(queue_name)
        return stats


async def example_basic_worker_usage():
    """Example: Basic worker usage patterns."""
    logger.info("=== Basic Worker Usage ===")

    # Create queue manager
    queue_manager = MemoryQueueManager()

    # Create and start a worker
    analyzer = PRAnalyzerWorker(
        name="pr-analyzer-1",
        queue_manager=queue_manager,
        input_queue="analysis",
        output_queue="results",
    )

    # Start worker in background
    worker_task = asyncio.create_task(analyzer.start())

    # Give worker time to start
    await asyncio.sleep(0.1)

    # Send some messages
    messages = [
        WorkerMessage(
            id=str(uuid.uuid4()),
            type="pr_analysis",
            payload={"pr_id": "123", "repository": "owner/repo", "head_sha": "abc123"},
            priority=MessagePriority.MEDIUM,
            created_at=datetime.utcnow(),
        ),
        WorkerMessage(
            id=str(uuid.uuid4()),
            type="pr_analysis",
            payload={"pr_id": "124", "repository": "owner/repo", "head_sha": "def456"},
            priority=MessagePriority.HIGH,
            created_at=datetime.utcnow(),
        ),
    ]

    # Enqueue messages
    for message in messages:
        await queue_manager.enqueue(message, "analysis")
        logger.info(f"Enqueued message: {message.id}")

    # Let worker process messages
    await asyncio.sleep(2)

    # Check results
    stats = analyzer.get_stats()
    logger.info(f"Worker stats: {stats}")

    # Stop worker
    await analyzer.stop()
    worker_task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await worker_task


async def example_multi_worker_pipeline():
    """Example: Multi-worker pipeline processing."""
    logger.info("=== Multi-Worker Pipeline ===")

    # Create queue manager
    queue_manager = MemoryQueueManager()

    # Create worker manager
    manager = WorkerManager(queue_manager)

    # Register workers for different stages
    analyzer = PRAnalyzerWorker(
        name="analyzer",
        queue_manager=queue_manager,
        input_queue="analysis",
        output_queue="fixes",
    )

    fixer = FixApplicatorWorker(
        name="fixer",
        queue_manager=queue_manager,
        input_queue="fixes",
        output_queue="notifications",
    )

    notifier = NotificationWorker(
        name="notifier", queue_manager=queue_manager, input_queue="notifications"
    )

    # Register workers
    manager.register_worker(analyzer)
    manager.register_worker(fixer)
    manager.register_worker(notifier)

    # Start all workers
    await manager.start_all_workers()

    # Give workers time to start
    await asyncio.sleep(0.1)

    # Create initial analysis message
    analysis_message = WorkerMessage(
        id=str(uuid.uuid4()),
        type="pr_analysis",
        payload={
            "pr_id": "456",
            "repository": "owner/test-repo",
            "head_sha": "pipeline123",
        },
        priority=MessagePriority.HIGH,
        created_at=datetime.utcnow(),
    )

    # Start the pipeline
    await queue_manager.enqueue(analysis_message, "analysis")
    logger.info("Started pipeline with analysis message")

    # Monitor pipeline progress
    for i in range(10):
        await asyncio.sleep(1)

        # Get queue stats
        queue_stats = await manager.get_queue_stats()
        manager.get_worker_stats()

        logger.info(f"Pipeline status (t+{i + 1}s):")
        logger.info(f"  Queues: {queue_stats}")

        # Check if pipeline is complete
        if all(size == 0 for size in queue_stats.values()):
            logger.info("Pipeline completed!")
            break

    # Final stats
    final_stats = manager.get_worker_stats()
    logger.info("Final worker statistics:")
    for worker_name, stats in final_stats.items():
        processed = stats["processed_count"]
        errors = stats["error_count"]
        logger.info(f"  {worker_name}: {processed} processed, {errors} errors")

    # Stop all workers
    await manager.stop_all_workers()


async def example_batch_processing():
    """Example: Batch processing optimization."""
    logger.info("=== Batch Processing Example ===")

    queue_manager = MemoryQueueManager()

    # Create batch processing worker
    batch_worker = BatchProcessingWorker(
        name="batch-processor",
        queue_manager=queue_manager,
        input_queue="batch_work",
        batch_size=5,  # Process 5 messages at once
    )

    # Start worker
    worker_task = asyncio.create_task(batch_worker.start())
    await asyncio.sleep(0.1)

    # Generate multiple messages
    messages = []
    for i in range(12):  # 12 messages will be processed in batches of 5
        message = WorkerMessage(
            id=str(uuid.uuid4()),
            type="batch_item",
            payload={"item_id": i, "data": f"item_{i}"},
            priority=MessagePriority.MEDIUM,
            created_at=datetime.utcnow(),
        )
        messages.append(message)

    # Enqueue all messages
    for message in messages:
        await queue_manager.enqueue(message, "batch_work")

    logger.info(f"Enqueued {len(messages)} messages for batch processing")

    # Wait for processing
    await asyncio.sleep(3)

    # Check stats
    stats = batch_worker.get_stats()
    logger.info(f"Batch processing stats: {stats}")

    # Stop worker
    await batch_worker.stop()
    worker_task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await worker_task


async def example_error_handling_and_retries():
    """Example: Error handling and retry mechanisms."""
    logger.info("=== Error Handling and Retries ===")

    class FailingWorker(BaseWorker):
        """Worker that fails sometimes to demonstrate retry logic."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.attempt_count = 0

        async def process_message(self, message: WorkerMessage) -> bool:
            self.attempt_count += 1

            # Fail first 2 attempts, succeed on 3rd
            if self.attempt_count <= 2:
                logger.warning(f"Simulated failure on attempt {self.attempt_count}")
                return False
            else:
                logger.info(f"Success on attempt {self.attempt_count}")
                return True

    queue_manager = MemoryQueueManager()

    failing_worker = FailingWorker(
        name="failing-worker", queue_manager=queue_manager, input_queue="test_queue"
    )

    # Start worker
    worker_task = asyncio.create_task(failing_worker.start())
    await asyncio.sleep(0.1)

    # Create message with retry configuration
    message = WorkerMessage(
        id=str(uuid.uuid4()),
        type="test_message",
        payload={"test": "data"},
        priority=MessagePriority.MEDIUM,
        created_at=datetime.utcnow(),
        max_retries=3,  # Allow 3 retries
    )

    await queue_manager.enqueue(message, "test_queue")
    logger.info("Enqueued message that will fail initially")

    # Wait for processing with retries
    await asyncio.sleep(5)

    # Check final stats
    stats = failing_worker.get_stats()
    logger.info(f"Error handling stats: {stats}")

    # Stop worker
    await failing_worker.stop()
    worker_task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await worker_task


async def comprehensive_worker_example():
    """Comprehensive example demonstrating all worker patterns."""
    logger.info("Starting comprehensive worker examples...")

    try:
        await example_basic_worker_usage()
        await example_multi_worker_pipeline()
        await example_batch_processing()
        await example_error_handling_and_retries()

        logger.info("All worker examples completed successfully!")

    except Exception as e:
        logger.error(f"Worker examples failed: {e}")


if __name__ == "__main__":
    # Run comprehensive examples
    asyncio.run(comprehensive_worker_example())
