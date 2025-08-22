# Webhook API Documentation

The Webhook API provides comprehensive webhook handling for GitHub events and external system integrations. The system supports both incoming webhook processing (GitHub events) and outgoing webhook notifications (system alerts and monitoring).

## Table of Contents

- [Overview](#overview)
- [GitHub Webhook Integration](#github-webhook-integration)
- [Outgoing Webhook Notifications](#outgoing-webhook-notifications)
- [Event Processing](#event-processing)
- [Security](#security)
- [Configuration](#configuration)
- [Error Handling](#error-handling)
- [Testing](#testing)
- [Best Practices](#best-practices)

## Overview

The webhook system is event-driven and handles two main types of webhooks:

1. **Incoming Webhooks**: GitHub events that trigger PR monitoring and analysis
2. **Outgoing Webhooks**: System notifications sent to external monitoring systems

```python
from src.models.enums import TriggerEvent
from src.repositories.pull_request import PullRequestRepository

# GitHub webhook events map to trigger events
webhook_event_mapping = {
    "pull_request.opened": TriggerEvent.OPENED,
    "pull_request.synchronize": TriggerEvent.SYNCHRONIZE,
    "pull_request.closed": TriggerEvent.CLOSED,
    "pull_request.reopened": TriggerEvent.REOPENED,
    "pull_request.edited": TriggerEvent.EDITED
}
```

## GitHub Webhook Integration

### Supported Events

The system processes the following GitHub webhook events:

```python
# Supported GitHub webhook events
SUPPORTED_EVENTS = [
    "pull_request.opened",         # New PR created
    "pull_request.synchronize",    # PR updated with new commits
    "pull_request.closed",         # PR closed/merged
    "pull_request.reopened",       # PR reopened
    "pull_request.edited",         # PR description/title changed
    "check_run.completed",         # Check run finished
    "check_suite.completed",       # Check suite finished
    "status",                      # Commit status changed
]
```

### Event Processing Flow

```python
async def process_github_webhook(event_type: str, payload: dict) -> None:
    """Process incoming GitHub webhook event.
    
    Args:
        event_type: GitHub event type (e.g., 'pull_request.opened')
        payload: GitHub webhook payload
    """
    if event_type.startswith("pull_request"):
        await handle_pull_request_event(event_type, payload)
    elif event_type.startswith("check_"):
        await handle_check_event(event_type, payload)
    elif event_type == "status":
        await handle_status_event(payload)
    else:
        logger.warning(f"Unsupported event type: {event_type}")

async def handle_pull_request_event(event_type: str, payload: dict) -> None:
    """Handle pull request events."""
    action = payload.get("action")
    pr_data = payload.get("pull_request", {})
    
    # Map GitHub action to trigger event
    trigger_event = webhook_event_mapping.get(f"pull_request.{action}")
    if not trigger_event:
        return
    
    # Update PR state
    async with get_database_session() as session:
        pr_repo = PullRequestRepository(session)
        await pr_repo.update_state(
            pr_id=pr_data["id"],
            new_state=get_pr_state_from_action(action),
            trigger_event=trigger_event,
            metadata={
                "github_event": event_type,
                "webhook_delivery_id": payload.get("delivery_id"),
                "sender": payload.get("sender", {}).get("login")
            }
        )
```

### Webhook Payload Processing

```python
from typing import Dict, Any
from datetime import datetime
import hmac
import hashlib

class GitHubWebhookProcessor:
    """Process GitHub webhook events."""
    
    def __init__(self, secret_token: str):
        self.secret_token = secret_token
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook signature."""
        expected = hmac.new(
            self.secret_token.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
    
    async def process_event(
        self, 
        event_type: str, 
        payload: Dict[str, Any],
        delivery_id: str
    ) -> bool:
        """Process webhook event.
        
        Args:
            event_type: GitHub event type header
            payload: Parsed webhook payload
            delivery_id: GitHub delivery ID
            
        Returns:
            True if processed successfully, False otherwise
        """
        try:
            # Validate event
            if not self._is_supported_event(event_type):
                logger.info(f"Ignoring unsupported event: {event_type}")
                return True
            
            # Extract common data
            repository = payload.get("repository", {})
            sender = payload.get("sender", {})
            
            # Route to specific handler
            if event_type == "pull_request":
                return await self._handle_pull_request(payload)
            elif event_type == "check_run":
                return await self._handle_check_run(payload)
            elif event_type == "check_suite":
                return await self._handle_check_suite(payload)
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing webhook {delivery_id}: {e}")
            return False
    
    async def _handle_pull_request(self, payload: Dict[str, Any]) -> bool:
        """Handle pull request webhook events."""
        action = payload.get("action")
        pr_data = payload.get("pull_request", {})
        
        # Create or update PR record
        async with get_database_session() as session:
            pr_repo = PullRequestRepository(session)
            
            if action == "opened":
                await pr_repo.create_or_update_from_github(pr_data)
            elif action in ["synchronize", "edited"]:
                await pr_repo.update_from_github(pr_data)
            elif action in ["closed", "merged"]:
                await pr_repo.mark_closed(pr_data)
        
        return True
```

### Webhook Endpoint Implementation

```python
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()
webhook_processor = GitHubWebhookProcessor(secret_token=GITHUB_WEBHOOK_SECRET)

@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str = Header(...)
):
    """GitHub webhook endpoint."""
    try:
        # Get raw payload for signature verification
        payload_bytes = await request.body()
        
        # Verify signature
        if not webhook_processor.verify_signature(payload_bytes, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse JSON payload
        payload = await request.json()
        
        # Process event
        success = await webhook_processor.process_event(
            event_type=x_github_event,
            payload=payload,
            delivery_id=x_github_delivery
        )
        
        if success:
            return JSONResponse({"status": "processed"})
        else:
            raise HTTPException(status_code=500, detail="Processing failed")
            
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Internal error")
```

## Outgoing Webhook Notifications

### Configuration

Outgoing webhooks are configured in the notification system:

```yaml
# config.yaml
notification:
  channels:
    - provider: webhook
      enabled: true
      webhook_url: "${MONITORING_WEBHOOK_URL}"
      webhook_headers:
        Authorization: "Bearer ${WEBHOOK_TOKEN}"
        Content-Type: "application/json"
        X-Environment: "production"
        X-Service: "agentic-coding-workflow"
```

### Webhook Notification Client

```python
import aiohttp
import json
from typing import Dict, Any, Optional

class WebhookNotificationClient:
    """Client for sending webhook notifications."""
    
    def __init__(
        self,
        webhook_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ):
        self.webhook_url = webhook_url
        self.headers = headers or {}
        self.timeout = timeout
    
    async def send_notification(
        self,
        event_type: str,
        data: Dict[str, Any],
        priority: str = "medium"
    ) -> bool:
        """Send webhook notification.
        
        Args:
            event_type: Type of event (e.g., 'pr.analysis.failed')
            data: Event data payload
            priority: Notification priority
            
        Returns:
            True if sent successfully, False otherwise
        """
        payload = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "priority": priority,
            "data": data
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Webhook notification sent: {event_type}")
                        return True
                    else:
                        logger.error(
                            f"Webhook failed: {response.status} - {await response.text()}"
                        )
                        return False
                        
        except Exception as e:
            logger.error(f"Webhook notification error: {e}")
            return False
    
    async def send_pr_analysis_failed(
        self,
        pr_id: str,
        repository: str,
        error_message: str
    ) -> bool:
        """Send PR analysis failure notification."""
        return await self.send_notification(
            event_type="pr.analysis.failed",
            data={
                "pr_id": pr_id,
                "repository": repository,
                "error_message": error_message,
                "action_required": "manual_review"
            },
            priority="high"
        )
    
    async def send_fix_applied(
        self,
        pr_id: str,
        repository: str,
        fixes_applied: list
    ) -> bool:
        """Send fix applied notification."""
        return await self.send_notification(
            event_type="pr.fix.applied",
            data={
                "pr_id": pr_id,
                "repository": repository,
                "fixes_applied": fixes_applied,
                "status": "success"
            },
            priority="medium"
        )
```

### Standard Event Types

```python
# Standard outgoing webhook event types
WEBHOOK_EVENTS = {
    # PR Events
    "pr.created": "New PR detected and queued for analysis",
    "pr.analysis.started": "PR analysis has begun",
    "pr.analysis.completed": "PR analysis completed successfully",
    "pr.analysis.failed": "PR analysis failed with errors",
    
    # Fix Events
    "pr.fix.started": "Automated fix process started",
    "pr.fix.applied": "Fixes successfully applied to PR",
    "pr.fix.failed": "Automated fix process failed",
    
    # Review Events
    "pr.review.started": "Multi-agent review process started",
    "pr.review.completed": "Review process completed",
    "pr.review.escalated": "Review escalated to human",
    
    # System Events
    "system.worker.started": "Worker process started",
    "system.worker.stopped": "Worker process stopped",
    "system.worker.error": "Worker encountered critical error",
    "system.queue.full": "Queue capacity exceeded",
    "system.health.degraded": "System health check failed"
}
```

## Event Processing

### Event Processing Pipeline

```python
from enum import Enum
from dataclasses import dataclass
from typing import Any, Callable, List

class EventPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class WebhookEvent:
    """Webhook event data structure."""
    event_type: str
    payload: Dict[str, Any]
    priority: EventPriority
    source: str
    timestamp: datetime
    metadata: Dict[str, Any] = None

class EventProcessor:
    """Process webhook events through pipeline."""
    
    def __init__(self):
        self.handlers: Dict[str, List[Callable]] = {}
        self.middleware: List[Callable] = []
    
    def register_handler(self, event_type: str, handler: Callable):
        """Register event handler."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    def add_middleware(self, middleware: Callable):
        """Add middleware to processing pipeline."""
        self.middleware.append(middleware)
    
    async def process_event(self, event: WebhookEvent) -> bool:
        """Process event through pipeline."""
        try:
            # Apply middleware
            for middleware in self.middleware:
                event = await middleware(event)
                if event is None:
                    return False  # Middleware stopped processing
            
            # Execute handlers
            handlers = self.handlers.get(event.event_type, [])
            for handler in handlers:
                await handler(event)
            
            return True
            
        except Exception as e:
            logger.error(f"Event processing error: {e}")
            return False

# Example middleware
async def rate_limiting_middleware(event: WebhookEvent) -> WebhookEvent:
    """Rate limiting middleware."""
    # Check if source is rate limited
    if await is_rate_limited(event.source):
        logger.warning(f"Rate limited event from {event.source}")
        return None
    return event

async def authentication_middleware(event: WebhookEvent) -> WebhookEvent:
    """Authentication middleware."""
    # Verify event source is authenticated
    if not await verify_source(event.source):
        logger.warning(f"Unauthenticated event from {event.source}")
        return None
    return event
```

### Event Routing

```python
class EventRouter:
    """Route events to appropriate handlers based on patterns."""
    
    def __init__(self):
        self.routes: List[tuple] = []  # (pattern, handler)
    
    def route(self, pattern: str):
        """Decorator to register route handler."""
        def decorator(handler):
            self.routes.append((pattern, handler))
            return handler
        return decorator
    
    async def route_event(self, event: WebhookEvent):
        """Route event to matching handlers."""
        for pattern, handler in self.routes:
            if self._matches_pattern(event.event_type, pattern):
                await handler(event)
    
    def _matches_pattern(self, event_type: str, pattern: str) -> bool:
        """Check if event type matches pattern."""
        import fnmatch
        return fnmatch.fnmatch(event_type, pattern)

# Usage example
router = EventRouter()

@router.route("pr.*")
async def handle_pr_events(event: WebhookEvent):
    """Handle all PR-related events."""
    logger.info(f"Processing PR event: {event.event_type}")

@router.route("system.worker.*")
async def handle_worker_events(event: WebhookEvent):
    """Handle worker events."""
    if event.priority == EventPriority.CRITICAL:
        await send_alert(event)
```

## Security

### Signature Verification

```python
import hmac
import hashlib
from typing import Optional

class WebhookSecurity:
    """Webhook security utilities."""
    
    @staticmethod
    def verify_github_signature(
        payload: bytes,
        signature: str,
        secret: str
    ) -> bool:
        """Verify GitHub webhook signature."""
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
    
    @staticmethod
    def verify_custom_signature(
        payload: bytes,
        signature: str,
        secret: str,
        algorithm: str = "sha256"
    ) -> bool:
        """Verify custom webhook signature."""
        hasher = getattr(hashlib, algorithm)
        expected = hmac.new(secret.encode(), payload, hasher).hexdigest()
        return hmac.compare_digest(signature, expected)
    
    @staticmethod
    def generate_signature(
        payload: bytes,
        secret: str,
        algorithm: str = "sha256"
    ) -> str:
        """Generate webhook signature."""
        hasher = getattr(hashlib, algorithm)
        return hmac.new(secret.encode(), payload, hasher).hexdigest()
```

### Rate Limiting

```python
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

class RateLimiter:
    """Rate limiter for webhook endpoints."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self.requests = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed."""
        async with self._lock:
            now = datetime.utcnow()
            cutoff = now - self.window
            
            # Clean old requests
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if req_time > cutoff
            ]
            
            # Check limit
            if len(self.requests[identifier]) >= self.max_requests:
                return False
            
            # Add current request
            self.requests[identifier].append(now)
            return True

# Usage in webhook endpoint
rate_limiter = RateLimiter(max_requests=50, window_seconds=60)

@app.post("/webhooks/custom")
async def custom_webhook(request: Request):
    client_ip = request.client.host
    
    if not await rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    # Process webhook
    return {"status": "ok"}
```

## Configuration

### Webhook Configuration Model

```python
from pydantic import BaseModel, Field, HttpUrl
from typing import Dict, Optional

class WebhookConfig(BaseModel):
    """Webhook configuration model."""
    
    url: HttpUrl = Field(..., description="Webhook URL")
    secret: Optional[str] = Field(None, description="Webhook secret for signature verification")
    headers: Dict[str, str] = Field(default_factory=dict, description="Custom headers")
    timeout: int = Field(30, description="Request timeout in seconds")
    retries: int = Field(3, description="Number of retry attempts")
    retry_delay: int = Field(5, description="Delay between retries in seconds")
    enabled: bool = Field(True, description="Whether webhook is enabled")

class IncomingWebhookConfig(BaseModel):
    """Incoming webhook configuration."""
    
    github: WebhookConfig
    custom: Optional[WebhookConfig] = None
    rate_limit: int = Field(100, description="Requests per minute")
    signature_required: bool = Field(True, description="Require signature verification")

class OutgoingWebhookConfig(BaseModel):
    """Outgoing webhook configuration."""
    
    monitoring: Optional[WebhookConfig] = None
    alerting: Optional[WebhookConfig] = None
    audit: Optional[WebhookConfig] = None
    batch_size: int = Field(10, description="Batch size for bulk notifications")
    flush_interval: int = Field(60, description="Flush interval in seconds")
```

### Environment Variables

```bash
# GitHub webhook configuration
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret

# Outgoing webhook URLs
MONITORING_WEBHOOK_URL=https://monitoring.example.com/webhooks/agentic
MONITORING_WEBHOOK_TOKEN=your_monitoring_token

ALERTING_WEBHOOK_URL=https://alerts.example.com/api/webhooks
ALERTING_WEBHOOK_TOKEN=your_alerting_token

# Security settings
WEBHOOK_RATE_LIMIT=100              # Requests per minute
WEBHOOK_SIGNATURE_REQUIRED=true     # Require signature verification
WEBHOOK_TIMEOUT=30                  # Request timeout in seconds
```

## Error Handling

### Webhook Error Handling

```python
from enum import Enum
import asyncio
from typing import Optional

class WebhookError(Exception):
    """Base webhook error."""
    pass

class SignatureError(WebhookError):
    """Signature verification failed."""
    pass

class RateLimitError(WebhookError):
    """Rate limit exceeded."""
    pass

class ProcessingError(WebhookError):
    """Event processing failed."""
    pass

class RetryableWebhookClient:
    """Webhook client with retry logic."""
    
    def __init__(
        self,
        webhook_url: str,
        max_retries: int = 3,
        retry_delay: int = 5,
        backoff_factor: float = 2.0
    ):
        self.webhook_url = webhook_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
    
    async def send_with_retry(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send webhook with retry logic."""
        last_error = None
        delay = self.retry_delay
        
        for attempt in range(self.max_retries + 1):
            try:
                return await self._send_webhook(payload, headers)
                
            except aiohttp.ClientError as e:
                last_error = e
                if attempt < self.max_retries:
                    logger.warning(
                        f"Webhook attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    delay *= self.backoff_factor
                else:
                    logger.error(f"Webhook failed after {self.max_retries} retries: {e}")
        
        return False
    
    async def _send_webhook(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send single webhook request."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                return True
```

### Dead Letter Queue

```python
import json
from datetime import datetime
from typing import Any, Dict

class WebhookDeadLetterQueue:
    """Handle failed webhook deliveries."""
    
    def __init__(self, storage_path: str = "failed_webhooks.jsonl"):
        self.storage_path = storage_path
    
    async def store_failed_webhook(
        self,
        webhook_url: str,
        payload: Dict[str, Any],
        error: str,
        attempts: int
    ):
        """Store failed webhook for manual review."""
        failed_webhook = {
            "timestamp": datetime.utcnow().isoformat(),
            "webhook_url": webhook_url,
            "payload": payload,
            "error": error,
            "attempts": attempts,
            "status": "failed"
        }
        
        # Append to JSONL file
        with open(self.storage_path, "a") as f:
            f.write(json.dumps(failed_webhook) + "\n")
        
        logger.error(f"Webhook stored in DLQ: {webhook_url}")
    
    async def retry_failed_webhooks(self) -> int:
        """Retry failed webhooks."""
        retried = 0
        
        try:
            with open(self.storage_path, "r") as f:
                for line in f:
                    webhook_data = json.loads(line.strip())
                    if webhook_data["status"] == "failed":
                        success = await self._retry_webhook(webhook_data)
                        if success:
                            retried += 1
            
            logger.info(f"Retried {retried} failed webhooks")
            return retried
            
        except FileNotFoundError:
            return 0
    
    async def _retry_webhook(self, webhook_data: Dict[str, Any]) -> bool:
        """Retry individual webhook."""
        client = RetryableWebhookClient(webhook_data["webhook_url"])
        return await client.send_with_retry(webhook_data["payload"])
```

## Testing

### Webhook Testing Utilities

```python
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

class MockWebhookServer:
    """Mock webhook server for testing."""
    
    def __init__(self):
        self.received_webhooks = []
        self.response_status = 200
        self.response_delay = 0
    
    async def receive_webhook(self, payload: Dict[str, Any]):
        """Receive webhook for testing."""
        if self.response_delay:
            await asyncio.sleep(self.response_delay)
        
        self.received_webhooks.append({
            "timestamp": datetime.utcnow(),
            "payload": payload
        })
        
        if self.response_status != 200:
            raise aiohttp.ClientResponseError(
                request_info=None,
                history=(),
                status=self.response_status
            )

@pytest.fixture
def webhook_server():
    """Webhook server fixture."""
    return MockWebhookServer()

async def test_github_webhook_processing(webhook_server):
    """
    Why: Ensure GitHub webhooks are processed correctly
    What: Tests webhook signature verification and event processing
    How: Sends mock GitHub webhook and verifies processing
    """
    # GitHub webhook payload
    payload = {
        "action": "opened",
        "pull_request": {
            "id": 123,
            "number": 1,
            "title": "Test PR",
            "state": "open"
        },
        "repository": {
            "full_name": "test/repo"
        }
    }
    
    # Test webhook processing
    processor = GitHubWebhookProcessor("test-secret")
    
    with patch('src.database.get_session') as mock_session:
        success = await processor.process_event(
            event_type="pull_request",
            payload=payload,
            delivery_id="test-delivery-123"
        )
    
    assert success
    mock_session.assert_called_once()

async def test_outgoing_webhook_retry(webhook_server):
    """
    Why: Ensure outgoing webhooks retry on failure
    What: Tests retry logic for failed webhook deliveries
    How: Simulates failure conditions and verifies retry behavior
    """
    webhook_server.response_status = 500  # Simulate server error
    
    client = RetryableWebhookClient(
        webhook_url="http://test.example.com/webhook",
        max_retries=2,
        retry_delay=0.1
    )
    
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_post.side_effect = aiohttp.ClientError("Connection failed")
        
        success = await client.send_with_retry({"test": "data"})
        
        assert not success
        assert mock_post.call_count == 3  # Initial + 2 retries

def test_webhook_signature_verification():
    """
    Why: Ensure webhook signatures are verified correctly
    What: Tests signature generation and verification
    How: Generates signatures and verifies them with correct/incorrect secrets
    """
    payload = b'{"test": "data"}'
    secret = "test-secret"
    
    # Generate signature
    signature = WebhookSecurity.generate_signature(payload, secret)
    
    # Verify correct signature
    assert WebhookSecurity.verify_custom_signature(payload, signature, secret)
    
    # Verify incorrect signature
    assert not WebhookSecurity.verify_custom_signature(payload, signature, "wrong-secret")
```

## Best Practices

### Security Best Practices

```python
# ✅ Always verify webhook signatures
def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    return WebhookSecurity.verify_github_signature(payload, signature, secret)

# ✅ Use HTTPS for all webhook URLs
WEBHOOK_URL = "https://secure.example.com/webhooks"  # Secure
# ❌ HTTP_WEBHOOK_URL = "http://insecure.example.com/webhooks"  # Insecure

# ✅ Rate limit webhook endpoints
@app.post("/webhooks/github")
async def github_webhook(request: Request):
    if not await rate_limiter.is_allowed(request.client.host):
        raise HTTPException(status_code=429, detail="Rate limited")
    # Process webhook
```

### Error Handling Best Practices

```python
# ✅ Use proper error types
try:
    await process_webhook(payload)
except SignatureError:
    return JSONResponse(status_code=401, content={"error": "Invalid signature"})
except ProcessingError:
    return JSONResponse(status_code=500, content={"error": "Processing failed"})

# ✅ Implement retry logic for outgoing webhooks
webhook_client = RetryableWebhookClient(
    webhook_url=config.webhook_url,
    max_retries=3,
    retry_delay=5
)

# ✅ Use dead letter queue for failed deliveries
if not await webhook_client.send_with_retry(payload):
    await dead_letter_queue.store_failed_webhook(url, payload, error, attempts)
```

### Performance Best Practices

```python
# ✅ Process webhooks asynchronously
@app.post("/webhooks/github")
async def github_webhook(request: Request):
    # Queue for background processing
    await webhook_queue.enqueue(await request.json())
    return {"status": "queued"}

# ✅ Batch outgoing notifications
class BatchWebhookClient:
    def __init__(self, batch_size: int = 10, flush_interval: int = 60):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.pending_webhooks = []
    
    async def queue_webhook(self, payload: Dict[str, Any]):
        self.pending_webhooks.append(payload)
        if len(self.pending_webhooks) >= self.batch_size:
            await self.flush_batch()

# ✅ Use connection pooling
async with aiohttp.ClientSession(
    connector=aiohttp.TCPConnector(limit=100)
) as session:
    # Reuse connections
    await session.post(webhook_url, json=payload)
```

### Monitoring and Observability

```python
# ✅ Add comprehensive logging
logger.info(
    "Webhook processed",
    extra={
        "event_type": event_type,
        "delivery_id": delivery_id,
        "processing_time_ms": processing_time,
        "source_ip": source_ip
    }
)

# ✅ Track webhook metrics
from prometheus_client import Counter, Histogram

webhook_requests_total = Counter(
    'webhook_requests_total',
    'Total webhook requests',
    ['event_type', 'status']
)

webhook_processing_duration = Histogram(
    'webhook_processing_duration_seconds',
    'Webhook processing duration'
)

# ✅ Health check endpoints
@app.get("/health/webhooks")
async def webhook_health():
    return {
        "status": "healthy",
        "active_connections": get_active_connections(),
        "queue_depth": await get_queue_depth(),
        "last_processed": get_last_processed_timestamp()
    }
```

---

**Next Steps:**
- 📖 **Examples**: Check [Webhook Examples](../examples/webhook-integration.py) for complete implementation
- 🔧 **Configuration**: See [Configuration API](configuration-api.md) for webhook configuration options  
- 🧪 **Testing**: Review [Testing Guide](../developer/testing-guide.md) for webhook testing patterns