import os

import asyncpg
import newrelic.agent

from src.migrations.core import get_tenant_migrations_dir, migrate_database
from src.steward.models import TenantCredentials, TenantRow
from src.utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)


def _get_control_database_url() -> str:
    val = os.environ.get("CONTROL_DATABASE_URL")
    if val:
        return val
    raise RuntimeError(
        "No Control database URL found. Set CONTROL_DATABASE_URL environment variable."
    )


def _get_tenant_database_host() -> str:
    val = os.environ.get("PG_TENANT_DATABASE_HOST")
    if val:
        return val
    raise RuntimeError(
        "No Tenant database host found. Set PG_TENANT_DATABASE_HOST environment variable."
    )


def _get_admin_connection_params() -> dict[str, str]:
    user = os.environ.get("PG_TENANT_DATABASE_ADMIN_USERNAME")
    password = os.environ.get("PG_TENANT_DATABASE_ADMIN_PASSWORD")
    db_name = os.environ.get("PG_TENANT_DATABASE_ADMIN_DB")

    if not user:
        raise RuntimeError("PG_TENANT_DATABASE_ADMIN_USERNAME environment variable is required")
    if not password:
        raise RuntimeError("PG_TENANT_DATABASE_ADMIN_PASSWORD environment variable is required")
    if not db_name:
        raise RuntimeError("PG_TENANT_DATABASE_ADMIN_DB environment variable is required")

    return {
        "host": _get_tenant_database_host(),
        "port": os.environ.get("PG_TENANT_DATABASE_PORT", "5432"),
        "user": user,
        "password": password,
        "database": db_name,
    }


def _get_tenant_connection_params(creds: TenantCredentials) -> dict[str, str]:
    return {
        "host": _get_tenant_database_host(),
        "port": os.environ.get("PG_TENANT_DATABASE_PORT", "5432"),
        "database": creds.db_name,
        "user": creds.db_rw_user,
        "password": creds.db_rw_pass,
    }


def _get_admin_connection_params_for_tenant_db(db_name: str) -> dict[str, str]:
    """Get tenant database connection params with admin credentials for schema operations."""
    user = os.environ.get("PG_TENANT_DATABASE_ADMIN_USERNAME")
    password = os.environ.get("PG_TENANT_DATABASE_ADMIN_PASSWORD")

    if not user:
        raise RuntimeError("PG_TENANT_DATABASE_ADMIN_USERNAME environment variable is required")
    if not password:
        raise RuntimeError("PG_TENANT_DATABASE_ADMIN_PASSWORD environment variable is required")

    return {
        "host": _get_tenant_database_host(),
        "port": os.environ.get("PG_TENANT_DATABASE_PORT", "5432"),
        "user": user,
        "password": password,
        "database": db_name,
    }


def _build_url_from_connection_params(params: dict[str, str]) -> str:
    """Build a PostgreSQL URL from connection parameters for legacy systems that require URLs."""
    from urllib.parse import quote_plus

    user = quote_plus(params["user"])
    password = quote_plus(params["password"])
    host = params["host"]
    port = params["port"]
    database = params["database"]

    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def _get_params_for_tenant_on_admin_db(creds: TenantCredentials) -> dict[str, str]:
    """Get postgres database params with tenant user credentials (for negative testing)."""
    return {
        "host": _get_tenant_database_host(),
        "port": os.environ.get("PG_TENANT_DATABASE_PORT", "5432"),
        "user": creds.db_rw_user,
        "password": creds.db_rw_pass,
        "database": os.environ.get("PG_TENANT_DATABASE_NAME", "postgres"),
    }


async def _create_control_pool() -> asyncpg.Pool:
    database_url = _get_control_database_url()
    return await asyncpg.create_pool(database_url, min_size=1, max_size=5, timeout=30)


async def _create_admin_pool() -> asyncpg.Pool:
    conn_params = _get_admin_connection_params()
    logger.info(
        "Creating admin pool with params",
        host=conn_params["host"],
        database=conn_params["database"],
        user=conn_params["user"],
    )
    return await asyncpg.create_pool(**conn_params, min_size=1, max_size=5, timeout=30)


