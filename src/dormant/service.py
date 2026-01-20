"""
Dormant tenant detection service.

Provides logic to detect tenants that have been provisioned but never set up
any integrations, Slack bot, or ingested any documents.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import asyncpg

from src.clients.tenant_db import tenant_db_manager
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Default configuration values
DEFAULT_DORMANT_DAYS_THRESHOLD = 7
DEFAULT_GRACE_PERIOD_DAYS = 14

# Concurrency limit for tenant DB queries to avoid overwhelming connections
TENANT_DB_CONCURRENCY_LIMIT = 5

# Cache for dormant columns existence check (doesn't change during execution)
_dormant_columns_cache: bool | None = None


def get_dormant_days_threshold() -> int:
    """Get the number of days after provisioning to consider a tenant dormant."""
    return int(os.environ.get("DORMANT_DAYS_THRESHOLD", DEFAULT_DORMANT_DAYS_THRESHOLD))


def get_grace_period_days() -> int:
    """Get the number of days after marking dormant before auto-deletion is allowed."""
    return int(os.environ.get("DORMANT_GRACE_PERIOD_DAYS", DEFAULT_GRACE_PERIOD_DAYS))


def is_auto_delete_enabled() -> bool:
    """Check if automatic deletion of expired dormant tenants is enabled."""
    from src.utils.config import get_config_value

    return get_config_value("DORMANT_AUTO_DELETE_ENABLED", False)


def is_detection_enabled() -> bool:
    """Check if dormant detection cron job is enabled."""
    from src.utils.config import get_config_value

    return get_config_value("DORMANT_DETECTION_ENABLED", False)


@dataclass
class TenantInfo:
    """Basic tenant information from control database."""

    id: str
    state: str
    provisioned_at: datetime | None
    created_at: datetime
    workos_org_id: str | None
    is_dormant: bool
    dormant_detected_at: datetime | None


@dataclass
class DormancyCheckResult:
    """Result of checking a tenant for dormancy."""

    tenant_id: str
    is_dormant: bool
    reasons: list[str]
    has_connectors: bool
    has_slack_bot: bool
    document_count: int
    usage_count: int
    days_since_provisioning: int | None
    company_name: str | None = None


@dataclass
class _BatchedControlData:
    """Pre-fetched control DB data for all tenants."""

    tenants_with_connectors: set[str] = field(default_factory=set)
    tenants_with_slack_bot: set[str] = field(default_factory=set)


async def _check_dormant_columns_exist(control_pool: asyncpg.Pool) -> bool:
    """Check if the dormant tracking columns exist in the tenants table (cached)."""
    global _dormant_columns_cache

    # Return cached result if available (schema doesn't change during execution)
    if _dormant_columns_cache is not None:
        return _dormant_columns_cache

    async with control_pool.acquire() as conn:
        result = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'tenants' AND column_name = 'is_dormant'
            )
            """
        )
        _dormant_columns_cache = bool(result)
        return _dormant_columns_cache


def clear_dormant_columns_cache() -> None:
    """Clear the dormant columns cache. Useful for testing."""
    global _dormant_columns_cache
    _dormant_columns_cache = None


