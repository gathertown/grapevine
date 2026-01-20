"""Phase 3: Final review synthesis from insights."""

import asyncio
import json
import uuid
from typing import Any

from fastmcp.server.context import Context

from src.mcp.api.agent import stream_advanced_search_answer
from src.pr_reviewer.agents.prompts import build_review_synthesizer_prompt
from src.pr_reviewer.categories import VALID_CATEGORY_VALUES
from src.pr_reviewer.models import DiffChunk, ExistingReviewComment
from src.pr_reviewer.utils.json_parsing import parse_llm_json
from src.utils.logging import get_logger
from src.utils.tenant_config import get_tenant_company_context, get_tenant_company_name

logger = get_logger(__name__)


def extract_valid_line_ranges(diff_chunks: list[DiffChunk]) -> dict[str, list[tuple[int, int]]]:
    """Extract valid line ranges per file from diff chunks.

    Args:
        diff_chunks: List of DiffChunk objects with line ranges

    Returns:
        Dictionary mapping filename to list of (start, end) line range tuples
    """
    valid_ranges: dict[str, list[tuple[int, int]]] = {}

    for chunk in diff_chunks:
        filename = chunk.filename
        if filename not in valid_ranges:
            valid_ranges[filename] = []
        valid_ranges[filename].append((chunk.line_start, chunk.line_end))

    return valid_ranges


async def generate_final_review(
    pr_data: dict[str, Any],
    all_insights: list[dict[str, Any]],
    context: Context,
    repo_name: str,
    diff_chunks: list[DiffChunk] | None = None,
    existing_comments: list[ExistingReviewComment] | None = None,
) -> dict[str, Any]:
    """Generate final structured review from insights.

    Args:
        pr_data: PR metadata and description
        all_insights: All insights collected from Phase 2
        context: FastMCP context with tenant_id and other state
        repo_name: Repository name in "owner/repo" format
        diff_chunks: List of DiffChunk objects with valid line ranges for commenting
        existing_comments: List of existing review comments on the PR to avoid duplicating

    Returns:
        Dictionary with 'decision' and 'comments' matching ground truth format
    """
    logger.info(f"Starting Phase 3: Final review synthesis from {len(all_insights)} insights")

    # Extract tenant_id from context for company info lookup
    from src.mcp.middleware.org_context import _extract_tenant_id_from_context

    tenant_id = _extract_tenant_id_from_context(context)
    if not tenant_id:
        raise ValueError("tenant_id not found in context")

    # Get tenant-specific company information
    company_name, company_context_text = await asyncio.gather(
        get_tenant_company_name(tenant_id),
        get_tenant_company_context(tenant_id),
    )

    # Extract valid line ranges from diff chunks
    valid_line_ranges = extract_valid_line_ranges(diff_chunks) if diff_chunks else {}

    # Build system prompt with review synthesis instructions
    system_prompt = await build_review_synthesizer_prompt(
        company_name=company_name,
        company_context_text=company_context_text,
        tenant_id=tenant_id,
        valid_line_ranges=valid_line_ranges,
        existing_comments=existing_comments,
    )

    # Build query with PR data and insights
    pr_number = pr_data.get("number", 0)
    pr_title = pr_data.get("title", "")
    pr_body = pr_data.get("body", "") or ""

    query = f"""Synthesize a final Pull Request review from the investigation findings.

Repository: {repo_name}
PR #{pr_number}: {pr_title}

Description:
{pr_body}

Investigation Insights:
{json.dumps(all_insights, indent=2)}

Generate a structured code review following the JSON format specified in your instructions."""

    # Call the agent
    logger.info("Calling agent for final review synthesis...")
    final_answer = ""

    try:
        async for event in stream_advanced_search_answer(
            query=query,
            system_prompt=system_prompt,
            context=context,
            previous_response_id=None,
            files=None,
            reasoning_effort="medium",
            verbosity="low",
            output_format=None,
            model="gpt-5",
            disable_citations=True,
        ):
            if event["type"] == "final_answer":
                final_answer = event.get("data", {}).get("answer", "")

        logger.info(f"Received review synthesis ({len(final_answer)} chars)")

        # Parse review from response
        review = parse_llm_json(
            final_answer,
            expected_type=dict,
            validator=validate_review,
        )

        # Sort comments by impact first, then confidence (highest first, None values at the end)
        if review.get("comments"):
            review["comments"].sort(
                key=lambda c: (
                    c.get("impact") is not None,
                    c.get("impact") or 0,
                    c.get("confidence") is not None,
                    c.get("confidence") or 0,
                ),
                reverse=True,
            )
            logger.info(
                f"Sorted {len(review['comments'])} comments by impact then confidence (highest first)"
            )

            # Generate UUID for each comment for robust matching after GitHub posting
            for comment in review["comments"]:
                comment["comment_id"] = str(uuid.uuid4())
            logger.info(f"Generated UUIDs for {len(review['comments'])} comments")

        return review

    except Exception as e:
        # Any error should crash the script
        logger.error(f"Error in review synthesis: {e}")
        logger.error("Error detected in Phase 3, cannot continue")
        raise


