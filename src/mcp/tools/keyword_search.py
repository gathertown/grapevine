from typing import Annotated, assert_never

from fastmcp.server.context import Context
from pydantic import Field

# Company name will be injected at runtime
from connectors.base.document_source import DocumentSource
from src.mcp.mcp_instance import get_mcp
from src.mcp.middleware.org_context import (
    acquire_connection_from_context,
    acquire_opensearch_from_context,
)
from src.mcp.tools.filters import SearchFilters, build_opensearch_filters, get_filter_description
from src.permissions.verifier import batch_verify_document_access
from src.utils.logging import get_logger
from src.utils.scoring import get_keyword_search_scoring_config


async def perform_keyword_search(
    context: Context,
    query: str,
    limit: int = 10,
    filters: SearchFilters = SearchFilters(),
    advanced: bool = False,
) -> dict:
    """
    Core keyword search implementation that can be called from MCP tool or other functions.

    Args:
        context: The FastMCP context
        query: The search query
        limit: Maximum number of results to return
        filters: Search filters to apply
        advanced: Enable advanced query syntax with operators (AND, OR, NOT, etc.)

    Returns:
        Dictionary with search results
    """
    logger = get_logger(__name__)

    if not query:
        raise ValueError("query is required")

    limit = max(1, min(100, limit))

    # Get scoring configuration
    config = get_keyword_search_scoring_config()

    # Debug logging
    logger.info(
        "perform_keyword_search called",
        query=query,
        limit=limit,
        filters=str(filters),
        filter_sources=filters.sources,
        filter_document_id=filters.document_id,
        advanced=advanced,
    )

    permission_principal_token = context.get_state("permission_principal_token")
    permission_audience = context.get_state("permission_audience")
    combined_filters = build_opensearch_filters(
        filters, permission_principal_token, permission_audience
    )

    # Determine fields to search in based on what sources are being searched
    fields = get_keyword_search_fields(filters.sources)

    # Debug logging for OpenSearch parameters
    logger.info(
        "OpenSearch parameters",
        combined_filters=combined_filters,
        fields=fields,
    )

    # Lazily acquire OpenSearch client and perform search
    async with acquire_opensearch_from_context(context) as (opensearch_client, index_name):
        # Use OpenSearch for keyword search with query, recency, and references weighting
        raw_results = await opensearch_client.keyword_search(
            index_name=index_name,
            query=query,
            fields=fields,
            query_weight=config["query_weight"],
            recency_weight=config["recency_weight"],
            references_weight=config["references_weight"],
            limit=limit,
            filters=combined_filters,
            advanced=advanced,
        )

    # Debug logging for raw results
    logger.info(
        "Raw OpenSearch results",
        result_count=len(raw_results),
        first_result_id=raw_results[0].get("id") if raw_results else None,
        first_result_score=raw_results[0].get("score") if raw_results else None,
    )

    # Process results to return only snippets instead of full content
    processed_results = []
    document_ids = []

    for result in raw_results:
        # Create a new result dict with snippets instead of full content
        processed_result = {
            "document_id": result["id"],  # Use document_id for consistency with semantic search
            "score": result["score"],
            "source": result["source"],
            "metadata": result.get("metadata", {}),
            "snippets": [],
        }

        # Extract snippets from highlights
        if "highlights" in result:
            highlights = result["highlights"]

            for key, snippets in highlights.items():
                for snippet in snippets:
                    processed_result["snippets"].append(
                        {
                            "field": key,
                            "text": snippet,
                        }
                    )

        processed_results.append(processed_result)
        document_ids.append(result["id"])  # Still use original ID for database lookup

    # Verify permissions using tenant-scoped connection
    accessible_document_ids = set()
    if document_ids:
        async with acquire_connection_from_context(context, readonly=True) as conn:
            # Verify document permissions - this is the authoritative security check
            accessible_document_ids = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=permission_principal_token,
                permission_audience=permission_audience,
                conn=conn,
            )

    # Filter results by permissions
    filtered_results = []
    for result in processed_results:
        document_id = result["document_id"]

        # Skip documents the user doesn't have access to
        if document_id not in accessible_document_ids:
            continue

        filtered_results.append(result)

    # Debug logging for final results
    logger.info(
        "Final results after permissions filtering",
        original_count=len(processed_results),
        filtered_count=len(filtered_results),
        top_result_id=filtered_results[0].get("document_id") if filtered_results else None,
        top_result_score=filtered_results[0].get("score") if filtered_results else None,
        top_5_ids=[r.get("document_id") for r in filtered_results[:5]],
    )

    return {
        "results": filtered_results,
        "count": len(filtered_results),
    }