async def get_all_provisioned_tenants(
    control_pool: asyncpg.Pool,
    min_age_days: int | None = None,
    include_already_dormant: bool = False,
) -> list[TenantInfo]:
    """
    Get all provisioned tenants from control database.

    Args:
        control_pool: Control database connection pool
        min_age_days: Only return tenants provisioned at least this many days ago
        include_already_dormant: Whether to include tenants already marked as dormant

    Returns:
        List of TenantInfo objects
    """
    # Check if dormant columns exist (migration may not have been applied)
    has_dormant_columns = await _check_dormant_columns_exist(control_pool)

    if has_dormant_columns:
        query = """
            SELECT id, state, provisioned_at, created_at, workos_org_id,
                   COALESCE(is_dormant, FALSE) as is_dormant, dormant_detected_at
            FROM tenants
            WHERE state = 'provisioned'
              AND deleted_at IS NULL
        """
    else:
        # Fallback query without dormant columns (pre-migration)
        query = """
            SELECT id, state, provisioned_at, created_at, workos_org_id
            FROM tenants
            WHERE state = 'provisioned'
              AND deleted_at IS NULL
        """

    params: list = []

    if min_age_days is not None:
        cutoff_date = datetime.now(UTC) - timedelta(days=min_age_days)
        query += " AND provisioned_at < $1"
        params.append(cutoff_date)

    if not include_already_dormant and has_dormant_columns:
        query += " AND (is_dormant IS NULL OR is_dormant = FALSE)"

    query += " ORDER BY provisioned_at ASC"

    async with control_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [
            TenantInfo(
                id=row["id"],
                state=row["state"],
                provisioned_at=row["provisioned_at"],
                created_at=row["created_at"],
                workos_org_id=row["workos_org_id"],
                is_dormant=row.get("is_dormant", False) if has_dormant_columns else False,
                dormant_detected_at=row.get("dormant_detected_at") if has_dormant_columns else None,
            )
            for row in rows
        ]


async def get_dormant_tenants(control_pool: asyncpg.Pool) -> list[TenantInfo]:
    """Get all tenants currently marked as dormant."""
    # Check if dormant columns exist
    has_dormant_columns = await _check_dormant_columns_exist(control_pool)
    if not has_dormant_columns:
        logger.warning("Dormant columns not found - migration may not have been applied")
        return []

    query = """
        SELECT id, state, provisioned_at, created_at, workos_org_id,
               is_dormant, dormant_detected_at
        FROM tenants
        WHERE is_dormant = TRUE
          AND deleted_at IS NULL
        ORDER BY dormant_detected_at ASC
    """

    async with control_pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [
            TenantInfo(
                id=row["id"],
                state=row["state"],
                provisioned_at=row["provisioned_at"],
                created_at=row["created_at"],
                workos_org_id=row["workos_org_id"],
                is_dormant=row["is_dormant"],
                dormant_detected_at=row["dormant_detected_at"],
            )
            for row in rows
        ]


async def get_expired_dormant_tenants(control_pool: asyncpg.Pool) -> list[TenantInfo]:
    """Get dormant tenants that have passed the grace period and are eligible for deletion."""
    # Check if dormant columns exist
    has_dormant_columns = await _check_dormant_columns_exist(control_pool)
    if not has_dormant_columns:
        logger.warning("Dormant columns not found - migration may not have been applied")
        return []

    grace_period_days = get_grace_period_days()
    cutoff_date = datetime.now(UTC) - timedelta(days=grace_period_days)

    query = """
        SELECT id, state, provisioned_at, created_at, workos_org_id,
               is_dormant, dormant_detected_at
        FROM tenants
        WHERE is_dormant = TRUE
          AND deleted_at IS NULL
          AND dormant_detected_at < $1
        ORDER BY dormant_detected_at ASC
    """

    async with control_pool.acquire() as conn:
        rows = await conn.fetch(query, cutoff_date)
        return [
            TenantInfo(
                id=row["id"],
                state=row["state"],
                provisioned_at=row["provisioned_at"],
                created_at=row["created_at"],
                workos_org_id=row["workos_org_id"],
                is_dormant=row["is_dormant"],
                dormant_detected_at=row["dormant_detected_at"],
            )
            for row in rows
        ]


async def check_has_connectors(control_pool: asyncpg.Pool, tenant_id: str) -> bool:
    """Check if tenant has any connector installations."""
    async with control_pool.acquire() as conn:
        # Use EXISTS instead of COUNT(*) - stops at first match
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM connector_installations WHERE tenant_id = $1)",
            tenant_id,
        )
        return bool(exists)


async def check_has_slack_bot(control_pool: asyncpg.Pool, tenant_id: str) -> bool:
    """Check if tenant has Slack bot installed."""
    async with control_pool.acquire() as conn:
        # Use EXISTS instead of COUNT(*) - stops at first match
        exists = await conn.fetchval(
            """SELECT EXISTS(
                SELECT 1 FROM connector_installations
                WHERE tenant_id = $1 AND type = 'slack' AND status != 'disconnected'
            )""",
            tenant_id,
        )
        return bool(exists)


