"""
Webhook delivery service for sending notifications about document changes.

Implements fire-and-forget webhook delivery with structured logging.
"""

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import asyncpg
import httpx

from src.utils.logging import get_logger

logger = get_logger(__name__)


class WebhookSubscription:
    """Webhook subscription data."""

    def __init__(self, id: str, url: str, secret: str, active: bool = True):
        self.id = id
        self.url = url
        self.secret = secret
        self.active = active


def generate_hmac_signature(secret: str, payload: dict[str, Any]) -> str:
    """Generate HMAC-SHA256 signature for webhook payload.

    Args:
        secret: The webhook signing secret
        payload: The JSON payload to sign

    Returns:
        Hex-encoded HMAC signature
    """
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return signature


async def get_active_webhook_subscriptions(db_pool: asyncpg.Pool) -> list[WebhookSubscription]:
    """Get all active webhook subscriptions for a tenant.

    Args:
        db_pool: Database pool for the tenant

    Returns:
        List of active webhook subscriptions
    """
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, url, secret, active
                FROM webhook_subscriptions
                WHERE active = true
                ORDER BY created_at ASC
                """
            )

            return [
                WebhookSubscription(
                    id=str(row["id"]), url=row["url"], secret=row["secret"], active=row["active"]
                )
                for row in rows
            ]
    except Exception as e:
        logger.error("Failed to fetch webhook subscriptions", error=str(e))
        return []


async def send_single_webhook(
    subscription: WebhookSubscription,
    payload: dict[str, Any],
    timeout_seconds: float = 5.0,
    max_attempts: int = 5,
    base_backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 10.0,
) -> None:
    """Send webhook to single subscription with timeout and logging.

    Args:
        subscription: The webhook subscription
        payload: The webhook payload to send
        timeout_seconds: HTTP request timeout in seconds
        max_attempts: Maximum number of delivery attempts
        base_backoff_seconds: Initial backoff delay between attempts
        max_backoff_seconds: Maximum backoff delay between attempts
    """
    signature = generate_hmac_signature(subscription.secret, payload)
    headers = {
        "Content-Type": "application/json",
        "X-Grapevine-Signature": f"sha256={signature}",
        "X-Grapevine-Event": "document.changed",
        "User-Agent": "Grapevine-Webhooks/1.0",
    }

    attempt = 1
    backoff_seconds = max(base_backoff_seconds, 0)

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        while attempt <= max_attempts:
            response_status: int | None = None
            error_message: str | None = None

            try:
                response = await client.post(
                    subscription.url,
                    json=payload,
                    headers=headers,
                )
                response_status = response.status_code

                if 200 <= response.status_code < 300:
                    logger.info(
                        "webhook_delivery_success",
                        tenant_id=payload["tenant_id"],
                        subscription_id=subscription.id,
                        document_id=payload["data"]["document_id"],
                        webhook_url=subscription.url,
                        response_status=response.status_code,
                        source=payload["data"]["source"],
                        attempt=attempt,
                    )
                    return

                error_message = f"HTTP {response.status_code}"

            except Exception as exc:
                error_message = str(exc)

            will_retry = attempt < max_attempts
            logger.warning(
                "webhook_delivery_failed",
                tenant_id=payload["tenant_id"],
                subscription_id=subscription.id,
                document_id=payload["data"]["document_id"],
                webhook_url=subscription.url,
                response_status=response_status,
                error=error_message,
                source=payload["data"]["source"],
                attempt=attempt,
                max_attempts=max_attempts,
                will_retry=will_retry,
            )

            if not will_retry:
                return

            if backoff_seconds > 0:
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)

            attempt += 1


async def send_webhooks_for_document(
    tenant_id: str, document_id: str, source: str, db_pool: asyncpg.Pool
) -> None:
    """Send webhooks for a document change in background.

    All failures are logged but isolated - this function never raises exceptions.

    Args:
        tenant_id: The tenant ID
        document_id: The document ID that was changed
        source: The source of the document (github, slack, etc.)
        db_pool: Database pool for the tenant
    """
    try:
        # Get active subscriptions for tenant
        subscriptions = await get_active_webhook_subscriptions(db_pool)

        if not subscriptions:
            logger.debug(
                "No active webhook subscriptions found",
                tenant_id=tenant_id,
                document_id=document_id,
            )
            return

        # Create webhook payload
        payload = {
            "event": "document.changed",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "tenant_id": tenant_id,
            "data": {"document_id": document_id, "source": source},
        }

        # Send to each subscription (in parallel, with timeout)
        await asyncio.gather(
            *[send_single_webhook(sub, payload) for sub in subscriptions],
            return_exceptions=True,  # Don't let webhook failures bubble up
        )

        logger.debug(
            "Webhook delivery completed",
            tenant_id=tenant_id,
            document_id=document_id,
            subscription_count=len(subscriptions),
        )

    except Exception as e:
        # Log but don't re-raise - this runs in background
        logger.error(
            "webhook_delivery_error",
            tenant_id=tenant_id,
            document_id=document_id,
            error=str(e),
        )


def trigger_webhooks_for_document(
    tenant_id: str, document_id: str, source: str, db_pool: asyncpg.Pool
) -> None:
    """Start webhook delivery as background task without awaiting.

    This is the main entry point for firing webhook notifications after successful indexing.
    It starts the webhook delivery process in the background and returns immediately.

    Args:
        tenant_id: The tenant ID
        document_id: The document ID that was indexed
        source: The source of the document
        db_pool: Database pool for the tenant
    """
    try:
        # Fire and forget - start background task
        asyncio.create_task(send_webhooks_for_document(tenant_id, document_id, source, db_pool))

        logger.debug(
            "Started webhook delivery background task",
            tenant_id=tenant_id,
            document_id=document_id,
            source=source,
        )

    except Exception as e:
        # Log but don't re-raise - webhook failures should never block indexing
        logger.error(
            "Failed to start webhook delivery task",
            tenant_id=tenant_id,
            document_id=document_id,
            source=source,
            error=str(e),
        )
