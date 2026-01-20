"""Phase 1: Initial PR analysis with parallel agents."""

import asyncio
import json
from typing import Any, cast

from fastmcp.server.context import Context

from src.mcp.api.agent import stream_advanced_search_answer
from src.pr_reviewer.agents.prompts import build_initial_analyzer_prompt
from src.pr_reviewer.models import DiffChunk
from src.pr_reviewer.utils.json_parsing import parse_llm_json
from src.utils.logging import get_logger
from src.utils.tenant_config import get_tenant_company_context, get_tenant_company_name

logger = get_logger(__name__)


async def run_parallel_initial_analysis(
    pr_data: dict[str, Any],
    file_contents: dict[str, str],
    diff_chunks: list[DiffChunk],
    context: Context,
    repo_name: str,
    num_agents: int = 3,
) -> list[dict[str, Any]]:
    """Run multiple agents in parallel for initial PR analysis.

    Args:
        pr_data: PR metadata and description
        file_contents: Dictionary mapping filenames to full content
        diff_chunks: List of DiffChunk objects with changes
        context: FastMCP context with tenant_id and other state
        repo_name: Repository name in "owner/repo" format
        num_agents: Number of parallel agents to run (default: 3)

    Returns:
        Combined list of change objects with path, line/lines, and change description
    """
    logger.info(f"Starting Phase 1: Initial analysis with {num_agents} agents")

    # Run agents in parallel
    tasks = [
        analyze_pr_changes(pr_data, file_contents, diff_chunks, agent_num, context, repo_name)
        for agent_num in range(1, num_agents + 1)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Combine all change objects
    all_changes: list[dict[str, Any]] = []

    for i, result in enumerate(results, 1):
        if isinstance(result, Exception):
            # Any error should crash the script
            logger.error(f"Agent {i} encountered error: {result}")
            logger.error("Error detected in Phase 1, cannot continue")
            raise result

        # Result is list[dict] here (not an exception)
        changes = cast(list[dict[str, Any]], result)
        all_changes.extend(changes)
        logger.info(f"Agent {i} returned {len(changes)} changes")

    logger.info(f"Phase 1 complete: {len(all_changes)} total changes collected")
    return all_changes


async def analyze_pr_changes(
    pr_data: dict[str, Any],
    file_contents: dict[str, str],
    diff_chunks: list[DiffChunk],
    agent_num: int,
    context: Context,
    repo_name: str,
) -> list[dict[str, Any]]:
    """Single agent analyzing PR changes.

    Args:
        pr_data: PR metadata and description
        file_contents: Dictionary mapping filenames to full content
        diff_chunks: List of DiffChunk objects with changes
        agent_num: Agent number for logging
        context: FastMCP context with tenant_id and other state
        repo_name: Repository name in "owner/repo" format

    Returns:
        List of change objects with path, line/lines, and change description
    """

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

    # Build system prompt with initial analysis instructions
    system_prompt = await build_initial_analyzer_prompt(
        company_name=company_name,
        company_context_text=company_context_text,
    )

    # Build query with PR data and changes
    pr_number = pr_data.get("number", 0)
    pr_title = pr_data.get("title", "")
    pr_body = pr_data.get("body", "") or ""

    # Format file changes with both diffs and full content
    changes_summary = []
    for chunk in diff_chunks:
        filename = chunk.filename
        patch = chunk.patch
        full_content = file_contents.get(filename, "[Content not available]")

        changes_summary.append(
            {
                "filename": filename,
                "lineStart": chunk.line_start,
                "lineEnd": chunk.line_end,
                "status": chunk.status,
                "patch": patch,
                "full_file_content": full_content[:10000],  # Limit to 10k chars per file
            }
        )

    query = f"""Analyze this GitHub Pull Request and provide a detailed list of the specific changes being made.

Repository: {repo_name}
PR #{pr_number}: {pr_title}

Description:
{pr_body}

File Changes:
{json.dumps(changes_summary, indent=2)}
"""

    # Call the agent
    logger.info(f"Agent {agent_num}: Calling agent loop...")
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

        logger.info(f"Agent {agent_num}: Received answer ({len(final_answer)} chars)")

        # Parse change objects from the answer
        changes = parse_changes_from_response(final_answer)
        return changes

    except Exception as e:
        logger.error(f"Agent {agent_num} error: {e}")
        return []


def parse_changes_from_response(text: str) -> list[dict[str, Any]]:
    """Parse change objects from agent response.

    Args:
        text: Response text from agent containing JSON array

    Returns:
        List of change objects with path, line/lines, and change description
    """

    # Parse JSON array from response
    changes = parse_llm_json(
        text,
        expected_type=list,
    )
    return changes