async def _batch_fetch_control_data(
    control_pool: asyncpg.Pool, tenant_ids: list[str]
) -> _BatchedControlData:
    """
    Batch fetch connector and slack installation data for multiple tenants.

    This reduces N+1 queries to just 2 queries total, regardless of tenant count.
    """
    if not tenant_ids:
        return _BatchedControlData()

    async with control_pool.acquire() as conn:
        # Single query to get all tenants with connectors
        connector_rows = await conn.fetch(
            """
            SELECT DISTINCT tenant_id
            FROM connector_installations
            WHERE tenant_id = ANY($1)
            """,
            tenant_ids,
        )
        tenants_with_connectors = {row["tenant_id"] for row in connector_rows}

        # Single query to get all tenants with slack bot
        slack_rows = await conn.fetch(
            """
            SELECT DISTINCT tenant_id
            FROM connector_installations
            WHERE tenant_id = ANY($1) AND type = 'slack' AND status != 'disconnected'
            """,
            tenant_ids,
        )
        tenants_with_slack_bot = {row["tenant_id"] for row in slack_rows}

    logger.debug(
        f"Batch fetched control data: {len(tenants_with_connectors)} with connectors, "
        f"{len(tenants_with_slack_bot)} with slack bot"
    )

    return _BatchedControlData(
        tenants_with_connectors=tenants_with_connectors,
        tenants_with_slack_bot=tenants_with_slack_bot,
    )


@dataclass
class _TenantDBData:
    """Combined tenant DB data fetched in a single query."""

    document_count: int = 0
    usage_count: int = 0
    company_name: str | None = None


async def _fetch_tenant_db_data(tenant_id: str) -> _TenantDBData:
    """
    Fetch all required tenant DB data in a single connection.

    Combines document count, usage count, and company name queries.
    Note: Queries run sequentially on the same connection (asyncpg limitation).
    The efficiency gain comes from reusing the connection, not parallel queries.

    Raises:
        Exception: If database connection or queries fail. Callers should handle
            errors appropriately - a failed fetch should NOT result in default
            values being used, as this could incorrectly mark active tenants as dormant.
    """
    async with tenant_db_manager.acquire_connection(tenant_id, readonly=True) as conn:
        # Run queries sequentially on the same connection
        # (asyncpg doesn't support concurrent queries on a single connection)
        doc_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
        usage_count = await conn.fetchval("SELECT COUNT(*) FROM usage_records")
        company_name = await conn.fetchval("SELECT value FROM config WHERE key = 'COMPANY_NAME'")
        return _TenantDBData(
            document_count=doc_count or 0,
            usage_count=usage_count or 0,
            company_name=company_name,
        )


async def get_document_count(tenant_id: str) -> int:
    """
    Get the number of documents in tenant's database (uses read-only connection).

    Raises:
        Exception: If database connection or query fails. Callers should handle
            errors appropriately - a failed fetch should NOT result in default
            values being used, as this could incorrectly mark active tenants as dormant.
    """
    async with tenant_db_manager.acquire_connection(tenant_id, readonly=True) as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM documents")
        return count or 0


async def get_usage_count(tenant_id: str) -> int:
    """
    Get the number of usage records in tenant's database (uses read-only connection).

    Raises:
        Exception: If database connection or query fails. Callers should handle
            errors appropriately - a failed fetch should NOT result in default
            values being used, as this could incorrectly mark active tenants as dormant.
    """
    async with tenant_db_manager.acquire_connection(tenant_id, readonly=True) as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM usage_records")
        return count or 0


async def get_company_name(tenant_id: str) -> str | None:
    """Get the company name from tenant's config (uses read-only connection)."""
    try:
        async with tenant_db_manager.acquire_connection(tenant_id, readonly=True) as conn:
            value = await conn.fetchval("SELECT value FROM config WHERE key = 'COMPANY_NAME'")
            return value
    except Exception as e:
        logger.warning(f"Failed to get company name for tenant {tenant_id}: {e}")
        return None


