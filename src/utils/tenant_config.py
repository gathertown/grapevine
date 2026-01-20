"""Tenant-specific config DB utilities."""

import asyncpg

from src.clients.tenant_db import tenant_db_manager
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Pool-based config utilities (when you already have a db_pool)
# =============================================================================


async def get_config_value_with_pool(key: str, db_pool: asyncpg.Pool) -> str | None:
    """Get a configuration value using an existing database pool.

    Use this when you already have a db_pool to avoid acquiring a new one.

    Args:
        key: Configuration key name
        db_pool: Existing database connection pool

    Returns:
        Configuration value or None if not found
    """
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow("SELECT value FROM config WHERE key = $1", key)
        if result:
            return result["value"]
        return None


async def set_config_value_with_pool(key: str, value: str, db_pool: asyncpg.Pool) -> None:
    """Set a configuration value using an existing database pool.

    Use this when you already have a db_pool to avoid acquiring a new one.

    Args:
        key: Configuration key name
        value: Configuration value to store
        db_pool: Existing database connection pool
    """
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO config (key, value, created_at, updated_at)
            VALUES ($1, $2, NOW(), NOW())
            ON CONFLICT (key)
            DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = NOW()
            """,
            key,
            value,
        )


async def delete_config_value_with_pool(key: str, db_pool: asyncpg.Pool) -> None:
    """Delete a configuration value using an existing database pool.

    Args:
        key: Configuration key name
        db_pool: Existing database connection pool
    """
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM config WHERE key = $1", key)


async def delete_config_values_by_prefix_with_pool(prefix: str, db_pool: asyncpg.Pool) -> int:
    """Delete all configuration values matching a key prefix using an existing database pool.

    Args:
        prefix: Key prefix to match (e.g., "TRELLO_SYNC_" will delete all keys starting with that)
        db_pool: Existing database connection pool

    Returns:
        Number of rows deleted
    """
    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM config WHERE key LIKE $1",
            f"{prefix}%",
        )
        # Result format is "DELETE N" where N is the count
        return int(result.split()[-1]) if result else 0


# =============================================================================
# Tenant ID-based config utilities (acquires pool internally)
# =============================================================================


async def get_tenant_config_value(key: str, tenant_id: str) -> str | None:
    """Get a configuration value from the tenant's database.

    Args:
        key: Configuration key name (e.g., "COMPANY_NAME")
        tenant_id: Tenant/organization ID for scoping

    Returns:
        Configuration value or None if not found
    """
    try:
        async with (
            tenant_db_manager.acquire_pool(tenant_id) as pool,
            pool.acquire() as conn,
        ):
            result = await conn.fetchrow("SELECT value FROM config WHERE key = $1", key)
            if result:
                return result["value"]
            return None
    except Exception as e:
        print(f"Error getting tenant config value {key} for tenant {tenant_id}: {e}")
        return None


async def set_tenant_config_value(key: str, value: str, tenant_id: str) -> None:
    """Set a configuration value in the tenant's database.

    Args:
        key: Configuration key name (e.g., "JIRA_WEBTRIGGER_BACKFILL_URL")
        value: Configuration value to store
        tenant_id: Tenant/organization ID for scoping
    """
    async with (
        tenant_db_manager.acquire_pool(tenant_id) as pool,
        pool.acquire() as conn,
    ):
        # Use UPSERT to insert or update the configuration value
        await conn.execute(
            """
            INSERT INTO config (key, value, created_at, updated_at)
            VALUES ($1, $2, NOW(), NOW())
            ON CONFLICT (key)
            DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = NOW()
            """,
            key,
            value,
        )


def get_backfill_total_index_jobs_key(backfill_id: str) -> str:
    return f"backfill_{backfill_id}_total_index_jobs"


async def increment_backfill_total_index_jobs(
    backfill_id: str, tenant_id: str, increment: int = 1
) -> int:
    """Atomically increment the total # index jobs for a backfill."""
    key = get_backfill_total_index_jobs_key(backfill_id)
    new_value = await _increment_tenant_config_value(key, tenant_id, increment)
    logger.info(f"Incremented backfill total index jobs for {backfill_id} to {new_value}")
    return new_value


def get_backfill_done_index_jobs_key(backfill_id: str) -> str:
    return f"backfill_{backfill_id}_done_index_jobs"


async def increment_backfill_done_index_jobs(
    backfill_id: str, tenant_id: str, increment: int = 1
) -> int:
    """Atomically increment the total # done index jobs for a backfill."""
    key = get_backfill_done_index_jobs_key(backfill_id)
    new_value = await _increment_tenant_config_value(key, tenant_id, increment)
    logger.info(f"Incremented backfill done index jobs for {backfill_id} to {new_value}")
    return new_value


def get_backfill_total_ingest_jobs_key(backfill_id: str) -> str:
    return f"backfill_{backfill_id}_total_ingest_jobs"


async def increment_backfill_total_ingest_jobs(
    backfill_id: str, tenant_id: str, increment: int = 1
) -> int:
    """Atomically increment the total # ingest jobs for a backfill."""
    key = get_backfill_total_ingest_jobs_key(backfill_id)
    new_value = await _increment_tenant_config_value(key, tenant_id, increment)
    logger.info(f"Incremented backfill total ingest jobs for {backfill_id} to {new_value}")
    return new_value


