"""
Ingest job worker entrypoint.

Processes ingest jobs from SQS queue.
"""

# Initialize New Relic agent before any other imports
import traceback
from pathlib import Path

import newrelic.agent

from connectors.asana import (
    AsanaFullBackfillConfig,
    AsanaFullBackfillExtractor,
    AsanaIncrBackfillConfig,
    AsanaIncrBackfillExtractor,
    AsanaPermissionsBackfillConfig,
    AsanaPermissionsBackfillExtractor,
)
from connectors.canva import (
    CanvaBackfillRootConfig,
    CanvaBackfillRootExtractor,
    CanvaDesignBackfillConfig,
    CanvaDesignBackfillExtractor,
    CanvaIncrementalBackfillConfig,
    CanvaIncrementalBackfillExtractor,
)
from connectors.clickup import (
    ClickupFullBackfillConfig,
    ClickupFullBackfillExtractor,
    ClickupIncrBackfillConfig,
    ClickupIncrBackfillExtractor,
    ClickupPermissionsBackfillConfig,
    ClickupPermissionsBackfillExtractor,
)
from connectors.figma import (
    FigmaBackfillRootConfig,
    FigmaBackfillRootExtractor,
    FigmaFileBackfillConfig,
    FigmaFileBackfillExtractor,
    FigmaIncrementalBackfillConfig,
    FigmaIncrementalBackfillExtractor,
    FigmaWebhookExtractor,
)
from connectors.fireflies import (
    FirefliesFullBackfillConfig,
    FirefliesFullBackfillExtractor,
    FirefliesIncrBackfillConfig,
    FirefliesIncrBackfillExtractor,
)
from connectors.monday import (
    MondayBackfillRootConfig,
    MondayBackfillRootExtractor,
    MondayIncrementalBackfillConfig,
    MondayIncrementalBackfillExtractor,
    MondayItemBackfillConfig,
    MondayItemBackfillExtractor,
)
from connectors.pipedrive.extractors import (
    PipedriveBackfillRootExtractor,
    PipedriveEntityBackfillExtractor,
    PipedriveIncrementalBackfillExtractor,
)
from connectors.pipedrive.pipedrive_models import (
    PipedriveBackfillEntityConfig,
    PipedriveBackfillRootConfig,
    PipedriveIncrementalBackfillConfig,
)
from connectors.posthog.extractors import (
    PostHogBackfillRootExtractor,
    PostHogIncrementalBackfillExtractor,
    PostHogProjectBackfillExtractor,
)
from connectors.posthog.posthog_models import (
    PostHogBackfillRootConfig,
    PostHogIncrementalBackfillConfig,
    PostHogProjectBackfillConfig,
)
from connectors.pylon.extractors.pylon_full_backfill_extractor import (
    PylonFullBackfillConfig,
    PylonFullBackfillExtractor,
)
from connectors.pylon.extractors.pylon_incremental_backfill_extractor import (
    PylonIncrementalBackfillConfig,
    PylonIncrementalBackfillExtractor,
)
from connectors.teamwork.extractors import (
    TeamworkBackfillRootExtractor,
    TeamworkIncrementalBackfillExtractor,
    TeamworkTaskBackfillExtractor,
)
from connectors.teamwork.teamwork_backfill_config import (
    TeamworkBackfillRootConfig,
    TeamworkIncrementalBackfillConfig,
    TeamworkTaskBackfillConfig,
)
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.config import get_config_value, get_grapevine_environment
from src.utils.rate_limiter import RateLimitedError
from src.utils.tenant_deletion import is_tenant_deleted

# Get the directory containing this file and environment
current_dir = Path(__file__).parent
config_path = current_dir / "newrelic_ingest_worker.toml"
grapevine_env = get_grapevine_environment()
# Initialize New Relic with the ingest worker-specific TOML config and environment
newrelic.agent.initialize(str(config_path), environment=grapevine_env)

import asyncio
import json
import time
from typing import Any
from uuid import uuid4