async def check_tenant_dormancy(
    control_pool: asyncpg.Pool,
    tenant: TenantInfo,
) -> DormancyCheckResult:
    """
    Check if a tenant meets all criteria for being considered dormant.

    A tenant is dormant if ALL of these conditions are true:
    - No connector installations
    - No Slack bot installed
    - Zero documents in tenant database
    - No MCP usage/requests recorded
    - Provisioned more than DORMANT_DAYS_THRESHOLD days ago

    Args:
        control_pool: Control database connection pool
        tenant: TenantInfo object to check

    Returns:
        DormancyCheckResult with detailed findings

    Note:
        If tenant DB queries fail (e.g., transient connectivity issues), this function
        will fail-safe by returning is_dormant=False to avoid incorrectly marking
        active tenants as dormant. The error will be logged.
    """
    reasons: list[str] = []

    # Check connectors
    has_connectors = await check_has_connectors(control_pool, tenant.id)
    if not has_connectors:
        reasons.append("No connector installations")

    # Check Slack bot
    has_slack_bot = await check_has_slack_bot(control_pool, tenant.id)
    if not has_slack_bot:
        reasons.append("No Slack bot installed")

    # Check documents and usage - catch exceptions to fail-safe
    # If we can't fetch this data, we should NOT mark as dormant
    document_count = 0
    usage_count = 0
    try:
        document_count = await get_document_count(tenant.id)
        usage_count = await get_usage_count(tenant.id)
    except Exception as e:
        # Fail-safe: if we can't fetch tenant DB data, don't mark as dormant
        # This prevents incorrectly marking active tenants as dormant during
        # transient database connectivity issues
        logger.error(
            f"Failed to fetch tenant DB data for {tenant.id}, cannot determine dormancy: {e}"
        )
        # Return early with is_dormant=False since we can't verify dormancy criteria
        return DormancyCheckResult(
            tenant_id=tenant.id,
            is_dormant=False,  # Fail-safe: don't mark as dormant if we can't verify
            reasons=[],
            has_connectors=has_connectors,
            has_slack_bot=has_slack_bot,
            document_count=0,  # Unknown due to error
            usage_count=0,  # Unknown due to error
            days_since_provisioning=None,
            company_name=None,
        )

    if document_count == 0:
        reasons.append("Zero documents")

    if usage_count == 0:
        reasons.append("No MCP usage recorded")

    # Calculate days since provisioning
    # Fall back to created_at if provisioned_at is not set (for tenants provisioned
    # before the column was added, or edge cases where state is 'provisioned' but
    # provisioned_at wasn't set)
    days_since_provisioning = None
    if tenant.provisioned_at:
        delta = datetime.now(UTC) - tenant.provisioned_at.replace(tzinfo=UTC)
        days_since_provisioning = delta.days
    elif tenant.created_at:
        # Fallback to created_at if provisioned_at is NULL
        delta = datetime.now(UTC) - tenant.created_at.replace(tzinfo=UTC)
        days_since_provisioning = delta.days

    threshold = get_dormant_days_threshold()
    if days_since_provisioning is not None and days_since_provisioning >= threshold:
        reasons.append(f"Provisioned {days_since_provisioning} days ago (threshold: {threshold})")

    # Get company name for reporting (non-critical, so we allow it to fail silently)
    company_name = await get_company_name(tenant.id)

    # Tenant is dormant if ALL conditions are met
    is_dormant = (
        not has_connectors
        and not has_slack_bot
        and document_count == 0
        and usage_count == 0
        and days_since_provisioning is not None
        and days_since_provisioning >= get_dormant_days_threshold()
    )

    return DormancyCheckResult(
        tenant_id=tenant.id,
        is_dormant=is_dormant,
        reasons=reasons if is_dormant else [],
        has_connectors=has_connectors,
        has_slack_bot=has_slack_bot,
        document_count=document_count,
        usage_count=usage_count,
        days_since_provisioning=days_since_provisioning,
        company_name=company_name,
    )


