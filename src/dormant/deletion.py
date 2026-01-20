"""
Tenant hard deletion service.

Provides functionality to permanently delete a tenant and all associated resources:
- PostgreSQL tenant database and role
- OpenSearch indices (alias + versioned indices)
- Turbopuffer namespace
- SSM parameters
- Control database records (cascades from tenants table)
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote

import asyncpg
from turbopuffer import NotFoundError

from src.clients.opensearch import OpenSearchClient
from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.clients.turbopuffer import close_turbopuffer_client, get_turbopuffer_client
from src.utils.config import (
    get_config_value,
    get_opensearch_admin_password,
    get_opensearch_admin_username,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def cleanup_tenant_db_manager() -> None:
    """
    Clean up singleton state for tenant_db_manager and turbopuffer client.

    This should be called between separate asyncio.run() calls to reset
    event-loop-bound state (locks, connection pools, aiohttp sessions)
    that become invalid when the event loop is destroyed.
    """
    await tenant_db_manager.cleanup()
    await close_turbopuffer_client()


@dataclass
class DeletionResult:
    """Result of tenant deletion operation."""

    tenant_id: str
    success: bool
    steps_completed: list[str] = field(default_factory=list)
    steps_failed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ResourceDiscoveryResult:
    """Result of discovering what resources exist for a tenant."""

    tenant_id: str
    # PostgreSQL
    database_exists: bool = False
    database_name: str = ""
    role_exists: bool = False
    role_name: str = ""
    # OpenSearch
    opensearch_indices: list[str] = field(default_factory=list)
    # Turbopuffer
    turbopuffer_namespace_exists: bool = False
    # SSM
    ssm_parameters: list[str] = field(default_factory=list)
    # Control DB
    control_db_tenant_exists: bool = False
    control_db_related_counts: dict[str, int] = field(default_factory=dict)
    # Errors during discovery
    errors: list[str] = field(default_factory=list)


async def discover_tenant_resources(tenant_id: str) -> ResourceDiscoveryResult:
    """
    Discover what resources exist for a tenant without deleting anything.

    This is useful for dry-run operations to show what would be deleted.

    Args:
        tenant_id: Tenant identifier

    Returns:
        ResourceDiscoveryResult with details of existing resources
    """
    result = ResourceDiscoveryResult(tenant_id=tenant_id)

    # Database and role names
    result.database_name = f"db_{tenant_id}"
    result.role_name = f"{tenant_id}_app_rw"

    # Check PostgreSQL database and role
    tenant_host = get_config_value("PG_TENANT_DATABASE_HOST")
    tenant_port = get_config_value("PG_TENANT_DATABASE_PORT", "5432")
    admin_username = get_config_value("PG_TENANT_DATABASE_ADMIN_USERNAME")
    admin_password = get_config_value("PG_TENANT_DATABASE_ADMIN_PASSWORD")

    if all([tenant_host, admin_username, admin_password]):
        admin_url = f"postgresql://{quote(admin_username)}:{quote(admin_password)}@{tenant_host}:{tenant_port}/postgres"
        try:
            conn = await asyncpg.connect(admin_url)
            try:
                # Check if database exists
                db_exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = $1)",
                    result.database_name,
                )
                result.database_exists = bool(db_exists)

                # Check if role exists
                role_exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = $1)",
                    result.role_name,
                )
                result.role_exists = bool(role_exists)
            finally:
                await conn.close()
        except Exception as e:
            result.errors.append(f"PostgreSQL check failed: {e}")
    else:
        result.errors.append("Missing PostgreSQL admin credentials")

    # Check OpenSearch indices
    os_user = get_opensearch_admin_username()
    os_pass = get_opensearch_admin_password()
    os_host = os.environ.get("OPENSEARCH_DOMAIN_HOST")
    os_port = os.environ.get("OPENSEARCH_PORT", "443")
    # Default to HTTPS for port 443, HTTP for other ports
    default_ssl = "true" if os_port == "443" else "false"
    use_ssl = os.environ.get("OPENSEARCH_USE_SSL", default_ssl).lower() in ("true", "1", "yes")
    protocol = "https" if use_ssl else "http"

    if os_user and os_pass and os_host:
        opensearch_url = f"{protocol}://{quote(os_user)}:{quote(os_pass)}@{os_host}:{os_port}"
        client = OpenSearchClient(opensearch_url)
        index_alias = f"tenant-{tenant_id}"

        try:
            # Check for indices via alias
            try:
                alias_response = await client.client.indices.get_alias(name=index_alias)
                result.opensearch_indices.extend(list(alias_response.keys()))
            except Exception:
                pass  # Alias might not exist

            # Check for versioned indices directly
            for version in range(1, 10):
                index_name = f"{index_alias}-v{version}"
                if index_name not in result.opensearch_indices:
                    try:
                        exists = await client.index_exists(index_name)
                        if exists:
                            result.opensearch_indices.append(index_name)
                    except Exception:
                        pass

            # Check for alias as index
            if index_alias not in result.opensearch_indices:
                try:
                    exists = await client.index_exists(index_alias)
                    if exists:
                        result.opensearch_indices.append(index_alias)
                except Exception:
                    pass

        except Exception as e:
            result.errors.append(f"OpenSearch check failed: {e}")
        finally:
            await client.aclose()
    else:
        result.errors.append("Missing OpenSearch credentials")

    # Check Turbopuffer namespace
    try:
        turbopuffer_client = get_turbopuffer_client()
        result.turbopuffer_namespace_exists = await turbopuffer_client.namespace_exists(tenant_id)
    except Exception as e:
        result.errors.append(f"Turbopuffer check failed: {e}")

    # Check SSM parameters
    try:
        ssm_client = SSMClient()
        parameters = await ssm_client.get_parameters_by_path(f"/{tenant_id}", decrypt=False)
        result.ssm_parameters = parameters
    except Exception as e:
        result.errors.append(f"SSM check failed: {e}")

    # Check control database
    try:
        control_pool = await tenant_db_manager.get_control_db()
        async with control_pool.acquire() as conn:
            # Check if tenant exists
            tenant_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM tenants WHERE id = $1)",
                tenant_id,
            )
            result.control_db_tenant_exists = bool(tenant_exists)

            # Count related records in the unified connector_installations table
            tables_to_check = [
                ("connector_installations", "tenant_id"),
                ("subscriptions", "tenant_id"),
                ("feature_allowlist", "tenant_id"),
            ]

            for table, column in tables_to_check:
                try:
                    count = await conn.fetchval(
                        f"SELECT COUNT(*) FROM {table} WHERE {column} = $1",  # noqa: S608
                        tenant_id,
                    )
                    if count and count > 0:
                        result.control_db_related_counts[table] = count
                except Exception:
                    pass  # Table might not exist

    except Exception as e:
        result.errors.append(f"Control DB check failed: {e}")

    return result


async def delete_tenant_database(tenant_id: str) -> tuple[bool, str | None]:
    """
    Drop the tenant's PostgreSQL database and role.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Tuple of (success, error_message)
    """
    # Get admin database credentials
    tenant_host = get_config_value("PG_TENANT_DATABASE_HOST")
    tenant_port = get_config_value("PG_TENANT_DATABASE_PORT", "5432")
    admin_username = get_config_value("PG_TENANT_DATABASE_ADMIN_USERNAME")
    admin_password = get_config_value("PG_TENANT_DATABASE_ADMIN_PASSWORD")

    if not all([tenant_host, admin_username, admin_password]):
        return False, "Missing tenant database admin credentials"

    # Database and role names follow the pattern db_{tenant_id} and {tenant_id}_app_rw
    db_name = f"db_{tenant_id}"
    db_role = f"{tenant_id}_app_rw"

    # Connect to postgres database (not the tenant database) to drop it
    admin_url = f"postgresql://{quote(admin_username)}:{quote(admin_password)}@{tenant_host}:{tenant_port}/postgres"

    errors: list[str] = []

    try:
        conn = await asyncpg.connect(admin_url)
        try:
            # Terminate any existing connections to the database
            await conn.execute(
                """
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = $1
                  AND pid <> pg_backend_pid()
                """,
                db_name,
            )

            # Drop the database
            # Note: DROP DATABASE cannot run inside a transaction block
            try:
                await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')  # noqa: S608
                logger.info(f"Successfully dropped database {db_name}")
            except Exception as e:
                error_msg = f"Failed to drop database {db_name}: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)

            # Drop the database role
            try:
                await conn.execute(f'DROP ROLE IF EXISTS "{db_role}"')  # noqa: S608
                logger.info(f"Successfully dropped role {db_role}")
            except Exception as e:
                error_msg = f"Failed to drop role {db_role}: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)

            if errors:
                return False, "; ".join(errors)
            return True, None

        finally:
            await conn.close()

    except Exception as e:
        error_msg = f"Failed to connect to admin database: {e}"
        logger.error(error_msg)
        return False, error_msg


async def delete_tenant_opensearch_indices(tenant_id: str) -> tuple[bool, str | None]:
    """
    Delete all OpenSearch indices for the tenant.

    This handles:
    - The alias (tenant-{tenant_id})
    - The underlying versioned indices (tenant-{tenant_id}-v1, tenant-{tenant_id}-v2, etc.)

    Args:
        tenant_id: Tenant identifier

    Returns:
        Tuple of (success, error_message)
    """
    # Build OpenSearch URL directly to get admin client (not tenant-scoped)
    # because we need to delete versioned indices that the tenant-scoped client won't allow
    os_user = get_opensearch_admin_username()
    os_pass = get_opensearch_admin_password()
    os_host = os.environ.get("OPENSEARCH_DOMAIN_HOST")
    os_port = os.environ.get("OPENSEARCH_PORT", "443")
    # Default to HTTPS for port 443, HTTP for other ports
    default_ssl = "true" if os_port == "443" else "false"
    use_ssl = os.environ.get("OPENSEARCH_USE_SSL", default_ssl).lower() in ("true", "1", "yes")
    protocol = "https" if use_ssl else "http"

    if not os_user or not os_pass or not os_host:
        return False, "Missing OpenSearch credentials"

    opensearch_url = f"{protocol}://{quote(os_user)}:{quote(os_pass)}@{os_host}:{os_port}"
    client = OpenSearchClient(opensearch_url)

    index_alias = f"tenant-{tenant_id}"
    deleted_indices: list[str] = []
    errors: list[str] = []

    try:
        # First, try to get indices that the alias points to and delete them
        try:
            alias_response = await client.client.indices.get_alias(name=index_alias)
            indices_with_alias = list(alias_response.keys())
            logger.info(f"Found indices with alias '{index_alias}': {indices_with_alias}")

            for index_name in indices_with_alias:
                try:
                    await client.delete_index(index_name)
                    deleted_indices.append(index_name)
                    logger.info(f"Deleted index '{index_name}'")
                except Exception as e:
                    error_msg = f"Failed to delete index {index_name}: {e}"
                    logger.warning(error_msg)
                    errors.append(error_msg)
        except Exception:
            # Alias might not exist, which is fine
            logger.debug(f"Alias '{index_alias}' not found or no indices attached")

        # Also try to delete any versioned indices directly (in case alias is broken/missing)
        for version in range(1, 10):  # Check v1 through v9
            index_name = f"{index_alias}-v{version}"
            if index_name in deleted_indices:
                continue  # Already deleted via alias

            try:
                exists = await client.index_exists(index_name)
                if exists:
                    await client.delete_index(index_name)
                    deleted_indices.append(index_name)
                    logger.info(f"Deleted orphaned versioned index '{index_name}'")
            except Exception as e:
                # Index might not exist, which is fine
                logger.debug(f"Index {index_name} check/delete failed: {e}")

        # Try to delete the alias itself if it still exists
        try:
            exists = await client.index_exists(index_alias)
            if exists:
                await client.delete_index(index_alias)
                deleted_indices.append(index_alias)
                logger.info(f"Deleted alias/index '{index_alias}'")
        except Exception:
            pass  # Alias might not exist or already deleted

        if deleted_indices:
            logger.info(f"Successfully deleted OpenSearch indices: {', '.join(deleted_indices)}")
        else:
            logger.info(f"No OpenSearch indices found for tenant {tenant_id}")

        if errors:
            return False, "; ".join(errors)
        return True, None

    except Exception as e:
        error_msg = f"Failed to delete OpenSearch indices for tenant {tenant_id}: {e}"
        logger.error(error_msg)
        return False, error_msg
    finally:
        await client.aclose()


async def delete_tenant_turbopuffer_namespace(tenant_id: str) -> tuple[bool, str | None]:
    """
    Delete the tenant's Turbopuffer namespace.

    Implements retry logic with exponential backoff for connection errors,
    which are often transient network issues.

    Note: The underlying client checks if the namespace exists before attempting
    deletion, so non-existent namespaces are handled gracefully without errors.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Tuple of (success, error_message)
    """
    max_retries = 3
    retry_delays = [2, 4, 8]  # Exponential backoff: 2s, 4s, 8s

    for attempt in range(max_retries):
        try:
            turbopuffer_client = get_turbopuffer_client()
            await turbopuffer_client.delete_namespace(tenant_id)
            return True, None

        except NotFoundError:
            # Namespace doesn't exist - this can happen in race conditions
            # even though we check existence first. Treat as success.
            logger.info(
                f"Turbopuffer namespace for tenant {tenant_id} does not exist (already deleted or never created)"
            )
            return True, None

        except Exception as e:
            error_str = str(e).lower()
            is_connection_error = any(
                keyword in error_str
                for keyword in ["connection", "timeout", "network", "unreachable", "refused"]
            )

            if is_connection_error and attempt < max_retries - 1:
                delay = retry_delays[attempt]
                logger.warning(
                    f"Turbopuffer connection error for tenant {tenant_id} (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
                continue

            # Non-retryable error or max retries reached
            error_msg = f"Failed to delete Turbopuffer namespace for tenant {tenant_id}: {e}"
            if attempt > 0:
                error_msg += f" (after {attempt + 1} attempts)"
            logger.error(error_msg)
            return False, error_msg

    # Should never reach here, but just in case
    error_msg = f"Failed to delete Turbopuffer namespace for tenant {tenant_id} after {max_retries} attempts"
    logger.error(error_msg)
    return False, error_msg


async def delete_tenant_ssm_parameters(tenant_id: str) -> tuple[bool, str | None]:
    """
    Delete all SSM parameters for the tenant.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Tuple of (success, error_message)
    """
    try:
        ssm_client = SSMClient()
        deleted_count, failed_count = await ssm_client.delete_tenant_parameters(tenant_id)

        if failed_count > 0:
            return False, f"Deleted {deleted_count} SSM parameters but {failed_count} failed"

        logger.info(f"Successfully deleted {deleted_count} SSM parameters for tenant {tenant_id}")
        return True, None

    except Exception as e:
        error_msg = f"Failed to delete SSM parameters for tenant {tenant_id}: {e}"
        logger.error(error_msg)
        return False, error_msg


async def delete_tenant_control_db_records(
    control_pool: asyncpg.Pool,
    tenant_id: str,
) -> tuple[bool, str | None]:
    """
    Delete tenant records from control database tables.

    This deletes the tenant record from the tenants table. All related records
    in other tables (connector_installations, subscriptions, feature_allowlist,
    snowflake_semantic_models) are automatically deleted via ON DELETE CASCADE
    foreign key constraints.

    Note: If the tenant doesn't exist (DELETE 0), this is treated as success
    since the goal is to ensure the tenant record doesn't exist. This can
    happen if the tenant was already deleted in a previous operation.

    Args:
        control_pool: Control database connection pool
        tenant_id: Tenant identifier

    Returns:
        Tuple of (success, error_message)
    """
    try:
        async with control_pool.acquire() as conn:
            # Delete the tenant record - CASCADE handles all related tables
            result = await conn.execute(
                "DELETE FROM tenants WHERE id = $1",
                tenant_id,
            )

            if result == "DELETE 0":
                # Tenant doesn't exist, which is fine - the goal is to ensure
                # it doesn't exist. This can happen if already deleted.
                logger.info(
                    f"Tenant {tenant_id} not found in control database (already deleted or never existed)"
                )
                return True, None

        logger.info(f"Successfully deleted control DB records for tenant {tenant_id}")
        return True, None

    except Exception as e:
        error_msg = f"Failed to delete control DB records for tenant {tenant_id}: {e}"
        logger.error(error_msg)
        return False, error_msg


async def mark_tenant_deactivating(
    control_pool: asyncpg.Pool,
    tenant_id: str,
) -> tuple[bool, str | None]:
    """
    Mark a tenant as deactivating before starting deletion.

    This prevents the tenant from being included in migration runs while
    the deletion process is in progress.

    Args:
        control_pool: Control database connection pool
        tenant_id: Tenant identifier

    Returns:
        Tuple of (success, error_message)
    """
    try:
        async with control_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE tenants
                SET state = 'deactivating', updated_at = $1
                WHERE id = $2 AND deleted_at IS NULL
                """,
                datetime.now(UTC),
                tenant_id,
            )

            if result == "UPDATE 0":
                return False, f"Tenant {tenant_id} not found or already deleted"

        logger.info(f"Marked tenant {tenant_id} as deactivating")
        return True, None

    except Exception as e:
        error_msg = f"Failed to mark tenant {tenant_id} as deactivating: {e}"
        logger.error(error_msg)
        return False, error_msg


