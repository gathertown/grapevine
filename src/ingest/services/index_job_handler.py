"""
Handler for indexing completed ingest jobs.
"""

import time

import asyncpg

from connectors.asana import AsanaTaskTransformer
from connectors.attio import AttioCompanyTransformer, AttioDealTransformer, AttioPersonTransformer
from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.canva import CanvaDesignTransformer
from connectors.clickup import ClickupTaskTransformer
from connectors.confluence import ConfluenceTransformer
from connectors.custom import CustomCollectionTransformer
from connectors.custom_data import CustomDataTransformer
from connectors.figma import FigmaCommentTransformer, FigmaFileTransformer
from connectors.fireflies import FirefliesTranscriptTransformer
from connectors.gather import GatherTransformer
from connectors.github import GithubFileTransformer, GithubPRTransformer
from connectors.gitlab import GitLabFileTransformer, GitLabMRTransformer
from connectors.gmail import GoogleEmailTransformer
from connectors.gong import GongCallTransformer
from connectors.google_drive import GoogleDriveTransformer
from connectors.hubspot import (
    HubSpotCompanyTransformer,
    HubSpotContactTransformer,
    HubSpotDealTransformer,
    HubSpotTicketTransformer,
)
from connectors.intercom.intercom_unified_transformer import IntercomUnifiedTransformer
from connectors.jira import JiraTransformer
from connectors.linear import LinearTransformer
from connectors.monday import MondayItemTransformer
from connectors.notion import NotionTransformer
from connectors.pipedrive.pipedrive_transformer import (
    PipedriveDealTransformer,
    PipedriveOrganizationTransformer,
    PipedrivePersonTransformer,
    PipedriveProductTransformer,
)
from connectors.posthog import (
    PostHogAnnotationTransformer,
    PostHogDashboardTransformer,
    PostHogExperimentTransformer,
    PostHogFeatureFlagTransformer,
    PostHogInsightTransformer,
    PostHogSurveyTransformer,
)
from connectors.pylon import PylonIssueTransformer
from connectors.salesforce import SalesforceTransformer
from connectors.slack import SlackChannelDocument, SlackTransformer
from connectors.teamwork.teamwork_transformer import TeamworkTaskTransformer
from connectors.trello import TrelloTransformer
from connectors.zendesk import ZendeskArticleTransformer, ZendeskTicketTransformer
from src.database.sample_questions import store_sample_questions
from src.ingest.utils import gen_and_store_embeddings
from src.jobs.exceptions import ExtendVisibilityException
from src.jobs.models import IndexJobMessage
from src.jobs.sqs_job_processor import SQSMessageMetadata
from src.utils.config import get_config_value
from src.utils.job_metrics import record_job_completion
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError
from src.utils.slack_question_extractor import extract_questions_from_messages
from src.webhooks.delivery import trigger_webhooks_for_document

logger = get_logger(__name__)