async def mark_tenant_dormant(control_pool: asyncpg.Pool, tenant_id: str) -> bool:
    """
    Mark a tenant as dormant in the control database.

    Args:
        control_pool: Control database connection pool
        tenant_id: Tenant ID to mark

    Returns:
        True if successfully marked, False otherwise
    """
    # Check if dormant columns exist
    has_dormant_columns = await _check_dormant_columns_exist(control_pool)
    if not has_dormant_columns:
        logger.warning(
            f"Cannot mark tenant {tenant_id} as dormant - migration not applied. "
            "Run the migration first or use --mark=False for dry-run only."
        )
        return False

    try:
        async with control_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tenants
                SET is_dormant = TRUE,
                    dormant_detected_at = $1,
                    updated_at = $1
                WHERE id = $2
                  AND (is_dormant IS NULL OR is_dormant = FALSE)
                """,
                datetime.now(UTC),
                tenant_id,
            )
        logger.info(f"Marked tenant {tenant_id} as dormant")
        return True
    except Exception as e:
        logger.error(f"Failed to mark tenant {tenant_id} as dormant: {e}")
        return False


async def unmark_tenant_dormant(control_pool: asyncpg.Pool, tenant_id: str) -> bool:
    """
    Remove dormant marking from a tenant.

    Args:
        control_pool: Control database connection pool
        tenant_id: Tenant ID to unmark

    Returns:
        True if successfully unmarked, False otherwise
    """
    # Check if dormant columns exist
    has_dormant_columns = await _check_dormant_columns_exist(control_pool)
    if not has_dormant_columns:
        logger.warning(f"Cannot unmark tenant {tenant_id} - migration not applied")
        return False

    try:
        async with control_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tenants
                SET is_dormant = FALSE,
                    dormant_detected_at = NULL,
                    updated_at = $1
                WHERE id = $2
                """,
                datetime.now(UTC),
                tenant_id,
            )
        logger.info(f"Unmarked tenant {tenant_id} as dormant")
        return True
    except Exception as e:
        logger.error(f"Failed to unmark tenant {tenant_id} as dormant: {e}")
        return False


@dataclass
class ScanResult:
    """Result of scanning tenants for dormancy."""

    total_scanned: int
    dormant_candidates: list[DormancyCheckResult]
    newly_marked: int
    errors: list[str]


@dataclass
class ActiveScanResult:
    """Result of scanning tenants for active (non-dormant) status."""

    total_scanned: int
    active_tenants: list[DormancyCheckResult]
    errors: list[str]


async def _check_tenant_dormancy_with_prefetched(
    tenant: TenantInfo,
    control_data: _BatchedControlData,
    tenant_db_data: _TenantDBData,
) -> DormancyCheckResult:
    """
    Check tenant dormancy using pre-fetched data.

    This is an optimized version that uses batched control DB data
    and combined tenant DB data.
    """
    reasons: list[str] = []
    threshold = get_dormant_days_threshold()

    # Use pre-fetched control data
    has_connectors = tenant.id in control_data.tenants_with_connectors
    has_slack_bot = tenant.id in control_data.tenants_with_slack_bot

    if not has_connectors:
        reasons.append("No connector installations")
    if not has_slack_bot:
        reasons.append("No Slack bot installed")

    # Use pre-fetched tenant DB data
    document_count = tenant_db_data.document_count
    usage_count = tenant_db_data.usage_count
    company_name = tenant_db_data.company_name

    if document_count == 0:
        reasons.append("Zero documents")
    if usage_count == 0:
        reasons.append("No MCP usage recorded")

    # Calculate days since provisioning
    # Fall back to created_at if provisioned_at is not set (for tenants provisioned
    # before the column was added, or edge cases where state is 'provisioned' but
    # provisioned_at wasn't set)
    days_since_provisioning = None
    if tenant.provisioned_at:
        delta = datetime.now(UTC) - tenant.provisioned_at.replace(tzinfo=UTC)
        days_since_provisioning = delta.days
    elif tenant.created_at:
        # Fallback to created_at if provisioned_at is NULL
        delta = datetime.now(UTC) - tenant.created_at.replace(tzinfo=UTC)
        days_since_provisioning = delta.days

    if days_since_provisioning is not None and days_since_provisioning >= threshold:
        reasons.append(f"Provisioned {days_since_provisioning} days ago (threshold: {threshold})")

    # Tenant is dormant if ALL conditions are met
    is_dormant = (
        not has_connectors
        and not has_slack_bot
        and document_count == 0
        and usage_count == 0
        and days_since_provisioning is not None
        and days_since_provisioning >= threshold
    )

    return DormancyCheckResult(
        tenant_id=tenant.id,
        is_dormant=is_dormant,
        reasons=reasons if is_dormant else [],
        has_connectors=has_connectors,
        has_slack_bot=has_slack_bot,
        document_count=document_count,
        usage_count=usage_count,
        days_since_provisioning=days_since_provisioning,
        company_name=company_name,
    )