async def fetch_and_lock_next_pending_tenant(control_pool: asyncpg.Pool) -> TenantRow | None:
    """Fetch and lock the next pending tenant, transitioning to provisioning.

    Uses a single CTE UPDATE with FOR UPDATE SKIP LOCKED semantics implemented by
    selecting in the CTE and updating rows joined from it.
    """
    async with control_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH cte AS (
                SELECT * FROM public.tenants
                WHERE state = 'pending'
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE public.tenants t
            SET state = 'provisioning',
                updated_at = now()
            FROM cte
            WHERE t.id = cte.id
            RETURNING t.id, t.state, t.error_message, t.provisioned_at, t.created_at, t.updated_at, t.workos_org_id, t.deleted_at, t.trial_start_at, t.source;
            """
        )
        if row is None:
            return None

        return TenantRow(**dict(row))


async def resolve_workos_org_to_tenant_id(
    control_pool: asyncpg.Pool, workos_org_id: str
) -> str | None:
    """Resolve a WorkOS organization ID to an internal tenant ID.

    Args:
        control_pool: Database connection pool
        workos_org_id: WorkOS organization ID to resolve

    Returns:
        Internal tenant ID if found, None otherwise
    """
    async with control_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM public.tenants
            WHERE workos_org_id = $1
              AND state = 'provisioned'
            """,
            workos_org_id,
        )
        if row:
            return row["id"]
        return None


async def mark_tenant_state(
    control_pool: asyncpg.Pool, tenant_id: str, state: str, *, error_message: str | None = None
):
    async with control_pool.acquire() as conn:
        set_clauses = ["state = $1", "updated_at = now()"]
        params = [state]
        idx = 2

        if state == "error":
            set_clauses.append(f"error_message = ${idx}")
            params.append(error_message or "Unknown error")
            idx += 1
        elif state == "provisioned":
            set_clauses.append("provisioned_at = now()")

        params.append(tenant_id)
        query = f"UPDATE public.tenants SET {', '.join(set_clauses)} WHERE id = ${idx}"
        await conn.execute(query, *params)


async def _create_pg_database_and_roles(admin_pool: asyncpg.Pool, creds: TenantCredentials) -> None:
    """Create PostgreSQL database and roles based on pseudo code logic."""
    async with admin_pool.acquire() as conn:
        # Create database if it doesn't exist
        existing_db = await conn.fetchrow(
            "SELECT 1 FROM pg_database WHERE datname = $1", creds.db_name
        )
        if existing_db:
            logger.info("PSQL database already exists, skipping creation", db_name=creds.db_name)
        else:
            # Note: CREATE DATABASE cannot be executed within a transaction block
            logger.info("Creating PSQL database", db_name=creds.db_name)
            await conn.execute(f'CREATE DATABASE "{creds.db_name}"')

        existing_rw_role = await conn.fetchrow(
            "SELECT 1 FROM pg_roles WHERE rolname = $1", creds.db_rw_user
        )
        if existing_rw_role:
            # TODO handle this case better by reading the password from SSM
            error = RuntimeError(
                f"PSQL role {creds.db_rw_user} already exists. We can't create it again, or guarantee it's the same password."
            )
            newrelic.agent.record_exception()
            raise error

        logger.info("Creating PSQL role", db_rw_user=creds.db_rw_user)
        # Use single quote escaping (safer and simpler)
        escaped_password = creds.db_rw_pass.replace("'", "''")
        sql = f"CREATE ROLE \"{creds.db_rw_user}\" LOGIN PASSWORD '{escaped_password}' NOINHERIT"
        await conn.execute(sql)

        # Grant CONNECT only to tenant database
        await conn.execute(f'GRANT CONNECT ON DATABASE "{creds.db_name}" TO "{creds.db_rw_user}"')

        # Revoke CONNECT from other databases for the RW role
        # Exclude AWS-managed databases that we don't have permission to modify
        other_dbs = await conn.fetch(
            """SELECT datname FROM pg_database
               WHERE datname <> $1
               AND datistemplate = false
               AND datname NOT IN ('rdsadmin', 'template0', 'template1')""",
            creds.db_name,
        )

        for db_row in other_dbs:
            db_name = db_row["datname"]
            try:
                # Revoke from PUBLIC first (this removes default permissions)
                await conn.execute(f'REVOKE CONNECT ON DATABASE "{db_name}" FROM PUBLIC')
                logger.debug("Revoked CONNECT from PUBLIC", db_name=db_name)

                # Then revoke from specific user (redundant but explicit)
                await conn.execute(
                    f'REVOKE CONNECT ON DATABASE "{db_name}" FROM "{creds.db_rw_user}"'
                )
                logger.debug(
                    "Revoked CONNECT from user", db_name=db_name, db_rw_user=creds.db_rw_user
                )
            except Exception as e:
                newrelic.agent.record_exception()
                logger.warning(
                    "Could not revoke CONNECT on database", db_name=db_name, error=str(e)
                )


