"""MCP tool for reviewing GitHub PRs with streaming progress updates."""

import json
from typing import Annotated

from fastmcp.server.context import Context
from pydantic import Field

from src.mcp.mcp_instance import get_mcp
from src.mcp.middleware.org_context import (
    _extract_non_billable_from_context,
    _extract_tenant_id_from_context,
)
from src.pr_reviewer import PRReviewer
from src.utils.logging import get_logger
from src.utils.usage_tracker import get_usage_tracker

logger = get_logger(__name__)


@get_mcp().tool(
    description="""Review a GitHub pull request using multi-stage agent analysis with streaming progress updates.

This tool performs a 3-phase analysis of a PR:
1. Initial Analysis: Analyze changes in the PR
2. Context Investigation: Multiple agents investigate each change for issues
3. Review Synthesis: Generate final structured review with decision and comments

The tool streams progress updates during each phase, allowing clients to see real-time status.

Returns:
- {"decision": string, "comments": list, "events": list}

Events include:
- status: Progress messages
- phase_complete: Completion of each analysis phase with intermediate results
- final_review: The complete review with decision and comments
"""
)
async def review_pr_streaming(
    context: Context,
    pr_number: Annotated[int, Field(description="Pull request number to review")],
    repo_url: Annotated[
        str,
        Field(description="GitHub repository URL or owner/repo format."),
    ],
    github_token: Annotated[
        str,
        Field(description="GitHub personal access token"),
    ],
) -> dict:
    """Review a GitHub PR with streaming progress updates.

    Args:
        context: FastMCP context for streaming updates
        pr_number: Pull request number to review
        repo_url: GitHub repository URL or owner/repo format
        github_token: GitHub token

    Returns:
        Dictionary with decision, comments, and event transcript
    """
    if pr_number <= 0:
        raise ValueError("pr_number must be a positive integer")

    # Extract tenant_id and non_billable for usage tracking
    tenant_id = _extract_tenant_id_from_context(context)
    if not tenant_id:
        raise ValueError("tenant_id not found in context")

    non_billable = _extract_non_billable_from_context(context)

    # Check usage limits and record usage
    usage_tracker = get_usage_tracker()
    usage_result = await usage_tracker.check_and_record_usage(
        tenant_id=tenant_id,
        usage_metrics={"requests": 1},
        source_type="review_pr_streaming",
        non_billable=non_billable,
    )

    # Return usage limit message if limits exceeded
    if not usage_result.allowed:
        from src.utils.usage_limit_message import generate_usage_limit_message

        usage_message = await generate_usage_limit_message(tenant_id, usage_result)
        return {
            "decision": "ERROR",
            "comments": [],
            "error": usage_message,
            "events": [],
        }

    # Create reviewer instance
    reviewer = PRReviewer(
        github_token=github_token,
    )

    # Stream events and collect final review
    final_review = None
    events = []

    try:
        async for event in reviewer.review_pr_streaming(
            repo_url=repo_url,
            pr_number=pr_number,
            context=context,
        ):
            # Send streaming update to client
            await context.info(json.dumps(event))

            # Collect events for final response
            events.append(event)

            if event.get("type") == "final_review":
                final_review = event.get("data")

    except Exception as e:
        error_msg = f"Error reviewing PR: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await context.error(error_msg)
        return {
            "decision": "ERROR",
            "comments": [],
            "error": error_msg,
            "events": events,
        }

    # Normalize result
    if not final_review:
        error_msg = "Review completed but no final review was generated"
        await context.error(error_msg)
        return {
            "decision": "ERROR",
            "comments": [],
            "error": error_msg,
            "events": events,
        }

    return {
        "decision": final_review.get("decision"),
        "comments": final_review.get("comments", []),
        "events": events[-50:],  # cap transcript length for response size
    }
