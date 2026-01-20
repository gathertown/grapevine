"""
Usage Tracking Service

Implementation of usage tracking with Redis persistence.
Records usage data to Redis time-series and enforces usage limits.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from src.clients.redis import get_client as get_redis_client
from src.clients.tenant_db import tenant_db_manager
from src.utils.billing_limits import get_billing_limits_service
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Metric types that can be tracked
METRIC_TYPES = ["requests", "input_tokens", "output_tokens", "embedding_tokens"]

# Source types for usage recording
SOURCE_TYPES = [
    "ask_agent",
    "ask_agent_streaming",
    "ingest_embedding",
    "search",
    "review_pr_streaming",
]


class UsageCheckResult(NamedTuple):
    """Result of usage check and record operation."""

    allowed: bool
    is_trial: bool = (
        False  # True if tenant is on a trial plan (no subscription) or Stripe trial period
    )
    quota_exceeded: bool = False  # True if usage quota has been exceeded
    tier: str = "trial"  # Subscription tier (trial, team, pro, ultra, enterprise, expired_trial)


# Redis key expiration time (3 months in seconds)
REDIS_KEY_EXPIRATION_SECONDS = 3 * 30 * 24 * 60 * 60  # 3 months


class UsageTracker:
    """
    Usage tracking service with Redis persistence.

    Records usage data to Redis time-series and enforces usage limits
    based on subscription tiers and billing configuration.
    """

    def __init__(self):
        """Initialize usage tracker."""
        logger.info("UsageTracker initialized with Redis persistence")

    def record_usage(
        self,
        tenant_id: str,
        metric_type: str,
        metric_value: int,
        source_type: str,
        source_details: dict[str, Any] | None = None,
    ) -> None:
        """
        Record usage data for a tenant in a fire-and-forget manner.

        This method validates inputs and schedules background task for Redis writing,
        ensuring the calling request is not blocked by Redis operations.

        Args:
            tenant_id: Tenant identifier
            metric_type: Type of metric ('requests', 'input_tokens', 'output_tokens', 'embedding_tokens')
            metric_value: Value of the metric (must be positive)
            source_type: Source of the usage ('ask_agent', 'ingest_embedding', 'search')
            source_details: Optional additional context as JSON
        """
        # Input validation (sync, fast)
        if metric_type not in METRIC_TYPES:
            raise ValueError(f"Invalid metric_type: {metric_type}. Must be one of {METRIC_TYPES}")

        if source_type not in SOURCE_TYPES:
            raise ValueError(f"Invalid source_type: {source_type}. Must be one of {SOURCE_TYPES}")

        if metric_value < 0:
            raise ValueError("metric_value must be non-negative")

        if not tenant_id:
            raise ValueError("tenant_id is required")

        # Schedule background task for Redis writing
        # This returns immediately, not blocking the request
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # If no loop is running, we can't schedule background tasks
                logger.warning("No event loop running, cannot schedule background usage recording")
                return

            # Schedule the background task
            task = loop.create_task(
                self._record_usage_background(
                    tenant_id, metric_type, metric_value, source_type, source_details
                )
            )

            # Add done callback to handle any task exceptions
            task.add_done_callback(self._background_task_done_callback)

        except Exception as e:
            logger.error(f"Failed to schedule background usage recording: {e}", exc_info=True)
            # Fail open - don't block the request if we can't schedule the background task

    async def _record_usage_background(
        self,
        tenant_id: str,
        metric_type: str,
        metric_value: int,
        source_type: str,
        source_details: dict[str, Any] | None = None,
    ) -> None:
        """
        Background task for writing usage data to Redis.

        This method performs the actual Redis operations asynchronously
        without blocking the main request processing.

        Uses billing period keys based on subscription billing_cycle_anchor or trial_start_at.
        """
        recorded_at = datetime.now(UTC)

        # Get billing period start for the tenant
        billing_period_start = await self._get_billing_period_start(tenant_id)

        # Create billing period key for accurate usage tracking
        time_key = billing_period_start.strftime("%Y-%m-%d")
        redis_key = f"usage:{tenant_id}:{metric_type}:{time_key}"

        # Log the usage event for debugging
        log_data = {
            "tenant_id": tenant_id,
            "metric_type": metric_type,
            "metric_value": metric_value,
            "source_type": source_type,
            "redis_key": redis_key,
            "recorded_at": recorded_at.isoformat(),
        }

        if source_details:
            log_data["source_details"] = source_details

        logger.info(f"Recording usage (background): {json.dumps(log_data)}")

        # Write to Redis using atomic INCR operation
        redis_success = False
        try:
            redis_client = await get_redis_client()

            # Atomic increment - handles race conditions automatically
            await redis_client.incrby(redis_key, metric_value)

            # Set expiration to 3 months for automatic cleanup
            # Only set TTL if the key was just created (first time)
            ttl = await redis_client.ttl(redis_key)
            if ttl == -1:  # Key exists but no TTL set
                await redis_client.expire(redis_key, REDIS_KEY_EXPIRATION_SECONDS)

            redis_success = True
            logger.debug(f"Usage data successfully written to Redis for tenant {tenant_id}")
        except Exception as e:
            logger.error(
                f"Failed to record usage data to Redis for tenant {tenant_id}: {e}", exc_info=True
            )
            # Continue to attempt database write even if Redis fails

        # Write-through to tenant database
        db_success = await self._write_to_tenant_database(
            tenant_id, metric_type, metric_value, source_type, source_details, recorded_at
        )

        # Log overall success/failure
        if redis_success and db_success:
            logger.info(
                f"Usage tracking successful for tenant {tenant_id}: both Redis and database updated"
            )
        elif redis_success:
            logger.warning(
                f"Partial usage tracking success for tenant {tenant_id}: Redis OK, database failed"
            )
        elif db_success:
            logger.warning(
                f"Partial usage tracking success for tenant {tenant_id}: database OK, Redis failed"
            )
        else:
            logger.error(
                f"Usage tracking failed for tenant {tenant_id}: both Redis and database failed"
            )
            # This implements the "fail open" strategy - we don't raise exceptions from background tasks

    async def _write_to_tenant_database(
        self,
        tenant_id: str,
        metric_type: str,
        metric_value: int,
        source_type: str,
        source_details: dict[str, Any] | None,
        recorded_at: datetime,
    ) -> bool:
        """
        Write usage record to tenant database.

        Args:
            tenant_id: Tenant identifier
            metric_type: Type of metric being recorded
            metric_value: Value of the metric
            source_type: Source of the usage
            source_details: Optional additional context
            recorded_at: Timestamp when the usage occurred

        Returns:
            True if write succeeded, False if it failed
        """
        try:
            async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                # Insert usage record into tenant database
                await conn.execute(
                    """
                    INSERT INTO usage_records (metric_type, metric_value, source_type, source_details, recorded_at, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    metric_type,
                    metric_value,
                    source_type,
                    json.dumps(source_details) if source_details else None,
                    recorded_at,
                    recorded_at,
                )

            logger.debug(
                f"Usage data successfully written to tenant database for tenant {tenant_id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to record usage data to tenant database for tenant {tenant_id}: {e}",
                exc_info=True,
            )
            # Return False to indicate failure, but don't raise - this implements "fail open" strategy
            return False

    def _background_task_done_callback(self, task: asyncio.Task) -> None:
        """
        Callback for completed background tasks to handle any exceptions.
        """
        try:
            # This will raise the exception if the task failed
            task.result()
            logger.debug("Background usage recording task completed successfully")
        except Exception as e:
            logger.error(f"Background usage recording task failed: {e}", exc_info=True)
            # Don't re-raise - background task failures should not affect main flow

    async def get_monthly_usage(self, tenant_id: str, metric_type: str) -> int:
        """
        Get monthly usage for a tenant and metric type.

        Queries Redis billing period key to get total usage for the current billing period.
        Falls back to database query if Redis is unavailable or missing data.

        Args:
            tenant_id: Tenant identifier
            metric_type: Type of metric to query

        Returns:
            Total usage for the current billing period
        """
        if metric_type not in METRIC_TYPES:
            raise ValueError(f"Invalid metric_type: {metric_type}. Must be one of {METRIC_TYPES}")

        # Get billing period start for the tenant (needed for both Redis and DB queries)
        billing_period_start = await self._get_billing_period_start(tenant_id)

        try:
            logger.info(f"[usage_tracker] Getting Redis client for tenant {tenant_id}")
            redis_client = await get_redis_client()

            # Create billing period key
            time_key = billing_period_start.strftime("%Y-%m-%d")
            redis_key = f"usage:{tenant_id}:{metric_type}:{time_key}"

            # Single GET operation to fetch current billing period's usage
            logger.info(f"[usage_tracker] Querying Redis for usage key {redis_key}")
            value = await redis_client.get(redis_key)

            if value is not None:
                total = int(value)
                logger.info(
                    f"Billing period usage for {tenant_id}:{metric_type} = {total} (period: {time_key}) [Redis]"
                )
                return total
            else:
                logger.info(
                    f"[usage_tracker] No Redis data found for {tenant_id}:{metric_type}:{time_key}, falling back to database"
                )
                # Redis key doesn't exist - fall back to database and repopulate Redis
                db_usage = await self._get_usage_from_database(
                    tenant_id, metric_type, billing_period_start
                )

                # Repopulate Redis key to avoid future database hits
                logger.info(
                    f"[usage_tracker] Repopulating Redis key {redis_key} with DB value {db_usage}"
                )
                await self._populate_redis_key(redis_client, redis_key, db_usage)

                return db_usage

        except Exception as e:
            logger.warning(
                f"Redis unavailable for tenant {tenant_id}, falling back to database: {e}"
            )
            # Redis is unavailable - fall back to database
            return await self._get_usage_from_database(tenant_id, metric_type, billing_period_start)

    async def check_and_record_usage(
        self,
        tenant_id: str,
        usage_metrics: dict[str, int],
        source_type: str = "ask_agent",
        non_billable: bool = False,
    ) -> UsageCheckResult:
        """
        Combined function to check usage limits and record usage metrics.

        For gather-managed tenants, this function provides early exit without checking
        or recording usage, since they don't have usage limits.

        Args:
            tenant_id: Tenant identifier
            usage_metrics: Dictionary of metric types to values (e.g., {"requests": 1})
            source_type: Source of the usage ('ask_agent', 'ask_agent_streaming', etc.)
            non_billable: If True, skip usage recording (for internal operations like sample questions)

        Returns:
            UsageCheckResult with allowed flag and trial status
        """
        try:
            # Get tenant billing limits (includes gather-managed flag)
            limits = await self.get_tenant_limits(tenant_id)

            # Early exit for gather-managed tenants - no usage tracking needed
            if limits.is_gather_managed:
                logger.info(
                    f"Skipping usage check and recording for gather-managed tenant {tenant_id}"
                )
                return UsageCheckResult(
                    allowed=True,
                    is_trial=limits.is_trial,
                    quota_exceeded=False,
                    tier=limits.tier,
                )

            # Early exit for non-billable requests - skip usage recording
            if non_billable:
                logger.info(
                    f"Skipping usage recording for non-billable request for tenant {tenant_id}"
                )
                return UsageCheckResult(
                    allowed=True,
                    is_trial=limits.is_trial,
                    quota_exceeded=False,
                    tier=limits.tier,
                )

            # For non-gather-managed tenants, perform usage checks and recording
            for metric_type, metric_value in usage_metrics.items():
                if metric_type not in METRIC_TYPES:
                    raise ValueError(
                        f"Invalid metric_type: {metric_type}. Must be one of {METRIC_TYPES}"
                    )

                # Only check request limits for now (simplified approach)
                if metric_type == "requests":
                    current_usage = await self.get_monthly_usage(tenant_id, metric_type)
                    if current_usage + metric_value > limits.monthly_requests:
                        # Set quota_exceeded based on tier
                        # expired_trial tier means time-based expiration (not quota-based)
                        quota_exceeded = limits.tier != "expired_trial"

                        logger.warning(
                            f"Usage limit exceeded for tenant {tenant_id}: {current_usage + metric_value}/{limits.monthly_requests} {metric_type} (tier: {limits.tier}, trial: {limits.is_trial}, quota_exceeded: {quota_exceeded})"
                        )
                        return UsageCheckResult(
                            allowed=False,
                            is_trial=limits.is_trial,
                            quota_exceeded=quota_exceeded,
                            tier=limits.tier,
                        )

                # Record the usage (fire-and-forget)
                self.record_usage(
                    tenant_id=tenant_id,
                    metric_type=metric_type,
                    metric_value=metric_value,
                    source_type=source_type,
                )

            logger.info(
                f"Usage check and recording completed for tenant {tenant_id}: {usage_metrics} / {limits.monthly_requests} requests (tier: {limits.tier}, trial: {limits.is_trial})"
            )
            return UsageCheckResult(
                allowed=True,
                is_trial=limits.is_trial,
                quota_exceeded=False,
                tier=limits.tier,
            )

        except Exception as e:
            logger.error(
                f"Failed to check and record usage for tenant {tenant_id}: {e}", exc_info=True
            )
            # Fail open - allow requests if we can't check limits
            # Default to non-trial status in error case to avoid incorrect messaging
            return UsageCheckResult(
                allowed=True, is_trial=False, quota_exceeded=False, tier="trial"
            )

    async def get_tenant_limits(self, tenant_id: str):
        """
        Get billing limits for a tenant.

        Convenience method to access billing limits from the usage tracker.

        Args:
            tenant_id: Tenant identifier

        Returns:
            BillingLimits object with usage limits and tier information
        """
        billing_limits_service = get_billing_limits_service()
        return await billing_limits_service.get_tenant_limits(tenant_id)

    async def _get_billing_period_start(self, tenant_id: str) -> datetime:
        """
        Get the billing period start date for a tenant.

        Uses billing_cycle_anchor for subscriptions or trial_start_at for trials.
        Reuses existing billing limits service logic to avoid duplication.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Datetime representing the start of the current billing period
        """
        try:
            # Get tenant billing limits which includes billing_cycle_anchor and trial info
            billing_limits_service = get_billing_limits_service()
            limits = await billing_limits_service.get_tenant_limits(tenant_id)

            if limits.billing_cycle_anchor:
                # For subscriptions, use billing cycle anchor as the basis
                # The billing cycle anchor already represents the start of billing periods
                return self._calculate_current_billing_period(limits.billing_cycle_anchor)
            elif limits.trial_start_at:
                # For trials, use trial_start_at from billing limits (already cached)
                return limits.trial_start_at
            else:
                # Fallback case - no billing cycle anchor or trial start found
                logger.warning(
                    f"No billing cycle anchor or trial start found for tenant {tenant_id}"
                )
                now = datetime.now(UTC)
                return datetime(now.year, now.month, 1, tzinfo=UTC)

        except Exception as e:
            logger.error(
                f"Failed to get billing period start for tenant {tenant_id}: {e}", exc_info=True
            )
            # Fall back to calendar month for backward compatibility
            now = datetime.now(UTC)
            return datetime(now.year, now.month, 1, tzinfo=UTC)

    def _calculate_current_billing_period(self, billing_cycle_anchor: datetime) -> datetime:
        """
        Calculate the current billing period start based on billing cycle anchor.

        Args:
            billing_cycle_anchor: The billing cycle anchor date from subscription

        Returns:
            Start date of the current billing period
        """
        now = datetime.now(UTC)
        anchor = (
            billing_cycle_anchor.replace(tzinfo=UTC)
            if billing_cycle_anchor.tzinfo is None
            else billing_cycle_anchor
        )

        # Calculate how many full months have passed since anchor
        months_diff = (now.year - anchor.year) * 12 + (now.month - anchor.month)

        # If we haven't reached the anchor day this month, we're still in previous period
        if now.day < anchor.day:
            months_diff -= 1

        # Calculate current period start by adding months to anchor
        year_offset = months_diff // 12
        month_offset = months_diff % 12

        new_year = anchor.year + year_offset
        new_month = anchor.month + month_offset

        # Handle month overflow
        if new_month > 12:
            new_year += 1
            new_month -= 12
        elif new_month < 1:
            new_year -= 1
            new_month += 12

        return anchor.replace(year=new_year, month=new_month)

    async def _get_usage_from_database(
        self, tenant_id: str, metric_type: str, billing_period_start: datetime
    ) -> int:
        """
        Query tenant database for usage records within the current billing period.

        This method provides fallback functionality when Redis data is unavailable,
        aggregating usage from the persistent tenant database.

        Args:
            tenant_id: Tenant identifier
            metric_type: Type of metric to query
            billing_period_start: Start date of the current billing period

        Returns:
            Total usage for the current billing period from database records
        """
        try:
            # Calculate billing period end (start of next billing period)
            billing_period_end = self._calculate_next_billing_period_start(billing_period_start)

            logger.info(f"[usage_tracker] Acquiring tenant DB connection for tenant {tenant_id}")
            async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                # Query usage records within the billing period
                logger.info(
                    f"[usage_tracker] Querying tenant DB for usage aggregation, tenant {tenant_id}, "
                    f"period: {billing_period_start.strftime('%Y-%m-%d')} to {billing_period_end.strftime('%Y-%m-%d')}"
                )
                query = """
                    SELECT COALESCE(SUM(metric_value), 0) as total_usage
                    FROM usage_records
                    WHERE metric_type = $1
                      AND recorded_at >= $2
                      AND recorded_at < $3
                """

                result = await conn.fetchrow(
                    query, metric_type, billing_period_start, billing_period_end
                )

                total_usage = int(result["total_usage"]) if result else 0

                logger.info(
                    f"Database fallback usage for {tenant_id}:{metric_type} = {total_usage} "
                    f"(period: {billing_period_start.strftime('%Y-%m-%d')} to {billing_period_end.strftime('%Y-%m-%d')}) [Database]"
                )

                return total_usage

        except Exception as e:
            logger.error(
                f"Failed to query database usage for tenant {tenant_id}: {e}", exc_info=True
            )
            # Fail open - return 0 if database query fails
            logger.warning(f"Database fallback failed for tenant {tenant_id}, returning 0 usage")
            return 0

    def _calculate_next_billing_period_start(self, current_period_start: datetime) -> datetime:
        """
        Calculate the start date of the next billing period.

        Args:
            current_period_start: Start date of current billing period

        Returns:
            Start date of the next billing period (exclusive end for queries)
        """
        # Add one month to get next billing period start
        if current_period_start.month == 12:
            return current_period_start.replace(year=current_period_start.year + 1, month=1)
        else:
            try:
                return current_period_start.replace(month=current_period_start.month + 1)
            except ValueError:
                # Handle case where day doesn't exist in next month (e.g., Jan 31 -> Feb 28/29)
                # Move to the last day of the next month
                next_month = current_period_start.month + 1
                next_year = current_period_start.year

                # Get last day of next month by going to first day of month after next, then subtract 1 day
                from calendar import monthrange

                _, last_day = monthrange(next_year, next_month)

                return datetime(
                    next_year,
                    next_month,
                    min(current_period_start.day, last_day),
                    current_period_start.hour,
                    current_period_start.minute,
                    current_period_start.second,
                    current_period_start.microsecond,
                    current_period_start.tzinfo,
                )

    async def rehydrate_redis_from_database(
        self, tenant_id: str, metric_type: str | None = None, days_back: int = 90
    ) -> dict[str, int]:
        """
        Rehydrate Redis usage data from database records.

        This method can be used to restore Redis data from the persistent database
        when Redis data is lost or needs to be rebuilt.

        Args:
            tenant_id: Tenant identifier
            metric_type: Specific metric type to rehydrate, or None for all metrics
            days_back: Number of days back to rehydrate (default: 90 days)

        Returns:
            Dictionary mapping Redis keys to values that were restored
        """
        restored_keys = {}
        metrics_to_process = [metric_type] if metric_type else METRIC_TYPES

        try:
            # Calculate cutoff date
            cutoff_date = datetime.now(UTC) - timedelta(days=days_back)

            async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                for metric in metrics_to_process:
                    # Query database for usage records grouped by billing period
                    query = """
                        SELECT
                            DATE_TRUNC('day', recorded_at) as record_date,
                            SUM(metric_value) as total_value
                        FROM usage_records
                        WHERE metric_type = $1
                          AND recorded_at >= $2
                        GROUP BY DATE_TRUNC('day', recorded_at)
                        ORDER BY record_date
                    """

                    rows = await conn.fetch(query, metric, cutoff_date)

                    for row in rows:
                        record_date = row["record_date"]
                        total_value = int(row["total_value"])

                        # Create Redis key for this date
                        time_key = record_date.strftime("%Y-%m-%d")
                        redis_key = f"usage:{tenant_id}:{metric}:{time_key}"

                        try:
                            # Set the value in Redis
                            redis_client = await get_redis_client()
                            await redis_client.set(redis_key, total_value)

                            # Set expiration to 3 months
                            await redis_client.expire(redis_key, REDIS_KEY_EXPIRATION_SECONDS)

                            restored_keys[redis_key] = total_value

                            logger.debug(f"Restored Redis key {redis_key} = {total_value}")

                        except Exception as e:
                            logger.error(f"Failed to restore Redis key {redis_key}: {e}")

            logger.info(
                f"Rehydrated {len(restored_keys)} Redis keys for tenant {tenant_id} "
                f"(metrics: {metrics_to_process}, {days_back} days back)"
            )

        except Exception as e:
            logger.error(f"Failed to rehydrate Redis for tenant {tenant_id}: {e}", exc_info=True)

        return restored_keys

    async def _populate_redis_key(self, redis_client, redis_key: str, value: int) -> None:
        """
        Safely populate a Redis key with a value.

        Uses SET to overwrite any existing value, since we're repopulating from
        the authoritative database source.

        Args:
            redis_client: Redis client instance
            redis_key: Redis key to populate
            value: Value to set
        """
        try:
            # Set the value in Redis (overwrites if exists)
            await redis_client.set(redis_key, value)

            # Set expiration to 3 months for automatic cleanup
            await redis_client.expire(redis_key, REDIS_KEY_EXPIRATION_SECONDS)

            logger.debug(f"Populated Redis key {redis_key} = {value}")

        except Exception as e:
            logger.warning(f"Failed to populate Redis key {redis_key}: {e}")
            # Don't raise - Redis population failure shouldn't block the read operation


# Singleton instance for global use
_usage_tracker_instance: UsageTracker | None = None


def get_usage_tracker() -> UsageTracker:
    """
    Get the global usage tracker instance.

    Returns:
        UsageTracker instance
    """
    global _usage_tracker_instance

    if _usage_tracker_instance is None:
        _usage_tracker_instance = UsageTracker()

    return _usage_tracker_instance