async def _harden_pg_schema(creds: TenantCredentials) -> None:
    """Harden PostgreSQL schema permissions based on pseudo code logic."""
    # Connect to tenant database as admin
    admin_conn_params = _get_admin_connection_params_for_tenant_db(creds.db_name)
    admin_conn = await asyncpg.connect(**admin_conn_params)

    try:
        # Revoke default public permissions
        await admin_conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")

        # Grant schema usage and create permissions
        await admin_conn.execute(f'GRANT ALL ON SCHEMA public TO "{creds.db_rw_user}"')

        # Grant all privileges on all current objects in the schema
        await admin_conn.execute(
            f'GRANT ALL ON ALL TABLES IN SCHEMA public TO "{creds.db_rw_user}"'
        )
        await admin_conn.execute(
            f'GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO "{creds.db_rw_user}"'
        )
        await admin_conn.execute(
            f'GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO "{creds.db_rw_user}"'
        )

        # Grant permissions on all FUTURE objects in the schema
        await admin_conn.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{creds.db_rw_user}"'
        )
        await admin_conn.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "{creds.db_rw_user}"'
        )
        await admin_conn.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO "{creds.db_rw_user}"'
        )
    finally:
        await admin_conn.close()


async def run_all_tenant_schema_migrations(creds: TenantCredentials) -> None:
    """Run all tenant migrations using the shared migration system."""
    # Get tenant database connection params with admin credentials
    admin_conn_params = _get_admin_connection_params_for_tenant_db(creds.db_name)
    # Build URL from connection params (migration system requires URL format)
    admin_tenant_url = _build_url_from_connection_params(admin_conn_params)

    try:
        applied_count, total_count, success = await migrate_database(
            admin_tenant_url,
            get_tenant_migrations_dir(),
            timeout=300,
            retries=1,
        )

        if not success:
            error_msg = (
                f"Failed to apply all tenant migrations: {applied_count}/{total_count} applied"
            )
            logger.error(
                error_msg,
                tenant_id=creds.tenant_id,
                applied_count=applied_count,
                total_count=total_count,
            )
            raise RuntimeError(error_msg)

        logger.info(
            f"Tenant migrations completed: {applied_count}/{total_count} applied",
            tenant_id=creds.tenant_id,
            applied_count=applied_count,
            total_count=total_count,
        )
    except Exception as e:
        newrelic.agent.record_exception()
        logger.error(
            "Failed to run tenant migrations",
            tenant_id=creds.tenant_id,
            error=str(e),
        )
        raise


async def _run_pg_sanity_checks(creds: TenantCredentials) -> None:
    """Run PostgreSQL sanity checks based on pseudo code logic."""
    # Positive test: RW user can connect to tenant database
    tenant_params = _get_tenant_connection_params(creds)
    logger.info(
        "Running sanity checks against tenant DB",
        host=tenant_params["host"],
        db=tenant_params["database"],
        user=tenant_params["user"],
    )
    rw_conn = await asyncpg.connect(**tenant_params)
    await rw_conn.close()

    logger.info("Positive test: RW user can connect to tenant database")

    # Negative test: RW user cannot connect to postgres database
    postgres_params = _get_params_for_tenant_on_admin_db(creds)
    try:
        bad_conn = await asyncpg.connect(**postgres_params)
        await bad_conn.close()
        raise RuntimeError(
            f"RW user {creds.db_rw_user} can connect to postgres DB (should be denied)"
        )
    except Exception as e:
        # This is expected - user should not be able to connect
        logger.info(
            "Negative test: RW user cannot connect to postgres database (expected)", error=str(e)
        )
        pass  # This is expected - user should not be able to connect


async def _save_tenant_config_values(
    creds: TenantCredentials, config_values: dict[str, str]
) -> None:
    """Save tenant config values to the database."""
    # Connect to tenant database
    conn_params = _get_tenant_connection_params(creds)
    conn = await asyncpg.connect(**conn_params)

    try:
        # Store each config value
        for key, value in config_values.items():
            await conn.execute(
                """
                INSERT INTO config (key, value, created_at, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (key)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                key,
                value,
            )
            logger.debug("Stored config value", tenant_id=creds.tenant_id, key=key, value=value)

        logger.info(
            "Successfully stored all config values",
            tenant_id=creds.tenant_id,
            config_count=len(config_values),
        )
    except Exception as e:
        # Log error but don't fail provisioning
        newrelic.agent.record_exception()
        logger.error("Failed to store config values", tenant_id=creds.tenant_id, error=str(e))
    finally:
        await conn.close()