async def soft_delete_tenant(
    control_pool: asyncpg.Pool,
    tenant_id: str,
) -> tuple[bool, str | None]:
    """
    Soft delete a tenant by setting deleted_at timestamp.

    This is a safer alternative to hard deletion that preserves the tenant record
    but marks it as deleted.

    Args:
        control_pool: Control database connection pool
        tenant_id: Tenant identifier

    Returns:
        Tuple of (success, error_message)
    """
    try:
        async with control_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE tenants
                SET deleted_at = $1, updated_at = $1
                WHERE id = $2 AND deleted_at IS NULL
                """,
                datetime.now(UTC),
                tenant_id,
            )

            if result == "UPDATE 0":
                return False, f"Tenant {tenant_id} not found or already deleted"

        logger.info(f"Soft deleted tenant {tenant_id}")
        return True, None

    except Exception as e:
        error_msg = f"Failed to soft delete tenant {tenant_id}: {e}"
        logger.error(error_msg)
        return False, error_msg


async def hard_delete_tenant(tenant_id: str) -> DeletionResult:
    """
    Permanently delete a tenant and all associated resources.

    This performs a hard delete which:
    1. Marks the tenant as 'deactivating' (excludes from migrations)
    2. Drops the PostgreSQL tenant database
    3. Deletes the OpenSearch index
    4. Deletes the Turbopuffer namespace
    5. Deletes all SSM parameters
    6. Deletes control database records

    WARNING: This operation is irreversible!

    Args:
        tenant_id: Tenant identifier

    Returns:
        DeletionResult with details of what was deleted
    """
    result = DeletionResult(tenant_id=tenant_id, success=True)

    # Get control database pool
    control_pool = await tenant_db_manager.get_control_db()

    # Step 0: Mark tenant as deactivating (prevents migrations from running on this tenant)
    logger.info(f"[{tenant_id}] Step 0: Marking tenant as deactivating")
    success, error = await mark_tenant_deactivating(control_pool, tenant_id)
    if success:
        result.steps_completed.append("Tenant marked as deactivating")
    else:
        result.steps_failed.append("Mark tenant as deactivating")
        if error:
            result.errors.append(error)
        result.success = False

    # Step 1: Delete PostgreSQL database and role
    logger.info(f"[{tenant_id}] Step 1: Deleting PostgreSQL database and role")
    success, error = await delete_tenant_database(tenant_id)
    if success:
        result.steps_completed.append("PostgreSQL database and role deleted")
    else:
        result.steps_failed.append("PostgreSQL database/role deletion")
        if error:
            result.errors.append(error)
        result.success = False

    # Step 2: Delete OpenSearch indices (alias + versioned indices)
    logger.info(f"[{tenant_id}] Step 2: Deleting OpenSearch indices")
    success, error = await delete_tenant_opensearch_indices(tenant_id)
    if success:
        result.steps_completed.append("OpenSearch indices deleted")
    else:
        result.steps_failed.append("OpenSearch indices deletion")
        if error:
            result.errors.append(error)
        result.success = False

    # Step 3: Delete Turbopuffer namespace
    logger.info(f"[{tenant_id}] Step 3: Deleting Turbopuffer namespace")
    success, error = await delete_tenant_turbopuffer_namespace(tenant_id)
    if success:
        result.steps_completed.append("Turbopuffer namespace deleted")
    else:
        result.steps_failed.append("Turbopuffer namespace deletion")
        if error:
            result.errors.append(error)
        result.success = False

    # Step 4: Delete SSM parameters
    logger.info(f"[{tenant_id}] Step 4: Deleting SSM parameters")
    success, error = await delete_tenant_ssm_parameters(tenant_id)
    if success:
        result.steps_completed.append("SSM parameters deleted")
    else:
        result.steps_failed.append("SSM parameters deletion")
        if error:
            result.errors.append(error)
        result.success = False

    # Step 5: Delete control database records (must be last)
    logger.info(f"[{tenant_id}] Step 5: Deleting control database records")
    success, error = await delete_tenant_control_db_records(control_pool, tenant_id)
    if success:
        result.steps_completed.append("Control DB records deleted")
    else:
        result.steps_failed.append("Control DB records deletion")
        if error:
            result.errors.append(error)
        result.success = False

    # Log final result
    if result.success:
        logger.info(
            f"Successfully hard deleted tenant {tenant_id}",
            extra={
                "tenant_id": tenant_id,
                "steps_completed": result.steps_completed,
            },
        )
    else:
        logger.error(
            f"Failed to fully delete tenant {tenant_id}",
            extra={
                "tenant_id": tenant_id,
                "steps_completed": result.steps_completed,
                "steps_failed": result.steps_failed,
                "errors": result.errors,
            },
        )

    return result
