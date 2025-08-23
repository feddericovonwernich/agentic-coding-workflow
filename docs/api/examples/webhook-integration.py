#!/usr/bin/env python3
"""
Webhook Integration Examples

This module demonstrates comprehensive webhook handling including
GitHub webhook processing, outgoing notifications, and event routing.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import aiohttp
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Event priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class WebhookEvent:
    """Webhook event data structure."""

    event_type: str
    payload: dict[str, Any]
    priority: EventPriority
    source: str
    timestamp: datetime
    metadata: dict[str, Any] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["priority"] = self.priority.value
        return data


class WebhookSecurity:
    """Webhook security utilities."""

    @staticmethod
    def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
        """Verify GitHub webhook signature."""
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    @staticmethod
    def generate_signature(
        payload: bytes, secret: str, algorithm: str = "sha256"
    ) -> str:
        """Generate webhook signature."""
        hasher = getattr(hashlib, algorithm)
        return hmac.new(secret.encode(), payload, hasher).hexdigest()


class GitHubWebhookProcessor:
    """Process GitHub webhook events."""

    def __init__(self, secret_token: str):
        self.secret_token = secret_token
        self.supported_events = {
            "pull_request",
            "check_run",
            "check_suite",
            "status",
            "push",
        }

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook signature."""
        return WebhookSecurity.verify_github_signature(
            payload, signature, self.secret_token
        )

    async def process_event(
        self, event_type: str, payload: dict[str, Any], delivery_id: str
    ) -> bool:
        """Process webhook event."""
        try:
            logger.info(f"Processing GitHub event: {event_type} (ID: {delivery_id})")

            if event_type not in self.supported_events:
                logger.info(f"Ignoring unsupported event: {event_type}")
                return True

            # Route to specific handler
            if event_type == "pull_request":
                return await self._handle_pull_request(payload, delivery_id)
            elif event_type == "check_run":
                return await self._handle_check_run(payload, delivery_id)
            elif event_type == "check_suite":
                return await self._handle_check_suite(payload, delivery_id)
            elif event_type == "status":
                return await self._handle_status(payload, delivery_id)
            elif event_type == "push":
                return await self._handle_push(payload, delivery_id)

            return True

        except Exception as e:
            logger.error(f"Error processing webhook {delivery_id}: {e}")
            return False

    async def _handle_pull_request(
        self, payload: dict[str, Any], delivery_id: str
    ) -> bool:
        """Handle pull request webhook events."""
        action = payload.get("action")
        pr_data = payload.get("pull_request", {})
        repository = payload.get("repository", {})

        repo_name = repository.get("full_name")
        pr_number = pr_data.get("number")
        logger.info(f"PR Event: {action} - PR #{pr_number} in {repo_name}")

        # Extract relevant data
        pr_info = {
            "id": pr_data.get("id"),
            "number": pr_data.get("number"),
            "title": pr_data.get("title"),
            "state": pr_data.get("state"),
            "author": pr_data.get("user", {}).get("login"),
            "head_sha": pr_data.get("head", {}).get("sha"),
            "base_sha": pr_data.get("base", {}).get("sha"),
            "repository": repository.get("full_name"),
            "action": action,
        }

        # Process based on action
        if action == "opened":
            await self._handle_pr_opened(pr_info, delivery_id)
        elif action == "synchronize":
            await self._handle_pr_updated(pr_info, delivery_id)
        elif action == "closed":
            await self._handle_pr_closed(pr_info, delivery_id)
        elif action == "reopened":
            await self._handle_pr_reopened(pr_info, delivery_id)

        return True

    async def _handle_pr_opened(self, pr_info: dict[str, Any], delivery_id: str):
        """Handle PR opened event."""
        logger.info(f"New PR opened: #{pr_info['number']} - {pr_info['title']}")

        # Simulate adding to processing queue
        queue_message = {
            "type": "pr_analysis",
            "pr_id": pr_info["id"],
            "repository": pr_info["repository"],
            "head_sha": pr_info["head_sha"],
            "priority": "medium",
            "webhook_delivery_id": delivery_id,
        }

        logger.info(f"Queued PR for analysis: {queue_message}")

    async def _handle_pr_updated(self, pr_info: dict[str, Any], delivery_id: str):
        """Handle PR synchronize (updated) event."""
        logger.info(
            f"PR updated: #{pr_info['number']} - new SHA: {pr_info['head_sha']}"
        )

        # Check if we need to re-analyze
        queue_message = {
            "type": "pr_reanalysis",
            "pr_id": pr_info["id"],
            "repository": pr_info["repository"],
            "head_sha": pr_info["head_sha"],
            "priority": "high",  # Updated PRs get higher priority
            "webhook_delivery_id": delivery_id,
        }

        logger.info(f"Queued PR for re-analysis: {queue_message}")

    async def _handle_pr_closed(self, pr_info: dict[str, Any], delivery_id: str):
        """Handle PR closed event."""
        merged = pr_info.get("merged", False)
        status = "merged" if merged else "closed"

        logger.info(f"PR {status}: #{pr_info['number']}")

        # Clean up any pending analysis
        cleanup_message = {
            "type": "pr_cleanup",
            "pr_id": pr_info["id"],
            "repository": pr_info["repository"],
            "final_status": status,
            "webhook_delivery_id": delivery_id,
        }

        logger.info(f"Queued PR for cleanup: {cleanup_message}")

    async def _handle_pr_reopened(self, pr_info: dict[str, Any], delivery_id: str):
        """Handle PR reopened event."""
        logger.info(f"PR reopened: #{pr_info['number']}")

        # Treat like a new PR
        await self._handle_pr_opened(pr_info, delivery_id)

    async def _handle_check_run(
        self, payload: dict[str, Any], delivery_id: str
    ) -> bool:
        """Handle check run webhook events."""
        action = payload.get("action")
        check_run = payload.get("check_run", {})
        repository = payload.get("repository", {})

        repo_name = repository.get("full_name")
        check_name = check_run.get("name")
        logger.info(f"Check Run Event: {action} - {check_name} in {repo_name}")

        if action == "completed":
            check_info = {
                "id": check_run.get("id"),
                "name": check_run.get("name"),
                "status": check_run.get("status"),
                "conclusion": check_run.get("conclusion"),
                "head_sha": check_run.get("head_sha"),
                "repository": repository.get("full_name"),
                "url": check_run.get("html_url"),
            }

            # Process completed check
            if check_info["conclusion"] == "failure":
                await self._handle_failed_check(check_info, delivery_id)
            else:
                logger.info(f"Check passed: {check_info['name']}")

        return True

    async def _handle_failed_check(self, check_info: dict[str, Any], delivery_id: str):
        """Handle failed check run."""
        logger.warning(
            f"Check failed: {check_info['name']} - {check_info['conclusion']}"
        )

        # Queue for analysis and potential fixing
        analysis_message = {
            "type": "check_analysis",
            "check_id": check_info["id"],
            "check_name": check_info["name"],
            "repository": check_info["repository"],
            "head_sha": check_info["head_sha"],
            "failure_url": check_info["url"],
            "priority": "high",
            "webhook_delivery_id": delivery_id,
        }

        logger.info(f"Queued failed check for analysis: {analysis_message}")

    async def _handle_check_suite(
        self, payload: dict[str, Any], delivery_id: str
    ) -> bool:
        """Handle check suite webhook events."""
        action = payload.get("action")
        check_suite = payload.get("check_suite", {})
        repository = payload.get("repository", {})

        logger.info(f"Check Suite Event: {action} in {repository.get('full_name')}")

        if action == "completed":
            conclusion = check_suite.get("conclusion")
            if conclusion == "failure":
                logger.warning("Check suite failed - triggering analysis")

                # Trigger analysis of the entire suite
                suite_message = {
                    "type": "suite_analysis",
                    "suite_id": check_suite.get("id"),
                    "repository": repository.get("full_name"),
                    "head_sha": check_suite.get("head_sha"),
                    "conclusion": conclusion,
                    "priority": "high",
                    "webhook_delivery_id": delivery_id,
                }

                logger.info(f"Queued suite for analysis: {suite_message}")

        return True

    async def _handle_status(self, payload: dict[str, Any], delivery_id: str) -> bool:
        """Handle status webhook events."""
        state = payload.get("state")
        context = payload.get("context")
        repository = payload.get("repository", {})

        logger.info(
            f"Status Event: {context} - {state} in {repository.get('full_name')}"
        )

        if state == "failure":
            status_message = {
                "type": "status_failure",
                "context": context,
                "state": state,
                "repository": repository.get("full_name"),
                "sha": payload.get("sha"),
                "target_url": payload.get("target_url"),
                "webhook_delivery_id": delivery_id,
            }

            logger.info(f"Queued status failure for analysis: {status_message}")

        return True

    async def _handle_push(self, payload: dict[str, Any], delivery_id: str) -> bool:
        """Handle push webhook events."""
        repository = payload.get("repository", {})
        ref = payload.get("ref")
        commits = payload.get("commits", [])

        repo_name = repository.get("full_name")
        logger.info(f"Push Event: {len(commits)} commits to {ref} in {repo_name}")

        # Only process pushes to main/master branches
        if ref in ["refs/heads/main", "refs/heads/master"]:
            push_message = {
                "type": "main_branch_push",
                "repository": repository.get("full_name"),
                "ref": ref,
                "commit_count": len(commits),
                "head_commit": payload.get("head_commit", {}).get("id"),
                "webhook_delivery_id": delivery_id,
            }

            logger.info(f"Queued main branch push for processing: {push_message}")

        return True


