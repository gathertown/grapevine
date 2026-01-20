"""
Functions to query MCP tools based on queries from evaluation files.
"""

import asyncio
import json
import re
from typing import Any

from connectors.base.document_source import DocumentSource
from src.mcp.api.tool_executor import get_tool_executor
from src.mcp.tools import register_tools
from src.utils.config import get_database_url, get_opensearch_url


def parse_eval_file(filepath: str) -> list[dict[str, Any]]:
    """Parse the simplified_eval.jsonl file which can be in JSONL or non-standard JSON format."""
    with open(filepath) as f:
        content = f.read()

    content = content.strip()
    objects = []

    # First, try to parse as standard JSONL (one JSON object per line)
    try:
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line:
                obj = json.loads(line)
                if "type" in obj and "query" in obj:  # Valid query object
                    objects.append(obj)
        if objects:  # Successfully parsed as JSONL
            return objects
    except json.JSONDecodeError:
        # If JSONL parsing fails, try the old format
        pass

    # Fall back to old format parsing
    # The file contains a single JSON object with nested objects
    # First, try to parse it as valid JSON by fixing the format
    # Function to convert sets to arrays
    def convert_sets_to_arrays(match):
        set_content = match.group(1)
        # Remove trailing comma if present
        set_content = re.sub(r",\s*}", "}", set_content)
        # Convert to array format
        items = []
        # Split by lines and clean up
        lines = set_content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and line != "{" and line != "}":
                # Remove trailing comma
                line = line.rstrip(",")
                if line:
                    items.append(line)
        return "[" + ",\n".join(items) + "]"

    # Replace gather_results and glean_results sets with arrays
    content = re.sub(
        r'"gather_results":\s*{([^}]+)}',
        lambda m: '"gather_results": ' + convert_sets_to_arrays(m),
        content,
    )
    content = re.sub(
        r'"glean_results":\s*{([^}]+)}',
        lambda m: '"glean_results": ' + convert_sets_to_arrays(m),
        content,
    )

    # Now parse the individual query objects
    # The file structure is { { query1 }, { query2 }, ... }
    # We need to extract each query object

    # Remove outer braces and split by top-level objects
    if content.startswith("{") and content.endswith("}"):
        content = content[1:-1].strip()

    # Use regex to find each object
    # Pattern matches { ... }, accounting for nested braces
    pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"

    matches = re.finditer(pattern, content)

    for match in matches:
        obj_str = match.group(0)
        try:
            # Parse the JSON object
            obj = json.loads(obj_str)
            if "type" in obj and "query" in obj:  # Valid query object
                objects.append(obj)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON object: {e}")
            print(f"Object string: {obj_str[:100]}...")

    return objects


def extract_sources_from_results(results: list[dict[str, Any]]) -> list[str]:
    """Extract unique sources from the MCP tool results."""
    sources = set()

    for result in results:
        # For keyword_search results
        if "source" in result:
            sources.add(result["source"])

        # For semantic_search results (document_id can help identify source)
        if "document_id" in result:
            doc_id = result["document_id"]
            # Extract source type from document_id if it follows a pattern
            if doc_id.startswith("github_file_"):
                sources.add(DocumentSource.GITHUB_CODE)
            elif doc_id.startswith("slack_"):
                sources.add(DocumentSource.SLACK)
            elif doc_id.startswith("notion_"):
                sources.add(DocumentSource.NOTION)
            elif doc_id.startswith("linear_") or doc_id.startswith("issue_"):
                sources.add(DocumentSource.LINEAR)
            else:
                # Try to infer from metadata
                metadata = result.get("metadata", {})
                if "channel_name" in metadata or "channel_id" in metadata:
                    sources.add(DocumentSource.SLACK)
                elif "pr_title" in metadata or "repo_name" in metadata:
                    sources.add(DocumentSource.GITHUB_PRS)
                elif "page_title" in metadata or "page_id" in metadata:
                    sources.add(DocumentSource.NOTION)
                elif "issue_title" in metadata or "issue_id" in metadata:
                    sources.add(DocumentSource.LINEAR)
                elif "file_path" in metadata or "repository" in metadata:
                    sources.add(DocumentSource.GITHUB_CODE)

    return list(sources)


