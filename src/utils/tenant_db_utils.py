"""
Utilities for tenant database operations.

This module provides shared functions for common tenant database queries
to avoid duplication across services.
"""

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


async def get_tenant_trial_start_at(tenant_id: str) -> datetime | None:
    """
    Get trial_start_at for a tenant from the control database.

    This is a shared utility to avoid duplicating the trial_start_at lookup
    logic across multiple services.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Trial start datetime with UTC timezone, or None if not found

    Raises:
        Exception: If database query fails
    """
    from src.clients.tenant_db import tenant_db_manager

    pool = await tenant_db_manager.get_control_db()

    async with pool.acquire() as conn:
        tenant_query = """
            SELECT trial_start_at
            FROM tenants
            WHERE id = $1
        """
        tenant_row = await conn.fetchrow(tenant_query, tenant_id)

        if not tenant_row or not tenant_row["trial_start_at"]:
            return None

        trial_start = tenant_row["trial_start_at"]
        # Ensure timezone is set to UTC
        return trial_start.replace(tzinfo=UTC) if trial_start.tzinfo is None else trial_start
