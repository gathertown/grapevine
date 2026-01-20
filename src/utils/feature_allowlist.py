"""Tenant feature allowlist service.

This module provides helper functions to determine whether a feature is enabled for a
particular tenant. It uses database-backed persistence with an in-memory cache for testing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

import asyncpg

from src.utils.config import get_control_database_url, get_grapevine_environment
from src.utils.logging import get_logger

logger = get_logger(__name__)


class FeatureKeys(str, Enum):
    """Feature identifiers shared across services."""

    DUMMY_FEATURE = "dummy:feature"
    MCP_TOOL_PR_REVIEWER = "mcp_tool:pr_reviewer"


FeatureKey = FeatureKeys


class GrapevineEnvironment(str, Enum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass(frozen=True)
class FeatureMetadata:
    """Metadata describing the default state of a feature."""

    environments: set[GrapevineEnvironment]


FEATURE_METADATA: dict[FeatureKey, FeatureMetadata] = {
    FeatureKeys.DUMMY_FEATURE: FeatureMetadata({GrapevineEnvironment.LOCAL}),
    FeatureKeys.MCP_TOOL_PR_REVIEWER: FeatureMetadata(
        {GrapevineEnvironment.LOCAL, GrapevineEnvironment.STAGING}
    ),
}


TenantId = str

# In-memory cache for testing purposes
_in_memory_allowlist: dict[TenantId, set[FeatureKey]] | None = None

# Singleton database pool
_control_db_pool: asyncpg.Pool | None = None


def _normalize_env(env: str) -> GrapevineEnvironment:
    env_lower = env.lower()
    if env_lower in {"prod", "production"}:
        return GrapevineEnvironment.PRODUCTION
    if env_lower == "staging":
        return GrapevineEnvironment.STAGING
    return GrapevineEnvironment.LOCAL


def _current_env() -> GrapevineEnvironment:
    return _normalize_env(get_grapevine_environment())


async def _get_control_db_pool() -> asyncpg.Pool | None:
    """Get or create the control database pool."""
    global _control_db_pool

    if _control_db_pool is not None:
        return _control_db_pool

    try:
        control_db_url = get_control_database_url()
        _control_db_pool = await asyncpg.create_pool(
            control_db_url, min_size=1, max_size=5, timeout=30
        )
        logger.info("Control database pool initialized for feature allowlist")
        return _control_db_pool
    except Exception as e:
        logger.error(f"Failed to initialize control database pool: {e}")
        return None


def configure_in_memory_allowlist(allowlist: dict[TenantId, Iterable[FeatureKey]]) -> None:
    """Replace the in-memory allowlist map (testing helper).

    When set, this overrides database queries.
    """
    global _in_memory_allowlist
    _in_memory_allowlist = {tenant: set(features) for tenant, features in allowlist.items()}


def reset_in_memory_allowlist() -> None:
    """Clear the in-memory allowlist map (testing helper)."""
    global _in_memory_allowlist
    _in_memory_allowlist = {}


def is_feature_allowed_in_env(feature: FeatureKey) -> bool:
    """Return whether the feature is enabled by default in the current environment."""
    metadata = FEATURE_METADATA.get(feature)
    if not metadata:
        return False

    return _current_env() in metadata.environments


async def get_tenant_features(tenant_id: TenantId) -> set[FeatureKey]:
    """Return the feature set that is explicitly allowlisted for a tenant."""
    # If in-memory allowlist is configured (for testing), use it
    if _in_memory_allowlist is not None:
        return set(_in_memory_allowlist.get(tenant_id, set()))

    # Otherwise query from database
    pool = await _get_control_db_pool()
    if pool is None:
        logger.error("Control database not available for feature allowlist query")
        return set()

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT feature_key FROM public.feature_allowlist WHERE tenant_id = $1",
                tenant_id,
            )
            return {FeatureKeys(row["feature_key"]) for row in rows}
    except Exception as e:
        logger.error(f"Failed to query feature allowlist for tenant {tenant_id}: {e}")
        return set()


async def is_feature_enabled(tenant_id: TenantId, feature: FeatureKey) -> bool:
    """Return whether the feature is enabled for the tenant in the current environment."""
    # First check if feature is enabled for the current environment
    if is_feature_allowed_in_env(feature):
        return True

    # Then check tenant-specific allowlist
    tenant_features = await get_tenant_features(tenant_id)
    return feature in tenant_features


async def enable_feature_for_tenant(tenant_id: TenantId, feature: FeatureKey) -> bool:
    """Enable a feature for a tenant."""
    pool = await _get_control_db_pool()
    if pool is None:
        logger.error("Control database not available for enabling feature")
        return False

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO public.feature_allowlist (tenant_id, feature_key, created_at, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id, feature_key) DO NOTHING
                """,
                tenant_id,
                feature.value,
            )
            logger.info(f"✅ Enabled feature {feature.value} for tenant {tenant_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to enable feature {feature.value} for tenant {tenant_id}: {e}")
        return False


async def disable_feature_for_tenant(tenant_id: TenantId, feature: FeatureKey) -> bool:
    """Disable a feature for a tenant."""
    pool = await _get_control_db_pool()
    if pool is None:
        logger.error("Control database not available for disabling feature")
        return False

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM public.feature_allowlist WHERE tenant_id = $1 AND feature_key = $2",
                tenant_id,
                feature.value,
            )
            logger.info(f"✅ Disabled feature {feature.value} for tenant {tenant_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to disable feature {feature.value} for tenant {tenant_id}: {e}")
        return False


def list_all_features() -> set[FeatureKey]:
    """Return the set of all known features."""
    return set(FEATURE_METADATA.keys())