class IndexJobHandler:
    """Handler for transforming and indexing artifacts from completed ingest jobs."""

    def __init__(self):
        # Don't pre-create transformers - create them fresh for each job
        # to avoid shared state issues in parallel execution
        pass

    def _get_transformer(self, source: DocumentSource) -> BaseTransformer | None:
        """Get a fresh transformer instance for the given source."""
        transformer_map: dict[DocumentSource, type[BaseTransformer]] = {
            DocumentSource.SLACK: SlackTransformer,
            DocumentSource.NOTION: NotionTransformer,
            DocumentSource.LINEAR: LinearTransformer,
            DocumentSource.GITHUB_PRS: GithubPRTransformer,
            DocumentSource.GITHUB_CODE: GithubFileTransformer,
            DocumentSource.GOOGLE_DRIVE: GoogleDriveTransformer,
            DocumentSource.GOOGLE_EMAIL: GoogleEmailTransformer,
            DocumentSource.SALESFORCE: SalesforceTransformer,
            DocumentSource.JIRA: JiraTransformer,
            DocumentSource.CONFLUENCE: ConfluenceTransformer,
            DocumentSource.HUBSPOT_DEAL: HubSpotDealTransformer,
            DocumentSource.HUBSPOT_TICKET: HubSpotTicketTransformer,
            DocumentSource.HUBSPOT_COMPANY: HubSpotCompanyTransformer,
            DocumentSource.HUBSPOT_CONTACT: HubSpotContactTransformer,
            DocumentSource.CUSTOM: CustomCollectionTransformer,
            DocumentSource.CUSTOM_DATA: CustomDataTransformer,
            DocumentSource.GONG: GongCallTransformer,
            DocumentSource.GATHER: GatherTransformer,
            DocumentSource.TRELLO: TrelloTransformer,
            DocumentSource.ZENDESK_TICKET: ZendeskTicketTransformer,
            DocumentSource.ZENDESK_ARTICLE: ZendeskArticleTransformer,
            DocumentSource.ASANA_TASK: AsanaTaskTransformer,
            DocumentSource.INTERCOM: IntercomUnifiedTransformer,
            DocumentSource.ATTIO_COMPANY: AttioCompanyTransformer,
            DocumentSource.ATTIO_PERSON: AttioPersonTransformer,
            DocumentSource.ATTIO_DEAL: AttioDealTransformer,
            DocumentSource.FIREFLIES_TRANSCRIPT: FirefliesTranscriptTransformer,
            DocumentSource.GITLAB_MR: GitLabMRTransformer,
            DocumentSource.GITLAB_CODE: GitLabFileTransformer,
            DocumentSource.PYLON_ISSUE: PylonIssueTransformer,
            DocumentSource.CLICKUP_TASK: ClickupTaskTransformer,
            DocumentSource.MONDAY_ITEM: MondayItemTransformer,
            DocumentSource.PIPEDRIVE_DEAL: PipedriveDealTransformer,
            DocumentSource.PIPEDRIVE_PERSON: PipedrivePersonTransformer,
            DocumentSource.PIPEDRIVE_ORGANIZATION: PipedriveOrganizationTransformer,
            DocumentSource.PIPEDRIVE_PRODUCT: PipedriveProductTransformer,
            DocumentSource.FIGMA_FILE: FigmaFileTransformer,
            DocumentSource.FIGMA_COMMENT: FigmaCommentTransformer,
            DocumentSource.POSTHOG_DASHBOARD: PostHogDashboardTransformer,
            DocumentSource.POSTHOG_INSIGHT: PostHogInsightTransformer,
            DocumentSource.POSTHOG_FEATURE_FLAG: PostHogFeatureFlagTransformer,
            DocumentSource.POSTHOG_ANNOTATION: PostHogAnnotationTransformer,
            DocumentSource.POSTHOG_EXPERIMENT: PostHogExperimentTransformer,
            DocumentSource.POSTHOG_SURVEY: PostHogSurveyTransformer,
            DocumentSource.CANVA_DESIGN: CanvaDesignTransformer,
            DocumentSource.TEAMWORK_TASK: TeamworkTaskTransformer,
        }
        transformer_class = transformer_map.get(source)
        if not transformer_class:
            return None
        return transformer_class()  # type: ignore[call-arg]

    async def handle_index_job(
        self,
        job_message: IndexJobMessage,
        readonly_db_pool: asyncpg.Pool,
        sqs_metadata: SQSMessageMetadata | None = None,
    ) -> None:
        """
        Process artifacts from a completed ingest job and index them.

        Args:
            job_message: The job message containing entity IDs, source, and tenant ID
            readonly_db_pool: Database pool to use
            sqs_metadata: Optional SQS message metadata for job completion tracking
        """
        start_time = time.perf_counter()

        # Extract data from job message for tracking
        entity_ids = job_message.entity_ids
        source = job_message.source
        tenant_id = job_message.tenant_id
        force_reindex = job_message.force_reindex
        turbopuffer_only = job_message.turbopuffer_only
        backfill_id = job_message.backfill_id

        entity_count = len(entity_ids)
        document_count = 0

        try:
            if not entity_ids:
                logger.error("entity_ids is required but not provided")
                return

            # Get a fresh transformer instance
            transformer = self._get_transformer(source)
            if not transformer:
                logger.error(f"No transformer found for source: {source}")
                return

            logger.info(
                f"Processing {len(entity_ids)} entities for indexing (source: {source}, tenant: {tenant_id})"
            )

            # Transform artifacts into documents
            # Pass tenant_id for Gong transformer (for workspace selection config)
            # Check if transformer accepts tenant_id parameter
            import inspect

            sig = inspect.signature(transformer.transform_artifacts)
            if "tenant_id" in sig.parameters:
                documents = await transformer.transform_artifacts(
                    entity_ids, readonly_db_pool, tenant_id
                )  # type: ignore[call-arg]
            else:
                documents = await transformer.transform_artifacts(entity_ids, readonly_db_pool)
            document_count = len(documents)

            if not documents:
                logger.warning(f"No documents created from {len(entity_ids)} entities")
                return

            logger.info(f"Created {len(documents)} documents from {len(entity_ids)} entities")

            # Process documents (generate embeddings and store) - this can throw
            await gen_and_store_embeddings(
                documents,
                tenant_id,
                readonly_db_pool,
                force_reindex=force_reindex,
                turbopuffer_only=turbopuffer_only,
                backfill_id=backfill_id,
            )

            # Trigger webhook delivery for each processed document (fire and forget)
            for document in documents:
                try:
                    trigger_webhooks_for_document(
                        tenant_id=tenant_id,
                        document_id=document.id,
                        source=source.value,
                        db_pool=readonly_db_pool,
                    )
                except Exception as e:
                    # Log webhook failure but don't fail the index job
                    logger.warning(
                        "Webhook delivery failed for document",
                        tenant_id=tenant_id,
                        document_id=document.id,
                        source=source.value,
                        error=str(e),
                    )

            # Extract sample questions from Slack documents
            # This is kind of lame that we have it here _instead of_ the Slack
            # index job proper; but we don't pass in the tenant id into the jobs.
            # If we keep this, we should refactor this to be part of the Slack index job.
            if source == DocumentSource.SLACK and get_config_value(
                "SLACK_EXPORT_QUESTIONS_ENABLED"
            ):
                logger.info("Starting sample question extraction from Slack documents")
                question_extract_start = time.perf_counter()
                await self._extract_sample_questions_from_slack_documents(documents, tenant_id)
                question_extract_duration = time.perf_counter() - question_extract_start
                logger.info(
                    f"Sample question extraction completed in {question_extract_duration:.2f} seconds"
                )

            # If we get here, entire job succeeded
            duration = time.perf_counter() - start_time
            base_fields = {
                "entities_processed": entity_count,
                "documents_created": document_count,
                "source": source,
                "tenant_id": tenant_id,
            }

            record_job_completion(
                logger,
                "Index",
                "success",
                base_fields,
                sqs_metadata=sqs_metadata,
                duration_seconds=duration,
            )

            # DEPRECATED: we don't use this field and it's adding wasted write qps.
            # Leaving this old logic here for now in case we want to understand why some rows have
            # this column set, but we should delete this once we drop the column.
            # Mark artifacts as indexed based on entity_ids
            # async with db_pool.acquire() as conn:
            #     result = await conn.execute(
            #         """
            #         UPDATE ingest_artifact
            #         SET indexed_at = NOW()
            #         WHERE entity_id = ANY($1)
            #         AND indexed_at IS NULL
            #         """,
            #         entity_ids,
            #     )
            #     # Extract the number of rows updated from the result
            #     updated_count = int(result.split()[-1]) if result else 0
            #     logger.info(
            #         f"Marked {updated_count} artifacts as indexed for entity_ids: {entity_ids}"
            #     )

        except (ExtendVisibilityException, RateLimitedError) as e:
            # Rate limit or visibility timeout - not a true failure
            duration = time.perf_counter() - start_time
            base_fields = {
                "entities_processed": entity_count,
                "documents_created": document_count,
                "source": source,
                "tenant_id": tenant_id,
            }

            record_job_completion(
                logger,
                "Index",
                "rate_limited",
                base_fields,
                rate_limit_reason=str(e),
                sqs_metadata=sqs_metadata,
                duration_seconds=duration,
            )

            # Re-raise to trigger retry mechanism
            raise

        except Exception as e:
            # Entire job failed - all documents failed
            duration = time.perf_counter() - start_time
            base_fields = {
                "entities_processed": entity_count,
                "documents_created": document_count,
                "source": source,
                "tenant_id": tenant_id,
            }

            record_job_completion(
                logger,
                "Index",
                "failed",
                base_fields,
                error_message=str(e),
                sqs_metadata=sqs_metadata,
                duration_seconds=duration,
            )

            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            # Re-raise to trigger retry mechanism
            raise

    async def _extract_sample_questions_from_slack_documents(
        self, documents: list, tenant_id: str
    ) -> None:
        """Extract sample questions from Slack channel documents.

        Args:
            documents: List of SlackChannelDocument instances
            tenant_id: The tenant ID for database operations
        """
        try:
            # Check if installer DM was already sent - if so, skip question extraction
            from src.utils.tenant_config import get_installer_dm_sent

            installer_dm_sent = await get_installer_dm_sent(tenant_id)

            if installer_dm_sent:
                logger.info(
                    f"Installer DM already sent at {installer_dm_sent} - skipping sample question extraction for tenant {tenant_id}"
                )
                return
            all_questions = []

            for document in documents:
                if not isinstance(document, SlackChannelDocument):
                    continue

                # Extract data from the document
                raw_data = document.raw_data
                messages = raw_data.get("messages", [])
                channel_id = raw_data.get("channel_id", "")
                channel_name = raw_data.get("channel_name", "")
                date = raw_data.get("date", "")

                if not messages or not channel_id:
                    continue

                # Extract questions using our utility
                questions = extract_questions_from_messages(
                    messages, channel_id, channel_name, date
                )

                all_questions.extend(questions)

            if all_questions:
                # Store all questions in the database
                stored_count = await store_sample_questions(tenant_id, all_questions)
                logger.info(
                    f"Extracted and stored {stored_count} sample questions from {len(documents)} Slack documents for tenant {tenant_id}"
                )
            else:
                logger.debug(f"No sample questions found in {len(documents)} Slack documents")

        except Exception as e:
            logger.error(f"Failed to extract sample questions: {e}", exc_info=True)
            # Don't re-raise - question extraction failure shouldn't block indexing


# Create a singleton instance
handler = IndexJobHandler()
