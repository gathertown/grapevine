"""Pydantic models for Intercom job configurations."""

from typing import Literal

from connectors.base.models import BackfillIngestConfig


class IntercomApiBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Root config that triggers all Intercom backfill jobs (conversations, help center, contacts, companies)."""

    source: Literal["intercom_api_backfill_root"] = "intercom_api_backfill_root"


class IntercomApiConversationsBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["intercom_api_conversations_backfill"] = "intercom_api_conversations_backfill"
    conversation_ids: list[str] | None = None
    per_page: int = 150  # Intercom max is 150
    order: Literal["asc", "desc"] = "desc"
    starting_after: str | None = None
    max_pages: int | None = None
    max_conversations: int | None = None


class IntercomApiHelpCenterBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["intercom_api_help_center_backfill"] = "intercom_api_help_center_backfill"
    article_ids: list[str] | None = None
    per_page: int = 150  # Intercom max is 150
    order: Literal["asc", "desc"] = "desc"
    starting_after: str | None = None
    max_pages: int | None = None
    max_articles: int | None = None


class IntercomApiContactsBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["intercom_api_contacts_backfill"] = "intercom_api_contacts_backfill"
    contact_ids: list[str] | None = None
    per_page: int = 150  # Intercom max is 150
    order: Literal["asc", "desc"] = "desc"
    starting_after: str | None = None
    max_pages: int | None = None
    max_contacts: int | None = None


class IntercomApiCompaniesBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["intercom_api_companies_backfill"] = "intercom_api_companies_backfill"
    company_ids: list[str] | None = None
    per_page: int = 50  # Intercom Companies API max is 50 (lower than other endpoints)
    order: Literal["asc", "desc"] = "desc"
    starting_after: str | None = None
    max_pages: int | None = None
    max_companies: int | None = None
