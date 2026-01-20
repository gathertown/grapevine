"""Rate limiter for Slack bot messages using Redis.

Implements per-tenant per-bot rate limiting with configurable limit.
Uses Redis INCR + TTL for efficient, distributed rate limiting.
"""

import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.clients.redis import get_client as get_redis_client
from src.utils.config import get_config_value

logger = logging.getLogger(__name__)

# Configuration
LIMIT_PER_HOUR = int(get_config_value("SLACK_BOT_RATE_LIMIT_PER_HOUR", "120"))
WINDOW_SECONDS = int(get_config_value("SLACK_BOT_RATE_LIMIT_WINDOW_SECONDS", "3600"))


def _get_rate_limit_key(tenant_id: str, bot_id: str) -> str:
    """Generate Redis key for rate limiting."""
    return f"rl:slack:bot_msg:{tenant_id}:{bot_id}"


async def should_allow_slack_bot_message(tenant_id: str, bot_id: str) -> bool:
    """Check if a Slack bot message should be allowed based on rate limits.

    Uses Redis INCR + TTL to track message counts per tenant per bot.
    Returns True if the message is under the limit, False if it should be dropped.

    On Redis errors: Always fail-closed (return False) to prevent spam.

    Args:
        tenant_id: Tenant identifier
        bot_id: Bot identifier from Slack message

    Returns:
        True if message should be allowed, False if rate limit exceeded
    """
    key = _get_rate_limit_key(tenant_id, bot_id)

    try:
        redis_client: Redis = await get_redis_client()

        # Increment counter and get new value
        count = await redis_client.incr(key)

        # Set TTL only on the first message in the window
        if count == 1:
            await redis_client.expire(key, WINDOW_SECONDS)

        # Check if under limit
        allowed = count <= LIMIT_PER_HOUR

        if not allowed:
            logger.info(
                f"Slack rate limit exceeded: tenant={tenant_id} bot={bot_id} "
                f"count={count} limit={LIMIT_PER_HOUR}"
            )

        return allowed

    except RedisError as e:
        # Always fail-closed on Redis errors to prevent spam
        logger.warning(f"Redis error; failing closed for tenant={tenant_id} bot={bot_id}: {e}")
        return False


def extract_bot_id(event: dict[str, Any]) -> str | None:
    """Extract bot ID from Slack message event.

    Args:
        event: Slack message event dictionary

    Returns:
        Bot ID if present, None otherwise
    """
    # Try bot_id field first (most reliable for bot messages)
    if "bot_id" in event:
        return event["bot_id"]

    # For messages with subtype=bot_message, there should be a bot_id
    # but fallback to app_id if available
    if "app_id" in event:
        return event["app_id"]

    return None