async def query_mcp_tool(
    tool_name: str, query: str, filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Query the specified MCP tool and return results."""
    # Get tool executor instance
    tool_executor = await get_tool_executor()

    # Prepare parameters
    params = {
        "query": query,
        "limit": 25,  # Get more results to show top 10 vs additional results
    }

    # Add filters if provided
    if filters:
        params["filters"] = filters

    try:
        result = await tool_executor.call_tool(tool_name, params)

        if result.get("success") == True:
            return result.get("result", {"results": [], "count": 0})  # type: ignore
        else:
            return {"results": [], "count": 0}
    except Exception as e:
        print(f"  Error calling tool: {e}")
        return {"results": [], "count": 0}


async def process_eval_queries(
    eval_file_path: str, output_file_path: str | None = None, progress_callback=None
) -> str:
    """
    Process queries from an evaluation file and return results.

    Args:
        eval_file_path: Path to the evaluation file
        output_file_path: Optional path to save results. If None, generates default name.
        progress_callback: Optional callback function to report progress

    Returns:
        Path to the output file
    """
    # Register all MCP tools
    register_tools()

    # First, let's discover what tools are available
    tool_executor = await get_tool_executor()
    available_tools = tool_executor.get_available_tools()

    if progress_callback:
        progress_callback(f"Available tools: {list(available_tools.keys())}")

    queries = parse_eval_file(eval_file_path)

    # Log the number of queries being processed
    print(f"Processing evaluation file: {eval_file_path}")
    print(f"Number of queries to process: {len(queries)}")

    if progress_callback:
        progress_callback(f"Found {len(queries)} queries to process")

    # Generate output filename if not provided
    if not output_file_path:
        import os
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Save to the results directory
        results_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")
        os.makedirs(results_dir, exist_ok=True)
        output_file_path = os.path.join(results_dir, f"search_eval_results_{timestamp}.jsonl")

    # Capture configuration URLs
    database_url = get_database_url()
    opensearch_url = get_opensearch_url()

    # Mask sensitive parts of URLs for display
    def mask_url(url: str) -> str:
        """Mask password in URL for safe display."""
        import re

        # Match password in URLs like postgresql://user:password@host or https://user:password@host
        return re.sub(r"(://[^:]+:)([^@]+)(@)", r"\1****\3", url)

    masked_db_url = mask_url(database_url)
    masked_opensearch_url = mask_url(opensearch_url)

    # Open output file for writing results
    with open(output_file_path, "w") as out_f:
        # Write metadata as first line
        metadata = {
            "_metadata": True,
            "database_url": masked_db_url,
            "opensearch_url": masked_opensearch_url,
            "timestamp": datetime.now().isoformat(),
        }
        out_f.write(json.dumps(metadata) + "\n")
        for i, query_obj in enumerate(queries):
            if progress_callback:
                progress_callback(f"Processing query {i + 1}/{len(queries)}")

            tool_type = query_obj.get("type", "keyword_search")
            query_text = query_obj.get("query", "")
            provenance = query_obj.get("provenance", {})

            # Get gather and glean results
            gather_results = query_obj.get("gather_results", [])
            glean_results = query_obj.get("glean_results", [])

            # Build filters from provenance
            filters = {}
            if isinstance(provenance, dict):
                # Handle date filters
                if "date_from" in provenance:
                    filters["date_from"] = provenance["date_from"]
                if "date_to" in provenance:
                    filters["date_to"] = provenance["date_to"]
                # Handle other filters
                for key, value in provenance.items():
                    if key not in ["date_from", "date_to"]:
                        filters[key] = value
            elif isinstance(provenance, str):
                # If provenance is a string, it might be a source filter
                if provenance == "github.code":
                    filters["sources"] = [DocumentSource.GITHUB_CODE]
                elif provenance == "linear":
                    filters["sources"] = [DocumentSource.LINEAR]
                else:
                    filters["provenance"] = provenance

            # Query the appropriate MCP tool
            results = await query_mcp_tool(tool_type, query_text, filters or {})

            # Extract sources
            sources = extract_sources_from_results(results.get("results", []))

            # Prepare new_gather results with score breakdown
            new_gather = []
            for result in results.get("results", []):
                gather_item = {
                    "doc_id": result.get("document_id", result.get("id", "unknown")),
                    "source": result.get("source", "unknown"),
                    "score": result.get("score", 0),
                }

                # Add score breakdown if available using centralized function
                from src.utils.scoring import add_score_breakdown_to_result

                detailed_result = add_score_breakdown_to_result(
                    result=result,
                    query=query_text,
                    search_type=tool_type,
                    filters=filters if filters else None,
                )

                # Copy the detailed breakdown to gather_item
                if tool_type == "semantic_search":
                    gather_item["semantic_score"] = detailed_result.get("semantic_score", 0)
                    gather_item["recency_component"] = detailed_result.get("recency_component", 0)
                    gather_item["references_component"] = detailed_result.get(
                        "references_component", 0
                    )
                    if "chunk_id" in detailed_result:
                        gather_item["chunk_id"] = detailed_result.get("chunk_id", "")
                elif tool_type == "keyword_search":
                    gather_item["query_component"] = detailed_result.get("query_component", 0)
                    gather_item["recency_component"] = detailed_result.get("recency_component", 0)
                    gather_item["references_component"] = detailed_result.get(
                        "references_component", 0
                    )

                # Add metadata if available (includes channel_name for Slack)
                if "metadata" in result and result["metadata"]:
                    gather_item["metadata"] = result["metadata"]

                new_gather.append(gather_item)

            # Create the output record
            output_record = {
                "query": query_text,
                "query_type": tool_type,
                "original_gather": gather_results,
                "original_glean": glean_results,
                "new_gather": new_gather,
                "sources_found": sources,
                "results_count": results.get("count", 0),
            }

            # Write to JSONL file
            out_f.write(json.dumps(output_record) + "\n")

            # Small delay to avoid overwhelming the API
            await asyncio.sleep(0.5)

    return output_file_path
