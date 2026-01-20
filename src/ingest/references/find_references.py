"""
Document reference finding implementation.

This module analyzes document content to find references to other documents
and returns a mapping of referenced document IDs to their occurrence counts.
"""

import re
from collections import defaultdict
from collections.abc import Callable

from src.ingest.references.reference_ids import (
    get_github_file_reference_id,
    get_github_pr_reference_id,
    get_gong_call_reference_id,
    get_google_drive_file_reference_id,
    get_linear_issue_reference_id,
    get_notion_page_reference_id,
    get_salesforce_reference_id,
)


def _strip_contributors_from_notion_header(content: str) -> str:
    """
    Notion docs include a Contributors line in the header with user mentions.
    Strip them out so we don't confuse those UUIDs for document references.
    """
    # See NotionPageDocument for where this line comes from
    return re.sub(r"^Contributors:.*$", "", content, flags=re.MULTILINE)


# Pattern definitions with their corresponding reference ID builders
# Each pattern can be either:
# - (pattern, ref_builder) tuple for simple patterns
# - (pattern, ref_builder, preprocess_function) tuple for patterns that need content preprocessing
DOC_REFERENCE_PATTERNS: list[tuple[str, Callable] | tuple[str, Callable, Callable[[str], str]]] = [
    # Linear issue identifier pattern (e.g., ENG-123, PROD-456) - excludes matches inside URLs
    (
        r"(?<!/)([A-Z]{2,4}-\d+)(?!/)\b",
        lambda m: get_linear_issue_reference_id(issue_id=m.group(1)),
    ),
    # Linear URL pattern
    (
        r"https://linear\.app/[^/]+/issue/([A-Z]+-\d+)(?:/[^\s]*)?",
        lambda m: get_linear_issue_reference_id(issue_id=m.group(1)),
    ),
    # GitHub PR URL pattern
    (
        r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)",
        lambda m: get_github_pr_reference_id(
            owner=m.group(1), repo=m.group(2), pr_number=m.group(3)
        ),
    ),
    # GitHub PR shorthand reference pattern (org/repo#123)
    (
        r"\b([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)#(\d+)\b",
        lambda m: get_github_pr_reference_id(
            owner=m.group(1), repo=m.group(2), pr_number=m.group(3)
        ),
    ),
    # Graphite PR URL pattern
    (
        r"https://app\.graphite\.dev/github/pr/([^/]+)/([^/]+)/(\d+)(?:/[^/\s]*)?",
        lambda m: get_github_pr_reference_id(
            owner=m.group(1), repo=m.group(2), pr_number=m.group(3)
        ),
    ),
    # GitHub file blob URL pattern
    (
        r'https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+?)(?:\s|$|[<>"\'#])',
        lambda m: get_github_file_reference_id(
            owner=m.group(1), repo=m.group(2), file_path=m.group(4)
        ),
    ),
    # Google Drive file URL pattern
    (
        r"https://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)(?:/[^/\s]*)?(?:\?[^\s]*)?",
        lambda m: get_google_drive_file_reference_id(file_id=m.group(1)),
    ),
    # Gong call URL pattern
    (
        r"https://[\w.-]+\.gong\.io/call\?id=(\d+)",
        lambda m: get_gong_call_reference_id(call_id=m.group(1)),
    ),
    # Slack message URL pattern. TODO: AIVP-384 figure out how to handle references to Slack docs
    # (
    #     r'https://([^.\s]+)\.slack\.com/archives/([A-Z0-9]{3,11})/p(\d{16})(?:\?[^"\s]*)?',
    #     lambda m: get_slack_doc_reference_id(
    #         workspace=m.group(1), channel_id=m.group(2), timestamp=m.group(3)
    #     ),
    # ),
    # Notion URL pattern with UUID
    (
        r"https://(?:www\.)?notion\.so/(?:[^/]+/)?(?:[^/]+-)?([a-fA-F0-9]{8}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{12})",
        lambda m: get_notion_page_reference_id(page_uuid=m.group(1)),
        _strip_contributors_from_notion_header,
    ),
    # Notion direct UUID pattern (with dashes)
    (
        r"(?<![\w/-])([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})(?![\w/-])",
        lambda m: get_notion_page_reference_id(page_uuid=m.group(1)),
        _strip_contributors_from_notion_header,
    ),
    # Notion direct UUID pattern (without dashes, 32 hex chars)
    (
        r"(?<![\w/-])([a-fA-F0-9]{32})(?![\w/-])",
        lambda m: get_notion_page_reference_id(page_uuid=m.group(1)),
        _strip_contributors_from_notion_header,
    ),
    # Salesforce Lightning URL pattern with object type
    (
        r"https://[^/]+(?:\.lightning\.force\.com|\.my\.salesforce\.com|\.salesforce\.com)/lightning/r/([A-Za-z]+)/([a-zA-Z0-9]{15}(?![a-zA-Z0-9])|[a-zA-Z0-9]{18}(?![a-zA-Z0-9]))(?:/[^\s]*)?",
        lambda m: get_salesforce_reference_id(object_type=m.group(1), record_id=m.group(2)),
    ),
]


def find_references_in_doc(content: str, doc_reference_id: str) -> dict[str, int]:
    """
    Find all references to other documents within the content of a given document.

    Args:
        content: The content of the document to analyze for references
        doc_reference_id: The reference ID (see reference_ids.py) of the document to exclude from results

    Returns:
        Dictionary mapping document IDs to their occurrence counts
        Example: {"notion_page_123": 2, "linear_issue_456": 1}
    """
    if not content:
        return {}

    # Track reference counts
    reference_counts: dict[str, int] = defaultdict(int)

    # Find all potential references using different patterns
    for pattern_tuple in DOC_REFERENCE_PATTERNS:
        if len(pattern_tuple) == 3:
            pattern, ref_builder, preprocess_func = (
                pattern_tuple[0],
                pattern_tuple[1],
                pattern_tuple[2],
            )
            _apply_pattern(content, pattern, ref_builder, reference_counts, preprocess_func)
        else:
            pattern, ref_builder = pattern_tuple[0], pattern_tuple[1]
            _apply_pattern(content, pattern, ref_builder, reference_counts)

    # Remove self-references
    if doc_reference_id in reference_counts:
        del reference_counts[doc_reference_id]

    return dict(reference_counts)


def _apply_pattern(
    content: str,
    pattern: str,
    ref_builder: Callable,
    reference_counts: dict[str, int],
    preprocess_func: Callable[[str], str] | None = None,
) -> None:
    """Apply a single regex pattern and count references."""
    # Apply preprocessing if provided
    search_content = preprocess_func(content) if preprocess_func else content

    for match in re.finditer(pattern, search_content):
        ref_id = ref_builder(match)
        reference_counts[ref_id] += 1
