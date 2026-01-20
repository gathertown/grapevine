"""
Proactive token refresh job for Snowflake OAuth tokens.

This job runs periodically (e.g., daily) to check all tenants with Snowflake
OAuth tokens and proactively refreshes tokens that are close to expiring.

This prevents users from encountering "refresh token expired" errors when they
return after extended periods of inactivity.

Usage:
    python -m src.warehouses.token_refresh_job --dry-run
    python -m src.warehouses.token_refresh_job --days-threshold 7
"""

import argparse
import asyncio
from datetime import datetime
from typing import Any

from src.clients.control_db import control_db_manager
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.warehouses.snowflake_service import PROACTIVE_REFRESH_THRESHOLD_DAYS, SnowflakeService

logger = get_logger(__name__)


async def get_tenants_with_snowflake_oauth() -> list[str]:
    """
    Get list of all tenant IDs that have Snowflake OAuth tokens configured.

    Returns list of tenant_ids.
    """
    ssm_client = SSMClient()
    tenant_ids = []

    try:
        # Get all tenants from control database
        async with control_db_manager.acquire_connection() as conn:
            result = await conn.fetch(
                """
                SELECT id FROM tenants
                WHERE state = 'provisioned'
                ORDER BY id
                """
            )
            all_tenant_ids = [row["id"] for row in result]

        # Check which tenants have Snowflake OAuth tokens
        for tenant_id in all_tenant_ids:
            ssm_key = f"/{tenant_id}/api-key/SNOWFLAKE_OAUTH_TOKEN_PAYLOAD"
            token_json = await ssm_client.get_parameter(ssm_key)
            if token_json:
                tenant_ids.append(tenant_id)

        logger.info(
            f"Found {len(tenant_ids)} tenants with Snowflake OAuth tokens",
            extra={"tenant_count": len(tenant_ids)},
        )
        return tenant_ids

    except Exception as e:
        logger.error(f"Error getting tenants with Snowflake OAuth: {e}")
        return []


async def refresh_token_for_tenant(
    tenant_id: str, days_threshold: int = PROACTIVE_REFRESH_THRESHOLD_DAYS, dry_run: bool = False
) -> dict[str, Any]:
    """
    Check and refresh token for a single tenant if needed.

    Args:
        tenant_id: Tenant identifier
        days_threshold: Refresh if token expires within this many days
        dry_run: If True, only check but don't actually refresh

    Returns:
        Dict with status and details about the refresh operation
    """
    service = SnowflakeService()
    result = {
        "tenant_id": tenant_id,
        "status": "skipped",
        "message": "",
        "refresh_token_expires_at": None,
        "refreshed": False,
    }

    try:
        # Get current token
        token = await service._get_oauth_token_from_ssm(tenant_id)
        if not token:
            result["status"] = "no_token"
            result["message"] = "No Snowflake OAuth token found"
            return result

        result["refresh_token_expires_at"] = token.refresh_token_expires_at

        # Check if refresh token is expired
        if token.is_refresh_token_expired():
            result["status"] = "expired"
            result["message"] = "Refresh token already expired - user must reconnect via OAuth flow"
            logger.warning(
                f"Tenant {tenant_id}: Refresh token expired",
                extra={
                    "tenant_id": tenant_id,
                    "expired_at": token.refresh_token_expires_at,
                },
            )
            return result

        # Check if refresh token is expiring soon
        if token.is_refresh_token_expiring_soon(days_threshold):
            result["status"] = "expiring_soon"
            msg = f"Refresh token expires within {days_threshold} days"
            result["message"] = msg

            if dry_run:
                result["message"] = msg + " (dry-run: would refresh)"
                logger.info(
                    f"Tenant {tenant_id}: Would refresh token (dry-run)",
                    extra={
                        "tenant_id": tenant_id,
                        "expires_at": token.refresh_token_expires_at,
                        "days_threshold": days_threshold,
                    },
                )
            else:
                try:
                    refreshed_token = await service.force_refresh_oauth_token(tenant_id)
                    result["refreshed"] = True
                    result["message"] = "Token refreshed successfully"
                    result["refresh_token_expires_at"] = refreshed_token.refresh_token_expires_at
                    logger.info(
                        f"Tenant {tenant_id}: Token refreshed successfully",
                        extra={
                            "tenant_id": tenant_id,
                            "new_expires_at": refreshed_token.refresh_token_expires_at,
                        },
                    )
                except Exception as refresh_error:
                    result["status"] = "error"
                    result["message"] = f"Failed to refresh token: {str(refresh_error)}"
                    logger.error(
                        f"Tenant {tenant_id}: Failed to refresh token",
                        extra={
                            "tenant_id": tenant_id,
                            "error": str(refresh_error),
                        },
                    )
        else:
            result["status"] = "ok"
            result["message"] = f"Token valid for more than {days_threshold} days"
            logger.debug(
                f"Tenant {tenant_id}: Token valid, no refresh needed",
                extra={
                    "tenant_id": tenant_id,
                    "expires_at": token.refresh_token_expires_at,
                },
            )

    except Exception as e:
        result["status"] = "error"
        result["message"] = f"Error checking token: {str(e)}"
        logger.error(
            f"Tenant {tenant_id}: Error checking token",
            extra={
                "tenant_id": tenant_id,
                "error": str(e),
            },
        )
    finally:
        await service.close()

    return result


async def run_token_refresh_job(
    days_threshold: int = PROACTIVE_REFRESH_THRESHOLD_DAYS, dry_run: bool = False
) -> None:
    """
    Main function to run the token refresh job for all tenants.

    Args:
        days_threshold: Refresh tokens expiring within this many days
        dry_run: If True, only check but don't actually refresh
    """
    start_time = datetime.now()
    logger.info(
        "Starting Snowflake token refresh job",
        extra={
            "days_threshold": days_threshold,
            "dry_run": dry_run,
        },
    )

    # Get all tenants with Snowflake OAuth
    tenant_ids = await get_tenants_with_snowflake_oauth()
    if not tenant_ids:
        logger.info("No tenants with Snowflake OAuth tokens found")
        return

    # Check and refresh tokens for each tenant
    results = []
    for tenant_id in tenant_ids:
        result = await refresh_token_for_tenant(tenant_id, days_threshold, dry_run)
        results.append(result)

    # Summarize results
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "refreshed": sum(1 for r in results if r["refreshed"]),
        "expiring_soon": sum(1 for r in results if r["status"] == "expiring_soon"),
        "expired": sum(1 for r in results if r["status"] == "expired"),
        "no_token": sum(1 for r in results if r["status"] == "no_token"),
        "error": sum(1 for r in results if r["status"] == "error"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
    }

    elapsed_seconds = (datetime.now() - start_time).total_seconds()

    logger.info(
        f"Token refresh job completed in {elapsed_seconds:.2f}s",
        extra={
            "summary": summary,
            "elapsed_seconds": elapsed_seconds,
            "dry_run": dry_run,
        },
    )

    # Log details for tokens that need attention
    for result in results:
        if result["status"] in ["expired", "error"]:
            logger.warning(
                f"Tenant {result['tenant_id']}: {result['message']}",
                extra=result,
            )


async def main():
    """CLI entry point for token refresh job."""
    parser = argparse.ArgumentParser(description="Proactive Snowflake OAuth token refresh job")
    parser.add_argument(
        "--days-threshold",
        type=int,
        default=7,
        help="Refresh tokens expiring within this many days (default: 7)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check tokens but don't actually refresh them",
    )

    args = parser.parse_args()

    await run_token_refresh_job(
        days_threshold=args.days_threshold,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    asyncio.run(main())