def _get_fields_for_source(source: DocumentSource) -> list[str]:
    """
    Get metadata fields for a specific document source.
    This function will cause a type error if any DocumentSource is not handled.

    Args:
        source: The document source to get fields for

    Returns:
        List of metadata field names for the source
    """
    match source:
        case DocumentSource.SLACK:
            return ["metadata.channel_name", "metadata.channel_id"]
        case DocumentSource.GITHUB_PRS:
            return ["metadata.pr_title", "metadata.pr_body", "metadata.repo_name"]
        case DocumentSource.GITHUB_CODE:
            return ["metadata.file_path", "metadata.contributors", "metadata.repository"]
        case DocumentSource.LINEAR:
            return [
                "metadata.issue_title",
                "metadata.team_name",
                "metadata.issue_id",
                "metadata.issue_url",
                "metadata.team_id",
            ]
        case DocumentSource.NOTION:
            return ["metadata.page_title", "metadata.page_id", "metadata.page_url"]
        case DocumentSource.HUBSPOT_DEAL:
            return [
                "metadata.deal_name",
                "metadata.deal_id",
                "metadata.pipeline_name",
                "metadata.pipeline_id",
                "metadata.stage_name",
                "metadata.stage_id",
                "metadata.company_names",
                "metadata.company_ids",
            ]
        case DocumentSource.HUBSPOT_CONTACT:
            return [
                "metadata.contact_name",
                "metadata.email",
                "metadata.contact_id",
                "metadata.company_names",
                "metadata.company_ids",
            ]
        case DocumentSource.HUBSPOT_TICKET:
            return [
                "metadata.ticket_name",
                "metadata.ticket_id",
                "metadata.pipeline_name",
                "metadata.pipeline_id",
                "metadata.stage_name",
                "metadata.stage_id",
                "metadata.company_names",
                "metadata.company_ids",
            ]
        case DocumentSource.HUBSPOT_COMPANY:
            return [
                "metadata.company_id",
                "metadata.company_name",
                "metadata.domain",
                "metadata.website",
                "metadata.industry",
            ]
        case DocumentSource.GOOGLE_DRIVE:
            return [
                "metadata.file_name",
                "metadata.drive_name",
                "metadata.owners",
            ]
        case DocumentSource.GOOGLE_EMAIL:
            return [
                "metadata.subject",
                "metadata.from_address",
                "metadata.to_addresses",
                "metadata.cc_addresses",
                "metadata.bcc_addresses",
            ]
        case DocumentSource.SALESFORCE:
            # Largely inspired by looking at metadata fields from salesforce_* documents
            return [
                "metadata.title",
                "metadata.email",
                "metadata.phone",
                "metadata.website",
                "metadata.case_number",
                "metadata.account_name",
                "metadata.contact_name",
                "metadata.contact_email",
                "metadata.contact_phone",
                "metadata.company",
            ]
        case DocumentSource.JIRA:
            return [
                "metadata.issue_title",
                "metadata.issue_key",
                "metadata.project_name",
                "metadata.assignee",
                "metadata.status",
                "metadata.priority",
            ]
        case DocumentSource.CONFLUENCE:
            return [
                "metadata.page_title",
                "metadata.page_id",
                "metadata.page_url",
                "metadata.space_name",
                "metadata.space_key",
                "metadata.contributors",
            ]
        case DocumentSource.CUSTOM:
            return [
                "metadata.collection_name",
                "metadata.item_id",
            ]
        case DocumentSource.GONG:
            return [
                "metadata.title",
                "metadata.owner_email",
                "metadata.call_id",
                "metadata.workspace_id",
                "metadata.participant_emails_internal",
                "metadata.participant_emails_external",
            ]
        case DocumentSource.GATHER:
            return [
                "metadata.meeting_type",
                "metadata.space_id",
                "metadata.calendar_event_title",
            ]
        case DocumentSource.TRELLO:
            return [
                "metadata.card_name",
                "metadata.card_id",
                "metadata.assigned_members_text",
                "metadata.labels_text",
                "metadata.board_name",
                "metadata.board_id",
                "metadata.list_name",
                "metadata.list_id",
            ]
        case DocumentSource.ZENDESK_TICKET:
            return [
                "metadata.ticket_id",
                "metadata.ticket_subject",
                "metadata.ticket_type",
                "metadata.ticket_status",
                "metadata.ticket_priority",
                "metadata.created_at",
                "metadata.updated_at",
                "metadata.brand_id",
                "metadata.brand_name",
                "metadata.requester_id",
                "metadata.requester_name",
                "metadata.submitter_id",
                "metadata.submitter_name",
                "metadata.assignee_id",
                "metadata.assignee_name",
                "metadata.organization_id",
                "metadata.organization_name",
                "metadata.group_id",
                "metadata.group_name",
            ]
        case DocumentSource.ZENDESK_ARTICLE:
            return [
                "metadata.article_id",
                "metadata.title",
                "metadata.label_names",
                "metadata.author_id",
                "metadata.section_id",
                "metadata.section_name",
                "metadata.category_id",
                "metadata.category_name",
            ]
        case DocumentSource.ASANA_TASK:
            return [
                "metadata.task_gid",
                "metadata.task_name",
                "metadata.project_gids",
                "metadata.section_gids",
                "metadata.assignee_gid",
                "metadata.assignee_name",
                "metadata.workspace_gid",
                "metadata.workspace_name",
            ]
        case DocumentSource.INTERCOM:
            return [
                "metadata.conversation_id",
                "metadata.title",
                "metadata.state",
                "metadata.priority",
                "metadata.contacts",
                "metadata.teammates",
                "metadata.participants",
            ]
        case DocumentSource.ATTIO_COMPANY:
            return [
                "metadata.company_id",
                "metadata.company_name",
                "metadata.domains",
                "metadata.description",
                "metadata.categories",
                "metadata.primary_location",
            ]
        case DocumentSource.ATTIO_PERSON:
            return [
                "metadata.person_id",
                "metadata.person_name",
                "metadata.email_addresses",
                "metadata.phone_numbers",
                "metadata.job_title",
                "metadata.company_name",
                "metadata.primary_location",
            ]
        case DocumentSource.ATTIO_DEAL:
            return [
                "metadata.deal_id",
                "metadata.deal_name",
                "metadata.pipeline_stage",
                "metadata.owner",
                "metadata.company_name",
            ]
        case DocumentSource.FIREFLIES_TRANSCRIPT:
            return [
                "metadata.transcript_id",
                "metadata.transcript_title",
                "metadata.date_string",
                "metadata.organizer_email",
                "metadata.meeting_participants",
                "metadata.duration",
            ]
        case DocumentSource.GITLAB_MR:
            # GitLab MRs
            return [
                "metadata.mr_iid",
                "metadata.mr_title",
                "metadata.mr_state",
                "metadata.project_path",
                "metadata.source_branch",
                "metadata.target_branch",
            ]
        case DocumentSource.GITLAB_CODE:
            # GitLab files/code
            return [
                "metadata.file_path",
                "metadata.file_extension",
                "metadata.project_path",
            ]
        case DocumentSource.CUSTOM_DATA:
            # Custom data documents - user-defined fields are in metadata
            return [
                "metadata.slug",
                "metadata.item_id",
                "metadata.name",
                "metadata.description",
            ]
        case DocumentSource.PYLON_ISSUE:
            # Pylon issues - support tickets
            return [
                "metadata.issue_id",
                "metadata.issue_number",
                "metadata.issue_title",
                "metadata.issue_state",
                "metadata.issue_priority",
                "metadata.requester_email",
                "metadata.account_name",
                "metadata.assignee_email",
            ]
        case DocumentSource.CLICKUP_TASK:
            return [
                "metadata.task_id",
                "metadata.task_name",
                "metadata.workspace_id",
                "metadata.workspace_name",
                "metadata.space_id",
                "metadata.folder_id",
                "metadata.folder_name",
                "metadata.list_id",
                "metadata.list_name",
                "metadata.date_created",
                "metadata.date_updated",
                "metadata.date_closed",
                "metadata.date_done",
            ]
        case DocumentSource.MONDAY_ITEM:
            # Monday.com items (tasks)
            return [
                "metadata.item_id",
                "metadata.item_name",
                "metadata.board_id",
                "metadata.board_name",
                "metadata.workspace_id",
                "metadata.workspace_name",
                "metadata.group_id",
                "metadata.group_title",
                "metadata.state",
                "metadata.creator_name",
            ]
        case DocumentSource.PIPEDRIVE_DEAL:
            # Pipedrive deals
            return [
                "metadata.deal_id",
                "metadata.deal_title",
                "metadata.deal_status",
                "metadata.deal_currency",
                "metadata.stage_name",
                "metadata.pipeline_name",
                "metadata.owner_name",
                "metadata.owner_email",
                "metadata.person_name",
                "metadata.person_email",
                "metadata.org_name",
            ]
        case DocumentSource.PIPEDRIVE_PERSON:
            # Pipedrive persons (contacts)
            return [
                "metadata.person_id",
                "metadata.person_name",
                "metadata.person_email",
                "metadata.person_phone",
                "metadata.org_name",
                "metadata.owner_name",
                "metadata.owner_email",
            ]
        case DocumentSource.PIPEDRIVE_ORGANIZATION:
            # Pipedrive organizations
            return [
                "metadata.org_id",
                "metadata.org_name",
                "metadata.org_address",
                "metadata.owner_name",
                "metadata.owner_email",
            ]
        case DocumentSource.PIPEDRIVE_PRODUCT:
            # Pipedrive products
            return [
                "metadata.product_id",
                "metadata.product_name",
                "metadata.product_code",
                "metadata.product_unit",
                "metadata.owner_name",
                "metadata.owner_email",
                "metadata.billing_frequency",
            ]
        case DocumentSource.FIGMA_FILE:
            # Figma design files
            return [
                "metadata.file_key",
                "metadata.file_name",
                "metadata.editor_type",
                "metadata.project_id",
                "metadata.team_id",
            ]
        case DocumentSource.FIGMA_COMMENT:
            # Figma comments
            return [
                "metadata.comment_id",
                "metadata.file_key",
                "metadata.file_name",
                "metadata.user_handle",
                "metadata.user_email",
            ]
        case DocumentSource.POSTHOG_DASHBOARD:
            # PostHog dashboards
            return [
                "metadata.dashboard_id",
                "metadata.name",
                "metadata.project_id",
                "metadata.tags",
            ]
        case DocumentSource.POSTHOG_INSIGHT:
            # PostHog insights
            return [
                "metadata.insight_id",
                "metadata.name",
                "metadata.short_id",
                "metadata.project_id",
                "metadata.tags",
            ]
        case DocumentSource.POSTHOG_FEATURE_FLAG:
            # PostHog feature flags
            return [
                "metadata.flag_id",
                "metadata.key",
                "metadata.name",
                "metadata.project_id",
                "metadata.tags",
            ]
        case DocumentSource.POSTHOG_ANNOTATION:
            # PostHog annotations
            return [
                "metadata.annotation_id",
                "metadata.project_id",
                "metadata.scope",
            ]
        case DocumentSource.POSTHOG_EXPERIMENT:
            # PostHog experiments
            return [
                "metadata.experiment_id",
                "metadata.name",
                "metadata.project_id",
                "metadata.feature_flag_key",
            ]
        case DocumentSource.POSTHOG_SURVEY:
            # PostHog surveys
            return [
                "metadata.survey_id",
                "metadata.name",
                "metadata.project_id",
                "metadata.survey_type",
            ]
        case DocumentSource.CANVA_DESIGN:
            # Canva design files - matches CanvaDesignDocument.metadata property
            return [
                "metadata.design_id",
                "metadata.design_title",
                "metadata.owner_user_id",
                "metadata.owner_team_id",
            ]
        case DocumentSource.TEAMWORK_TASK:
            # Teamwork tasks - project management tasks
            return [
                "metadata.task_id",
                "metadata.task_name",
                "metadata.project_id",
                "metadata.project_name",
                "metadata.task_list_name",
                "metadata.status",
                "metadata.priority",
                "metadata.assignee_name",
                "metadata.creator_name",
                "metadata.tags",
            ]
        case _:
            # This will cause a type error if any DocumentSource value is not handled above
            assert_never(source)