def validate_review(review_data: dict[str, Any]) -> dict[str, Any] | None:
    """Validate review structure and normalize fields.

    Args:
        review_data: Parsed review dictionary

    Returns:
        Validated review or None if invalid
    """
    # Ensure decision field exists
    if "decision" not in review_data:
        return None

    # Ensure comments is a list
    if "comments" not in review_data:
        review_data["comments"] = []

    # Validate decision value
    valid_decisions = ["APPROVE", "CHANGES_REQUESTED", "COMMENT"]
    if review_data["decision"] not in valid_decisions:
        logger.warning(f"Invalid decision: {review_data['decision']}, defaulting to COMMENT")
        review_data["decision"] = "COMMENT"

    # Parse and validate impact, impact_reason, confidence, and confidence_reason for each comment
    for comment in review_data["comments"]:
        # Validate impact
        impact = comment.get("impact")
        if impact is not None:
            try:
                impact = int(impact)
                if not 0 <= impact <= 100:
                    logger.warning(f"Impact {impact} out of range [0, 100], setting to None")
                    impact = None
            except (ValueError, TypeError):
                logger.warning(f"Invalid impact value: {impact}, setting to None")
                impact = None
        comment["impact"] = impact

        # Validate impact_reason (should be a non-empty string)
        impact_reason = comment.get("impact_reason")
        if impact_reason is not None:
            if not isinstance(impact_reason, str) or not impact_reason.strip():
                logger.warning(f"Invalid impact_reason: {impact_reason}, setting to None")
                impact_reason = None
            else:
                impact_reason = impact_reason.strip()
        comment["impact_reason"] = impact_reason

        # Validate confidence
        confidence = comment.get("confidence")
        if confidence is not None:
            try:
                confidence = int(confidence)
                if not 0 <= confidence <= 100:
                    logger.warning(
                        f"Confidence {confidence} out of range [0, 100], setting to None"
                    )
                    confidence = None
            except (ValueError, TypeError):
                logger.warning(f"Invalid confidence value: {confidence}, setting to None")
                confidence = None
        comment["confidence"] = confidence

        # Validate confidence_reason (should be a non-empty string)
        confidence_reason = comment.get("confidence_reason")
        if confidence_reason is not None:
            if not isinstance(confidence_reason, str) or not confidence_reason.strip():
                logger.warning(f"Invalid confidence_reason: {confidence_reason}, setting to None")
                confidence_reason = None
            else:
                confidence_reason = confidence_reason.strip()
        comment["confidence_reason"] = confidence_reason

        # Validate categories (should be a non-empty list of valid category strings)
        categories = comment.get("categories")
        if categories is not None:
            if not isinstance(categories, list):
                logger.warning(f"Invalid categories (not a list): {categories}, setting to None")
                categories = None
            else:
                # Filter to only valid categories
                filtered = [
                    c for c in categories if isinstance(c, str) and c in VALID_CATEGORY_VALUES
                ]
                if not filtered:
                    logger.warning(f"No valid categories in: {categories}, setting to None")
                    categories = None
                else:
                    categories = filtered
        comment["categories"] = categories

    logger.info(f"Parsed review: {json.dumps(review_data, indent=2)}")
    return review_data