async def scan_for_dormant_tenants(
    mark: bool = False,
) -> ScanResult:
    """
    Scan all provisioned tenants for dormancy.

    This is an optimized implementation that:
    1. Batches control DB queries (2 queries total vs N*2)
    2. Skips tenant DB queries for tenants with connectors/slack (early exit)
    3. Runs tenant DB queries with controlled concurrency
    4. Combines multiple tenant DB queries into one connection

    Args:
        mark: If True, mark detected dormant tenants in the database

    Returns:
        ScanResult with summary and details
    """
    control_pool = await tenant_db_manager.get_control_db()

    # Get all provisioned tenants older than threshold
    threshold_days = get_dormant_days_threshold()
    tenants = await get_all_provisioned_tenants(
        control_pool,
        min_age_days=threshold_days,
        include_already_dormant=False,
    )

    if not tenants:
        logger.info("No tenants to scan for dormancy")
        return ScanResult(total_scanned=0, dormant_candidates=[], newly_marked=0, errors=[])

    logger.info(f"Scanning {len(tenants)} tenants for dormancy (threshold: {threshold_days} days)")

    # Step 1: Batch fetch all control DB data in 2 queries (vs 2*N queries before)
    tenant_ids = [t.id for t in tenants]
    control_data = await _batch_fetch_control_data(control_pool, tenant_ids)

    # Step 2: Filter tenants that need tenant DB queries (early termination optimization)
    # If a tenant has connectors OR slack bot, they can't be dormant - skip expensive tenant DB queries
    tenants_needing_db_check = [
        t
        for t in tenants
        if t.id not in control_data.tenants_with_connectors
        and t.id not in control_data.tenants_with_slack_bot
    ]

    logger.info(
        f"Skipping tenant DB queries for {len(tenants) - len(tenants_needing_db_check)} tenants "
        f"with connectors or slack bot (early exit optimization)"
    )

    # Step 3: Fetch tenant DB data with controlled concurrency using semaphore
    semaphore = asyncio.Semaphore(TENANT_DB_CONCURRENCY_LIMIT)
    tenant_db_data_map: dict[str, _TenantDBData] = {}
    # Track tenants that had DB fetch errors - these must be excluded from dormancy
    # consideration to avoid incorrectly marking active tenants as dormant during
    # transient database connectivity issues
    tenants_with_fetch_errors: set[str] = set()
    errors: list[str] = []

    async def fetch_with_semaphore(tenant_id: str) -> tuple[str, _TenantDBData | None, str | None]:
        async with semaphore:
            try:
                data = await _fetch_tenant_db_data(tenant_id)
                return (tenant_id, data, None)
            except Exception as e:
                error_msg = f"Error fetching DB data for tenant {tenant_id}: {e}"
                logger.error(error_msg)
                return (tenant_id, None, error_msg)

    # Run tenant DB queries concurrently (with semaphore limiting)
    if tenants_needing_db_check:
        fetch_results = await asyncio.gather(
            *[fetch_with_semaphore(t.id) for t in tenants_needing_db_check],
            return_exceptions=True,
        )

        # Use zip to correlate results with tenant IDs so we can track which tenant
        # had errors even when BaseException occurs (e.g., CancelledError)
        for tenant, fetch_result in zip(tenants_needing_db_check, fetch_results, strict=False):
            tenant_id = tenant.id
            if isinstance(fetch_result, BaseException):
                error_msg = f"Unexpected error for tenant {tenant_id}: {fetch_result}"
                errors.append(error_msg)
                logger.error(error_msg)
                # Track this tenant as having a fetch error - do NOT use default
                # values which would make them appear dormant
                tenants_with_fetch_errors.add(tenant_id)
            else:
                _, data, error = fetch_result
                if error:
                    errors.append(error)
                    # Track this tenant as having a fetch error - do NOT use default
                    # values which would make them appear dormant
                    tenants_with_fetch_errors.add(tenant_id)
                if data:
                    tenant_db_data_map[tenant_id] = data

    if tenants_with_fetch_errors:
        logger.warning(
            f"Excluding {len(tenants_with_fetch_errors)} tenants from dormancy check "
            f"due to DB fetch errors (fail-safe to avoid false positives)"
        )

    # Step 4: Build dormancy results
    dormant_candidates: list[DormancyCheckResult] = []

    for tenant in tenants:
        # Skip tenants that had DB fetch errors - we cannot safely determine their
        # dormancy status and must fail-safe to avoid incorrectly marking active
        # tenants as dormant
        if tenant.id in tenants_with_fetch_errors:
            logger.debug(f"Skipping tenant {tenant.id} due to DB fetch error")
            continue

        # For tenants with connectors/slack, use empty tenant DB data (they won't be dormant anyway)
        tenant_db_data = tenant_db_data_map.get(tenant.id, _TenantDBData())

        dormancy_result = await _check_tenant_dormancy_with_prefetched(
            tenant, control_data, tenant_db_data
        )

        if dormancy_result.is_dormant:
            dormant_candidates.append(dormancy_result)

    # Step 5: Mark dormant tenants (if requested)
    newly_marked = 0
    if mark and dormant_candidates:
        # Batch mark could be more efficient, but marking is infrequent
        # and individual updates allow for better error tracking
        for candidate in dormant_candidates:
            try:
                success = await mark_tenant_dormant(control_pool, candidate.tenant_id)
                if success:
                    newly_marked += 1
                else:
                    errors.append(f"Failed to mark tenant {candidate.tenant_id}")
            except Exception as e:
                error_msg = f"Error marking tenant {candidate.tenant_id}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

    return ScanResult(
        total_scanned=len(tenants),
        dormant_candidates=dormant_candidates,
        newly_marked=newly_marked,
        errors=errors,
    )


