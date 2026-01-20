"""Citation utilities and helper functions."""

import json
import re

import asyncpg

from connectors.base.document_source import DocumentSource, DocumentWithSourceAndMetadata
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def fetch_documents_batch(
    doc_ids: list[str], db_pool: asyncpg.Pool
) -> dict[str, DocumentWithSourceAndMetadata]:
    """Fetch multiple documents with their source and metadata.

    Adapted from get_document and keyword_search patterns.

    Args:
        doc_ids: List of document IDs to fetch
        db_pool: Database connection pool

    Returns:
        Dictionary mapping document IDs to their source and metadata
    """
    if not doc_ids:
        return {}

    async with db_pool.acquire() as conn:
        # Similar to keyword_search.py line 128, but fetch full document data
        rows = await conn.fetch(
            """
            SELECT id, source, metadata
            FROM documents
            WHERE id = ANY($1::varchar[])
            """,
            doc_ids,
        )

        documents: dict[str, DocumentWithSourceAndMetadata] = {}
        for row in rows:
            metadata = row["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            documents[row["id"]] = DocumentWithSourceAndMetadata(
                id=row["id"],
                source=DocumentSource(row["source"]),
                metadata=metadata,
            )

        return documents


def parse_citations(answer: str) -> list[tuple[str, str]]:
    """Parse all [doc_id|excerpt] citations from answer.

    Args:
        answer: Text containing citations

    Returns:
        List of (doc_id, excerpt) tuples
    """
    pattern = r"\[([^|\]]+)\|([^\]]*(?:\n[^\]]*)*)\]"
    matches = re.findall(pattern, answer)
    return matches


def collapse_duplicate_citations(text: str, output_format: str | None = None) -> str:
    """Collapse duplicate citations within citation clusters only.

    A citation cluster is a sequence of citations separated only by whitespace/commas.
    Within each cluster, remove duplicate citation numbers (keep first occurrence).
    Citations separated by regular text are in different clusters and both kept.

    Examples:
        [[1]][[2]][[1]] → [[1]][[2]] (cluster: remove duplicate 1)
        [[1]] text [[1]] → [[1]] text [[1]] (separate clusters: keep both)

    Args:
        text: Text with citation numbers (either [[1]](url) or <url|[1]> format)
        output_format: Output format ('slack' for Slack markdown, None for standard)

    Returns:
        Text with duplicate citations removed within each cluster
    """
    if output_format == "slack":
        # Single citation pattern for Slack: <url|[number]>
        single_citation = r"<[^>]+\|\[(\d+)\]>"
        # Cluster: one citation followed by (separator + citation)*
        cluster_pattern = rf"{single_citation}(?:[\s,]*{single_citation})*"
    else:
        # Single citation pattern for standard markdown: [[number]](url)
        single_citation = r"\[\[(\d+)\]\]\([^)]+\)"
        # Cluster: one citation followed by (separator + citation)*
        cluster_pattern = rf"{single_citation}(?:[\s,]*{single_citation})*"

    def process_cluster(match: re.Match[str]) -> str:
        """Process a single cluster of citations, removing duplicates."""
        cluster_text = match.group(0)

        # Find all citations in this cluster
        citations = list(re.finditer(single_citation, cluster_text))

        # Track which citation numbers we've seen in THIS cluster only
        seen_in_cluster: set[str] = set()
        result_parts = []
        last_end = 0

        for citation_match in citations:
            # Extract citation number
            number = citation_match.group(1)

            # Get any separator text before this citation
            separator = cluster_text[last_end : citation_match.start()]

            if number in seen_in_cluster:
                # Skip this duplicate citation (and its separator)
                pass
            else:
                # Keep this citation (and its separator)
                result_parts.append(separator)
                result_parts.append(citation_match.group(0))
                seen_in_cluster.add(number)

            last_end = citation_match.end()

        return "".join(result_parts)

    return re.sub(cluster_pattern, process_cluster, text)
