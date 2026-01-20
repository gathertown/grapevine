"""Pydantic models for Attio job configurations."""

from datetime import datetime
from typing import Literal

from connectors.base.models import BackfillIngestConfig


class AttioBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Root config that triggers all Attio backfill jobs (companies, people, deals)."""

    source: Literal["attio_backfill_root"] = "attio_backfill_root"


class AttioCompanyBackfillConfig(BackfillIngestConfig, frozen=True):
    """Config for Attio company backfill batch job."""

    source: Literal["attio_company_backfill"] = "attio_company_backfill"
    record_ids: list[str]  # Required - batch of record IDs to process
    start_timestamp: datetime | None = None  # For rate-limited delayed processing


class AttioPersonBackfillConfig(BackfillIngestConfig, frozen=True):
    """Config for Attio person backfill batch job."""

    source: Literal["attio_person_backfill"] = "attio_person_backfill"
    record_ids: list[str]  # Required - batch of record IDs to process
    start_timestamp: datetime | None = None  # For rate-limited delayed processing


class AttioDealBackfillConfig(BackfillIngestConfig, frozen=True):
    """Config for Attio deal backfill batch job."""

    source: Literal["attio_deal_backfill"] = "attio_deal_backfill"
    record_ids: list[str]  # Required - batch of record IDs to process
    start_timestamp: datetime | None = None  # For rate-limited delayed processing
    include_notes: bool = True
    include_tasks: bool = True
