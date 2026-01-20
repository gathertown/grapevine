"""Compare PR reviews with and without working directory changes.

This script runs pr_reviewer on multiple PRs in parallel, comparing the results
with the current working directory changes versus a clean git state.

Uses git worktree to enable true parallel execution of both batches.
"""

import argparse
import asyncio
import html
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, cast

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import extract_tenant_id_from_token
from src.utils.logging import get_logger

logger = get_logger(__name__)


class GitWorktreeManager:
    """Manages git worktree for clean state testing."""

    def __init__(self):
        self.worktree_path: Path | None = None
        self.temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def create_clean_worktree(self) -> Path:
        """Create a git worktree in a clean state.

        Returns:
            Path to the clean worktree directory
        """
        try:
            # Get current commit SHA (not branch name, to avoid conflicts)
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            current_commit = result.stdout.strip()

            # Create temporary directory for worktree
            self.temp_dir = tempfile.TemporaryDirectory(prefix="pr_review_clean_")
            worktree_path = Path(self.temp_dir.name) / "worktree"

            # Create worktree at the current commit (detached HEAD)
            # This allows the same commit to be used in multiple worktrees
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), current_commit],
                check=True,
                capture_output=True,
            )

            self.worktree_path = worktree_path
            logger.info(
                f"Created clean worktree at: {worktree_path} (detached at {current_commit[:8]})"
            )
            return worktree_path

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create worktree: {e}")
            raise

    def cleanup(self) -> None:
        """Remove the worktree and clean up."""
        if self.worktree_path:
            try:
                subprocess.run(
                    ["git", "worktree", "remove", str(self.worktree_path), "--force"],
                    check=True,
                    capture_output=True,
                )
                logger.info(f"Removed worktree: {self.worktree_path}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to remove worktree: {e}")

        if self.temp_dir:
            try:
                self.temp_dir.cleanup()
            except Exception as e:
                logger.error(f"Failed to cleanup temp directory: {e}")


def run_pr_reviewer(
    pr_number: int,
    repo_url: str,
    github_token: str,
    tenant_id: str,
    output_dir: str,
    working_dir: Path | None = None,
) -> dict[str, Any]:
    """Run pr_reviewer on a single PR in a subprocess.

    Args:
        pr_number: PR number to review
        repo_url: Repository URL
        github_token: GitHub token
        tenant_id: Tenant ID for context
        output_dir: Directory to save review output (absolute path)
        working_dir: Optional working directory to run subprocess from (for clean worktree)

    Returns:
        Review result dictionary with 'decision' and 'comments'
    """
    logger.info(f"Running pr_reviewer for PR #{pr_number} (subprocess)")

    # Use absolute paths to avoid issues with working directory
    output_dir_abs = Path(output_dir).resolve()
    output_dir_abs.mkdir(parents=True, exist_ok=True)

    # Determine the working directory for the subprocess
    subprocess_cwd = working_dir.resolve() if working_dir else Path.cwd()

    try:
        # Build command to run pr_reviewer script
        # Note: tenant_id is now extracted from REMOTE_MCP_TOKEN env var by the subprocess
        cmd = [
            sys.executable,  # Use same Python interpreter
            "-m",
            "scripts.reviewer.pr_reviewer",
            str(pr_number),
            "--repo-url",
            repo_url,
            "--github-token",
            github_token,
            "--output-dir",
            str(output_dir_abs),
        ]

        logger.info(f"PR #{pr_number}: Running subprocess in {subprocess_cwd}")

        # Run subprocess with specific working directory
        result = subprocess.run(
            cmd,
            cwd=subprocess_cwd,
            capture_output=True,
            text=True,
            check=False,  # Don't raise on non-zero exit
        )

        # Check if subprocess succeeded
        if result.returncode != 0:
            logger.error(
                f"PR #{pr_number} subprocess failed with exit code {result.returncode}\n"
                f"STDOUT: {result.stdout}\n"
                f"STDERR: {result.stderr}"
            )
            return {
                "decision": "ERROR",
                "comments": [],
                "error": f"Subprocess failed with exit code {result.returncode}: {result.stderr}",
            }

        # Find the output file (most recent JSON file for this PR)
        output_files = list(output_dir_abs.glob(f"pr-{pr_number}-*.json"))
        if not output_files:
            logger.error(f"PR #{pr_number}: No output file found in {output_dir_abs}")
            return {
                "decision": "ERROR",
                "comments": [],
                "error": "No output file found after subprocess completion",
            }

        # Get the most recent file
        output_file = max(output_files, key=lambda p: p.stat().st_mtime)

        # Read the review result
        with open(output_file) as f:
            review_result = json.load(f)

        logger.info(f"PR #{pr_number} review completed successfully")
        return review_result

    except Exception as e:
        logger.error(f"Failed to review PR #{pr_number}: {e}", exc_info=True)
        return {
            "decision": "ERROR",
            "comments": [],
            "error": str(e),
        }


