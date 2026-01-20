"""Utilities for resolving tenant metadata from the control database."""

from __future__ import annotations

import asyncpg

from src.clients.tenant_db import _tenant_db_manager
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def resolve_tenant_to_workos_org(
    tenant_id: str,
    *,
    control_pool: asyncpg.Pool | None = None,
) -> str | None:
    """Resolve a tenant ID to its WorkOS organization identifier.

    Args:
        tenant_id: Internal tenant identifier (tn_xxx)
        control_pool: Optional control DB pool for testing

    Returns:
        WorkOS organization ID if available and tenant provisioned, otherwise ``None``.
    """

    if not tenant_id:
        raise ValueError("tenant_id is required")

    pool = control_pool or await _tenant_db_manager.get_control_db()

    query = """
        SELECT workos_org_id
        FROM public.tenants
        WHERE id = $1
          AND state = 'provisioned'
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, tenant_id)
        if row is None:
            logger.warning("Tenant lookup failed", tenant_id=tenant_id)
            return None
        org_id = row.get("workos_org_id")
        if org_id:
            return org_id
        logger.warning(
            "Tenant missing WorkOS org id",
            tenant_id=tenant_id,
        )
        return None
