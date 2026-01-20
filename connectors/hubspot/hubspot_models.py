"""Pydantic models for HubSpot job configurations."""

from datetime import datetime
from typing import Literal

from connectors.base.models import BackfillIngestConfig


class HubSpotBackfillRootConfig(BackfillIngestConfig, frozen=True):
    source: Literal["hubspot_backfill_root"] = "hubspot_backfill_root"


class HubSpotCompanyBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["hubspot_company_backfill"] = "hubspot_company_backfill"
    start_date: datetime
    end_date: datetime


class HubSpotDealBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["hubspot_deal_backfill"] = "hubspot_deal_backfill"
    start_date: datetime
    end_date: datetime


class HubSpotTicketBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["hubspot_ticket_backfill"] = "hubspot_ticket_backfill"
    start_date: datetime
    end_date: datetime


class HubSpotContactBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["hubspot_contact_backfill"] = "hubspot_contact_backfill"
    start_date: datetime
    end_date: datetime


class HubSpotObjectSyncConfig(BackfillIngestConfig, frozen=True):
    source: Literal["hubspot_object_sync"] = "hubspot_object_sync"
    object_type: str