def get_backfill_done_ingest_jobs_key(backfill_id: str) -> str:
    return f"backfill_{backfill_id}_done_ingest_jobs"


async def increment_backfill_done_ingest_jobs(
    backfill_id: str, tenant_id: str, increment: int = 1
) -> int:
    """Atomically increment the total # done ingest jobs for a backfill."""
    key = get_backfill_done_ingest_jobs_key(backfill_id)
    new_value = await _increment_tenant_config_value(key, tenant_id, increment)
    logger.info(f"Incremented backfill done ingest jobs for {backfill_id} to {new_value}")
    return new_value


def get_backfill_attempted_ingest_jobs_key(backfill_id: str) -> str:
    return f"backfill_{backfill_id}_attempted_ingest_jobs"


async def increment_backfill_attempted_ingest_jobs(
    backfill_id: str, tenant_id: str, increment: int = 1
) -> int:
    """Atomically increment the total # attempted ingest jobs for a backfill."""
    key = get_backfill_attempted_ingest_jobs_key(backfill_id)
    new_value = await _increment_tenant_config_value(key, tenant_id, increment)
    logger.info(f"Incremented backfill attempted ingest jobs for {backfill_id} to {new_value}")
    return new_value


def get_backfill_complete_notification_sent_key(backfill_id: str) -> str:
    return f"backfill_{backfill_id}_done_notif_sent"


async def _increment_tenant_config_value(key: str, tenant_id: str, increment: int = 1) -> int:
    """Atomically increment a config value and return the new value.

    If the key doesn't exist, it will be initialized to 0 before incrementing.

    Args:
        key: Configuration key name
        tenant_id: Tenant/organization ID for scoping
        increment: Amount to increment by (default 1)

    Returns:
        The new value after incrementing
    """
    async with (
        tenant_db_manager.acquire_pool(tenant_id) as pool,
        pool.acquire() as conn,
    ):
        # Use UPSERT with atomic increment
        result = await conn.fetchrow(
            """
            INSERT INTO config (key, value, created_at, updated_at)
            VALUES ($1, $2, NOW(), NOW())
            ON CONFLICT (key)
            DO UPDATE SET
                value = (COALESCE(config.value::int, 0) + $3)::text,
                updated_at = NOW()
            RETURNING value::int
        """,
            key,
            str(increment),
            increment,
        )

        return result["value"]


async def get_tenant_company_name(tenant_id: str) -> str | None:
    """Get company name from tenant's database."""
    return await get_tenant_config_value("COMPANY_NAME", tenant_id)


async def get_tenant_company_context(tenant_id: str) -> str | None:
    """Get company context from tenant's database."""
    return await get_tenant_config_value("COMPANY_CONTEXT", tenant_id)


async def get_installer_dm_sent(tenant_id: str) -> str | None:
    """Check if installer DM was already sent for a tenant."""
    return await get_tenant_config_value("SLACK_INSTALLER_DM_SENT", tenant_id)


async def check_and_mark_backfill_complete(backfill_id: str, tenant_id: str) -> bool:
    """Check if backfill is complete and atomically mark notification as sent.

    Returns True if the backfill is complete AND the notification hasn't been sent yet.
    This ensures the completion notification is only sent once, even with concurrent calls.

    Args:
        backfill_id: Unique backfill identifier
        tenant_id: Tenant/organization ID for scoping

    Returns:
        True if notification should be sent (complete and not previously sent)
    """
    async with (
        tenant_db_manager.acquire_pool(tenant_id) as pool,
        pool.acquire() as conn,
    ):
        # Get config keys
        total_ingest_key = get_backfill_total_ingest_jobs_key(backfill_id)
        attempted_ingest_key = get_backfill_attempted_ingest_jobs_key(backfill_id)
        total_index_key = get_backfill_total_index_jobs_key(backfill_id)
        done_index_key = get_backfill_done_index_jobs_key(backfill_id)
        notification_key = get_backfill_complete_notification_sent_key(backfill_id)

        # Atomically check completion and mark as sent in one operation
        # Only inserts if all jobs have been attempted AND notification not already sent
        result = await conn.fetchrow(
            """
            INSERT INTO config (key, value, created_at, updated_at)
            SELECT $5::varchar, 'true', NOW(), NOW()
            WHERE (
                -- Check that all ingest jobs have been attempted (success or failure)
                COALESCE((SELECT value::int FROM config WHERE key = $1::varchar), 0) > 0 AND
                COALESCE((SELECT value::int FROM config WHERE key = $2::varchar), 0) >=
                    COALESCE((SELECT value::int FROM config WHERE key = $1::varchar), 0) AND
                -- Check that all index jobs are complete
                COALESCE((SELECT value::int FROM config WHERE key = $3::varchar), 0) > 0 AND
                COALESCE((SELECT value::int FROM config WHERE key = $4::varchar), 0) >=
                    COALESCE((SELECT value::int FROM config WHERE key = $3::varchar), 0) AND
                -- Check that notification hasn't been sent yet
                NOT EXISTS (SELECT 1 FROM config WHERE key = $5::varchar)
            )
            ON CONFLICT (key) DO NOTHING
            RETURNING key
            """,
            total_ingest_key,
            attempted_ingest_key,
            total_index_key,
            done_index_key,
            notification_key,
        )

        # Return True only if we successfully inserted the notification key
        # This means this process won the race and should send the notification
        return result is not None
