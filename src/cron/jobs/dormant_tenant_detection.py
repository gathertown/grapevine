"""
Dormant tenant detection cron job.

Runs daily to:
1. Scan all provisioned tenants for dormancy criteria
2. Mark newly detected dormant tenants
3. Optionally auto-delete expired dormant tenants (past grace period)
4. Emit structured logs for monitoring
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.cron import cron
from src.dormant.deletion import discover_tenant_resources, hard_delete_tenant
from src.dormant.service import (
    DormancyCheckResult,
    get_dormant_days_threshold,
    get_expired_dormant_tenants,
    get_grace_period_days,
    is_auto_delete_enabled,
    is_detection_enabled,
    scan_for_dormant_tenants,
)
from src.utils.config import get_config_value
from src.utils.logging import get_logger

logger = get_logger(__name__)


def is_dry_run_enabled() -> bool:
    """Check if dry-run mode is enabled (no actual marking or deletion)."""
    return get_config_value("DORMANT_DRY_RUN", True)


@cron(
    id="dormant_tenant_detection",
    crontab="*/30 * * * *",  # Every 30 minutes
    tags=["ops", "tenant-lifecycle"],
    enabled_env="DORMANT_DETECTION_ENABLED",
)
async def dormant_tenant_detection() -> None:
    """
    Detect and manage dormant tenants.

    A tenant is considered dormant if ALL of these conditions are true:
    - No connector installations
    - No Slack bot installed
    - Zero documents in tenant database
    - No MCP usage/requests recorded
    - Provisioned more than DORMANT_DAYS_THRESHOLD days ago

    This job:
    1. Scans all eligible tenants and marks newly detected dormant ones
    2. If DORMANT_AUTO_DELETE_ENABLED=1, deletes expired dormant tenants
       (those past the DORMANT_GRACE_PERIOD_DAYS threshold)

    Environment Variables:
        DORMANT_DETECTION_ENABLED: Set to "true" to enable this job (default: false)
        DORMANT_DRY_RUN: Set to "true" for dry-run mode (default: true)
            - Logs what would happen without marking or deleting
            - Set to "false" to enable actual marking and deletion
        DORMANT_DAYS_THRESHOLD: Days since provisioning to consider dormant (default: 7)
        DORMANT_GRACE_PERIOD_DAYS: Days after marking before deletion (default: 14)
        DORMANT_AUTO_DELETE_ENABLED: Set to "true" to enable auto-deletion (default: false)
    """
    if not is_detection_enabled():
        logger.info(
            "Dormant tenant detection is disabled",
            extra={
                "dormant_detection_enabled": False,
                "hint": "Set DORMANT_DETECTION_ENABLED=true to enable",
            },
        )
        return

    threshold_days = get_dormant_days_threshold()
    grace_period_days = get_grace_period_days()
    auto_delete = is_auto_delete_enabled()
    dry_run = is_dry_run_enabled()

    logger.info(
        "Starting dormant tenant detection",
        extra={
            "dormant_threshold_days": threshold_days,
            "grace_period_days": grace_period_days,
            "auto_delete_enabled": auto_delete,
            "dry_run": dry_run,
        },
    )

    if dry_run:
        logger.info("DRY RUN MODE: No tenants will be marked or deleted")

    # Phase 1: Scan and mark dormant tenants (skip marking in dry-run mode)
    scan_result = await scan_for_dormant_tenants(mark=not dry_run)

    dormant_tenant_ids = [c.tenant_id for c in scan_result.dormant_candidates]

    logger.info(
        "Dormant tenant scan completed",
        extra={
            "total_tenants_scanned": scan_result.total_scanned,
            "dormant_candidates_found": len(scan_result.dormant_candidates),
            "newly_marked_dormant": scan_result.newly_marked,
            "scan_errors": len(scan_result.errors),
            "dormant_tenant_ids": dormant_tenant_ids,
        },
    )

    # Log details for each dormant tenant found
    for candidate in scan_result.dormant_candidates:
        _log_dormant_candidate(candidate)

    # Phase 2: Auto-delete expired dormant tenants (if enabled and not dry-run)
    deleted_count = 0
    would_delete_count = 0
    delete_errors: list[str] = []

    if auto_delete:
        logger.info("Auto-delete enabled, checking for expired dormant tenants")

        from src.clients.tenant_db import tenant_db_manager

        control_pool = await tenant_db_manager.get_control_db()
        expired_tenants = await get_expired_dormant_tenants(control_pool)

        if expired_tenants:
            logger.info(
                f"Found {len(expired_tenants)} expired dormant tenants eligible for deletion",
                extra={"dry_run": dry_run},
            )

            for tenant in expired_tenants:
                tenant_info = {
                    "tenant_id": tenant.id,
                    "dormant_detected_at": (
                        tenant.dormant_detected_at.isoformat()
                        if tenant.dormant_detected_at
                        else None
                    ),
                    "days_dormant": (
                        _days_since(tenant.dormant_detected_at)
                        if tenant.dormant_detected_at
                        else None
                    ),
                }

                if dry_run:
                    # In dry-run mode, discover resources but don't delete
                    logger.info(
                        f"DRY RUN: Would delete expired dormant tenant {tenant.id}",
                        extra=tenant_info,
                    )
                    try:
                        discovery = await discover_tenant_resources(tenant.id)
                        logger.info(
                            f"DRY RUN: Resources for tenant {tenant.id}",
                            extra={
                                "tenant_id": tenant.id,
                                "database_exists": discovery.database_exists,
                                "database_name": discovery.database_name,
                                "role_exists": discovery.role_exists,
                                "opensearch_indices": discovery.opensearch_indices,
                                "turbopuffer_namespace_exists": discovery.turbopuffer_namespace_exists,
                                "ssm_parameter_count": len(discovery.ssm_parameters),
                                "control_db_tenant_exists": discovery.control_db_tenant_exists,
                                "control_db_related_counts": discovery.control_db_related_counts,
                            },
                        )
                    except Exception as e:
                        logger.warning(
                            f"DRY RUN: Failed to discover resources for {tenant.id}: {e}"
                        )
                    would_delete_count += 1
                else:
                    # Actually delete the tenant
                    logger.info(
                        f"Auto-deleting expired dormant tenant {tenant.id}",
                        extra=tenant_info,
                    )

                    result = await hard_delete_tenant(tenant.id)

                    if result.success:
                        deleted_count += 1
                    else:
                        delete_errors.append(f"Tenant {tenant.id}: {', '.join(result.errors)}")

    # Final summary log
    summary_extra = {
        "dry_run": dry_run,
        "total_scanned": scan_result.total_scanned,
        "dormant_found": len(scan_result.dormant_candidates),
        "newly_marked": scan_result.newly_marked if not dry_run else 0,
        "would_mark": len(scan_result.dormant_candidates) if dry_run else 0,
        "expired_deleted": deleted_count,
        "would_delete": would_delete_count if dry_run else 0,
        "delete_errors": len(delete_errors),
        "dormant_tenant_ids": dormant_tenant_ids,
    }

    if dry_run:
        logger.info(
            "DRY RUN: Dormant tenant detection job completed (no changes made)",
            extra=summary_extra,
        )
    else:
        logger.info(
            "Dormant tenant detection job completed",
            extra=summary_extra,
        )

    if scan_result.errors:
        logger.warning(
            "Scan errors encountered",
            extra={"errors": scan_result.errors},
        )

    if delete_errors:
        logger.warning(
            "Delete errors encountered",
            extra={"errors": delete_errors},
        )


def _log_dormant_candidate(candidate: DormancyCheckResult) -> None:
    """Log detailed information about a dormant tenant candidate."""
    logger.info(
        f"Dormant tenant: {candidate.tenant_id}",
        extra={
            "tenant_id": candidate.tenant_id,
            "company_name": candidate.company_name,
            "has_connectors": candidate.has_connectors,
            "has_slack_bot": candidate.has_slack_bot,
            "document_count": candidate.document_count,
            "usage_count": candidate.usage_count,
            "days_since_provisioning": candidate.days_since_provisioning,
            "reasons": candidate.reasons,
        },
    )


def _days_since(dt: datetime | None) -> int | None:
    """Calculate days since a datetime."""
    if dt is None:
        return None
    now = datetime.now(UTC)
    dt_utc = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
    return (now - dt_utc).days
