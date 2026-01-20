"""Tenant Provisioner Service

A background service that:
- Atomically fetches and locks the next pending tenant (using SKIP LOCKED)
- Marks it as provisioning
- Provisions tenant resources: PostgreSQL database, OpenSearch index, and credentials
- Updates state to provisioned or error accordingly
"""

from __future__ import annotations

from pathlib import Path

import newrelic.agent

from src.utils.amplitude import get_amplitude_service
from src.utils.config import get_grapevine_environment
from src.utils.logging import LogContext, get_logger
from src.utils.posthog import get_posthog_service

# Initialize New Relic with steward-specific TOML config and environment
config_path = Path(__file__).parent / "newrelic.toml"
grapevine_env = get_grapevine_environment()
# Initialize New Relic with the steward-specific TOML config and environment
newrelic.agent.initialize(str(config_path), environment=grapevine_env)

import asyncio
import os
import signal
from datetime import datetime

import asyncpg
import workos

from src.clients.ssm import SSMClient
from src.steward.models import TenantCredentials, TenantRow
from src.steward.opensearch import _create_os_index, _run_os_sanity_checks
from src.steward.postgres import (
    _create_admin_pool,
    _create_control_pool,
    _create_pg_database_and_roles,
    _harden_pg_schema,
    _run_pg_sanity_checks,
    _save_tenant_config_values,
    fetch_and_lock_next_pending_tenant,
    mark_tenant_state,
    run_all_tenant_schema_migrations,
)

# Configuration
POLL_INTERVAL_SECONDS = float(os.environ.get("STEWARD_POLL_INTERVAL_SECONDS", "2.0"))
DEFAULT_TENANT_NAME = "Your Company"

# Default tenant configuration values for new tenants
# These are used both for storing config in the database and for analytics tracking
DEFAULT_TENANT_CONFIG = {
    "ALLOW_DATA_SHARING_FOR_IMPROVEMENTS": False,
    "SLACK_BOT_QA_ALL_CHANNELS": True,
    "SLACK_BOT_QA_SKIP_CHANNELS_WITH_EXTERNAL_GUESTS": False,
    "SLACK_BOT_QA_SKIP_MENTIONS_BY_NON_MEMBERS": True,
}

# Initialize logger
logger = get_logger(__name__)

# Credential storage constants
PG_KEYS = {"db_name", "db_rw_user", "db_rw_pass"}

# Required environment variables
REQUIRED_ENV_VARS = [
    "CONTROL_DATABASE_URL",
    "PG_TENANT_DATABASE_HOST",
    "PG_TENANT_DATABASE_ADMIN_USERNAME",
    "PG_TENANT_DATABASE_ADMIN_PASSWORD",
    "PG_TENANT_DATABASE_ADMIN_DB",
    "OPENSEARCH_DOMAIN_HOST",
    "OPENSEARCH_PORT",
    "KMS_KEY_ID",
    "WORKOS_API_KEY",
]


def validate_environment() -> None:
    """Validate that all required environment variables are present."""
    missing_vars = []
    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            missing_vars.append(var)

    # Check for OpenSearch admin credentials (basic auth required)
    opensearch_auth_vars = ["OPENSEARCH_ADMIN_USERNAME", "OPENSEARCH_ADMIN_PASSWORD"]
    for var in opensearch_auth_vars:
        if not os.environ.get(var):
            missing_vars.append(var)

    if missing_vars:
        error = RuntimeError(
            f"Missing required environment variables: {', '.join(missing_vars)}. "
            "Please set these variables before starting the steward service."
        )
        newrelic.agent.record_exception()
        raise error


async def _store_credentials_in_ssm(tenant_id: str, creds: TenantCredentials) -> None:
    """Store credentials in AWS SSM Parameter Store."""
    ssm_client = SSMClient()

    # Prepare all parameter tasks
    tasks = []

    for key in PG_KEYS:
        tasks.append(
            ssm_client.put_parameter(
                parameter_name=f"/{tenant_id}/credentials/postgresql/{key}",
                value=str(getattr(creds, key)),
                description=f"PostgreSQL credential {key} for tenant {tenant_id}",
            )
        )

    # Execute all parameter saves concurrently
    await asyncio.gather(*tasks)