async def run_reviews_batch(
    pr_numbers: list[int],
    repo_url: str,
    github_token: str,
    tenant_id: str,
    output_dir: str,
    label: str,
    working_dir: Path | None = None,
) -> dict[int, dict[str, Any]]:
    """Run pr_reviewer on multiple PRs in parallel using subprocesses.

    Args:
        pr_numbers: List of PR numbers to review
        repo_url: Repository URL
        github_token: GitHub token
        tenant_id: Tenant ID for context
        output_dir: Directory to save review outputs
        label: Label for this batch (e.g., "with_changes" or "clean")
        working_dir: Optional working directory to run subprocesses from (for worktree)

    Returns:
        Dictionary mapping PR number to review result
    """
    logger.info(f"Starting {label} reviews for {len(pr_numbers)} PRs (parallel subprocesses)")

    # Create tasks for parallel execution using asyncio.to_thread
    # This allows blocking subprocess calls to run in threads without blocking the event loop
    tasks = [
        asyncio.to_thread(
            run_pr_reviewer,
            pr_num,
            repo_url,
            github_token,
            tenant_id,
            output_dir,
            working_dir,
        )
        for pr_num in pr_numbers
    ]

    # Run all reviews in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Map results back to PR numbers
    result_map: dict[int, dict[str, Any]] = {}
    for pr_num, result in zip(pr_numbers, results, strict=False):
        if isinstance(result, Exception):
            logger.error(f"PR #{pr_num} ({label}) failed: {result}")
            result_map[pr_num] = {
                "decision": "ERROR",
                "comments": [],
                "error": str(result),
            }
        else:
            result_map[pr_num] = cast(dict[str, Any], result)

    logger.info(f"Completed {label} reviews")
    return result_map


