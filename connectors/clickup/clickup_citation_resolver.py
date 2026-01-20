from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.clickup.transformers.clickup_task_document import ClickupTaskDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class ClickupTaskCitationResolver(BaseCitationResolver[ClickupTaskDocumentMetadata]):
    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[ClickupTaskDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        return document.metadata["task_url"]