async def _fetch_workos_org_name(workos_org_id: str | None, max_retries: int = 3) -> str | None:
    """Fetch WorkOS organization name with retry logic and exponential backoff.

    Args:
        workos_org_id: The WorkOS organization ID
        max_retries: Maximum number of retry attempts

    Returns:
        Organization name if successful, None if all retries fail
    """
    workos_api_key = os.environ.get("WORKOS_API_KEY")
    if not workos_api_key:
        logger.warning("WORKOS_API_KEY not configured, skipping org name fetch")
        return None

    if not workos_org_id:
        logger.warning("WorkOS organization ID not provided, skipping org name fetch")
        return None

    client = workos.WorkOSClient(api_key=workos_api_key)

    for attempt in range(max_retries):
        try:
            logger.info(
                f"Fetching WorkOS organization name (attempt {attempt + 1}/{max_retries})",
                workos_org_id=workos_org_id,
            )

            organization = client.organizations.get_organization(workos_org_id)
            org_name = organization.name

            logger.info(
                "Successfully fetched WorkOS organization name",
                workos_org_id=workos_org_id,
                org_name=org_name,
            )
            return org_name

        except Exception as e:
            logger.warning(
                f"Failed to fetch WorkOS organization (attempt {attempt + 1}/{max_retries})",
                workos_org_id=workos_org_id,
                error=str(e),
            )

            # If this is the last attempt, don't wait
            if attempt < max_retries - 1:
                # Exponential backoff: 1s, 2s, 4s
                wait_time = 2**attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)

    logger.error("All attempts to fetch WorkOS organization failed", workos_org_id=workos_org_id)
    return None


async def _store_default_config_values(
    tenant: TenantRow, company_name: str, creds: TenantCredentials
) -> None:
    """Store default configuration values in the tenant database.

    Args:
        tenant: The tenant object
        company_name: The company/organization name
        creds: The tenant credentials for database access
    """

    tenant_mode = "qa" if tenant.source == "landing_page" else "dev_platform"
    # Default configuration values (using shared defaults)
    default_configs = {
        "COMPANY_NAME": company_name,
        "TENANT_MODE": tenant_mode,
    }

    for key, value in DEFAULT_TENANT_CONFIG.items():
        default_configs[key] = str(value).lower()

    logger.info(
        "Storing default configuration values for tenant",
        tenant_id=tenant.id,
        config_count=len(default_configs),
        tenant_mode=tenant_mode,
    )

    # Store the config values using the postgres module function
    await _save_tenant_config_values(creds, default_configs)


async def _track_tenant_provisioned(tenant: TenantRow, company_name: str) -> None:
    """Track tenant provisioning in both Amplitude and PostHog with complete person properties.

    Args:
        tenant: The tenant object
        company_name: The company/organization name
    """
    try:
        # Build complete person properties with defaults (using shared defaults)
        person_properties = {
            "org_name": company_name,
            "workos_org_id": tenant.workos_org_id,
            "data_sharing_enabled": DEFAULT_TENANT_CONFIG["ALLOW_DATA_SHARING_FOR_IMPROVEMENTS"],
            "proactivity_enabled": DEFAULT_TENANT_CONFIG["SLACK_BOT_QA_ALL_CHANNELS"],
            "skip_external_guests": DEFAULT_TENANT_CONFIG[
                "SLACK_BOT_QA_SKIP_CHANNELS_WITH_EXTERNAL_GUESTS"
            ],
            "last_updated_at": datetime.now().isoformat(),
        }

        # Add trial_start_at if available
        if tenant.trial_start_at:
            person_properties["trial_start_at"] = tenant.trial_start_at.isoformat()

        # Track in Amplitude
        amplitude_service = get_amplitude_service()
        if amplitude_service.is_initialized:
            amplitude_service.identify(
                user_id=tenant.id,
                user_properties=person_properties,
            )
            amplitude_service.flush()
            logger.info(
                "Successfully tracked tenant provisioning in Amplitude",
                tenant_id=tenant.id,
                organization_name=company_name,
            )
        else:
            logger.warning(
                "Amplitude service not initialized, skipping Amplitude tracking",
                tenant_id=tenant.id,
            )

        # Track in PostHog (note: source=backend added automatically by posthog service)

        posthog_service = get_posthog_service()
        if posthog_service.is_initialized:
            # Set person properties
            posthog_service.set(distinct_id=tenant.id, properties=person_properties)
            # Capture tenant provisioned event
            posthog_service.capture(
                distinct_id=tenant.id,
                event="tenant_provisioned",
                properties={
                    "org_name": company_name,
                    "workos_org_id": tenant.workos_org_id,
                },
            )
            posthog_service.flush()
            logger.info(
                "Successfully tracked tenant provisioning in PostHog",
                tenant_id=tenant.id,
                organization_name=company_name,
            )
        else:
            logger.warning(
                "PostHog service not initialized, skipping PostHog tracking",
                tenant_id=tenant.id,
            )

    except Exception as e:
        # Don't let analytics tracking errors fail tenant provisioning
        logger.error(
            "Failed to track tenant provisioning in analytics", error=str(e), tenant_id=tenant.id
        )