def format_html_comparison(
    with_changes: dict[int, dict[str, Any]],
    clean: dict[int, dict[str, Any]],
) -> str:
    """Format comparison results as an HTML table with full content.

    Args:
        with_changes: Results with working directory changes
        clean: Results without working directory changes

    Returns:
        HTML string with complete comparison table
    """
    html_parts = [
        """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PR Review Comparison</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
        }
        .pr-section {
            background-color: white;
            margin: 20px 0;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .pr-header {
            font-size: 1.5em;
            color: #0066cc;
            margin-bottom: 15px;
            font-weight: bold;
        }
        .decision-section {
            margin: 15px 0;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
        .decision-row {
            display: flex;
            justify-content: space-between;
            margin: 5px 0;
        }
        .decision-label {
            font-weight: bold;
            color: #555;
        }
        .decision-value {
            font-weight: bold;
        }
        .decision-APPROVE {
            color: #28a745;
        }
        .decision-REQUEST_CHANGES {
            color: #dc3545;
        }
        .decision-COMMENT {
            color: #ffc107;
        }
        .decision-ERROR {
            color: #dc3545;
        }
        .match-yes {
            color: #28a745;
            font-weight: bold;
        }
        .match-no {
            color: #dc3545;
            font-weight: bold;
        }
        .comments-section {
            margin: 20px 0;
        }
        .comments-header {
            font-size: 1.2em;
            font-weight: bold;
            margin-bottom: 10px;
            color: #333;
        }
        .comment-group {
            margin: 15px 0;
        }
        .comment-group-title {
            font-weight: bold;
            color: #0066cc;
            margin-bottom: 10px;
            font-size: 1.1em;
        }
        .comment-card {
            background-color: #ffffff;
            border-left: 4px solid #0066cc;
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .comment-meta {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 10px;
        }
        .comment-body {
            white-space: pre-wrap;
            line-height: 1.6;
            color: #333;
        }
        .error-section {
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 15px;
            margin: 15px 0;
            border-radius: 5px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin: 15px 0;
        }
        .stat-card {
            background-color: #e9ecef;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
        }
        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #0066cc;
        }
        .stat-label {
            color: #666;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <h1>PR Review Comparison: With Changes vs Clean State</h1>
"""
    ]

    for pr_num in sorted(with_changes.keys()):
        with_result = with_changes[pr_num]
        clean_result = clean[pr_num]

        # PR Section Header
        html_parts.append('<div class="pr-section">')
        html_parts.append(f'<div class="pr-header">PR #{pr_num}</div>')

        # Decision comparison
        with_decision = with_result.get("decision", "N/A")
        clean_decision = clean_result.get("decision", "N/A")
        decision_match = with_decision == clean_decision

        html_parts.append('<div class="decision-section">')
        html_parts.append('<div class="decision-row">')
        html_parts.append('<span class="decision-label">With Changes:</span>')
        html_parts.append(
            f'<span class="decision-value decision-{with_decision}">{html.escape(with_decision)}</span>'
        )
        html_parts.append("</div>")

        html_parts.append('<div class="decision-row">')
        html_parts.append('<span class="decision-label">Clean State:</span>')
        html_parts.append(
            f'<span class="decision-value decision-{clean_decision}">{html.escape(clean_decision)}</span>'
        )
        html_parts.append("</div>")

        html_parts.append('<div class="decision-row">')
        html_parts.append('<span class="decision-label">Decisions Match:</span>')
        match_class = "match-yes" if decision_match else "match-no"
        match_text = "✓ Yes" if decision_match else "✗ No"
        html_parts.append(f'<span class="{match_class}">{match_text}</span>')
        html_parts.append("</div>")
        html_parts.append("</div>")

        # Comment count stats
        with_comments = with_result.get("comments", [])
        clean_comments = clean_result.get("comments", [])

        html_parts.append('<div class="stats-grid">')
        html_parts.append('<div class="stat-card">')
        html_parts.append(f'<div class="stat-number">{len(with_comments)}</div>')
        html_parts.append('<div class="stat-label">Comments (With Changes)</div>')
        html_parts.append("</div>")

        html_parts.append('<div class="stat-card">')
        html_parts.append(f'<div class="stat-number">{len(clean_comments)}</div>')
        html_parts.append('<div class="stat-label">Comments (Clean State)</div>')
        html_parts.append("</div>")
        html_parts.append("</div>")

        # Comments comparison
        html_parts.append('<div class="comments-section">')
        html_parts.append('<div class="comments-header">Comments Comparison</div>')

        # All with_changes comments
        if with_comments:
            html_parts.append('<div class="comment-group">')
            html_parts.append(
                f'<div class="comment-group-title">All Comments from "With Changes" ({len(with_comments)})</div>'
            )
            for i, comment in enumerate(with_comments, 1):
                html_parts.append('<div class="comment-card">')
                html_parts.append(f'<div class="comment-meta">Comment #{i}')
                if comment.get("path"):
                    html_parts.append(
                        f" • {html.escape(comment['path'])}:{comment.get('line', '?')}"
                    )
                html_parts.append("</div>")
                html_parts.append(
                    f'<div class="comment-body">{html.escape(comment.get("body", ""))}</div>'
                )
                html_parts.append("</div>")
            html_parts.append("</div>")

        # All clean comments
        if clean_comments:
            html_parts.append('<div class="comment-group">')
            html_parts.append(
                f'<div class="comment-group-title">All Comments from "Clean State" ({len(clean_comments)})</div>'
            )
            for i, comment in enumerate(clean_comments, 1):
                html_parts.append('<div class="comment-card">')
                html_parts.append(f'<div class="comment-meta">Comment #{i}')
                if comment.get("path"):
                    html_parts.append(
                        f" • {html.escape(comment['path'])}:{comment.get('line', '?')}"
                    )
                html_parts.append("</div>")
                html_parts.append(
                    f'<div class="comment-body">{html.escape(comment.get("body", ""))}</div>'
                )
                html_parts.append("</div>")
            html_parts.append("</div>")

        html_parts.append("</div>")  # comments-section

        # Show errors if any
        if "error" in with_result:
            html_parts.append('<div class="error-section">')
            html_parts.append("<strong>ERROR (With Changes):</strong><br>")
            html_parts.append(html.escape(with_result["error"]))
            html_parts.append("</div>")

        if "error" in clean_result:
            html_parts.append('<div class="error-section">')
            html_parts.append("<strong>ERROR (Clean State):</strong><br>")
            html_parts.append(html.escape(clean_result["error"]))
            html_parts.append("</div>")

        html_parts.append("</div>")  # pr-section

    html_parts.append(
        """
</body>
</html>
"""
    )

    return "".join(html_parts)