from connectors.attio import (
    AttioBackfillRootConfig,
    AttioBackfillRootExtractor,
    AttioCompanyBackfillConfig,
    AttioCompanyBackfillExtractor,
    AttioDealBackfillConfig,
    AttioDealBackfillExtractor,
    AttioPersonBackfillConfig,
    AttioPersonBackfillExtractor,
    AttioWebhookExtractor,
)
from connectors.base import BaseExtractor
from connectors.base.document_source import DocumentSource
from connectors.base.models import BackfillIngestConfig
from connectors.confluence import (
    ConfluenceApiBackfillExtractor,
    ConfluenceApiBackfillRootExtractor,
    ConfluenceWebhookExtractor,
)
from connectors.confluence.confluence_models import (
    ConfluenceApiBackfillConfig,
    ConfluenceApiBackfillRootConfig,
)
from connectors.custom import CustomCollectionExtractor
from connectors.custom_data import CustomDataIngestConfig, CustomDataIngestExtractor
from connectors.gather import (
    GatherApiBackfillExtractor,
    GatherApiBackfillRootExtractor,
    GatherWebhookExtractor,
)
from connectors.gather.gather_models import (
    GatherApiBackfillConfig,
    GatherApiBackfillRootConfig,
)
from connectors.github import (
    GitHubFileBackfillExtractor,
    GitHubFileBackfillRootExtractor,
    GitHubPRBackfillExtractor,
    GitHubPRBackfillRepoExtractor,
    GitHubPRBackfillRootExtractor,
    GitHubWebhookExtractor,
)
from connectors.github.github_models import (
    GitHubFileBackfillConfig,
    GitHubFileBackfillRootConfig,
    GitHubPRBackfillConfig,
    GitHubPRBackfillRepoConfig,
    GitHubPRBackfillRootConfig,
)
from connectors.gitlab import (
    GitLabBackfillRootExtractor,
    GitLabFileBackfillExtractor,
    GitLabFileBackfillProjectExtractor,
    GitLabFileIncrBackfillProjectExtractor,
    GitLabIncrBackfillRootExtractor,
    GitLabMRBackfillExtractor,
    GitLabMRBackfillProjectExtractor,
    GitLabMRIncrBackfillProjectExtractor,
)
from connectors.gitlab.gitlab_models import (
    GitLabBackfillRootConfig,
    GitLabFileBackfillConfig,
    GitLabFileBackfillProjectConfig,
    GitLabFileIncrBackfillProjectConfig,
    GitLabIncrBackfillConfig,
    GitLabMRBackfillConfig,
    GitLabMRBackfillProjectConfig,
    GitLabMRIncrBackfillProjectConfig,
)
from connectors.gmail import (
    GoogleEmailDiscoveryExtractor,
    GoogleEmailUserExtractor,
    GoogleEmailWebhookExtractor,
    GoogleEmailWebhookRefreshExtractor,
)
from connectors.gmail.gmail_models import (
    GoogleEmailDiscoveryConfig,
    GoogleEmailUserConfig,
    GoogleEmailWebhookRefreshConfig,
)
from connectors.gong import (
    GongCallBackfillExtractor,
    GongCallBackfillRootExtractor,
    GongWebhookExtractor,
)
from connectors.gong.gong_models import (
    GongCallBackfillConfig,
    GongCallBackfillRootConfig,
)
from connectors.google_drive import (
    GoogleDriveDiscoveryExtractor,
    GoogleDriveSharedDriveExtractor,
    GoogleDriveUserDriveExtractor,
    GoogleDriveWebhookExtractor,
)
from connectors.google_drive.google_drive_models import (
    GoogleDriveDiscoveryConfig,
    GoogleDriveSharedDriveConfig,
    GoogleDriveUserDriveConfig,
    GoogleDriveWebhookRefreshConfig,
)
from connectors.hubspot import (
    HubSpotBackfillRootExtractor,
    HubSpotCompanyBackfillExtractor,
    HubSpotContactBackfillExtractor,
    HubSpotDealBackfillExtractor,
    HubSpotObjectSyncExtractor,
    HubSpotTicketBackfillExtractor,
    HubSpotWebhookExtractor,
)
from connectors.hubspot.hubspot_models import (
    HubSpotBackfillRootConfig,
    HubSpotCompanyBackfillConfig,
    HubSpotContactBackfillConfig,
    HubSpotDealBackfillConfig,
    HubSpotObjectSyncConfig,
    HubSpotTicketBackfillConfig,
)
from connectors.intercom import (
    IntercomApiBackfillRootConfig,
    IntercomApiCompaniesBackfillConfig,
    IntercomApiContactsBackfillConfig,
    IntercomApiConversationsBackfillConfig,
    IntercomApiHelpCenterBackfillConfig,
    IntercomBackfillRootExtractor,
    IntercomCompaniesBackfillExtractor,
    IntercomContactsBackfillExtractor,
    IntercomConversationsBackfillExtractor,
    IntercomHelpCenterBackfillExtractor,
)
from connectors.jira import (
    JiraApiBackfillExtractor,
    JiraApiBackfillRootExtractor,
    JiraWebhookExtractor,
)
from connectors.jira.jira_models import (
    JiraApiBackfillConfig,
    JiraApiBackfillRootConfig,
)
from connectors.linear import (
    LinearApiBackfillExtractor,
    LinearApiBackfillRootExtractor,
    LinearWebhookExtractor,
)
from connectors.linear.linear_models import (
    LinearApiBackfillConfig,
    LinearApiBackfillRootConfig,
)
from connectors.notion import (
    NotionApiBackfillExtractor,
    NotionApiBackfillRootExtractor,
    NotionUserRefreshExtractor,
    NotionWebhookExtractor,
)
from connectors.notion.notion_models import (
    NotionApiBackfillConfig,
    NotionApiBackfillRootConfig,
    NotionUserRefreshConfig,
)
from connectors.salesforce import (
    SalesforceBackfillExtractor,
    SalesforceBackfillRootExtractor,
    SalesforceCDCExtractor,
    SalesforceObjectSyncExtractor,
)
from connectors.salesforce.salesforce_models import (
    SalesforceBackfillConfig,
    SalesforceBackfillRootConfig,
    SalesforceObjectSyncConfig,
)
from connectors.slack import (
    SlackExportBackfillExtractor,
    SlackExportBackfillRootExtractor,
    SlackWebhookExtractor,
)
from connectors.slack.slack_models import (
    SlackExportBackfillConfig,
    SlackExportBackfillRootConfig,
)
from connectors.trello import (
    TrelloApiBackfillExtractor,
    TrelloApiBackfillRootExtractor,
    TrelloIncrementalSyncExtractor,
    TrelloWebhookExtractor,
)
from connectors.trello.trello_models import (
    TrelloApiBackfillConfig,
    TrelloApiBackfillRootConfig,
    TrelloIncrementalSyncConfig,
)
from connectors.zendesk import (
    ZendeskFullBackfillConfig,
    ZendeskFullBackfillExtractor,
    ZendeskIncrementalBackfillConfig,
    ZendeskIncrementalBackfillExtractor,
    ZendeskWindowBackfillConfig,
    ZendeskWindowBackfillExtractor,
    ZendeskWindowWithNextBackfillConfig,
    ZendeskWindowWithNextBackfillExtractor,
)
from src.clients.sqs import SQSClient
from src.ingest.full_reindex import FullReindexExtractor
from src.ingest.tenant_data_deletion import TenantDataDeletionExtractor
from src.jobs.base_worker import BaseJobWorker
from src.jobs.models import (
    IndexJobMessage,
    ReindexJobMessage,
    TenantDataDeletionMessage,
    WebhookIngestJobMessage,
)
from src.jobs.sqs_job_processor import SQSJobProcessor, SQSMessageMetadata
from src.utils.job_metrics import record_job_completion
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