async def scan_for_active_tenants() -> ActiveScanResult:
    """
    Scan all provisioned tenants and return those that are NOT dormant (active).

    This is the reverse of scan_for_dormant_tenants - it shows tenants that
    don't meet dormancy criteria (have connectors, slack bot, documents, usage, etc.).

    Returns:
        ActiveScanResult with active tenants
    """
    control_pool = await tenant_db_manager.get_control_db()

    # Get all provisioned tenants (no age filter for active scan)
    tenants = await get_all_provisioned_tenants(
        control_pool,
        min_age_days=None,  # Check all tenants regardless of age
        include_already_dormant=False,  # Exclude already marked dormant
    )

    if not tenants:
        logger.info("No tenants to scan for active status")
        return ActiveScanResult(total_scanned=0, active_tenants=[], errors=[])

    logger.info(f"Scanning {len(tenants)} tenants for active (non-dormant) status")

    # Step 1: Batch fetch all control DB data
    tenant_ids = [t.id for t in tenants]
    control_data = await _batch_fetch_control_data(control_pool, tenant_ids)

    # Step 2: Fetch tenant DB data with controlled concurrency
    semaphore = asyncio.Semaphore(TENANT_DB_CONCURRENCY_LIMIT)
    tenant_db_data_map: dict[str, _TenantDBData] = {}
    tenants_with_fetch_errors: set[str] = set()
    errors: list[str] = []

    async def fetch_with_semaphore(tenant_id: str) -> tuple[str, _TenantDBData | None, str | None]:
        async with semaphore:
            try:
                data = await _fetch_tenant_db_data(tenant_id)
                return (tenant_id, data, None)
            except Exception as e:
                error_msg = f"Error fetching DB data for tenant {tenant_id}: {e}"
                logger.error(error_msg)
                return (tenant_id, None, error_msg)

    # Run tenant DB queries concurrently
    fetch_results = await asyncio.gather(
        *[fetch_with_semaphore(t.id) for t in tenants],
        return_exceptions=True,
    )

    for tenant, fetch_result in zip(tenants, fetch_results, strict=False):
        tenant_id = tenant.id
        if isinstance(fetch_result, BaseException):
            error_msg = f"Unexpected error for tenant {tenant_id}: {fetch_result}"
            errors.append(error_msg)
            logger.error(error_msg)
            tenants_with_fetch_errors.add(tenant_id)
        else:
            _, data, error = fetch_result
            if error:
                errors.append(error)
                tenants_with_fetch_errors.add(tenant_id)
            if data:
                tenant_db_data_map[tenant_id] = data

    # Step 3: Build active tenant results (reverse of dormant check)
    active_tenants: list[DormancyCheckResult] = []

    for tenant in tenants:
        # Skip tenants that had DB fetch errors
        if tenant.id in tenants_with_fetch_errors:
            logger.debug(f"Skipping tenant {tenant.id} due to DB fetch error")
            continue

        # Get tenant DB data (use empty if not fetched)
        tenant_db_data = tenant_db_data_map.get(tenant.id, _TenantDBData())

        # Check dormancy status
        dormancy_result = await _check_tenant_dormancy_with_prefetched(
            tenant, control_data, tenant_db_data
        )

        # Active tenants are those that are NOT dormant
        if not dormancy_result.is_dormant:
            active_tenants.append(dormancy_result)

    return ActiveScanResult(
        total_scanned=len(tenants),
        active_tenants=active_tenants,
        errors=errors,
    )