class OutgoingWebhookClient:
    """Client for sending outgoing webhook notifications."""

    def __init__(
        self,
        webhook_url: str,
        secret: str | None = None,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        self.webhook_url = webhook_url
        self.secret = secret
        self.headers = headers or {}
        self.max_retries = max_retries
        self.timeout = timeout

    async def send_notification(
        self,
        event_type: str,
        data: dict[str, Any],
        priority: EventPriority = EventPriority.MEDIUM,
    ) -> bool:
        """Send webhook notification."""
        event = WebhookEvent(
            event_type=event_type,
            payload=data,
            priority=priority,
            source="agentic-coding-workflow",
            timestamp=datetime.utcnow(),
        )

        return await self._send_with_retry(event)

    async def _send_with_retry(self, event: WebhookEvent) -> bool:
        """Send webhook with retry logic."""

        for attempt in range(self.max_retries + 1):
            try:
                return await self._send_webhook(event)

            except Exception as e:
                if attempt < self.max_retries:
                    wait_time = 2**attempt  # Exponential backoff
                    logger.warning(
                        f"Webhook attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Webhook failed after {self.max_retries} retries: {e}"
                    )

        return False

    async def _send_webhook(self, event: WebhookEvent) -> bool:
        """Send single webhook request."""
        payload = event.to_dict()
        payload_bytes = json.dumps(payload).encode()

        headers = {**self.headers}
        headers["Content-Type"] = "application/json"

        # Add signature if secret is provided
        if self.secret:
            signature = WebhookSecurity.generate_signature(payload_bytes, self.secret)
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        async with (
            aiohttp.ClientSession() as session,
            session.post(
                self.webhook_url,
                data=payload_bytes,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response,
        ):
            if response.status == 200:
                logger.info(f"Webhook sent successfully: {event.event_type}")
                return True
            else:
                error_text = await response.text()
                logger.error(f"Webhook failed: {response.status} - {error_text}")
                return False


class WebhookEventRouter:
    """Route webhook events to appropriate handlers."""

    def __init__(self):
        self.routes: list[tuple] = []  # (pattern, handler)
        self.middleware: list[Callable] = []

    def route(self, pattern: str):
        """Decorator to register route handler."""

        def decorator(handler):
            self.routes.append((pattern, handler))
            return handler

        return decorator

    def middleware(self, middleware_func: Callable):
        """Register middleware."""
        self.middleware.append(middleware_func)
        return middleware_func

    async def route_event(self, event: WebhookEvent):
        """Route event to matching handlers."""
        try:
            # Apply middleware
            for middleware in self.middleware:
                event = await middleware(event)
                if event is None:
                    return  # Middleware stopped processing

            # Route to handlers
            for pattern, handler in self.routes:
                if self._matches_pattern(event.event_type, pattern):
                    await handler(event)

        except Exception as e:
            logger.error(f"Event routing error: {e}")

    def _matches_pattern(self, event_type: str, pattern: str) -> bool:
        """Check if event type matches pattern."""
        import fnmatch

        return fnmatch.fnmatch(event_type, pattern)


# Example FastAPI webhook endpoint
app = FastAPI(title="Webhook Integration Example")

# Initialize webhook processor
GITHUB_WEBHOOK_SECRET = "your-github-webhook-secret"
github_processor = GitHubWebhookProcessor(GITHUB_WEBHOOK_SECRET)

# Initialize outgoing webhook client
outgoing_client = OutgoingWebhookClient(
    webhook_url="https://your-monitoring-system.com/webhooks",
    secret="your-outgoing-webhook-secret",
)

# Initialize event router
router = WebhookEventRouter()


@router.middleware
async def logging_middleware(event: WebhookEvent) -> WebhookEvent:
    """Log all incoming events."""
    logger.info(f"Processing event: {event.event_type} from {event.source}")
    return event


@router.middleware
async def rate_limiting_middleware(event: WebhookEvent) -> WebhookEvent:
    """Rate limiting middleware (simplified example)."""
    # In real implementation, you'd check rate limits here
    return event


@router.route("pr.*")
async def handle_pr_events(event: WebhookEvent):
    """Handle all PR-related events."""
    logger.info(f"PR Event Handler: {event.event_type}")

    # Send notification for critical PR events
    if event.priority == EventPriority.HIGH:
        await outgoing_client.send_notification(
            event_type="pr.critical_event",
            data={"original_event": event.event_type, "details": event.payload},
            priority=EventPriority.HIGH,
        )


@router.route("check.*")
async def handle_check_events(event: WebhookEvent):
    """Handle check-related events."""
    logger.info(f"Check Event Handler: {event.event_type}")


@router.route("system.*")
async def handle_system_events(event: WebhookEvent):
    """Handle system events."""
    logger.info(f"System Event Handler: {event.event_type}")

    # Always send system events to monitoring
    await outgoing_client.send_notification(
        event_type=event.event_type, data=event.payload, priority=event.priority
    )


@app.post("/webhooks/github")
async def github_webhook_endpoint(
    request: Request,
    x_github_event: str = Header(...),
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str = Header(...),
):
    """GitHub webhook endpoint."""
    try:
        # Get raw payload for signature verification
        payload_bytes = await request.body()

        # Verify signature
        if not github_processor.verify_signature(payload_bytes, x_hub_signature_256):
            logger.warning(f"Invalid signature for delivery {x_github_delivery}")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse JSON payload
        payload = await request.json()

        # Process event
        success = await github_processor.process_event(
            event_type=x_github_event, payload=payload, delivery_id=x_github_delivery
        )

        if success:
            return JSONResponse(
                {"status": "processed", "delivery_id": x_github_delivery}
            )
        else:
            raise HTTPException(status_code=500, detail="Processing failed")

    except json.JSONDecodeError as e:
        logger.error("Invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid JSON") from e
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Internal error") from e


@app.post("/webhooks/custom")
async def custom_webhook_endpoint(request: Request):
    """Custom webhook endpoint for internal events."""
    try:
        payload = await request.json()

        # Create event
        event = WebhookEvent(
            event_type=payload.get("event_type", "unknown"),
            payload=payload.get("data", {}),
            priority=EventPriority(payload.get("priority", "medium")),
            source=payload.get("source", "unknown"),
            timestamp=datetime.utcnow(),
        )

        # Route event
        await router.route_event(event)

        return {"status": "processed"}

    except Exception as e:
        logger.error(f"Custom webhook error: {e}")
        raise HTTPException(status_code=500, detail="Processing failed") from e


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "supported_events": list(github_processor.supported_events),
    }


async def example_outgoing_notifications():
    """Example of sending outgoing notifications."""
    logger.info("=== Outgoing Notification Examples ===")

    client = OutgoingWebhookClient(
        webhook_url="https://httpbin.org/post",  # Echo service for testing
        secret="test-secret",
        headers={"X-Service": "agentic-coding-workflow"},
    )

    # Example notifications
    notifications = [
        {
            "event_type": "pr.analysis.completed",
            "data": {
                "pr_id": "123",
                "repository": "owner/repo",
                "result": "success",
                "fixes_applied": 3,
            },
            "priority": EventPriority.MEDIUM,
        },
        {
            "event_type": "system.worker.error",
            "data": {
                "worker_id": "analyzer-1",
                "error": "Connection timeout",
                "timestamp": datetime.utcnow().isoformat(),
            },
            "priority": EventPriority.HIGH,
        },
        {
            "event_type": "pr.review.escalated",
            "data": {
                "pr_id": "456",
                "repository": "owner/repo",
                "reason": "complex_changes",
                "assignee": "senior-dev",
            },
            "priority": EventPriority.CRITICAL,
        },
    ]

    # Send notifications
    for notification in notifications:
        success = await client.send_notification(**notification)
        event_type = notification["event_type"]
        status = "Success" if success else "Failed"
        logger.info(f"Notification sent: {event_type} - {status}")


async def example_event_simulation():
    """Simulate processing various webhook events."""
    logger.info("=== Event Simulation ===")

    # Simulate GitHub webhook events
    events = [
        WebhookEvent(
            event_type="pr.opened",
            payload={"pr_id": "123", "title": "New feature"},
            priority=EventPriority.MEDIUM,
            source="github",
            timestamp=datetime.utcnow(),
        ),
        WebhookEvent(
            event_type="check.failed",
            payload={"check_name": "tests", "pr_id": "123"},
            priority=EventPriority.HIGH,
            source="github",
            timestamp=datetime.utcnow(),
        ),
        WebhookEvent(
            event_type="system.queue.full",
            payload={"queue": "analysis", "size": 1000},
            priority=EventPriority.CRITICAL,
            source="internal",
            timestamp=datetime.utcnow(),
        ),
    ]

    # Process events through router
    for event in events:
        await router.route_event(event)


async def comprehensive_webhook_example():
    """Comprehensive webhook integration example."""
    logger.info("Starting comprehensive webhook examples...")

    try:
        await example_outgoing_notifications()
        await example_event_simulation()

        logger.info("All webhook examples completed successfully!")

    except Exception as e:
        logger.error(f"Webhook examples failed: {e}")


if __name__ == "__main__":
    # Run examples
    asyncio.run(comprehensive_webhook_example())

    # To run the FastAPI server, use: uvicorn webhook-integration:app --reload
