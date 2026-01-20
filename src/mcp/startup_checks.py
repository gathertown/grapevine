"""Startup health checks for critical services."""

import asyncio
import sys

from src.clients.openai import get_openai_client
from src.clients.supabase import get_control_db_connection
from src.utils.logging import get_logger

logger = get_logger(__name__)


class StartupCheckError(Exception):
    """Raised when a startup check fails."""

    pass


async def check_openai_connectivity() -> tuple[bool, str]:
    """Check if OpenAI API is accessible and responding.

    Returns:
        Tuple of (success, message)
    """
    try:
        client = get_openai_client()

        # Test basic connectivity by listing models
        models = client.list_models()

        if models and len(models) > 0:
            model_count = len(models)
            embedding_model = client.get_embedding_model()
            return (
                True,
                f"OpenAI API accessible with {model_count} models (embedding: {embedding_model})",
            )
        else:
            return False, "OpenAI API responded but no models available"

    except Exception as e:
        return False, f"OpenAI API connection failed: {str(e)}"


async def check_supabase_connectivity() -> tuple[bool, str]:
    """Check if Control PostgreSQL database is accessible and responding.

    Returns:
        Tuple of (success, message)
    """
    try:
        conn = await get_control_db_connection()

        try:
            # Test basic connectivity by running a simple query
            result = await conn.fetchval("SELECT 1")

            if result == 1:
                # Get some basic database info for the success message
                version = await conn.fetchval("SELECT version()")
                db_name = await conn.fetchval("SELECT current_database()")

                # Extract just the PostgreSQL version number
                version_short = version.split()[1] if version else "unknown"

                return True, f"Control PostgreSQL {version_short} database '{db_name}' accessible"
            else:
                return False, "Control database responded but test query failed"

        finally:
            await conn.close()

    except Exception as e:
        return False, f"Control PostgreSQL connection failed: {str(e)}"


async def run_startup_checks_async() -> None:
    """Run all startup health checks in parallel and exit if any fail.

    Raises:
        StartupCheckError: If any check fails
        SystemExit: If critical services are not accessible
    """
    logger.info("=" * 60)
    logger.info("🔍 Running startup health checks in parallel...")
    logger.info("=" * 60)

    # Run all checks in parallel
    checks = [
        ("OpenAI", check_openai_connectivity()),
        ("Control PostgreSQL", check_supabase_connectivity()),
    ]

    failed_checks = []

    # Log that we're starting all checks
    for service_name, _ in checks:
        logger.info(f"🔌 Starting {service_name} check...")

    # Wait for all checks to complete
    try:
        results = await asyncio.gather(
            *[check_coro for _, check_coro in checks], return_exceptions=True
        )

        # Process results
        for (service_name, _), result in zip(checks, results, strict=False):
            if isinstance(result, Exception):
                error_msg = f"Unexpected error during {service_name} check: {str(result)}"
                logger.error(f"❌ {service_name}: {error_msg}")
                failed_checks.append((service_name, error_msg))
            else:
                success, message = result  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                if success:
                    logger.info(f"✅ {service_name}: {message}")
                else:
                    logger.error(f"❌ {service_name}: {message}")
                    failed_checks.append((service_name, message))

    except Exception as e:
        logger.error(f"❌ Unexpected error during parallel checks: {str(e)}")
        failed_checks.append(("Parallel execution", str(e)))

    logger.info("=" * 60)

    if failed_checks:
        logger.error("🚨 STARTUP CHECKS FAILED 🚨")
        logger.error("The following critical services are not accessible:")

        for service_name, error_msg in failed_checks:
            logger.error(f"  • {service_name}: {error_msg}")

        logger.error("")
        logger.error("The MCP server cannot start without these services.")
        logger.error("Please check your configuration and ensure all services are running.")
        logger.error("=" * 60)

        # Exit immediately with error code
        sys.exit(1)

    else:
        logger.info("✅ All startup health checks passed!")
        logger.info("🚀 MCP server ready to start...")
        logger.info("=" * 60)


def run_startup_checks() -> None:
    """Run all startup health checks synchronously (wrapper for async version).

    Raises:
        StartupCheckError: If any check fails
        SystemExit: If critical services are not accessible
    """
    asyncio.run(run_startup_checks_async())