async def get_tenant_info(tenant_id: str) -> TenantInfo | None:
    """Get tenant info by ID."""
    control_pool = await tenant_db_manager.get_control_db()

    # Check if dormant columns exist
    has_dormant_columns = await _check_dormant_columns_exist(control_pool)

    if has_dormant_columns:
        query = """
            SELECT id, state, provisioned_at, created_at, workos_org_id,
                   COALESCE(is_dormant, FALSE) as is_dormant, dormant_detected_at
            FROM tenants
            WHERE id = $1
        """
    else:
        query = """
            SELECT id, state, provisioned_at, created_at, workos_org_id
            FROM tenants
            WHERE id = $1
        """

    async with control_pool.acquire() as conn:
        row = await conn.fetchrow(query, tenant_id)

        if row is None:
            return None

        return TenantInfo(
            id=row["id"],
            state=row["state"],
            provisioned_at=row["provisioned_at"],
            created_at=row["created_at"],
            workos_org_id=row["workos_org_id"],
            is_dormant=row.get("is_dormant", False) if has_dormant_columns else False,
            dormant_detected_at=row.get("dormant_detected_at") if has_dormant_columns else None,
        )


async def inspect_tenant(tenant_id: str) -> DormancyCheckResult | None:
    """
    Inspect a specific tenant's dormancy status.

    Args:
        tenant_id: Tenant ID to inspect

    Returns:
        DormancyCheckResult or None if tenant not found
    """
    tenant = await get_tenant_info(tenant_id)
    if tenant is None:
        return None

    control_pool = await tenant_db_manager.get_control_db()
    return await check_tenant_dormancy(control_pool, tenant)
