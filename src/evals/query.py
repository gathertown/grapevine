#!/usr/bin/env python
"""
Simple query script for the corporate-context agent.

Usage:
    python -m src.evals.query "What are the latest updates?"
    python -m src.evals.query "What are the recent discussions about deployment?" --verbose
"""

import argparse
import asyncio

from rich.console import Console

from src.evals.cli import call_ask_agent_via_mcp, setup_model_config
from src.utils.config import get_openai_api_key


async def main():
    parser = argparse.ArgumentParser(
        description="Query the corporate-context agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.evals.query "What are the latest updates?"
  python -m src.evals.query "What are recent discussions?" --verbose
  python -m src.evals.query "Show me GitHub issues" --model o3
        """,
    )

    parser.add_argument("query", type=str, help="The search query to execute")

    parser.add_argument(
        "--model", "-m", type=str, default="o3", help="Model to use for the agent. Default: o3"
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")

    args = parser.parse_args()
    console = Console()

    # Check API key
    if args.model == "o3" and not get_openai_api_key():
        console.print("[bold red]Error:[/bold red] OPENAI_API_KEY environment variable is not set.")
        console.print("This is required when using --model o3.")
        return

    # Setup model
    setup_model_config(args.model, console)

    console.print(f"[bold cyan]Question:[/bold cyan] {args.query}")
    console.print("[cyan]Using all available tools from MCP[/cyan]")
    console.print("─" * 60)

    try:
        console.print("[bold green]Agent is thinking...[/bold green]")

        final_answer, tool_calls_made, trace_info = await call_ask_agent_via_mcp(
            args.query, console, args.verbose
        )

        console.print("─" * 60)
        console.print("[bold green]Final Answer:[/bold green]")

        if isinstance(final_answer, dict):
            answer_text = final_answer.get("answer", str(final_answer))
            console.print(answer_text)
        else:
            console.print(final_answer)

        console.print(f"\n[dim]Total tool calls made: {tool_calls_made}[/dim]")

        if trace_info:
            console.print(f"[bold blue]Trace URL:[/bold blue] {trace_info.get('trace_url', 'N/A')}")

    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise


if __name__ == "__main__":
    asyncio.run(main())