def log_job_complete() -> None:
    """Log successful completion of an ingest job with consistent format."""
    logger.info("Successfully processed ingest job")


class IngestJobWorker(BaseJobWorker):
    """Worker for processing all types of ingest jobs from SQS."""

    def __init__(self, sqs_client: SQSClient, http_port: int | None = None):
        super().__init__(http_port)

        self.sqs_client = sqs_client

        # Webhook extractors: source_type -> extractor
        # See also: WebhookIngestJobMessage
        self.webhook_extractors: dict[str, BaseExtractor] = {
            "slack": SlackWebhookExtractor(),
            "linear": LinearWebhookExtractor(self.ssm_client, self.sqs_client),
            "notion": NotionWebhookExtractor(self.ssm_client, self.sqs_client),
            "github": GitHubWebhookExtractor(self.ssm_client),
            "confluence": ConfluenceWebhookExtractor(self.ssm_client, self.sqs_client),
            "google_drive": GoogleDriveWebhookExtractor(self.ssm_client),
            "google_email": GoogleEmailWebhookExtractor(self.ssm_client),
            "jira": JiraWebhookExtractor(self.ssm_client, self.sqs_client),
            "salesforce": SalesforceCDCExtractor(self.ssm_client),
            "hubspot": HubSpotWebhookExtractor(self.ssm_client),
            "gather": GatherWebhookExtractor(self.ssm_client, self.sqs_client),
            "custom": CustomCollectionExtractor(),
            "gong": GongWebhookExtractor(),
            "trello": TrelloWebhookExtractor(self.ssm_client, self.sqs_client),
            "attio": AttioWebhookExtractor(self.ssm_client),
            "figma": FigmaWebhookExtractor(self.ssm_client),
        }

        # Backfill extractors: source -> extractor
        # See also: BackfillIngestJobMessage
        self.backfill_extractors: dict[str, BaseExtractor] = {
            "linear_api_backfill_root": LinearApiBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "linear_api_backfill": LinearApiBackfillExtractor(self.ssm_client, self.sqs_client),
            "github_pr_backfill_root": GitHubPRBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "github_pr_backfill_repo": GitHubPRBackfillRepoExtractor(
                self.ssm_client, self.sqs_client
            ),
            "github_pr_backfill": GitHubPRBackfillExtractor(self.ssm_client),
            "github_file_backfill_root": GitHubFileBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "github_file_backfill": GitHubFileBackfillExtractor(self.ssm_client),
            "google_drive_discovery": GoogleDriveDiscoveryExtractor(
                self.ssm_client, self.sqs_client
            ),
            "google_email_discovery": GoogleEmailDiscoveryExtractor(
                self.ssm_client, self.sqs_client
            ),
            "google_email_user": GoogleEmailUserExtractor(),
            "google_email_webhook_refresh": GoogleEmailWebhookRefreshExtractor(),
            "google_drive_user_drive": GoogleDriveUserDriveExtractor(),
            "google_drive_shared_drive": GoogleDriveSharedDriveExtractor(),
            "slack_export_backfill_root": SlackExportBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "slack_export_backfill": SlackExportBackfillExtractor(),
            "notion_api_backfill_root": NotionApiBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "notion_api_backfill": NotionApiBackfillExtractor(self.ssm_client, self.sqs_client),
            "notion_user_refresh": NotionUserRefreshExtractor(self.ssm_client, self.sqs_client),
            "salesforce_backfill_root": SalesforceBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "salesforce_backfill": SalesforceBackfillExtractor(self.ssm_client),
            "salesforce_object_sync": SalesforceObjectSyncExtractor(self.ssm_client),
            "jira_api_backfill_root": JiraApiBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "jira_api_backfill": JiraApiBackfillExtractor(self.ssm_client, self.sqs_client),
            "confluence_api_backfill_root": ConfluenceApiBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "confluence_api_backfill": ConfluenceApiBackfillExtractor(
                self.ssm_client, self.sqs_client
            ),
            "hubspot_backfill_root": HubSpotBackfillRootExtractor(self.ssm_client, self.sqs_client),
            "hubspot_company_backfill": HubSpotCompanyBackfillExtractor(self.ssm_client),
            "hubspot_contact_backfill": HubSpotContactBackfillExtractor(self.ssm_client),
            "hubspot_deal_backfill": HubSpotDealBackfillExtractor(self.ssm_client),
            "hubspot_ticket_backfill": HubSpotTicketBackfillExtractor(self.ssm_client),
            "hubspot_object_sync": HubSpotObjectSyncExtractor(self.ssm_client),
            "gong_call_backfill_root": GongCallBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "gong_call_backfill": GongCallBackfillExtractor(self.ssm_client),
            "gather_api_backfill_root": GatherApiBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "gather_api_backfill": GatherApiBackfillExtractor(self.ssm_client, self.sqs_client),
            "trello_api_backfill_root": TrelloApiBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "trello_api_backfill": TrelloApiBackfillExtractor(self.ssm_client, self.sqs_client),
            "trello_incremental_sync": TrelloIncrementalSyncExtractor(
                self.ssm_client, self.sqs_client
            ),
            "zendesk_full_backfill": ZendeskFullBackfillExtractor(self.ssm_client, self.sqs_client),
            "zendesk_incremental_backfill": ZendeskIncrementalBackfillExtractor(
                self.ssm_client, self.sqs_client
            ),
            "zendesk_window_backfill": ZendeskWindowBackfillExtractor(
                self.ssm_client, self.sqs_client
            ),
            "zendesk_window_with_next_backfill": ZendeskWindowWithNextBackfillExtractor(
                self.ssm_client, self.sqs_client
            ),
            "asana_full_backfill": AsanaFullBackfillExtractor(self.ssm_client, self.sqs_client),
            "asana_incr_backfill": AsanaIncrBackfillExtractor(self.ssm_client, self.sqs_client),
            "asana_permissions_backfill": AsanaPermissionsBackfillExtractor(self.ssm_client),
            "intercom_api_backfill_root": IntercomBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            # Child extractors don't need sqs_client - only root extractor sends jobs to SQS
            "intercom_api_conversations_backfill": IntercomConversationsBackfillExtractor(
                self.ssm_client
            ),
            "intercom_api_help_center_backfill": IntercomHelpCenterBackfillExtractor(
                self.ssm_client
            ),
            "intercom_api_contacts_backfill": IntercomContactsBackfillExtractor(self.ssm_client),
            "intercom_api_companies_backfill": IntercomCompaniesBackfillExtractor(self.ssm_client),
            # Attio extractors
            "attio_backfill_root": AttioBackfillRootExtractor(self.ssm_client, self.sqs_client),
            "attio_company_backfill": AttioCompanyBackfillExtractor(self.ssm_client),
            "attio_person_backfill": AttioPersonBackfillExtractor(self.ssm_client),
            "attio_deal_backfill": AttioDealBackfillExtractor(self.ssm_client),
            # Fireflies extractors
            "fireflies_full_backfill": FirefliesFullBackfillExtractor(
                self.ssm_client, self.sqs_client
            ),
            "fireflies_incr_backfill": FirefliesIncrBackfillExtractor(self.ssm_client),
            # GitLab extractors
            "gitlab_backfill_root": GitLabBackfillRootExtractor(self.ssm_client, self.sqs_client),
            "gitlab_mr_backfill_project": GitLabMRBackfillProjectExtractor(
                self.ssm_client, self.sqs_client
            ),
            "gitlab_mr_backfill": GitLabMRBackfillExtractor(self.ssm_client),
            "gitlab_file_backfill_project": GitLabFileBackfillProjectExtractor(
                self.ssm_client, self.sqs_client
            ),
            "gitlab_file_backfill": GitLabFileBackfillExtractor(self.ssm_client),
            # GitLab incremental extractors
            "gitlab_incr_backfill": GitLabIncrBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "gitlab_mr_incr_backfill_project": GitLabMRIncrBackfillProjectExtractor(
                self.ssm_client
            ),
            "gitlab_file_incr_backfill_project": GitLabFileIncrBackfillProjectExtractor(
                self.ssm_client
            ),
            # Pylon extractors
            "pylon_full_backfill": PylonFullBackfillExtractor(self.ssm_client, self.sqs_client),
            "pylon_incremental_backfill": PylonIncrementalBackfillExtractor(
                self.ssm_client, self.sqs_client
            ),
            # Custom Data extractor (documents passed directly in payload)
            "custom_data_ingest": CustomDataIngestExtractor(),
            # ClickUp extractors
            "clickup_full_backfill": ClickupFullBackfillExtractor(self.ssm_client, self.sqs_client),
            "clickup_incr_backfill": ClickupIncrBackfillExtractor(self.ssm_client),
            "clickup_permissions_backfill": ClickupPermissionsBackfillExtractor(self.ssm_client),
            # Monday.com extractors
            "monday_backfill_root": MondayBackfillRootExtractor(self.ssm_client, self.sqs_client),
            "monday_item_backfill": MondayItemBackfillExtractor(self.ssm_client, self.sqs_client),
            "monday_incremental_backfill": MondayIncrementalBackfillExtractor(self.ssm_client),
            # Pipedrive extractors
            "pipedrive_backfill_root": PipedriveBackfillRootExtractor(
                self.ssm_client, self.sqs_client
            ),
            "pipedrive_entity_backfill": PipedriveEntityBackfillExtractor(
                self.ssm_client, self.sqs_client
            ),
            "pipedrive_incremental_backfill": PipedriveIncrementalBackfillExtractor(
                self.ssm_client
            ),
            # Figma extractors
            "figma_backfill_root": FigmaBackfillRootExtractor(self.sqs_client),
            "figma_file_backfill": FigmaFileBackfillExtractor(),
            "figma_incremental_backfill": FigmaIncrementalBackfillExtractor(),
            # PostHog extractors
            "posthog_backfill_root": PostHogBackfillRootExtractor(self.sqs_client),
            "posthog_project_backfill": PostHogProjectBackfillExtractor(),
            "posthog_incremental_backfill": PostHogIncrementalBackfillExtractor(self.ssm_client),
            # Canva extractors
            "canva_backfill_root": CanvaBackfillRootExtractor(self.sqs_client),
            "canva_design_backfill": CanvaDesignBackfillExtractor(),
            "canva_incremental_backfill": CanvaIncrementalBackfillExtractor(),
            # Teamwork extractors
            "teamwork_backfill_root": TeamworkBackfillRootExtractor(
                self.sqs_client, self.ssm_client
            ),
            "teamwork_task_backfill": TeamworkTaskBackfillExtractor(self.ssm_client),
            "teamwork_incremental_backfill": TeamworkIncrementalBackfillExtractor(self.ssm_client),
        }

        # Reindex extractor for full re-indexing operations
        self.full_reindex_extractor = FullReindexExtractor()

        # Tenant data deletion extractor
        self.tenant_data_deletion_extractor = TenantDataDeletionExtractor()

    def _get_default_http_port(self) -> int:
        """Get the default HTTP server port for ingest worker."""
        return int(get_config_value("INGEST_HTTP_PORT", "8080"))

    def _register_custom_routes(self, app) -> None:
        """Register ingest worker specific routes."""
        pass

    async def process_webhook(self, webhook_message: WebhookIngestJobMessage) -> None:
        """Process a webhook message using the appropriate extractor.

        Args:
            webhook_message: The processed webhook from the gatekeeper
        """
        source_type = webhook_message.source_type
        extractor = self.webhook_extractors.get(source_type)

        if not extractor:
            available_sources = ", ".join(self.webhook_extractors.keys())
            raise ValueError(
                f"No webhook extractor found for source: {source_type}. Available: {available_sources}"
            )

        logger.info(
            f"Processing webhook for tenant {webhook_message.tenant_id}, source: {source_type}"
        )

        async with self.tenant_db_manager.acquire_pool(webhook_message.tenant_id) as tenant_db_pool:
            # Generate a job ID for this webhook processing
            job_id = str(uuid4())

            # Parse webhook body as JSON if it's a string
            webhook_body = webhook_message.webhook_body
            if isinstance(webhook_body, str):
                webhook_body = {} if not webhook_body.strip() else json.loads(webhook_body)

            # Create config in the format expected by webhook extractors
            config_data = {"body": webhook_body, "tenant_id": webhook_message.tenant_id}

            # GitHub, Google Email, Google Drive, Gather webhooks need headers
            if source_type in ["github", "google_drive", "google_email", "gather"]:
                config_data["headers"] = webhook_message.webhook_headers

            parsed_config = extractor.parse_config(config_data)

            # Process the job using tenant database pool
            await extractor.process_job(
                job_id, parsed_config, tenant_db_pool, self._trigger_indexing
            )

            log_job_complete()

    async def process_backfill(self, backfill_message: BackfillIngestConfig) -> None:
        """Process a backfill message using the appropriate extractor.

        Args:
            backfill_message: The backfill config message
        """
        source = backfill_message.source
        extractor = self.backfill_extractors.get(source)

        if not extractor:
            available_sources = ", ".join(self.backfill_extractors.keys())
            logger.error(f"No backfill extractor found for source {source}")
            raise ValueError(
                f"No backfill extractor found for source: {source}. Available: {available_sources}"
            )

        async with self.tenant_db_manager.acquire_pool(
            backfill_message.tenant_id
        ) as tenant_db_pool:
            # Generate a job ID for this backfill processing
            job_id = str(uuid4())
            with LogContext(job_id=job_id):
                # Process the job using tenant database pool
                # The backfill_message is already the config object we need
                try:
                    await extractor.process_job(
                        job_id, backfill_message, tenant_db_pool, self._trigger_indexing
                    )

                    log_job_complete()
                except* ExtendVisibilityException:
                    raise
                except* Exception:
                    logger.error(
                        f"Failed to process backfill job {job_id} for tenant {backfill_message.tenant_id}, source: {source}"
                    )
                    raise

    async def process_reindex(self, reindex_message: ReindexJobMessage) -> None:
        """Process a reindex message using the full reindex extractor.

        Args:
            reindex_message: The reindex config message
        """
        tenant_id = reindex_message.tenant_id

        async with self.tenant_db_manager.acquire_pool(
            tenant_id, readonly=True
        ) as readonly_tenant_db_pool:
            # Generate a job ID for this reindex processing
            job_id = str(uuid4())
            with LogContext(job_id=job_id):
                # Process the job using the singleton reindex extractor
                await self.full_reindex_extractor.process_job(
                    job_id, reindex_message, readonly_tenant_db_pool, self._trigger_indexing
                )

                log_job_complete()

    async def process_tenant_data_deletion(
        self, deletion_message: TenantDataDeletionMessage
    ) -> None:
        """Process a tenant data deletion message."""
        tenant_id = deletion_message.tenant_id

        async with self.tenant_db_manager.acquire_pool(tenant_id) as tenant_db_pool:
            # Generate a job ID for this deletion processing
            job_id = str(uuid4())
            with LogContext(job_id=job_id):
                # Process the deletion job using the tenant data deletion extractor
                await self.tenant_data_deletion_extractor.process_job(
                    job_id, deletion_message, tenant_db_pool, self._trigger_indexing
                )

                log_job_complete()

    async def _trigger_indexing(
        self,
        entity_ids: list[str],
        source: DocumentSource,
        tenant_id: str,
        backfill_id: str | None = None,
        suppress_notification: bool = False,
    ) -> None:
        """Generic indexing trigger that sends messages to the index jobs queue.

        Args:
            entity_ids: List of entity IDs to index
            source: DocumentSource enum value
            tenant_id: Tenant ID for the indexing job
            backfill_id: Optional backfill ID for tracking backfill completion
            suppress_notification: If True, suppress backfill completion notifications
        """
        if not entity_ids:
            logger.warning("No entity IDs provided for indexing")
            return

        # Create the index job message
        index_message = IndexJobMessage(
            entity_ids=entity_ids,
            source=source,
            tenant_id=tenant_id,
            backfill_id=backfill_id,
            suppress_notification=suppress_notification,
        )

        # Send message to SQS
        success = await self.sqs_client.send_index_message(index_message=index_message)

        if success:
            logger.info(
                f"Triggered indexing for {len(entity_ids)} {source.value} entities (backfill_id: {backfill_id})"
            )
        else:
            logger.error(
                f"Failed to trigger indexing for {len(entity_ids)} {source.value} entities"
            )


