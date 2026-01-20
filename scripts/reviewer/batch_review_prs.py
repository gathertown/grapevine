#!/usr/bin/env python3
"""Batch PR reviewer script that runs reviews on multiple PRs in parallel.

Usage:
    python scripts/reviewer/batch_review_prs.py <pr_list.txt

Or with inline PRs:
    python scripts/reviewer/batch_review_prs.py --prs "gather-town-v2#16984" "corporate-context#2364"
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import NamedTuple

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastmcp.server.context import Context

from src.mcp.mcp_instance import get_mcp
from src.mcp.tools import register_tools
from src.pr_reviewer import PRReviewer
from src.pr_reviewer.utils.file_saver import save_review_to_file
from src.utils.config import extract_tenant_id_from_token
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Register MCP tools for agent loop
register_tools()

# Repository name mappings
REPO_MAPPINGS = {
    "gather-town-v2": "gathertown/gather-town-v2",
    "grapevine": "gathertown/grapevine",
}


class PRSpec(NamedTuple):
    """PR specification with repo and number."""

    repo_name: str
    repo_url: str
    pr_number: int

    def __str__(self) -> str:
        return f"{self.repo_name}#{self.pr_number}"


def parse_pr_spec(pr_spec: str) -> PRSpec:
    """Parse a PR spec in format 'repo#PR' into PRSpec.

    Args:
        pr_spec: PR specification like "gather-town-v2#16984"

    Returns:
        PRSpec with repo name, repo URL, and PR number

    Raises:
        ValueError: If format is invalid or repo is unknown
    """
    if "#" not in pr_spec:
        raise ValueError(f"Invalid PR spec format: {pr_spec}. Expected format: repo#PR")

    repo_name, pr_str = pr_spec.split("#", 1)

    try:
        pr_number = int(pr_str)
    except ValueError as e:
        raise ValueError(f"Invalid PR number in {pr_spec}: {pr_str}") from e

    if pr_number <= 0:
        raise ValueError(f"PR number must be positive: {pr_number}")

    repo_url = REPO_MAPPINGS.get(repo_name)
    if not repo_url:
        available = ", ".join(REPO_MAPPINGS.keys())
        raise ValueError(f"Unknown repo name: {repo_name}. Available repos: {available}")

    return PRSpec(repo_name=repo_name, repo_url=repo_url, pr_number=pr_number)


async def review_single_pr(
    pr_spec: PRSpec,
    github_token: str,
    context: Context,
    output_dir: Path,
    ignore_existing_comments: bool = False,
) -> dict[str, any]:
    """Review a single PR and save results.

    Args:
        pr_spec: PR specification
        github_token: GitHub personal access token
        context: FastMCP context with tenant_id
        output_dir: Base output directory for reviews
        ignore_existing_comments: If True, ignore existing PR comments

    Returns:
        Dictionary with review result and metadata
    """
    reviewer = PRReviewer(github_token=github_token)

    try:
        logger.info(f"Starting review for {pr_spec}")
        result = await reviewer.review_pr(
            pr_spec.repo_url,
            pr_spec.pr_number,
            context,
            ignore_existing_comments=ignore_existing_comments,
        )

        # Save review to file in repo-specific subdirectory
        repo_output_dir = output_dir / pr_spec.repo_name
        repo_output_dir.mkdir(parents=True, exist_ok=True)
        filepath = save_review_to_file(result, pr_spec.pr_number, str(repo_output_dir))

        logger.info(f"✅ Completed review for {pr_spec} -> {filepath}")

        return {
            "pr_spec": pr_spec,
            "status": "success",
            "result": result,
            "filepath": filepath,
            "decision": result.get("decision"),
            "comments_count": len(result.get("comments", [])),
        }

    except Exception as e:
        logger.error(f"❌ Error reviewing {pr_spec}: {e}", exc_info=True)
        return {
            "pr_spec": pr_spec,
            "status": "error",
            "error": str(e),
        }


async def main() -> None:
    """Main entry point for batch PR reviewer."""
    parser = argparse.ArgumentParser(
        description="Review multiple GitHub PRs in parallel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Review PRs from a file (one per line)
  python scripts/reviewer/batch_review_prs.py < pr_list.txt

  # Review specific PRs
  python scripts/reviewer/batch_review_prs.py --prs gather-town-v2#16984 corporate-context#2364

  # Review with custom output directory
  python scripts/reviewer/batch_review_prs.py --prs gather-town-v2#16984 --output-dir reviews/
        """,
    )
    parser.add_argument(
        "--prs",
        nargs="+",
        help="List of PRs in format 'repo#PR' (e.g., gather-town-v2#16984)",
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
    parser.add_argument(
        "--ignore-existing-comments",
        action="store_true",
        help="Ignore existing PR comments (useful for evaluating review quality)",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum number of concurrent reviews (default: 5)",
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

    # Parse PR specs
    pr_specs: list[PRSpec] = []

    if args.prs:
        # Parse from command line arguments
        for pr_spec_str in args.prs:
            try:
                pr_specs.append(parse_pr_spec(pr_spec_str))
            except ValueError as e:
                print(f"Error parsing PR spec '{pr_spec_str}': {e}", file=sys.stderr)
                sys.exit(1)
    else:
        # Read from stdin (one per line)
        logger.info("Reading PR specs from stdin...")
        for line in sys.stdin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                pr_specs.append(parse_pr_spec(line))
            except ValueError as e:
                print(f"Error parsing PR spec '{line}': {e}", file=sys.stderr)
                sys.exit(1)

    if not pr_specs:
        print("Error: No PR specs provided", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    logger.info(f"Reviewing {len(pr_specs)} PRs with max {args.max_concurrent} concurrent reviews")

    # Create FastMCP context for reviews
    mcp = get_mcp()
    context = Context(fastmcp=mcp)
    context.set_state("tenant_id", tenant_id)
    context.set_state("non_billable", True)  # CLI usage is non-billable

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run reviews in parallel with semaphore to limit concurrency
    semaphore = asyncio.Semaphore(args.max_concurrent)

    async def review_with_semaphore(pr_spec: PRSpec) -> dict[str, any]:
        async with semaphore:
            return await review_single_pr(
                pr_spec,
                github_token,
                context,
                output_dir,
                ignore_existing_comments=args.ignore_existing_comments,
            )

    # Run all reviews
    results = await asyncio.gather(
        *[review_with_semaphore(pr_spec) for pr_spec in pr_specs],
        return_exceptions=True,
    )

    # Print summary
    print("\n" + "=" * 80)
    print("📊 BATCH REVIEW SUMMARY")
    print("=" * 80)

    successful = [r for r in results if isinstance(r, dict) and r.get("status") == "success"]
    failed = [r for r in results if isinstance(r, dict) and r.get("status") == "error"]
    exceptions = [r for r in results if isinstance(r, Exception)]

    print(f"\n✅ Successful: {len(successful)}")
    for result in successful:
        pr_spec = result["pr_spec"]
        decision = result.get("decision", "UNKNOWN")
        comments_count = result.get("comments_count", 0)
        print(f"  {pr_spec}: {decision} ({comments_count} comments) -> {result.get('filepath')}")

    if failed:
        print(f"\n❌ Failed: {len(failed)}")
        for result in failed:
            pr_spec = result["pr_spec"]
            error = result.get("error", "Unknown error")
            print(f"  {pr_spec}: {error}")

    if exceptions:
        print(f"\n💥 Exceptions: {len(exceptions)}")
        for exc in exceptions:
            print(f"  {type(exc).__name__}: {exc}")

    print(f"\n📁 Reviews saved to: {output_dir.absolute()}")
    print("=" * 80)

    # Exit with error code if any reviews failed
    if failed or exceptions:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