def get_keyword_search_fields(sources: list[DocumentSource] | None = None) -> list[str]:
    """
    Get the list of fields to search based on document sources.

    Args:
        sources: List of document sources to filter by. None means all sources.

    Returns:
        List of field names to search in OpenSearch
    """
    fields = ["content"]

    # If no sources specified, include fields for all sources
    sources_to_include = sources if sources else list(DocumentSource)

    # Get fields for each source using the type-safe helper function
    for source in sources_to_include:
        fields.extend(_get_fields_for_source(source))

    return fields


@get_mcp().tool(
    description=f"""Search your organization's internal context for documents containing specific keywords or phrases.

This tool supports two modes:

**Standard Mode (advanced=false, default):**
- Optimized for natural language queries
- Automatically creates phrase matches, near-phrase matches, and AND/OR variants
- Best for finding documents when you're not sure of exact phrasing
- Example: "rate limiting API" finds documents with these terms in any order

**Advanced Mode (advanced=true):**
- Preserves OpenSearch query syntax operators
- Supports: AND, OR, NOT, +/-, wildcards (*), field queries (field:value), grouping with parentheses
- Best for precise searches when you know exactly what you're looking for
- Examples:
  - "error AND warning" - must contain both terms
  - "API OR database" - contains either term
  - "error NOT deprecated" - contains "error" but not "deprecated"
  - "+required -optional" - must have "required", must not have "optional"
  - "(error OR warning) AND api" - complex boolean logic
  - "content:authentication" - search only in content field

The search is performed on the full document content and metadata, but returns only highlighted snippets with expanded context.

This tool differs from semantic search:
- keyword_search: Finds exact term matches or uses query operators
- semantic_search: Finds conceptually similar content using AI embeddings

Common use cases:
- Find specific files from the codebase
- Find all documents mentioning specific error messages
- Search for documents containing person names or product names
- Locate documents with specific technical terms
- Complex boolean searches in advanced mode

{get_filter_description()}

EXAMPLE: Find recent discussions mentioning a specific error message
```
{{
    "query": "\"validation error\"",
    "filters": {{
        "sources": ["{DocumentSource.SLACK.value}", "{DocumentSource.GITHUB_PRS.value}", "{DocumentSource.NOTION.value}", "{DocumentSource.LINEAR.value}"],
        "date_from": "2025-06-01",
    }},
    "limit": 8
}}
```

EXAMPLE: Find standup updates from a specific week in a specific Slack channel
```
{{
    "query": "standup",
    "filters": {{
        "sources": ["{DocumentSource.SLACK.value}"],
        "provenance": "team-platform",
        "date_from": "2025-07-16",
        "date_to": "2025-07-23",
    }},
    "limit": 10
}}
```

EXAMPLE: Find code referencing a specific function in the codebase
```
{{
    "query": "calculateValue",
    "filters": {{
        "sources": ["{DocumentSource.GITHUB_CODE.value}"],
        "provenance": "your-repo-name-here",
    }},
    "limit": 20
}}
```

EXAMPLE: Search custom collection data
```
{{
    "query": "performance issues",
    "filters": {{
        "sources": ["{DocumentSource.CUSTOM.value}"],
        "provenance": "customer-feedback",
    }},
    "limit": 10
}}
```

EXAMPLE: Search custom uploaded data (invoices, receipts, transactions, etc.)
```
{{
    "query": "Acme Corp invoice",
    "filters": {{
        "sources": ["{DocumentSource.CUSTOM_DATA.value}"],
    }},
    "limit": 10
}}
```

Returns:
- Dict with search results containing only snippets with expanded context: {{results: [{{document_id, score, snippets, metadata, source, annotations}}], count}}
"""
)
async def keyword_search(
    context: Context,
    query: Annotated[
        str,
        Field(
            description="""Keywords to search for.

In standard mode (advanced=false): Natural language query, e.g., "rate limiting API"

In advanced mode (advanced=true): Supports OpenSearch query syntax:
• AND operator: "error AND warning" (both terms required)
• OR operator: "error OR warning" (either term)
• NOT operator: "error NOT deprecated" (exclude terms)
• Required/excluded: "+required -optional"
• Wildcards: "config*" or "conf?"
• Exact phrases: "\"API rate limit\""
• Field queries: "content:authentication"
• Grouping: "(error OR warning) AND api"
• Fuzzy search: "configuraton~" (matches typos)
• Boosting: "critical^2 error"
"""
        ),
    ],
    limit: Annotated[int, Field(description="Max # of results to return", ge=1, le=100)] = 10,
    filters: Annotated[
        SearchFilters, Field(description="Filters to apply to this search to narrow down results")
    ] = SearchFilters(),
    advanced: Annotated[
        bool,
        Field(
            description="Enable advanced query mode to use OpenSearch operators (AND, OR, NOT, etc.). Default is false for natural language queries."
        ),
    ] = False,
) -> dict:
    logger = get_logger(__name__)

    # Debug logging for MCP tool call
    logger.info(
        "MCP keyword_search tool called",
        query=query,
        limit=limit,
        filters_raw=str(filters),
        filters_type=type(filters).__name__,
        advanced=advanced,
    )

    # Use the core keyword search implementation
    result = await perform_keyword_search(
        context=context, query=query, limit=limit, filters=filters, advanced=advanced
    )

    # Debug logging for MCP tool result
    logger.info(
        "MCP keyword_search tool returning results",
        result_count=result.get("count", 0),
    )

    return result
