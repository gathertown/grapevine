"""Phase 2: Context investigation with parallel agents."""

import asyncio
from typing import Any, cast

from fastmcp.server.context import Context

from src.mcp.api.agent import stream_advanced_search_answer
from src.pr_reviewer.agents.prompts import (
    build_category_investigator_prompt,
    build_context_investigator_prompt,
)
from src.pr_reviewer.categories import ALL_CATEGORIES, VALID_CATEGORY_VALUES, Category
from src.pr_reviewer.models import DiffChunk
from src.pr_reviewer.utils.json_parsing import parse_llm_json
from src.utils.logging import get_logger
from src.utils.tenant_config import get_tenant_company_context, get_tenant_company_name

logger = get_logger(__name__)

# Configuration
MAX_BATCH_TOKENS = 40_000  # Leave room for system prompt, diff context, etc.
MAX_PATCH_TOKEN_LENGTH = 3_000  # Truncate diff patches to this many tokens
MAX_CONTEXT_TOKEN_LENGTH = 5_000  # Truncate code context to this many tokens


def estimate_change_tokens(
    change: dict[str, Any],
    file_contents: dict[str, str] | None,
    diff_chunks: list[DiffChunk] | None,
) -> int:
    """Estimate token count for a change with its context.

    Args:
        change: Change object with path, line/lines, and change description
        file_contents: Dictionary mapping filename to full file content
        diff_chunks: List of DiffChunk objects with patches

    Returns:
        Estimated token count (~4 chars per token)
    """
    total_chars = 0

    # Change description
    total_chars += len(change.get("change", ""))

    # Diff patch (if available)
    change_path = change.get("path", "")
    if diff_chunks:
        for chunk in diff_chunks:
            if chunk.filename == change_path:
                total_chars += len(chunk.patch[:MAX_PATCH_TOKEN_LENGTH])  # Truncated as in query
                break

    # Code context (if available)
    if file_contents and change_path in file_contents:
        # Extract actual code context to get accurate length
        change_line = change.get("line")
        change_lines = change.get("lines")
        line_num = change_line if change_line else (change_lines[0] if change_lines else 1)
        end_line = (
            change_line
            if change_line
            else (change_lines[1] if change_lines and len(change_lines) > 1 else line_num)
        )
        code_context = extract_code_context(file_contents[change_path], line_num, end_line)
        # Use minimum of actual context length and the MAX_CONTEXT_TOKEN_LENGTH char limit
        total_chars += min(len(code_context), MAX_CONTEXT_TOKEN_LENGTH)

    # PR context overhead
    total_chars += 500

    return total_chars // 4  # Rough token estimate


def batch_changes_by_tokens(
    changes: list[dict[str, Any]],
    file_contents: dict[str, str] | None,
    diff_chunks: list[DiffChunk] | None,
    max_tokens: int = MAX_BATCH_TOKENS,
) -> list[list[dict[str, Any]]]:
    """Batch changes dynamically based on token count.

    Args:
        changes: List of change objects
        file_contents: Dictionary mapping filename to full file content
        diff_chunks: List of DiffChunk objects with patches
        max_tokens: Maximum tokens per batch

    Returns:
        List of batches, where each batch is a list of changes
    """
    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    current_tokens = 0

    for change in changes:
        change_tokens = estimate_change_tokens(change, file_contents, diff_chunks)

        # If single change exceeds limit, put it in its own batch
        if change_tokens > max_tokens:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            batches.append([change])
            logger.warning(
                f"Change at {change.get('path', 'unknown')} exceeds token limit "
                f"({change_tokens} tokens), processing alone"
            )
            continue

        # If adding this change would exceed limit, start new batch
        if current_tokens + change_tokens > max_tokens:
            batches.append(current_batch)
            current_batch = [change]
            current_tokens = change_tokens
        else:
            current_batch.append(change)
            current_tokens += change_tokens

    # Add remaining batch
    if current_batch:
        batches.append(current_batch)

    logger.info(
        f"Batched {len(changes)} changes into {len(batches)} batch(es) "
        f"(max {max_tokens} tokens per batch)"
    )
    return batches


