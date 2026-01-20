"""Citation resolver for Teamwork documents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.teamwork.teamwork_task_document import TeamworkTaskDocumentMetadata
from src.utils.logging import get_logger
from src.utils.tenant_config import get_config_value_with_pool

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class TeamworkCitationResolver(BaseCitationResolver[TeamworkTaskDocumentMetadata]):
    """Resolve citations for Teamwork task documents."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[TeamworkTaskDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """
        Generate a deep link URL to the Teamwork task.

        Teamwork tasks are accessible at:
        https://{company}.teamwork.com/app/tasks/{task_id}

        The api_domain is stored in tenant config during OAuth setup.
        """
        task_id = document.metadata.get("task_id")

        # Get the API domain from tenant config
        api_domain = await get_config_value_with_pool("TEAMWORK_API_DOMAIN", resolver.db_pool)

        if not api_domain:
            logger.warning(
                "Could not find TEAMWORK_API_DOMAIN for citation",
                document_id=document.id,
            )
            return ""

        # Remove trailing slash if present
        api_domain = api_domain.rstrip("/")

        if task_id:
            return f"{api_domain}/app/tasks/{task_id}"

        # Fallback: try to extract task_id from document.id (format: teamwork_task_{task_id})
        if document.id.startswith("teamwork_task_"):
            extracted_id = document.id[len("teamwork_task_") :]
            return f"{api_domain}/app/tasks/{extracted_id}"

        # Last resort: log warning and return base tasks URL
        logger.warning(
            "Could not extract task_id for citation",
            document_id=document.id,
        )
        return f"{api_domain}/app/tasks"