# Global worker instance with shared SQS client
sqs_client = SQSClient()
worker = IngestJobWorker(sqs_client)


@newrelic.agent.background_task(name="IngestWorker/process_ingest_job")
async def process_ingest_job(
    message_data: dict[str, Any], sqs_metadata: SQSMessageMetadata
) -> None:
    """Process an ingest job message.

    Handles both webhook and backfill ingest job messages.

    Args:
        message_data: Parsed message data from SQS
        sqs_metadata: SQS message metadata
    """
    start_time = time.perf_counter()

    # Determine message type from raw data first
    message_type = message_data.get("message_type")
    if not message_type:
        logger.error("Message missing message_type field", raw_message=json.dumps(message_data))
        raise ValueError("Message missing message_type field")

    tenant_id = message_data.get("tenant_id")
    source = message_data.get("source_type") or message_data.get("source")

    # Add New Relic attributes
    newrelic.agent.add_custom_attribute("ingest.message_type", message_type)
    newrelic.agent.add_custom_attribute("tenant_id", tenant_id)
    newrelic.agent.add_custom_attribute("ingest.source", source)
    if sqs_metadata["message_id"]:
        newrelic.agent.add_custom_attribute("sqs.message_id", sqs_metadata["message_id"])
    if sqs_metadata["approximate_receive_count"]:
        newrelic.agent.add_custom_attribute(
            "sqs.receive_count", sqs_metadata["approximate_receive_count"]
        )

    try:
        with LogContext(message_type=message_type, tenant_id=tenant_id, source=source):
            # Check if tenant is deleted before processing
            # Exception: Allow tenant_data_deletion messages to process even if tenant is deleted
            if tenant_id and message_type != "tenant_data_deletion":
                control_db_pool = await worker.tenant_db_manager.get_control_db()
                if await is_tenant_deleted(control_db_pool, tenant_id):
                    logger.warning(f"Skipping ingest job for deleted tenant {tenant_id}")
                    return

            if message_type == "webhook":
                # Parse as webhook message
                webhook_message = WebhookIngestJobMessage.model_validate(message_data)
                logger.info(
                    f"Processing webhook ingest job from {webhook_message.tenant_id} with source {webhook_message.source_type}, length {len(webhook_message.webhook_body)} chars"
                )

                await worker.process_webhook(webhook_message)

            elif message_type == "backfill":
                # For backfill messages, we need to determine the specific config type
                source = message_data.get("source")
                if not source:
                    logger.error(
                        "Backfill message missing source field",
                        raw_message=json.dumps(message_data),
                    )
                    raise ValueError("Backfill message missing source field")

                # Parse based on the source type
                # TODO @vic make this a switch so it's enforceable with types
                backfill_message: BackfillIngestConfig
                if source == "linear_api_backfill_root":
                    backfill_message = LinearApiBackfillRootConfig.model_validate(message_data)
                elif source == "linear_api_backfill":
                    backfill_message = LinearApiBackfillConfig.model_validate(message_data)
                elif source == "github_pr_backfill_root":
                    backfill_message = GitHubPRBackfillRootConfig.model_validate(message_data)
                elif source == "github_pr_backfill_repo":
                    backfill_message = GitHubPRBackfillRepoConfig.model_validate(message_data)
                elif source == "github_pr_backfill":
                    backfill_message = GitHubPRBackfillConfig.model_validate(message_data)
                elif source == "github_file_backfill_root":
                    backfill_message = GitHubFileBackfillRootConfig.model_validate(message_data)
                elif source == "github_file_backfill":
                    backfill_message = GitHubFileBackfillConfig.model_validate(message_data)
                elif source == "gong_call_backfill_root":
                    backfill_message = GongCallBackfillRootConfig.model_validate(message_data)
                elif source == "gong_call_backfill":
                    backfill_message = GongCallBackfillConfig.model_validate(message_data)
                elif source == "google_drive_discovery":
                    backfill_message = GoogleDriveDiscoveryConfig.model_validate(message_data)
                elif source == "google_email_discovery":
                    backfill_message = GoogleEmailDiscoveryConfig.model_validate(message_data)
                elif source == "google_email_webhook_refresh":
                    backfill_message = GoogleEmailWebhookRefreshConfig.model_validate(message_data)
                elif source == "google_email_user":
                    backfill_message = GoogleEmailUserConfig.model_validate(message_data)
                elif source == "google_drive_webhook_refresh":
                    backfill_message = GoogleDriveWebhookRefreshConfig.model_validate(message_data)
                elif source == "google_drive_user_drive":
                    backfill_message = GoogleDriveUserDriveConfig.model_validate(message_data)
                elif source == "google_drive_shared_drive":
                    backfill_message = GoogleDriveSharedDriveConfig.model_validate(message_data)
                elif source == "notion_api_backfill_root":
                    backfill_message = NotionApiBackfillRootConfig.model_validate(message_data)
                elif source == "notion_api_backfill":
                    backfill_message = NotionApiBackfillConfig.model_validate(message_data)
                elif source == "notion_user_refresh":
                    backfill_message = NotionUserRefreshConfig.model_validate(message_data)
                elif source == "slack_export_backfill_root":
                    backfill_message = SlackExportBackfillRootConfig.model_validate(message_data)
                elif source == "slack_export_backfill":
                    backfill_message = SlackExportBackfillConfig.model_validate(message_data)
                elif source == "salesforce_backfill_root":
                    backfill_message = SalesforceBackfillRootConfig.model_validate(message_data)
                elif source == "salesforce_backfill":
                    backfill_message = SalesforceBackfillConfig.model_validate(message_data)
                elif source == "salesforce_object_sync":
                    backfill_message = SalesforceObjectSyncConfig.model_validate(message_data)
                elif source == "jira_api_backfill_root":
                    backfill_message = JiraApiBackfillRootConfig.model_validate(message_data)
                elif source == "jira_api_backfill":
                    backfill_message = JiraApiBackfillConfig.model_validate(message_data)
                elif source == "confluence_api_backfill_root":
                    backfill_message = ConfluenceApiBackfillRootConfig.model_validate(message_data)
                elif source == "confluence_api_backfill":
                    backfill_message = ConfluenceApiBackfillConfig.model_validate(message_data)
                elif source == "hubspot_backfill_root":
                    backfill_message = HubSpotBackfillRootConfig.model_validate(message_data)
                elif source == "hubspot_company_backfill":
                    backfill_message = HubSpotCompanyBackfillConfig.model_validate(message_data)
                elif source == "hubspot_contact_backfill":
                    backfill_message = HubSpotContactBackfillConfig.model_validate(message_data)
                elif source == "hubspot_deal_backfill":
                    backfill_message = HubSpotDealBackfillConfig.model_validate(message_data)
                elif source == "hubspot_ticket_backfill":
                    backfill_message = HubSpotTicketBackfillConfig.model_validate(message_data)
                elif source == "hubspot_object_sync":
                    backfill_message = HubSpotObjectSyncConfig.model_validate(message_data)
                elif source == "gather_api_backfill_root":
                    backfill_message = GatherApiBackfillRootConfig.model_validate(message_data)
                elif source == "gather_api_backfill":
                    backfill_message = GatherApiBackfillConfig.model_validate(message_data)
                elif source == "trello_api_backfill_root":
                    backfill_message = TrelloApiBackfillRootConfig.model_validate(message_data)
                elif source == "trello_api_backfill":
                    backfill_message = TrelloApiBackfillConfig.model_validate(message_data)
                elif source == "trello_incremental_sync":
                    backfill_message = TrelloIncrementalSyncConfig.model_validate(message_data)
                elif source == "zendesk_full_backfill":
                    backfill_message = ZendeskFullBackfillConfig.model_validate(message_data)
                elif source == "zendesk_incremental_backfill":
                    backfill_message = ZendeskIncrementalBackfillConfig.model_validate(message_data)
                elif source == "zendesk_window_backfill":
                    backfill_message = ZendeskWindowBackfillConfig.model_validate(message_data)
                elif source == "zendesk_window_with_next_backfill":
                    backfill_message = ZendeskWindowWithNextBackfillConfig.model_validate(
                        message_data
                    )
                elif source == "asana_full_backfill":
                    backfill_message = AsanaFullBackfillConfig.model_validate(message_data)
                elif source == "asana_incr_backfill":
                    backfill_message = AsanaIncrBackfillConfig.model_validate(message_data)
                elif source == "asana_permissions_backfill":
                    backfill_message = AsanaPermissionsBackfillConfig.model_validate(message_data)
                elif source == "intercom_api_backfill_root":
                    backfill_message = IntercomApiBackfillRootConfig.model_validate(message_data)
                elif source == "intercom_api_conversations_backfill":
                    backfill_message = IntercomApiConversationsBackfillConfig.model_validate(
                        message_data
                    )
                elif source == "intercom_api_help_center_backfill":
                    backfill_message = IntercomApiHelpCenterBackfillConfig.model_validate(
                        message_data
                    )
                elif source == "intercom_api_contacts_backfill":
                    backfill_message = IntercomApiContactsBackfillConfig.model_validate(
                        message_data
                    )
                elif source == "intercom_api_companies_backfill":
                    backfill_message = IntercomApiCompaniesBackfillConfig.model_validate(
                        message_data
                    )
                # Attio sources
                elif source == "attio_backfill_root":
                    backfill_message = AttioBackfillRootConfig.model_validate(message_data)
                elif source == "attio_company_backfill":
                    backfill_message = AttioCompanyBackfillConfig.model_validate(message_data)
                elif source == "attio_person_backfill":
                    backfill_message = AttioPersonBackfillConfig.model_validate(message_data)
                elif source == "attio_deal_backfill":
                    backfill_message = AttioDealBackfillConfig.model_validate(message_data)

                elif source == "fireflies_full_backfill":
                    backfill_message = FirefliesFullBackfillConfig.model_validate(message_data)
                elif source == "fireflies_incr_backfill":
                    backfill_message = FirefliesIncrBackfillConfig.model_validate(message_data)

                # GitLab sources
                elif source == "gitlab_backfill_root":
                    backfill_message = GitLabBackfillRootConfig.model_validate(message_data)
                elif source == "gitlab_mr_backfill_project":
                    backfill_message = GitLabMRBackfillProjectConfig.model_validate(message_data)
                elif source == "gitlab_mr_backfill":
                    backfill_message = GitLabMRBackfillConfig.model_validate(message_data)
                elif source == "gitlab_file_backfill_project":
                    backfill_message = GitLabFileBackfillProjectConfig.model_validate(message_data)
                elif source == "gitlab_file_backfill":
                    backfill_message = GitLabFileBackfillConfig.model_validate(message_data)
                # GitLab incremental sources
                elif source == "gitlab_incr_backfill":
                    backfill_message = GitLabIncrBackfillConfig.model_validate(message_data)
                elif source == "gitlab_mr_incr_backfill_project":
                    backfill_message = GitLabMRIncrBackfillProjectConfig.model_validate(
                        message_data
                    )
                elif source == "gitlab_file_incr_backfill_project":
                    backfill_message = GitLabFileIncrBackfillProjectConfig.model_validate(
                        message_data
                    )

                # Pylon sources
                elif source == "pylon_full_backfill":
                    backfill_message = PylonFullBackfillConfig.model_validate(message_data)
                elif source == "pylon_incremental_backfill":
                    backfill_message = PylonIncrementalBackfillConfig.model_validate(message_data)

                # ClickUp
                elif source == "clickup_full_backfill":
                    backfill_message = ClickupFullBackfillConfig.model_validate(message_data)
                elif source == "clickup_incr_backfill":
                    backfill_message = ClickupIncrBackfillConfig.model_validate(message_data)
                elif source == "clickup_permissions_backfill":
                    backfill_message = ClickupPermissionsBackfillConfig.model_validate(message_data)

                elif source == "custom_data_ingest":
                    backfill_message = CustomDataIngestConfig.model_validate(message_data)

                # Monday.com
                elif source == "monday_backfill_root":
                    backfill_message = MondayBackfillRootConfig.model_validate(message_data)
                elif source == "monday_item_backfill":
                    backfill_message = MondayItemBackfillConfig.model_validate(message_data)
                elif source == "monday_incremental_backfill":
                    backfill_message = MondayIncrementalBackfillConfig.model_validate(message_data)

                # Pipedrive
                elif source == "pipedrive_backfill_root":
                    backfill_message = PipedriveBackfillRootConfig.model_validate(message_data)
                elif source == "pipedrive_entity_backfill":
                    backfill_message = PipedriveBackfillEntityConfig.model_validate(message_data)
                elif source == "pipedrive_incremental_backfill":
                    backfill_message = PipedriveIncrementalBackfillConfig.model_validate(
                        message_data
                    )

                # Figma
                elif source == "figma_backfill_root":
                    backfill_message = FigmaBackfillRootConfig.model_validate(message_data)
                elif source == "figma_file_backfill":
                    backfill_message = FigmaFileBackfillConfig.model_validate(message_data)
                elif source == "figma_incremental_backfill":
                    backfill_message = FigmaIncrementalBackfillConfig.model_validate(message_data)

                # PostHog
                elif source == "posthog_backfill_root":
                    backfill_message = PostHogBackfillRootConfig.model_validate(message_data)
                elif source == "posthog_project_backfill":
                    backfill_message = PostHogProjectBackfillConfig.model_validate(message_data)
                elif source == "posthog_incremental_backfill":
                    backfill_message = PostHogIncrementalBackfillConfig.model_validate(message_data)

                # Canva
                elif source == "canva_backfill_root":
                    backfill_message = CanvaBackfillRootConfig.model_validate(message_data)
                elif source == "canva_design_backfill":
                    backfill_message = CanvaDesignBackfillConfig.model_validate(message_data)
                elif source == "canva_incremental_backfill":
                    backfill_message = CanvaIncrementalBackfillConfig.model_validate(message_data)

                # Teamwork
                elif source == "teamwork_backfill_root":
                    backfill_message = TeamworkBackfillRootConfig.model_validate(message_data)
                elif source == "teamwork_task_backfill":
                    backfill_message = TeamworkTaskBackfillConfig.model_validate(message_data)
                elif source == "teamwork_incremental_backfill":
                    backfill_message = TeamworkIncrementalBackfillConfig.model_validate(
                        message_data
                    )

                else:
                    raise ValueError(f"Unknown backfill source: {source}")

                logger.info(
                    f"Processing backfill ingest job for tenant {backfill_message.tenant_id}, source: {backfill_message.source}"
                )

                await worker.process_backfill(backfill_message)

            elif message_type == "reindex":
                # Parse as reindex message
                reindex_message = ReindexJobMessage.model_validate(message_data)
                logger.info(
                    f"Processing reindex job for tenant {reindex_message.tenant_id}, source: {reindex_message.source.value}"
                )

                await worker.process_reindex(reindex_message)

            elif message_type == "tenant_data_deletion":
                # Parse as tenant data deletion message
                deletion_message = TenantDataDeletionMessage.model_validate(message_data)
                logger.info(
                    f"Processing tenant data deletion job for tenant {deletion_message.tenant_id}"
                )

                await worker.process_tenant_data_deletion(deletion_message)

            else:
                raise ValueError(f"Unknown message_type: {message_type}")

        # If we get here, ingest job succeeded
        duration = time.perf_counter() - start_time
        base_fields = {
            "message_type": message_type,
            "source": source,
            "tenant_id": tenant_id,
        }

        record_job_completion(
            logger,
            "Ingest",
            "success",
            base_fields,
            sqs_metadata=sqs_metadata,
            duration_seconds=duration,
        )

    except* (ExtendVisibilityException, RateLimitedError):
        # Rate limit or visibility timeout - not a true failure
        duration = time.perf_counter() - start_time
        base_fields = {
            "message_type": message_type,
            "source": source,
            "tenant_id": tenant_id,
        }

        rate_limit_reason = traceback.format_exc()
        record_job_completion(
            logger,
            "Ingest",
            "rate_limited",
            base_fields,
            rate_limit_reason=rate_limit_reason,
            sqs_metadata=sqs_metadata,
            duration_seconds=duration,
        )

        # Re-raise to trigger retry mechanism
        raise

    except* Exception:
        # Ingest job failed
        duration = time.perf_counter() - start_time
        base_fields = {
            "message_type": message_type,
            "source": source,
            "tenant_id": tenant_id,
        }

        error_message = traceback.format_exc()

        record_job_completion(
            logger,
            "Ingest",
            "failed",
            base_fields,
            error_message=error_message,
            sqs_metadata=sqs_metadata,
            duration_seconds=duration,
        )

        # Re-raise to trigger retry mechanism
        raise


