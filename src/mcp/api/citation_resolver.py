"""Main citation resolver orchestrator."""

from typing import Any

import asyncpg

from connectors.asana import AsanaTaskCitationResolver
from connectors.attio import (
    AttioCompanyCitationResolver,
    AttioDealCitationResolver,
    AttioPersonCitationResolver,
)
from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentSource, DocumentWithSourceAndMetadata
from connectors.canva import CanvaDesignCitationResolver
from connectors.clickup import ClickupTaskCitationResolver
from connectors.confluence import ConfluenceCitationResolver
from connectors.figma import FigmaCommentCitationResolver, FigmaFileCitationResolver
from connectors.fireflies import FirefliesTranscriptCitationResolver
from connectors.github import GitHubFileCitationResolver, GitHubPRCitationResolver
from connectors.gitlab import GitLabFileCitationResolver, GitLabMRCitationResolver
from connectors.gmail import GoogleEmailCitationResolver
from connectors.gong import GongCitationResolver
from connectors.google_drive import GoogleDriveCitationResolver
from connectors.hubspot import (
    HubspotCompanyCitationResolver,
    HubspotContactCitationResolver,
    HubspotDealCitationResolver,
    HubspotTicketCitationResolver,
)
from connectors.intercom import IntercomCitationResolver
from connectors.jira import JiraCitationResolver
from connectors.linear import LinearCitationResolver
from connectors.monday import MondayCitationResolver
from connectors.notion import NotionCitationResolver
from connectors.pipedrive import (
    PipedriveDealCitationResolver,
    PipedriveOrganizationCitationResolver,
    PipedrivePersonCitationResolver,
    PipedriveProductCitationResolver,
)
from connectors.posthog import (
    PostHogAnnotationCitationResolver,
    PostHogDashboardCitationResolver,
    PostHogExperimentCitationResolver,
    PostHogFeatureFlagCitationResolver,
    PostHogInsightCitationResolver,
    PostHogSurveyCitationResolver,
)
from connectors.pylon import PylonIssueCitationResolver
from connectors.salesforce import SalesforceCitationResolver
from connectors.slack import SlackCitationResolver
from connectors.teamwork import TeamworkCitationResolver
from connectors.trello import TrelloCitationResolver
from connectors.zendesk import ZendeskTicketCitationResolver
from src.utils.citations import (
    collapse_duplicate_citations,
    fetch_documents_batch,
    parse_citations,
)
from src.utils.logging import get_logger
from src.utils.tracing import create_agent_metadata, trace_span

logger = get_logger(__name__)


class CitationResolver:
    """Main citation resolver orchestrator."""

    def __init__(
        self, db_pool: asyncpg.Pool, tenant_id: str, permission_principal_token: str | None = None
    ):
        self.db_pool = db_pool
        self.tenant_id = tenant_id
        self.permission_principal_token = permission_principal_token
        self.resolvers: dict[DocumentSource, BaseCitationResolver[Any]] = {
            DocumentSource.SLACK: SlackCitationResolver(),
            DocumentSource.GITHUB_PRS: GitHubPRCitationResolver(),
            DocumentSource.GITHUB_CODE: GitHubFileCitationResolver(),
            DocumentSource.JIRA: JiraCitationResolver(),
            DocumentSource.CONFLUENCE: ConfluenceCitationResolver(),
            DocumentSource.LINEAR: LinearCitationResolver(),
            DocumentSource.NOTION: NotionCitationResolver(),
            DocumentSource.GONG: GongCitationResolver(),
            DocumentSource.GOOGLE_DRIVE: GoogleDriveCitationResolver(),
            DocumentSource.GOOGLE_EMAIL: GoogleEmailCitationResolver(),
            DocumentSource.TRELLO: TrelloCitationResolver(),
            DocumentSource.HUBSPOT_DEAL: HubspotDealCitationResolver(),
            DocumentSource.HUBSPOT_COMPANY: HubspotCompanyCitationResolver(),
            DocumentSource.HUBSPOT_CONTACT: HubspotContactCitationResolver(),
            DocumentSource.HUBSPOT_TICKET: HubspotTicketCitationResolver(),
            DocumentSource.SALESFORCE: SalesforceCitationResolver(),
            DocumentSource.ZENDESK_TICKET: ZendeskTicketCitationResolver(),
            DocumentSource.ASANA_TASK: AsanaTaskCitationResolver(),
            DocumentSource.ATTIO_COMPANY: AttioCompanyCitationResolver(),
            DocumentSource.ATTIO_PERSON: AttioPersonCitationResolver(),
            DocumentSource.ATTIO_DEAL: AttioDealCitationResolver(),
            DocumentSource.INTERCOM: IntercomCitationResolver(),
            DocumentSource.FIREFLIES_TRANSCRIPT: FirefliesTranscriptCitationResolver(),
            DocumentSource.PYLON_ISSUE: PylonIssueCitationResolver(),
            DocumentSource.GITLAB_MR: GitLabMRCitationResolver(),
            DocumentSource.GITLAB_CODE: GitLabFileCitationResolver(),
            DocumentSource.CLICKUP_TASK: ClickupTaskCitationResolver(),
            DocumentSource.MONDAY_ITEM: MondayCitationResolver(),
            DocumentSource.PIPEDRIVE_DEAL: PipedriveDealCitationResolver(),
            DocumentSource.PIPEDRIVE_PERSON: PipedrivePersonCitationResolver(),
            DocumentSource.PIPEDRIVE_ORGANIZATION: PipedriveOrganizationCitationResolver(),
            DocumentSource.PIPEDRIVE_PRODUCT: PipedriveProductCitationResolver(),
            DocumentSource.FIGMA_FILE: FigmaFileCitationResolver(),
            DocumentSource.FIGMA_COMMENT: FigmaCommentCitationResolver(),
            DocumentSource.POSTHOG_DASHBOARD: PostHogDashboardCitationResolver(),
            DocumentSource.POSTHOG_INSIGHT: PostHogInsightCitationResolver(),
            DocumentSource.POSTHOG_FEATURE_FLAG: PostHogFeatureFlagCitationResolver(),
            DocumentSource.POSTHOG_ANNOTATION: PostHogAnnotationCitationResolver(),
            DocumentSource.POSTHOG_EXPERIMENT: PostHogExperimentCitationResolver(),
            DocumentSource.POSTHOG_SURVEY: PostHogSurveyCitationResolver(),
            DocumentSource.CANVA_DESIGN: CanvaDesignCitationResolver(),
            DocumentSource.TEAMWORK_TASK: TeamworkCitationResolver(),
        }

        self.document_contents_cache: dict[str, str] = {}

    async def resolve_citation(
        self, document: DocumentWithSourceAndMetadata[Any], excerpt: str
    ) -> str:
        """Resolve a single citation using the appropriate source resolver."""
        resolver = self.resolvers.get(document.source)
        if not resolver:
            logger.error(f"No resolver found for source: {document.source}")
            return ""

        return await resolver.resolve_citation(document, excerpt, self)

    async def _get_document_contents(self, document_id: str) -> str:
        """Get document contents from cache or database."""
        if document_id in self.document_contents_cache:
            return self.document_contents_cache[document_id]
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT content FROM documents WHERE id = $1", document_id)
            if not row:
                raise ValueError(f"Document {document_id} not found")
            self.document_contents_cache[document_id] = row["content"]
            return row["content"]