def extract_code_context(
    file_content: str,
    line_start: int,
    line_end: int | None = None,
    context_lines: int = 40,
) -> str:
    """Extract code context around changed lines.

    Args:
        file_content: Full file content
        line_start: Start line number (1-indexed)
        line_end: End line number (1-indexed), defaults to line_start
        context_lines: Number of lines to include before and after

    Example:
            44 |   @ga.computed
            45 |   get allOnboardingFlagsEnabled() {
            46 |     return (
            47 |       this.isMeetingForwardOnboardingEnabled &&
            48 |       this.isStatusForwardOnboardingEnabled &&
            49 |       this.autoLockDesksDefault &&
            50 |       this.enableAmbientAudio
            51 |     )
            52 |   }
            53 |
        >   54 |   @ga.computed
        >   55 |   get hasAllowedEmailDomains() {
        >   56 |     return this.allowedEmailDomains.length > 0
        >   57 |   }
            58 |
            59 |   toggleStudioEnabled = MethodAction({
            60 |     target: this,
            61 |     id: "toggleStudioEnabled",
            62 |     requiredPermission: SpaceSettingsPermission.UpdateSpaceSetting,
            63 |     fn: () => () => {
            64 |       this.isStudioEnabled = !this.isStudioEnabled
            65 |     },
            66 |   })
    """
    if not file_content:
        return ""

    lines = file_content.split("\n")
    if line_end is None:
        line_end = line_start

    # Convert to 0-indexed
    start_idx = max(0, line_start - 1 - context_lines)
    end_idx = min(len(lines), line_end + context_lines)

    # Extract lines and add line numbers
    context_lines_list = []
    for i in range(start_idx, end_idx):
        line_num = i + 1
        # Mark the actual changed lines
        marker = ">" if line_start <= line_num <= line_end else " "
        context_lines_list.append(f"{marker} {line_num:4d} | {lines[i]}")

    return "\n".join(context_lines_list)


