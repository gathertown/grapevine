"""
Billing Limits Service

Provides tenant billing limits based on subscription tiers and trial status.
Integrates with control database for subscription data and Redis for caching.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.clients.redis import get_client as get_redis_client
from src.utils.config import get_billing_enabled
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BillingLimits:
    """Billing limits for a tenant."""

    monthly_requests: int
    is_trial: bool
    tier: str
    billing_cycle_anchor: datetime | None = None  # When billing cycles reset
    billing_interval: str = "month"  # "month" or "year" - from Stripe
    trial_start_at: datetime | None = None  # When trial started (for trial tenants)
    is_gather_managed: bool = False  # Whether this tenant is gather-managed (no usage limits)


class BillingLimitsService:
    """
    Service for retrieving tenant billing limits.

    Queries control database for subscription information and applies
    appropriate limits based on subscription tier and trial status.
    Results are cached in Redis to minimize database queries.
    """

    # Whether billing limits are enabled (tied to whether Stripe/billing is configured)
    # When billing is disabled, uses temporary high limit for all tiers
    # When billing is enabled, uses correct per-tier limits
    BILLING_LIMITS_ENABLED = get_billing_enabled()

    # High limit used when billing is disabled (no Stripe configured)
    NO_BILLING_HIGH_LIMIT = 15_000

    # Per-tier limits (used when billing is enabled)
    REAL_TIER_LIMITS = {
        "trial": 300,  # Conservative trial limit
        "basic": 200,
        "team": 500,
        "pro": 4_000,
        "ultra": 15_000,
        "enterprise": 15_000,  # Same as ultra for now
    }

    # Default limits for different tiers
    TIER_LIMITS = {
        "trial": BillingLimits(
            monthly_requests=REAL_TIER_LIMITS["trial"]
            if BILLING_LIMITS_ENABLED
            else NO_BILLING_HIGH_LIMIT,
            is_trial=True,
            tier="trial",
            billing_cycle_anchor=None,
            billing_interval="month",
            is_gather_managed=False,
        ),
        "basic": BillingLimits(
            monthly_requests=REAL_TIER_LIMITS["basic"]
            if BILLING_LIMITS_ENABLED
            else NO_BILLING_HIGH_LIMIT,
            is_trial=False,
            tier="basic",
            billing_cycle_anchor=None,
            billing_interval="month",
            is_gather_managed=False,
        ),
        "team": BillingLimits(
            monthly_requests=REAL_TIER_LIMITS["team"]
            if BILLING_LIMITS_ENABLED
            else NO_BILLING_HIGH_LIMIT,
            is_trial=False,
            tier="team",
            billing_cycle_anchor=None,  # Will be populated from subscription data
            billing_interval="month",  # Default, will be updated from subscription
            is_gather_managed=False,
        ),
        "pro": BillingLimits(
            monthly_requests=REAL_TIER_LIMITS["pro"]
            if BILLING_LIMITS_ENABLED
            else NO_BILLING_HIGH_LIMIT,
            is_trial=False,
            tier="pro",
            billing_cycle_anchor=None,
            billing_interval="month",
            is_gather_managed=False,
        ),
        "ultra": BillingLimits(
            monthly_requests=REAL_TIER_LIMITS["ultra"]
            if BILLING_LIMITS_ENABLED
            else NO_BILLING_HIGH_LIMIT,
            is_trial=False,
            tier="ultra",
            billing_cycle_anchor=None,
            billing_interval="month",
            is_gather_managed=False,
        ),
        "enterprise": BillingLimits(
            monthly_requests=REAL_TIER_LIMITS["enterprise"]
            if BILLING_LIMITS_ENABLED
            else NO_BILLING_HIGH_LIMIT,
            is_trial=False,
            tier="enterprise",
            billing_cycle_anchor=None,
            billing_interval="month",
            is_gather_managed=False,
        ),
    }

    def __init__(self):
        """Initialize billing limits service."""
        logger.info("BillingLimitsService initialized")

    async def get_tenant_limits(self, tenant_id: str) -> BillingLimits:
        """
        Get billing limits for a tenant.

        First checks Redis cache, then falls back to database query.
        Results are cached for 1 hour to reduce database load.

        Args:
            tenant_id: Tenant identifier

        Returns:
            BillingLimits object with usage limits and tier information
        """
        # Try cache first
        try:
            cached_limits = await self._get_cached_limits(tenant_id)
            if cached_limits:
                logger.debug(f"Using cached limits for tenant {tenant_id}")
                return cached_limits
        except Exception as e:
            logger.warning(f"Failed to retrieve cached limits for {tenant_id}: {e}")

        # Query database for subscription info
        try:
            limits = await self._query_tenant_limits(tenant_id)

            # Cache the result for 1 hour
            await self._cache_limits(tenant_id, limits)

            logger.info(
                f"Retrieved limits for tenant {tenant_id}: tier={limits.tier}, trial={limits.is_trial}"
            )
            return limits

        except Exception as e:
            logger.error(f"Failed to query limits for tenant {tenant_id}: {e}", exc_info=True)
            # Fall back to trial limits
            return self.TIER_LIMITS["trial"]

    async def _get_cached_limits(self, tenant_id: str) -> BillingLimits | None:
        """
        Retrieve cached limits from Redis.

        Args:
            tenant_id: Tenant identifier

        Returns:
            BillingLimits if found in cache, None otherwise
        """
        logger.info(f"[billing_limits] Getting Redis client for tenant {tenant_id}")
        redis_client = await get_redis_client()
        cache_key = f"billing_limits:{tenant_id}"

        logger.info(f"[billing_limits] Querying Redis cache for tenant {tenant_id}")
        cached_data = await redis_client.get(cache_key)
        if not cached_data:
            return None

        try:
            data = json.loads(cached_data)
            # Handle datetime deserialization
            if data.get("billing_cycle_anchor"):
                data["billing_cycle_anchor"] = datetime.fromisoformat(data["billing_cycle_anchor"])
            if data.get("trial_start_at"):
                data["trial_start_at"] = datetime.fromisoformat(data["trial_start_at"])
            return BillingLimits(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to deserialize cached limits for {tenant_id}: {e}")
            # Clear invalid cache entry
            await redis_client.delete(cache_key)
            return None

    async def _cache_limits(self, tenant_id: str, limits: BillingLimits) -> None:
        """
        Cache limits in Redis with 1 hour TTL.

        Args:
            tenant_id: Tenant identifier
            limits: BillingLimits to cache
        """
        try:
            logger.info(
                f"[billing_limits] Getting Redis client for cache write, tenant {tenant_id}"
            )
            redis_client = await get_redis_client()
            cache_key = f"billing_limits:{tenant_id}"

            # Convert to dict for JSON serialization
            limits_dict = {
                "monthly_requests": limits.monthly_requests,
                "is_trial": limits.is_trial,
                "tier": limits.tier,
                "billing_cycle_anchor": limits.billing_cycle_anchor.isoformat()
                if limits.billing_cycle_anchor
                else None,
                "billing_interval": limits.billing_interval,
                "trial_start_at": limits.trial_start_at.isoformat()
                if limits.trial_start_at
                else None,
                "is_gather_managed": limits.is_gather_managed,
            }

            # Cache for 1 hour
            logger.info(f"[billing_limits] Writing to Redis cache for tenant {tenant_id}")
            await redis_client.setex(
                cache_key,
                3600,  # 1 hour in seconds
                json.dumps(limits_dict),
            )

            logger.debug(f"Cached limits for tenant {tenant_id}")

        except Exception as e:
            logger.warning(f"Failed to cache limits for {tenant_id}: {e}")
            # Don't raise - caching failure shouldn't block operation

    async def _query_tenant_limits(self, tenant_id: str) -> BillingLimits:
        """
        Query database for tenant subscription and determine limits.

        Precedence order:
        1. Enterprise plan (if enterprise_plan_request_limit is set)
        2. Gather-managed (no limits)
        3. Standard billing (Stripe subscriptions/trial)

        Args:
            tenant_id: Tenant identifier

        Returns:
            BillingLimits based on subscription tier or trial status
        """
        # Use existing tenant DB manager for control DB access
        from src.clients.tenant_db import tenant_db_manager

        logger.info(f"[billing_limits] Getting control DB pool for tenant {tenant_id}")
        pool = await tenant_db_manager.get_control_db()

        logger.info(f"[billing_limits] Acquiring control DB connection for tenant {tenant_id}")
        async with pool.acquire() as conn:
            # Get tenant info including billing mode and enterprise plan limit
            tenant_info = await self._get_tenant_info(conn, tenant_id)
            billing_mode = str(tenant_info["billing_mode"])
            enterprise_limit = tenant_info["enterprise_plan_request_limit"]

            # Check for enterprise plan first (highest precedence)
            if enterprise_limit is not None:
                return self._handle_enterprise_plan_case(tenant_id, int(enterprise_limit))

            # Check for active subscription
            subscription_row = await self._get_active_subscription(conn, tenant_id)

            if not subscription_row:
                # No subscription - check 30-day trial status
                return await self._handle_no_subscription_case(conn, tenant_id, billing_mode)

            # Has subscription - determine tier and limits (respects subscription limits even during trial)
            return self._get_subscription_limits(tenant_id, subscription_row, billing_mode)

    async def _get_tenant_info(self, conn, tenant_id: str) -> dict[str, str | int | None]:
        """
        Query tenant info including billing mode and enterprise plan limit.

        Args:
            conn: Database connection
            tenant_id: Tenant identifier

        Returns:
            Dict with billing_mode and enterprise_plan_request_limit
        """
        try:
            logger.info(
                f"[billing_limits] Querying tenant info from control DB for tenant {tenant_id}"
            )
            tenant_query = """
                SELECT billing_mode, enterprise_plan_request_limit
                FROM tenants
                WHERE id = $1
            """
            result = await conn.fetchrow(tenant_query, tenant_id)
            if result:
                return {
                    "billing_mode": result["billing_mode"] or "grapevine_managed",
                    "enterprise_plan_request_limit": result["enterprise_plan_request_limit"],
                }
            else:
                logger.warning(f"Tenant {tenant_id} not found, defaulting to grapevine_managed")
                return {
                    "billing_mode": "grapevine_managed",
                    "enterprise_plan_request_limit": None,
                }
        except Exception as e:
            logger.error(f"Failed to query tenant info for {tenant_id}: {e}", exc_info=True)
            return {
                "billing_mode": "grapevine_managed",
                "enterprise_plan_request_limit": None,
            }

    async def _get_active_subscription(self, conn, tenant_id: str):
        """
        Query for active subscription.

        Args:
            conn: Database connection
            tenant_id: Tenant identifier

        Returns:
            Subscription row or None
        """
        logger.info(
            f"[billing_limits] Querying active subscription from control DB for tenant {tenant_id}"
        )
        subscription_query = """
            SELECT
                s.status,
                s.stripe_price_id,
                s.trial_start,
                s.trial_end,
                s.canceled_at,
                s.ended_at,
                s.billing_cycle_anchor
            FROM subscriptions s
            WHERE s.tenant_id = $1
              AND s.status IN ('active', 'trialing', 'past_due')
            ORDER BY s.created_at DESC
            LIMIT 1
        """
        return await conn.fetchrow(subscription_query, tenant_id)

    async def _handle_no_subscription_case(
        self, conn, tenant_id: str, billing_mode: str
    ) -> BillingLimits:
        """
        Handle case where tenant has no active subscription.

        Checks if tenant is still within 30-day trial period from tenant.trial_start_at.

        Args:
            conn: Database connection (unused, kept for compatibility)
            tenant_id: Tenant identifier

        Returns:
            BillingLimits for trial or expired trial
        """
        # Use shared utility for trial_start_at lookup
        from src.utils.tenant_db_utils import get_tenant_trial_start_at

        try:
            trial_start = await get_tenant_trial_start_at(tenant_id)
        except Exception as e:
            logger.error(
                f"Failed to get trial start date for tenant {tenant_id}: {e}", exc_info=True
            )
            trial_start = None

        if not trial_start:
            logger.warning(f"No trial_start_at found for tenant {tenant_id}, using trial limits")
            trial_limits = self.TIER_LIMITS["trial"]
            return BillingLimits(
                monthly_requests=trial_limits.monthly_requests,
                is_trial=trial_limits.is_trial,
                tier=trial_limits.tier,
                billing_cycle_anchor=trial_limits.billing_cycle_anchor,
                billing_interval=trial_limits.billing_interval,
                trial_start_at=trial_limits.trial_start_at,
                is_gather_managed=(billing_mode == "gather_managed"),
            )

        # Calculate if 30-day trial has expired
        trial_end = trial_start + timedelta(days=30)
        now = datetime.now(UTC)

        if now <= trial_end:
            logger.info(f"Tenant {tenant_id} is in 30-day trial period (no subscription)")
            trial_limits = self.TIER_LIMITS["trial"]
            return BillingLimits(
                monthly_requests=trial_limits.monthly_requests,
                is_trial=True,
                tier="trial",
                billing_cycle_anchor=None,
                billing_interval="month",
                trial_start_at=trial_start,
                is_gather_managed=(billing_mode == "gather_managed"),
            )
        else:
            logger.warning(
                f"Tenant {tenant_id} trial period expired, but no subscription - restricting access"
            )
            # Return very limited access for expired trials without subscriptions
            return BillingLimits(
                monthly_requests=0,  # No requests allowed
                is_trial=False,
                tier="expired_trial",
                billing_cycle_anchor=None,
                billing_interval="month",
                trial_start_at=trial_start,
                is_gather_managed=(billing_mode == "gather_managed"),
            )

    def _handle_enterprise_plan_case(self, tenant_id: str, request_limit: int) -> BillingLimits:
        """
        Handle enterprise plan billing limits.

        Enterprise plans have custom request limits and no trial period.
        They are not gather-managed (they're a distinct billing category).

        Args:
            tenant_id: Tenant identifier
            request_limit: Custom monthly request limit for the enterprise plan

        Returns:
            BillingLimits with custom enterprise request limit
        """
        logger.info(
            f"Tenant {tenant_id} has enterprise plan with {request_limit:,} monthly requests"
        )

        return BillingLimits(
            monthly_requests=request_limit,
            is_trial=False,
            tier="enterprise",
            billing_cycle_anchor=None,  # Enterprise plans don't use Stripe billing cycles
            billing_interval="month",
            trial_start_at=None,
            is_gather_managed=False,  # Enterprise is a distinct category from gather_managed
        )

    def _is_subscription_in_trial(self, subscription_row) -> bool:
        """
        Check if subscription is currently in trial period.

        Args:
            subscription_row: Database row from subscriptions table

        Returns:
            True if subscription is in trial period
        """
        now = datetime.now(UTC)
        return subscription_row["status"] == "trialing" or (
            subscription_row["trial_start"]
            and subscription_row["trial_end"]
            and subscription_row["trial_start"] <= now <= subscription_row["trial_end"]
        )

    def _get_subscription_limits(
        self, tenant_id: str, subscription_row, billing_mode: str
    ) -> BillingLimits:
        """
        Get billing limits for an active subscription.

        Args:
            tenant_id: Tenant identifier
            subscription_row: Database row from subscriptions table

        Returns:
            BillingLimits for the subscription tier
        """
        # Map Stripe price ID to tier
        tier = self._map_price_id_to_tier(subscription_row["stripe_price_id"])

        if tier not in self.TIER_LIMITS:
            logger.warning(f"Unknown tier {tier} for tenant {tenant_id}, using trial limits")
            return self.TIER_LIMITS["trial"]

        # Check if subscription is in trial period
        is_subscription_trial = self._is_subscription_in_trial(subscription_row)

        # Get base limits for the tier
        base_limits = self.TIER_LIMITS[tier]

        # Create a new BillingLimits with actual billing cycle data
        # Respect subscription limits even during trial period
        return BillingLimits(
            monthly_requests=base_limits.monthly_requests,
            is_trial=is_subscription_trial,  # Indicate if subscription is in trial
            tier=tier,
            billing_cycle_anchor=subscription_row["billing_cycle_anchor"],
            billing_interval="month",  # TODO: Get from Stripe price interval when needed
            trial_start_at=None,  # Subscriptions don't use trial_start_at field
            is_gather_managed=(billing_mode == "gather_managed"),
        )

    def _map_price_id_to_tier(self, stripe_price_id: str | None) -> str:
        """
        Map Stripe price ID to subscription tier.

        Args:
            stripe_price_id: Stripe price identifier

        Returns:
            Tier name (team, pro, ultra, enterprise, or trial as fallback)
        """
        if not stripe_price_id:
            return "trial"

        # Map Stripe price IDs from environment variables to tiers
        price_id_mapping = {}

        # Map environment variables to tier names
        if basic_price_id := os.getenv("STRIPE_PRICE_ID_BASIC_MONTHLY"):
            price_id_mapping[basic_price_id] = "basic"

        if team_price_id := os.getenv("STRIPE_PRICE_ID_TEAM_MONTHLY"):
            price_id_mapping[team_price_id] = "team"

        if pro_price_id := os.getenv("STRIPE_PRICE_ID_PRO_MONTHLY"):
            price_id_mapping[pro_price_id] = "pro"

        if ultra_price_id := os.getenv("STRIPE_PRICE_ID_ULTRA_MONTHLY"):
            price_id_mapping[ultra_price_id] = "ultra"

        tier = price_id_mapping.get(stripe_price_id, "trial")
        logger.debug(f"Mapped price ID {stripe_price_id} to tier {tier}")

        return tier


# Singleton instance for global use
_billing_limits_service_instance: BillingLimitsService | None = None


def get_billing_limits_service() -> BillingLimitsService:
    """
    Get the global billing limits service instance.

    Returns:
        BillingLimitsService instance
    """
    global _billing_limits_service_instance

    if _billing_limits_service_instance is None:
        _billing_limits_service_instance = BillingLimitsService()

    return _billing_limits_service_instance
