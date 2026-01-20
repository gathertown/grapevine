"""
Re-run queries from an evaluation file using current MCP tools.

This script takes an existing evaluation JSONL file with original gather results
and re-runs all the queries using the current keyword_search and semantic_search tools.
The output maintains the same format but with updated gather_results.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from connectors.base.document_source import DocumentSource
from src.evals.search_utils.eval_searcher import parse_eval_file, query_mcp_tool
from src.mcp.tools import register_tools

app = typer.Typer()


def extract_results_from_mcp(results: dict[str, Any]) -> list[str]:
    """Extract gather-style results from MCP tool response."""
    gather_results = []

    for result in results.get("results", []):
        # Try to format result similar to original gather format
        doc_id = result.get("document_id", result.get("id", ""))
        metadata = result.get("metadata", {})

        # Format based on document type/source
        if result.get("source") == DocumentSource.SLACK or metadata.get("channel_name"):
            # Slack format: "Channel: <#CHANNEL_ID|#channel-name> Date: YYYY-MM-DD"
            channel_name = metadata.get("channel_name", "unknown")
            channel_id = metadata.get("channel_id", "")
            date = (
                metadata.get("formatted_time", "").split()[0]
                if metadata.get("formatted_time")
                else ""
            )

            if channel_id and channel_name:
                formatted = f"Channel: <#{channel_id}|#{channel_name}> Date: {date}"
            else:
                formatted = doc_id
            gather_results.append(formatted)

        elif "github.com" in str(result.get("url", "")) or "github_file_" in doc_id:
            # GitHub format - try to use URL if available, otherwise doc_id
            url = result.get("url", "")
            if url:
                gather_results.append(url)
            else:
                gather_results.append(doc_id)

        elif "linear.app" in str(result.get("url", "")) or "linear_issue_" in doc_id:
            # Linear format
            url = result.get("url", "")
            if url:
                gather_results.append(url)
            else:
                # Try to construct from metadata
                issue_title = metadata.get("issue_title", metadata.get("title", ""))
                issue_id = metadata.get("issue_id", "")
                if issue_title and issue_id:
                    formatted = f"Issue: <{issue_id}|{issue_title}> URL: {url}" if url else doc_id
                    gather_results.append(formatted)
                else:
                    gather_results.append(doc_id)

        elif "notion.so" in str(result.get("url", "")) or "notion_page_" in doc_id:
            # Notion format
            url = result.get("url", "")
            if url:
                gather_results.append(url)
            else:
                gather_results.append(doc_id)

        else:
            # Default: use URL if available, otherwise doc_id
            url = result.get("url", "")
            gather_results.append(url if url else doc_id)

    return gather_results


async def rerun_queries(input_file: Path, output_name: str) -> Path:
    """Re-run all queries from the input file and save results."""
    # Register all MCP tools
    register_tools()

    # Parse input file
    queries = parse_eval_file(str(input_file))
    print(f"Loaded {len(queries)} queries from {input_file}")

    # Prepare output path
    output_dir = input_file.parent
    output_file = output_dir / f"{output_name}.jsonl"

    # Process each query
    with open(output_file, "w") as f:
        for i, query_obj in enumerate(queries):
            print(f"Processing query {i + 1}/{len(queries)}: {query_obj.get('query', '')[:50]}...")

            # Extract query parameters
            tool_type = query_obj.get("type", "keyword_search")
            query_text = query_obj.get("query", "")
            provenance = query_obj.get("provenance", {})
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

            # Query the MCP tool
            try:
                results = await query_mcp_tool(tool_type, query_text, filters if filters else None)
                new_gather_results = extract_results_from_mcp(results)
            except Exception as e:
                print(f"  Error querying: {e}")
                new_gather_results = []

            # Create output record with same structure as input
            output_record = {
                "type": tool_type,
                "query": query_text,
                "gather_results": new_gather_results,
                "glean_results": glean_results,
            }

            # Include provenance if it exists
            if provenance:
                output_record["provenance"] = provenance

            # Write to output file
            f.write(json.dumps(output_record) + "\n")

            # Small delay to avoid overwhelming the API
            await asyncio.sleep(0.5)

    print(f"\nResults saved to: {output_file}")
    return output_file


@app.command()
def main(
    input_file: Path = typer.Argument(..., help="Input JSONL file with original gather results"),
    output_name: str = typer.Option(
        "rerun_gather",
        "--output-name",
        "-o",
        help="Name for output file (without .jsonl extension)",
    ),
):
    """Re-run queries from an evaluation file using current MCP tools."""
    if not input_file.exists():
        typer.echo(f"Error: Input file {input_file} does not exist", err=True)
        raise typer.Exit(1)

    if input_file.suffix != ".jsonl":
        typer.echo("Error: Input file must be a .jsonl file", err=True)
        raise typer.Exit(1)

    # Run async function
    output_file = asyncio.run(rerun_queries(input_file, output_name))
    typer.echo(f"✅ Successfully re-ran queries and saved to {output_file}")


if __name__ == "__main__":
    app()