async def replace_citations_with_deeplinks(
    answer: str,
    db_pool: asyncpg.Pool,
    tenant_id: str,
    permission_principal_token: str | None = None,
    output_format: str | None = None,
) -> str:
    """Process citations by replacing [doc_id|"excerpt"] patterns with deeplinks.

    Args:
        answer: The generated answer containing document ID citations with excerpts
        db_pool: Database connection pool for fetching document metadata
        tenant_id: Tenant identifier for accessing the correct data
        output_format: Output format for citations ('slack' for Slack markdown, None for standard)

    Returns:
        Answer text with citations replaced by numbered deeplinks
    """

    async with trace_span(
        name="collect_citations",
        input_data={"answer": answer},
        metadata=create_agent_metadata("collect_citations"),
    ) as citations_span:
        # 1. Parse citations
        citations = parse_citations(answer)

        if not citations:
            logger.info("No citations found in answer")
            return answer

        # 2. Get unique document IDs and fetch all documents
        unique_doc_ids = list({doc_id for doc_id, _ in citations})
        logger.info(
            f"Found {len(citations)} citations across {len(unique_doc_ids)} unique documents"
        )

        # Fetch all documents we need
        documents = await fetch_documents_batch(unique_doc_ids, db_pool)

        # Check if we have all documents
        missing_doc_ids = [doc_id for doc_id in unique_doc_ids if doc_id not in documents]
        if missing_doc_ids:
            logger.warning(f"Missing documents: {missing_doc_ids}")

        # 3. Create resolvers
        resolver = CitationResolver(db_pool, tenant_id, permission_principal_token)

        # 4. Resolve each citation; TODO: parallelize this while preserving order
        resolved_citations = {}
        for doc_id, excerpt in citations:
            if doc_id not in documents:
                logger.warning(f"Document {doc_id} not found in tool results")
                url = ""
            else:
                doc = documents[doc_id]
                try:
                    url = await resolver.resolve_citation(doc, excerpt)
                    logger.info(f"Resolved citation for doc_id={doc_id}: {url}")
                except ValueError as e:
                    logger.error(f"Invalid source value '{doc.source}' for document {doc_id}: {e}")
                    url = ""
                except Exception as e:
                    logger.error(f"Error resolving citation for {doc_id}: {e}")
                    url = ""

            resolved_citations[(doc_id, excerpt)] = url

        # 5. Deduplicate by URL and assign numbers
        unique_urls = {}
        citation_number = 1
        for citation in resolved_citations:
            original = f"[{citation[0]}|{citation[1]}]"
            url_key = resolved_citations[citation] or original  # Use original citation if no URL
            if url_key not in unique_urls:
                unique_urls[url_key] = citation_number
                citation_number += 1

        # 6. Build replacements
        final_answer = answer

        for citation in resolved_citations:
            original = f"[{citation[0]}|{citation[1]}]"
            url = resolved_citations[citation]
            url_key = url or original  # Use same logic as deduplication
            number = unique_urls[url_key]

            if output_format == "slack":
                replacement = f"<{url}|[{number}]>" if url else original
            else:
                replacement = f"[[{number}]]({url})" if url else original

            final_answer = final_answer.replace(original, replacement)

        # 7. Collapse duplicate citation numbers within the same claim/sentence
        final_answer = collapse_duplicate_citations(final_answer, output_format)

        citations_span.update(output={"answer": final_answer})
        return final_answer