async def main() -> None:
    """Main entry point for the comparison script."""
    parser = argparse.ArgumentParser(
        description="Compare PR reviews with and without working directory changes"
    )
    parser.add_argument(
        "pr_numbers",
        help="Comma-separated list of PR numbers (e.g., '1,2,3')",
    )
    parser.add_argument(
        "--repo-url",
        default="gathertown/gather-town-v2-frozen-11-17-25",
        help="GitHub repository URL (default: gathertown/gather-town-v2-frozen-11-17-25)",
    )
    parser.add_argument(
        "--github-token",
        help="GitHub personal access token (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="scripts/reviewer/reviews/comparison",
        help="Output directory for review files (default: scripts/reviewer/reviews/comparison/)",
    )

    args = parser.parse_args()

    # Parse PR numbers
    try:
        pr_numbers = [int(num.strip()) for num in args.pr_numbers.split(",")]
    except ValueError as e:
        print(f"Error: Invalid PR numbers format. Expected comma-separated integers: {e}")
        sys.exit(1)

    if not pr_numbers:
        print("Error: No PR numbers provided")
        sys.exit(1)

    # Get credentials
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
    logger.info(f"Comparing reviews for PRs: {pr_numbers}")
    logger.info(f"Repository: {args.repo_url}")

    # Create output directories (use absolute paths to avoid issues with worktree)
    output_base = Path(args.output_dir).resolve()
    with_changes_dir = output_base / "with_changes"
    clean_dir = output_base / "clean"
    with_changes_dir.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)

    # Create git worktree for clean state
    worktree_manager = GitWorktreeManager()

    try:
        logger.info("\n" + "=" * 60)
        logger.info("SETUP: Creating clean git worktree for parallel execution")
        logger.info("=" * 60)

        clean_worktree = worktree_manager.create_clean_worktree()

        # Run both batches in parallel using asyncio.gather
        logger.info("\n" + "=" * 60)
        logger.info("RUNNING: Both batches in parallel")
        logger.info("  - Batch 1: Reviews WITH working directory changes (main directory)")
        logger.info(f"  - Batch 2: Reviews in CLEAN state (worktree: {clean_worktree})")
        logger.info("=" * 60)

        with_changes_task = run_reviews_batch(
            pr_numbers,
            args.repo_url,
            github_token,
            tenant_id,
            str(with_changes_dir),
            "with_changes",
            None,  # Use current directory
        )

        clean_task = run_reviews_batch(
            pr_numbers,
            args.repo_url,
            github_token,
            tenant_id,
            str(clean_dir),
            "clean",
            clean_worktree,  # Use clean worktree
        )

        # Run both in parallel!
        with_changes_results, clean_results = await asyncio.gather(with_changes_task, clean_task)

    finally:
        # Always clean up worktree
        logger.info("\n" + "=" * 60)
        logger.info("CLEANUP: Removing git worktree")
        logger.info("=" * 60)
        worktree_manager.cleanup()

    # Generate HTML comparison output
    logger.info("\n" + "=" * 60)
    logger.info("GENERATING: HTML comparison report")
    logger.info("=" * 60)

    # HTML comparison (full content, no truncation)
    html_comparison = format_html_comparison(with_changes_results, clean_results)
    html_file = output_base / f"comparison_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.html"
    with open(html_file, "w") as f:
        f.write(html_comparison)

    logger.info(f"✅ HTML comparison saved to: {html_file}")
    logger.info(f"\n🎉 Comparison complete! Open {html_file} in your browser to view results.\n")


if __name__ == "__main__":
    asyncio.run(main())
