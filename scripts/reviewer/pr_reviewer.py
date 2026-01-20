#!/usr/bin/env python3
"""CLI script for reviewing GitHub PRs.

This is a thin wrapper around the src.pr_reviewer library.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastmcp.server.context import Context

from src.mcp.mcp_instance import get_mcp
from src.mcp.tools import register_tools
from src.pr_reviewer import DEFAULT_REPO, PRReviewer
from src.pr_reviewer.utils.file_saver import format_review_for_display, save_review_to_file
from src.utils.config import extract_tenant_id_from_token
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Register MCP tools for agent loop
register_tools()


async def main() -> None:
    """Main entry point for the PR reviewer script."""
    parser = argparse.ArgumentParser(description="Review a GitHub PR using Grapevine's ask agent")
    parser.add_argument("pr_number", type=int, help="Pull request number")
    parser.add_argument(
        "--repo-url",
        default=DEFAULT_REPO,
        help=f"GitHub repository URL (e.g., https://github.com/owner/repo or owner/repo). Default: {DEFAULT_REPO}",
    )
    parser.add_argument(
        "--github-token",
        help="GitHub personal access token (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="scripts/reviewer/reviews",
        help="Output directory for review files (default: scripts/reviewer/reviews/)",
    )

    args = parser.parse_args()

    # Get credentials from args or environment
    github_token = args.github_token or os.getenv("GITHUB_TOKEN")

    if not github_token:
        print("Error: GitHub token required (--github-token or GITHUB_TOKEN env var)")
        sys.exit(1)

    # Get and verify REMOTE_MCP_TOKEN
    remote_mcp_token = os.getenv("REMOTE_MCP_TOKEN")
    if not remote_mcp_token:
        print("Error: REMOTE_MCP_TOKEN environment variable must be set")
        sys.exit(1)

    # Extract tenant_id from MCP token
    tenant_id = await extract_tenant_id_from_token(remote_mcp_token)
    if not tenant_id:
        print("Error: Failed to extract tenant_id from REMOTE_MCP_TOKEN")
        print("       Make sure the token is valid and contains tenant_id")
        sys.exit(1)

    logger.info(f"Extracted tenant_id: {tenant_id}")

    # Create FastMCP context for the review
    mcp = get_mcp()
    context = Context(fastmcp=mcp)
    context.set_state("tenant_id", tenant_id)
    context.set_state("non_billable", True)  # CLI usage is non-billable

    # Create reviewer
    reviewer = PRReviewer(
        github_token=github_token,
    )

    # Review PR
    try:
        result = await reviewer.review_pr(args.repo_url, args.pr_number, context)

        # Save review to file
        logger.info("\n" + "=" * 60)
        logger.info("💾 Saving Review")
        logger.info("=" * 60)
        filepath = save_review_to_file(result, args.pr_number, args.output_dir)
        logger.info(f"Review saved to: {filepath}")

        # Print formatted review
        print("\n" + "=" * 60)
        print("📝 FINAL REVIEW")
        print("=" * 60)
        print(format_review_for_display(result))
        print("=" * 60)
        print(f"\n💾 Review saved to: {filepath}\n")

    except Exception as e:
        logger.error(f"Error reviewing PR: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