async def run_parallel_investigations(
    changes: list[dict[str, Any]],
    pr_data: dict[str, Any],
    context: Context,
    repo_name: str,
    file_contents: dict[str, str] | None = None,
    diff_chunks: list[DiffChunk] | None = None,
) -> list[dict[str, Any]]:
    """Run agents in parallel to investigate batches of changes with category-specific agents.

    For each batch, runs multiple agents in parallel:
    - One agent per category (correctness, performance, security, reliability)
    - One general agent (no category)

    Args:
        changes: List of change objects with path, line/lines, and change description
        pr_data: PR metadata for context
        context: FastMCP context with tenant_id and other state
        repo_name: Repository name in "owner/repo" format
        file_contents: Dictionary mapping filename to full file content
        diff_chunks: List of DiffChunk objects with patches

    Returns:
        List of insight dictionaries with path, line/lines, insight, sources, and category
    """
    # Batch changes by token count
    batches = batch_changes_by_tokens(changes, file_contents, diff_chunks)

    num_agents_per_batch = len(ALL_CATEGORIES) + 1  # categories + general
    total_agents = len(batches) * num_agents_per_batch

    logger.info(
        f"Starting Phase 2: {len(changes)} changes → {len(batches)} batch(es) × "
        f"{num_agents_per_batch} agents = {total_agents} total LLM calls"
    )

    # Create tasks: for each batch, create tasks for all categories + one general agent
    tasks = []
    for batch in batches:
        # Category-specific agents
        for category in ALL_CATEGORIES:
            tasks.append(
                investigate_batch(
                    batch,
                    pr_data,
                    context,
                    repo_name=repo_name,
                    all_changes=changes,
                    file_contents=file_contents,
                    diff_chunks=diff_chunks,
                    category=category,
                )
            )
        # General agent (no category)
        tasks.append(
            investigate_batch(
                batch,
                pr_data,
                context,
                repo_name=repo_name,
                all_changes=changes,
                file_contents=file_contents,
                diff_chunks=diff_chunks,
                category=None,
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect insights from all investigations
    insights: list[dict[str, Any]] = []

    for i, result in enumerate(results, 1):
        if isinstance(result, Exception):
            # Any error should crash the script
            logger.error(f"Investigation {i}/{total_agents} encountered error: {result}")
            logger.error("Error detected in Phase 2, cannot continue")
            raise result

        # Result is list[dict[str, Any]] here (not an exception)
        investigation_insights = cast(list[dict[str, Any]], result)
        if investigation_insights:
            insights.extend(investigation_insights)
            logger.debug(
                f"Investigation {i}/{total_agents}: Found {len(investigation_insights)} insight(s)"
            )
        else:
            logger.debug(f"Investigation {i}/{total_agents}: No relevant insights found")

    logger.info(f"Phase 2 complete: {len(insights)} actionable insights found")
    return insights


async def investigate_batch(
    batch: list[dict[str, Any]],
    pr_data: dict[str, Any],
    context: Context,
    repo_name: str,
    all_changes: list[dict[str, Any]] | None = None,
    file_contents: dict[str, str] | None = None,
    diff_chunks: list[DiffChunk] | None = None,
    category: Category | None = None,
) -> list[dict[str, Any]]:
    """Investigate a batch of changes using company context.

    Args:
        batch: List of change objects to investigate together
        pr_data: PR metadata for context
        context: FastMCP context with tenant_id and other state
        repo_name: Repository name in "owner/repo" format
        all_changes: All changes in the PR (for context about related changes)
        file_contents: Dictionary mapping filename to full file content
        diff_chunks: List of DiffChunk objects with patches
        category: Optional category to focus on (correctness, performance, security, reliability).
                  If None, uses general context investigation prompt.

    Returns:
        List of insight dictionaries with path, line/lines, insight, sources, and category.
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

    # Build system prompt based on whether we have a category
    if category:
        system_prompt = await build_category_investigator_prompt(
            category=category,
            company_name=company_name,
            company_context_text=company_context_text,
            tenant_id=tenant_id,
        )
    else:
        system_prompt = await build_context_investigator_prompt(
            company_name=company_name,
            company_context_text=company_context_text,
            tenant_id=tenant_id,
        )

    # Build query with all changes in the batch
    pr_number = pr_data.get("number", 0)
    pr_title = pr_data.get("title", "")
    pr_body = pr_data.get("body", "")

    # Build sections of the query
    sections = []

    # PR Context section
    sections.append(f"""## PR Context
Repository: {repo_name}
PR #{pr_number}: {pr_title}""")

    if pr_body:
        sections.append(f"""
PR Description:
{pr_body}""")

    # Changes section - include all changes in batch
    sections.append(f"\n## Changes to Investigate ({len(batch)} changes)\n")

    for i, change in enumerate(batch, 1):
        change_path = change.get("path", "unknown")
        change_line = change.get("line")
        change_lines = change.get("lines")
        change_description = change.get("change", "")

        # Format line info
        if change_line:
            line_info = f"Line {change_line}"
        elif change_lines:
            line_info = f"Lines {change_lines}"
        else:
            line_info = "unknown lines"

        # Find the corresponding diff chunk
        diff_patch = ""
        file_status = "modified"
        if diff_chunks:
            for chunk in diff_chunks:
                if chunk.filename == change_path:
                    diff_patch = chunk.patch
                    file_status = chunk.status
                    break

        # Extract surrounding code context
        code_context = ""
        if file_contents and change_path in file_contents:
            line_num = change_line if change_line else (change_lines[0] if change_lines else 1)
            end_line = (
                change_line
                if change_line
                else (change_lines[1] if change_lines and len(change_lines) > 1 else line_num)
            )
            code_context = extract_code_context(file_contents[change_path], line_num, end_line)

        # Build change section
        sections.append(f"""### Change {i}: {change_path} ({file_status})
Location: {line_info}

**Change Description:**
{change_description}
""")

        # Code Change (diff)
        if diff_patch:
            sections.append(f"""**Code Change (Unified Diff):**
```diff
{diff_patch[:MAX_PATCH_TOKEN_LENGTH]}
```
""")

        # Surrounding Code Context
        if code_context:
            # Truncate to complete lines only to avoid mid-line cuts
            context_to_show = code_context
            if len(code_context) > MAX_CONTEXT_TOKEN_LENGTH:
                # Find the last newline within the limit
                truncation_point = code_context.rfind("\n", 0, MAX_CONTEXT_TOKEN_LENGTH)
                if truncation_point > 0:
                    # Include the newline character itself
                    context_to_show = code_context[: truncation_point + 1]
                else:
                    # No newline found (single very long line), truncate at limit
                    context_to_show = code_context[:MAX_CONTEXT_TOKEN_LENGTH]

            sections.append(f"""**Surrounding Code Context:**
(Lines marked with '>' are the changed lines)
```
{context_to_show}
```
""")

        sections.append("\n---\n")

    # Related changes context (changes not in this batch)
    if all_changes:
        other_changes = [c for c in all_changes if c not in batch]
        if other_changes:
            sections.append("\n## Other Changes in This PR\n")
            related_list = []
            for i, related_change in enumerate(other_changes[:15], 1):
                rel_path = related_change.get("path", "unknown")
                rel_line = related_change.get("line")
                rel_lines = related_change.get("lines")
                rel_desc = related_change.get("change", "")[:300]

                if rel_line:
                    loc = f"line {rel_line}"
                elif rel_lines:
                    loc = f"lines {rel_lines}"
                else:
                    loc = "unknown"

                related_list.append(f"  {i}. {rel_path}:{loc} - {rel_desc}")

            if len(other_changes) > 15:
                related_list.append(f"  ... and {len(other_changes) - 15} more changes")

            sections.append("\n".join(related_list))
            sections.append(
                "\n\nConsider whether these other changes might address or relate to concerns about the changes being investigated."
            )

    query = "\n".join(sections)

    # Call the agent
    category_str = f" ({category.value})" if category else " (general)"
    logger.info(f"Investigating batch of {len(batch)} changes{category_str}...")
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
        ):
            if event["type"] == "final_answer":
                final_answer = event.get("data", {}).get("answer", "")

        # Parse insight(s) from response and tag with category
        insights = parse_insights(final_answer, batch, category)
        return insights

    except Exception as e:
        logger.error(f"Investigation error for batch{category_str}: {e}")
        return []


async def investigate_change(
    change: dict[str, Any],
    pr_data: dict[str, Any],
    context: Context,
    repo_name: str,
    all_changes: list[dict[str, Any]] | None = None,
    file_contents: dict[str, str] | None = None,
    diff_chunks: list[DiffChunk] | None = None,
) -> list[dict[str, Any]]:
    """Investigate a single change using company context (wrapper for investigate_batch).

    Args:
        change: Change object with path, line/lines, and change description
        pr_data: PR metadata for context
        context: FastMCP context with tenant_id and other state
        repo_name: Repository name in "owner/repo" format
        all_changes: All changes in the PR (for context about related changes)
        file_contents: Dictionary mapping filename to full file content
        diff_chunks: List of DiffChunk objects with patches

    Returns:
        List of insight dictionaries with path, line/lines, insight, and sources.
        Returns empty list if no relevant context found.
    """
    # Delegate to investigate_batch with a single-item batch
    return await investigate_batch(
        batch=[change],
        pr_data=pr_data,
        context=context,
        repo_name=repo_name,
        all_changes=all_changes,
        file_contents=file_contents,
        diff_chunks=diff_chunks,
    )


def parse_insights(
    text: str, batch: list[dict[str, Any]], category: Category | None = None
) -> list[dict[str, Any]]:
    """Parse insights from batch investigation response.

    Args:
        text: Response text from agent containing JSON array
        batch: List of changes that were investigated (for fallback context)
        category: The category this investigation focused on (or None for general)

    Returns:
        List of insight dictionaries with path, line/lines, insight, sources, and category.
        Returns empty list if no insights found.
    """

    def validate_insight(insight_data: dict[str, Any]) -> dict[str, Any] | None:
        """Validate insight structure."""
        # Must have insight field (or no_insight flag)
        if "insight" not in insight_data and not insight_data.get("no_insight"):
            return None

        # Skip no_insight responses
        if insight_data.get("no_insight"):
            return None

        # Path is required
        if "path" not in insight_data:
            logger.warning("Insight missing 'path' field, skipping")
            return None

        # Ensure line or lines field is present
        if "line" not in insight_data and "lines" not in insight_data:
            logger.warning(f"Insight for {insight_data['path']} missing line info, skipping")
            return None

        # Ensure sources is a list
        if "sources" not in insight_data:
            insight_data["sources"] = []

        # Parse and validate impact if present
        impact = insight_data.get("impact")
        if impact is not None:
            try:
                impact = int(impact)
                if not 0 <= impact <= 100:
                    logger.warning(f"Impact {impact} out of range [0, 100], setting to None")
                    impact = None
            except (ValueError, TypeError):
                logger.warning(f"Invalid impact value: {impact}, setting to None")
                impact = None
        insight_data["impact"] = impact

        # Validate impact_reason if present
        impact_reason = insight_data.get("impact_reason")
        if impact_reason is not None:
            if not isinstance(impact_reason, str) or not impact_reason.strip():
                logger.warning(f"Invalid impact_reason: {impact_reason}, setting to None")
                impact_reason = None
            else:
                impact_reason = impact_reason.strip()
        insight_data["impact_reason"] = impact_reason

        # Parse and validate confidence if present
        confidence = insight_data.get("confidence")
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
        insight_data["confidence"] = confidence

        # Validate confidence_reason if present
        confidence_reason = insight_data.get("confidence_reason")
        if confidence_reason is not None:
            if not isinstance(confidence_reason, str) or not confidence_reason.strip():
                logger.warning(f"Invalid confidence_reason: {confidence_reason}, setting to None")
                confidence_reason = None
            else:
                confidence_reason = confidence_reason.strip()
        insight_data["confidence_reason"] = confidence_reason

        # Set category from the investigation's category parameter
        # (overrides any category the LLM might have returned)
        if category:
            insight_data["category"] = category.value
        else:
            # General investigation - validate category if present or set to "other"
            insight_category = insight_data.get("category")
            if insight_category and insight_category in VALID_CATEGORY_VALUES:
                insight_data["category"] = insight_category
            else:
                insight_data["category"] = "other"

        # Set source_agent: indicates which agent produced this finding
        if category:
            insight_data["source_agent"] = category.value
        else:
            insight_data["source_agent"] = "general"

        return insight_data

    def validate_insight_list(
        insight_list: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """Validate a list of insights."""
        validated = []
        for item in insight_list:
            if isinstance(item, dict):
                validated_item = validate_insight(item)
                if validated_item is not None:
                    validated.append(validated_item)
        return validated if validated else None

    # Try to parse as a list
    try:
        insight_list = parse_llm_json(
            text,
            expected_type=list,
            validator=validate_insight_list,
        )
        if insight_list:
            return insight_list
    except ValueError as e:
        logger.warning(f"Could not parse insights as list: {e}")

    # Fallback: try parsing as single object
    try:
        insight_data = parse_llm_json(
            text,
            expected_type=dict,
            validator=validate_insight,
        )
        return [insight_data] if insight_data else []
    except ValueError:
        logger.warning(f"Could not parse insights from response: {text[:200]}...")
        return []


def parse_insight(text: str, change: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse insight(s) from agent response (legacy single-change version).

    Args:
        text: Response text from agent
        change: Original change object being investigated

    Returns:
        List of insight dictionaries with path, line/lines, insight, and sources.
        Returns empty list if no insights found or no_insight response.
    """

    def validate_insight(insight_data: dict[str, Any]) -> dict[str, Any] | None:
        """Validate insight structure (not semantic meaning)."""
        # Validate that we have the required insight field
        # Note: We allow no_insight responses to pass validation since they're
        # structurally valid - the semantic check happens after parsing
        if "insight" not in insight_data and not insight_data.get("no_insight"):
            return None

        # Ensure path field is present (fallback to original change)
        if "path" not in insight_data:
            insight_data["path"] = change.get("path", "unknown")

        # Ensure line or lines field is present (fallback to original change)
        if "line" not in insight_data and "lines" not in insight_data:
            if "line" in change:
                insight_data["line"] = change["line"]
            elif "lines" in change:
                insight_data["lines"] = change["lines"]

        # Ensure sources is a list
        if "sources" not in insight_data:
            insight_data["sources"] = []

        # Parse and validate impact if present
        impact = insight_data.get("impact")
        if impact is not None:
            try:
                impact = int(impact)
                if not 0 <= impact <= 100:
                    logger.warning(f"Impact {impact} out of range [0, 100], setting to None")
                    impact = None
            except (ValueError, TypeError):
                logger.warning(f"Invalid impact value: {impact}, setting to None")
                impact = None
        insight_data["impact"] = impact

        # Validate impact_reason if present (should be a non-empty string)
        impact_reason = insight_data.get("impact_reason")
        if impact_reason is not None:
            if not isinstance(impact_reason, str) or not impact_reason.strip():
                logger.warning(f"Invalid impact_reason: {impact_reason}, setting to None")
                impact_reason = None
            else:
                impact_reason = impact_reason.strip()
        insight_data["impact_reason"] = impact_reason

        # Parse and validate confidence if present
        confidence = insight_data.get("confidence")
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
        insight_data["confidence"] = confidence

        # Validate confidence_reason if present (should be a non-empty string)
        confidence_reason = insight_data.get("confidence_reason")
        if confidence_reason is not None:
            if not isinstance(confidence_reason, str) or not confidence_reason.strip():
                logger.warning(f"Invalid confidence_reason: {confidence_reason}, setting to None")
                confidence_reason = None
            else:
                confidence_reason = confidence_reason.strip()
        insight_data["confidence_reason"] = confidence_reason

        return insight_data

    def validate_insight_list(
        insight_list: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """Validate a list of insights."""
        validated = []
        for item in insight_list:
            if isinstance(item, dict):
                validated_item = validate_insight(item)
                if validated_item is not None:
                    validated.append(validated_item)
        return validated if validated else None

    # Try to parse as a list first (LLM may return multiple insights)
    try:
        insight_list = parse_llm_json(
            text,
            expected_type=list,
            validator=validate_insight_list,
        )
        # Filter out no_insight responses
        return [i for i in insight_list if not i.get("no_insight")]
    except ValueError:
        pass

    # Fall back to parsing as a single dict
    try:
        insight_data = parse_llm_json(
            text,
            expected_type=dict,
            validator=validate_insight,
        )

        # Handle semantic "no result" case after successful parsing
        if insight_data and insight_data.get("no_insight"):
            logger.info("Agent returned no_insight response")
            return []

        return [insight_data] if insight_data else []
    except ValueError:
        logger.warning(f"Could not parse insight from response: {text[:200]}...")
        return []
