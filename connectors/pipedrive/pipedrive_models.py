"""Pipedrive connector models and configuration types."""

from typing import Literal

from connectors.base.models import BackfillIngestConfig


class PipedriveBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Pipedrive full backfill job."""

    source: Literal["pipedrive_backfill_root"] = "pipedrive_backfill_root"


class PipedriveBackfillEntityConfig(BackfillIngestConfig, frozen=True):
    """Configuration for backfilling a specific Pipedrive entity type with record IDs."""

    source: Literal["pipedrive_entity_backfill"] = "pipedrive_entity_backfill"
    entity_type: str  # "deal", "person", "organization"
    record_ids: tuple[int, ...] = ()  # Tuple of record IDs to process (frozen-compatible)


class PipedriveIncrementalBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Pipedrive incremental backfill job.

    Uses cursor-based pagination with updated_after filter to sync
    recently modified records.
    """

    source: Literal["pipedrive_incremental_backfill"] = "pipedrive_incremental_backfill"
    lookback_hours: int = 2  # How many hours back to check for updates


# Config keys for sync state persistence
PIPEDRIVE_ACCESS_TOKEN_KEY = "PIPEDRIVE_ACCESS_TOKEN"
PIPEDRIVE_REFRESH_TOKEN_KEY = "PIPEDRIVE_REFRESH_TOKEN"
PIPEDRIVE_API_DOMAIN_KEY = "PIPEDRIVE_API_DOMAIN"
PIPEDRIVE_COMPANY_ID_KEY = "PIPEDRIVE_COMPANY_ID"
PIPEDRIVE_COMPANY_NAME_KEY = "PIPEDRIVE_COMPANY_NAME"
PIPEDRIVE_TOKEN_EXPIRES_AT_KEY = "PIPEDRIVE_TOKEN_EXPIRES_AT"

# Sync state config keys
PIPEDRIVE_DEALS_SYNCED_UNTIL_KEY = "PIPEDRIVE_DEALS_SYNCED_UNTIL"
PIPEDRIVE_PERSONS_SYNCED_UNTIL_KEY = "PIPEDRIVE_PERSONS_SYNCED_UNTIL"
PIPEDRIVE_ORGS_SYNCED_UNTIL_KEY = "PIPEDRIVE_ORGS_SYNCED_UNTIL"
PIPEDRIVE_PRODUCTS_SYNCED_UNTIL_KEY = "PIPEDRIVE_PRODUCTS_SYNCED_UNTIL"
PIPEDRIVE_FULL_BACKFILL_COMPLETE_KEY = "PIPEDRIVE_FULL_BACKFILL_COMPLETE"

# Pagination cursor keys (for resumable backfills)
PIPEDRIVE_DEALS_CURSOR_KEY = "PIPEDRIVE_DEALS_CURSOR"
PIPEDRIVE_PERSONS_CURSOR_KEY = "PIPEDRIVE_PERSONS_CURSOR"
PIPEDRIVE_ORGS_CURSOR_KEY = "PIPEDRIVE_ORGS_CURSOR"
PIPEDRIVE_PRODUCTS_CURSOR_KEY = "PIPEDRIVE_PRODUCTS_CURSOR"

# Reference data keys (for hydration during transformation)
PIPEDRIVE_PERSON_LABELS_KEY = "PIPEDRIVE_PERSON_LABELS"  # JSON: {id: name, ...}

# All Pipedrive config keys (for cleanup on disconnect)
PIPEDRIVE_CONFIG_KEYS = [
    PIPEDRIVE_ACCESS_TOKEN_KEY,
    PIPEDRIVE_REFRESH_TOKEN_KEY,
    PIPEDRIVE_API_DOMAIN_KEY,
    PIPEDRIVE_COMPANY_ID_KEY,
    PIPEDRIVE_COMPANY_NAME_KEY,
    PIPEDRIVE_TOKEN_EXPIRES_AT_KEY,
    PIPEDRIVE_DEALS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_PERSONS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_ORGS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_PRODUCTS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_FULL_BACKFILL_COMPLETE_KEY,
    PIPEDRIVE_DEALS_CURSOR_KEY,
    PIPEDRIVE_PERSONS_CURSOR_KEY,
    PIPEDRIVE_ORGS_CURSOR_KEY,
    PIPEDRIVE_PRODUCTS_CURSOR_KEY,
    PIPEDRIVE_PERSON_LABELS_KEY,
]

# Sensitive keys stored in SSM (not in tenant config table)
PIPEDRIVE_SENSITIVE_KEYS = [
    PIPEDRIVE_ACCESS_TOKEN_KEY,
    PIPEDRIVE_REFRESH_TOKEN_KEY,
]

# Non-sensitive keys stored in tenant config table
PIPEDRIVE_NON_SENSITIVE_KEYS = [
    PIPEDRIVE_API_DOMAIN_KEY,
    PIPEDRIVE_COMPANY_ID_KEY,
    PIPEDRIVE_COMPANY_NAME_KEY,
    PIPEDRIVE_TOKEN_EXPIRES_AT_KEY,
    PIPEDRIVE_DEALS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_PERSONS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_ORGS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_PRODUCTS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_FULL_BACKFILL_COMPLETE_KEY,
    PIPEDRIVE_DEALS_CURSOR_KEY,
    PIPEDRIVE_PERSONS_CURSOR_KEY,
    PIPEDRIVE_ORGS_CURSOR_KEY,
    PIPEDRIVE_PRODUCTS_CURSOR_KEY,
    PIPEDRIVE_PERSON_LABELS_KEY,
]