async def main() -> None:
    """Main entry point for ingest job worker."""
    # Get queue ARN from configuration
    queue_arn = get_config_value("INGEST_JOBS_QUEUE_ARN") or "corporate-context-ingest-jobs"

    logger.info(f"Starting ingest job worker for queue: {queue_arn}")

    # manually register the newrelic APM application since ingest worker only does background jobs (no web requests)
    # See https://docs.newrelic.com/docs/apm/agents/python-agent/python-agent-api/registerapplication-python-agent-api/#description
    newrelic.agent.register_application()

    async def run_sqs_processor():
        try:
            # Create and start the processor
            processor = SQSJobProcessor(
                queue_arn=queue_arn,
                process_function=process_ingest_job,
                max_messages=1,  # Process one job at a time
                wait_time_seconds=20,  # Long polling
                # 15 min vis timeout - some edge case jobs may take a long time to process, e.g. see AIVP-276
                # TODO AIVP-460 extend visibility timeouts for long running tasks
                visibility_timeout_seconds=15 * 60,
                sqs_client=sqs_client,  # Use the shared SQS client
            )

            await processor.start()
        finally:
            # Clean up worker resources
            await worker.cleanup()

    # Run SQS processor with dedicated HTTP server thread
    await worker.run_with_dedicated_http_thread(run_sqs_processor())


if __name__ == "__main__":
    asyncio.run(main())