@newrelic.agent.background_task(name="Steward/provision_tenant")
async def provision_tenant(
    admin_pool: asyncpg.Pool,
    tenant: TenantRow,
    tenant_name: str,
) -> bool:
    """Provision tenant resources: PostgreSQL database, OpenSearch index, and store credentials in SSM."""
    # Add New Relic attributes
    newrelic.agent.add_custom_attribute("tenant_id", tenant.id)

    try:
        logger.info(f"Starting provisioning for tenant {tenant.id}")

        # Generate credentials
        creds = TenantCredentials(tenant.id)

        # Step 1: Create PostgreSQL database and roles
        logger.info(f"Creating PostgreSQL database and roles for tenant {tenant.id}")
        await _create_pg_database_and_roles(admin_pool, creds)

        # Step 2: Run tenant schema migration
        logger.info(f"Running tenant schema migration for tenant {tenant.id}")
        await run_all_tenant_schema_migrations(creds)

        # Step 3: Harden PostgreSQL schema
        logger.info(f"Hardening PostgreSQL schema for tenant {tenant.id}")
        await _harden_pg_schema(creds)

        # Step 4: Run sanity checks
        logger.info(f"Running PostgreSQL sanity checks for tenant {tenant.id}")
        await _run_pg_sanity_checks(creds)

        logger.info(
            f"Successfully provisioned PostgreSQL for tenant {tenant.id}, moving on to OpenSearch"
        )

        # Step 5: Create OpenSearch index
        logger.info(f"Creating OpenSearch index for tenant {tenant.id}")
        await _create_os_index(creds)

        # Step 6: Run sanity checks
        logger.info(f"Running OpenSearch sanity checks for tenant {tenant.id}")
        await _run_os_sanity_checks(creds)

        # Step 7: Store credentials in SSM
        logger.info(f"Storing credentials in SSM for tenant {tenant.id}")
        await _store_credentials_in_ssm(tenant.id, creds)

        # Step 8: Store default configuration values
        logger.info(f"Storing default configuration values for tenant {tenant.id}")
        await _store_default_config_values(tenant, tenant_name, creds)

        logger.info(f"Successfully provisioned tenant {tenant.id}")
        return True

    except Exception as e:
        newrelic.agent.record_exception()
        logger.error(f"Failed to provision tenant {tenant.id}", error=str(e))
        raise e


def log_error(err: BaseException):
    logger.error("Steward error", error=str(err))


async def run_once(control_pool: asyncpg.Pool, admin_pool: asyncpg.Pool) -> bool:
    tenant = await fetch_and_lock_next_pending_tenant(control_pool)
    if tenant is None:
        return False

    with LogContext(tenant_id=tenant.id):
        # Fetch company name for analytics tracking
        company_name = await _fetch_workos_org_name(tenant.workos_org_id)
        if not company_name:
            company_name = DEFAULT_TENANT_NAME

        try:
            if await provision_tenant(admin_pool, tenant, company_name):
                await mark_tenant_state(control_pool, tenant.id, "provisioned")
                # Track tenant provisioning in both Amplitude and PostHog
                await _track_tenant_provisioned(tenant, company_name)
        except Exception as e:  # noqa: BLE001 - intentional broad catch for service loop
            newrelic.agent.record_exception()
            log_error(e)
            try:
                await mark_tenant_state(control_pool, tenant.id, "error", error_message=str(e))
            except Exception as inner:
                newrelic.agent.record_exception()
                log_error(inner)
                await mark_tenant_state(control_pool, tenant.id, "error", error_message=str(inner))
        return True


def _install_signal_handlers(stop_event: asyncio.Event):
    def _handler(signum, _frame):  # noqa: ARG001
        logger.info("Received signal, setting stop event", signal=signum)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handler)


async def main():
    # first register signal handlers in case there's an early SIGTERM
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    # manually register the newrelic APM application since steward only does background jobs (no web requests)
    # See https://docs.newrelic.com/docs/apm/agents/python-agent/python-agent-api/registerapplication-python-agent-api/#description
    newrelic.agent.register_application()

    # Validate required environment variables
    validate_environment()

    control_pool = await _create_control_pool()
    admin_pool = await _create_admin_pool()

    try:
        while not stop_event.is_set():
            progressed = await run_once(control_pool, admin_pool)
            if not progressed:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        logger.info("Stop event is set, shutting down")
    except Exception as e:
        newrelic.agent.record_exception()
        logger.error("Unexpected error in main loop", error=str(e))
        raise
    finally:
        await control_pool.close()
        await admin_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
