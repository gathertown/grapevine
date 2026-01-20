"""Pydantic models for Salesforce job configurations."""

from typing import Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig
from connectors.salesforce.salesforce_artifacts import SUPPORTED_SALESFORCE_OBJECTS


class SalesforceObjectBatch(BaseModel):
    """Metadata for a batch of Salesforce objects to process."""

    object_type: SUPPORTED_SALESFORCE_OBJECTS
    record_ids: list[str]


class SalesforceBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for discovering Salesforce objects."""

    source: Literal["salesforce_backfill_root"] = "salesforce_backfill_root"


class SalesforceBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for processing Salesforce object batches."""

    source: Literal["salesforce_backfill"] = "salesforce_backfill"
    object_batches: list[SalesforceObjectBatch]


class SalesforceObjectSyncConfig(BackfillIngestConfig, frozen=True):
    """Configuration for incremental Salesforce object sync."""

    source: Literal["salesforce_object_sync"] = "salesforce_object_sync"
    object_type: SUPPORTED_SALESFORCE_OBJECTS


# See more: https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/salesforce_change_data_capture.pdf
class SalesforceCDCEvent(BaseModel):
    """Salesforce Change Data Capture event data."""

    record_id: str
    object_type: SUPPORTED_SALESFORCE_OBJECTS
    change_event_header: dict[str, object]
    operation_type: Literal["INSERT", "UPDATE", "DELETE", "UNDELETE"]
    record_data: dict[str, object]
