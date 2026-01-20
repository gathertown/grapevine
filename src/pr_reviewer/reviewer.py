"""GitHub PR Reviewer using multi-stage agent analysis.

This module provides the core PRReviewer class for reviewing GitHub PRs.
It performs a 3-phase analysis:
1. Initial Analysis: Analyze changes in the PR
2. Context Investigation: N agents investigate each change for issues
3. Review Synthesis: Generate final structured review
"""

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

from fastmcp.server.context import Context
from github import GithubException

from src.clients.github import GitHubClient
from src.pr_reviewer.agents.context_investigator import run_parallel_investigations
from src.pr_reviewer.agents.initial_analyzer import run_parallel_initial_analysis
from src.pr_reviewer.agents.review_synthesizer import generate_final_review
from src.pr_reviewer.models import DiffChunk, ExistingReviewComment
from src.pr_reviewer.utils.file_saver import (
    format_changes_for_display,
    format_insights_for_display,
)
from src.pr_reviewer.utils.github_fetcher import fetch_file_contents_with_context
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError
from src.utils.tracing import trace_span

logger = get_logger(__name__)

# Default configuration for production Grapevine
DEFAULT_REPO = "gathertown/gather-town-v2-frozen-11-17-25"


class PRReviewer:
    """GitHub PR reviewer using multi-stage agent analysis."""

    def __init__(
        self,
        github_token: str,
    ):
        """Initialize the PR reviewer.

        Args:
            github_token: GitHub personal access token
        """
        self.github_client = GitHubClient(token=github_token)

    def parse_repo_url(self, repo_url: str) -> str:
        """Parse GitHub repository URL to extract owner/repo format.

        Args:
            repo_url: GitHub repository URL (e.g., https://github.com/owner/repo)

        Returns:
            Repository in "owner/repo" format

        Raises:
            ValueError: If URL format is invalid
        """
        # Handle both full URLs and owner/repo format
        if "/" in repo_url and not repo_url.startswith("http"):
            # Already in owner/repo format
            return repo_url

        parsed = urlparse(repo_url)
        if parsed.netloc != "github.com":
            raise ValueError(f"Invalid GitHub URL: {repo_url}")

        # Extract path parts (e.g., /owner/repo or /owner/repo.git)
        path_parts = parsed.path.strip("/").rstrip(".git").split("/")
        if len(path_parts) < 2:
            raise ValueError(f"Invalid GitHub URL format: {repo_url}")

        return f"{path_parts[0]}/{path_parts[1]}"

    def parse_unified_diff(self, patch: str) -> list[tuple[int, int]]:
        """Parse unified diff to extract precise line number ranges for each change.

        Args:
            patch: Unified diff patch content

        Returns:
            List of (line_start, line_end) tuples for changed lines in the new file
        """
        line_ranges = []
        lines = patch.split("\n")

        # Match diff chunk headers like @@ -10,7 +10,8 @@
        chunk_pattern = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@")

        i = 0
        while i < len(lines):
            match = chunk_pattern.match(lines[i])
            if match:
                new_line = int(match.group(1))
                i += 1

                # Track changes within this hunk
                change_start = None
                change_end = None

                while i < len(lines) and not lines[i].startswith("@@"):
                    line = lines[i]

                    # Skip metadata lines
                    if line.startswith("---") or line.startswith("+++") or line.startswith("\\"):
                        i += 1
                        continue

                    # Addition or modification line
                    if line.startswith("+"):
                        if change_start is None:
                            change_start = new_line
                        change_end = new_line
                        new_line += 1
                        i += 1

                    # Deletion line (doesn't increment new_line)
                    elif line.startswith("-"):
                        # Mark the position where deletion occurred
                        if change_start is None:
                            change_start = new_line
                            change_end = new_line
                        i += 1

                    # Context line or empty
                    else:
                        # If we were tracking a change, save it
                        if change_start is not None and change_end is not None:
                            line_ranges.append((change_start, change_end))
                            change_start = None
                            change_end = None

                        # Context lines increment the new line counter
                        if line.startswith(" ") or line == "":
                            new_line += 1
                        i += 1

                # Save any remaining change at end of hunk
                if change_start is not None and change_end is not None:
                    line_ranges.append((change_start, change_end))

            else:
                i += 1

        return line_ranges

    def extract_diff_chunks(self, files: list[dict[str, Any]]) -> list[DiffChunk]:
        """Extract diff chunks from PR files.

        Args:
            files: List of file change dictionaries from GitHub API

        Returns:
            List of DiffChunk objects
        """
        chunks = []

        for file in files:
            filename = file.get("filename", "")
            patch = file.get("patch")
            status = file.get("status", "modified")

            if not patch:
                # No patch means no changes to process (e.g., binary files)
                continue

            # Parse line ranges from the unified diff
            line_ranges = self.parse_unified_diff(patch)

            if not line_ranges:
                # Fallback: treat entire file as one chunk
                line_ranges = [(1, 1)]

            # Create a chunk for each range
            for line_start, line_end in line_ranges:
                chunk = DiffChunk(
                    filename=filename,
                    line_start=line_start,
                    line_end=line_end,
                    patch=patch,
                    status=status,
                )
                chunks.append(chunk)

        return chunks

    async def fetch_pr_data(self, repo_spec: str, pr_number: int) -> dict[str, Any]:
        """Fetch PR data from GitHub.

        Args:
            repo_spec: Repository in "owner/repo" format
            pr_number: Pull request number

        Returns:
            Dictionary with PR data and file diffs
        """
        logger.info(f"Fetching PR #{pr_number} from {repo_spec}")

        # Fetch PR metadata
        pr_data = self.github_client.get_individual_pull_request(repo_spec, pr_number)
        if not pr_data:
            raise ValueError(f"PR #{pr_number} not found in {repo_spec}")

        # Fetch PR file diffs
        files = self.github_client.get_pr_files(repo_spec, pr_number)

        return {
            "pr": pr_data,
            "files": files,
        }

    async def review_pr(
        self,
        repo_url: str,
        pr_number: int,
        context: Context,
        ignore_existing_comments: bool = False,
    ) -> dict[str, Any]:
        """Review a GitHub PR using 3-phase multi-agent analysis.

        This is a non-streaming wrapper around review_pr_streaming() that prints
        progress to stdout/logger for CLI usage.

        Phase 1: Initial analysis
        Phase 2: Parallel context investigations (N agents)
        Phase 3: Final review synthesis

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number
            context: FastMCP context with tenant_id and other state
            ignore_existing_comments: If True, skip fetching existing PR comments

        Returns:
            Dictionary with 'decision' and 'comments' in ground truth format
        """
        final_review = None

        # Consume streaming events and print progress for CLI
        async for event in self.review_pr_streaming(
            repo_url, pr_number, context, ignore_existing_comments=ignore_existing_comments
        ):
            event_type = event.get("type")
            event_data = event.get("data")

            if event_type == "status":
                # Log status messages
                logger.info(event_data)

            elif event_type == "phase_complete":
                if event_data is None:
                    continue
                # Print formatted phase results
                phase = event_data.get("phase")
                phase_name = event_data.get("phase_name")

                logger.info(f"✅ Phase {phase} complete: {phase_name}")
                print("\n" + "=" * 60)
                print(
                    f"{'📊' if phase == 1 else '🔍' if phase == 2 else '📝'} PHASE {phase} RESULTS: {phase_name}"
                )
                print("=" * 60)

                if phase == 1:
                    changes = event_data.get("changes", [])
                    print(format_changes_for_display(changes))
                elif phase == 2:
                    insights = event_data.get("insights", [])
                    print(format_insights_for_display(insights))
                elif phase == 3:
                    decision = event_data.get("decision")
                    comments_count = event_data.get("comments_count", 0)
                    logger.info(f"Decision: {decision} with {comments_count} comments")

            elif event_type == "final_review" and event_data is not None:
                final_review = event_data

        if not final_review:
            logger.error("No final review generated")
            return {
                "decision": "APPROVE",
                "comments": [],
            }

        return final_review

    async def review_pr_streaming(
        self,
        repo_url: str,
        pr_number: int,
        context: Context,
        ignore_existing_comments: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Review a GitHub PR with streaming progress updates.

        Yields progress events for each phase of the review process.

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number
            context: FastMCP context with tenant_id and other state
            ignore_existing_comments: If True, skip fetching existing PR comments

        Yields:
            Event dictionaries with 'type' and 'data' keys:
            - {"type": "status", "data": "message"}
            - {"type": "phase_complete", "data": {"phase": 1, "changes": [...]}}
            - {"type": "final_review", "data": {"decision": "...", "comments": [...]}}
        """
        async with trace_span(
            name="review_pr_streaming",
            input_data={"repo_url": repo_url, "pr_number": pr_number},
            metadata={"tool": "pr_reviewer"},
        ) as top_span:
            # Parse repo URL
            repo_spec = self.parse_repo_url(repo_url)

            yield {"type": "status", "data": f"Reviewing PR #{pr_number} from {repo_spec}"}

            # Fetch PR data and diffs
            yield {"type": "status", "data": "Fetching PR data and diffs..."}
            pr_data = await self.fetch_pr_data(repo_spec, pr_number)
            diff_chunks = self.extract_diff_chunks(pr_data["files"])
            yield {
                "type": "status",
                "data": f"Extracted {len(diff_chunks)} diff chunks from {len(pr_data['files'])} files",
            }

            # Fetch full file contents with context
            yield {"type": "status", "data": "Fetching file contents with context..."}
            file_contents = await fetch_file_contents_with_context(
                self.github_client, repo_spec, pr_data["pr"], pr_data["files"]
            )
            yield {"type": "status", "data": f"Fetched content for {len(file_contents)} files"}

            # Phase 1: Initial analysis
            yield {"type": "status", "data": "📊 PHASE 1: Initial Analysis"}
            async with trace_span(
                name="pr_review_phase_1_initial_analysis",
                input_data={"chunks_count": len(diff_chunks), "files_count": len(pr_data["files"])},
                metadata={"phase": 1, "phase_name": "Initial Analysis"},
            ) as phase1_span:
                changes = await run_parallel_initial_analysis(
                    pr_data["pr"],
                    file_contents,
                    diff_chunks,
                    context,
                    repo_name=repo_spec,
                    num_agents=1,
                )
                phase1_span.update(output={"changes_count": len(changes)})

            yield {
                "type": "phase_complete",
                "data": {
                    "phase": 1,
                    "phase_name": "Initial Analysis",
                    "changes_count": len(changes),
                    "changes": changes,
                },
            }

            if not changes:
                top_span.update(output={"decision": "APPROVE", "comments_count": 0})
                yield {
                    "type": "final_review",
                    "data": {
                        "decision": "APPROVE",
                        "comments": [],
                    },
                }
                return

            # Phase 2: Parallel context investigations
            yield {"type": "status", "data": "🔍 PHASE 2: Context Investigation"}
            async with trace_span(
                name="pr_review_phase_2_context_investigation",
                input_data={"changes_count": len(changes)},
                metadata={"phase": 2, "phase_name": "Context Investigation"},
            ) as phase2_span:
                insights = await run_parallel_investigations(
                    changes,
                    pr_data["pr"],
                    context,
                    repo_name=repo_spec,
                    file_contents=file_contents,
                    diff_chunks=diff_chunks,
                )
                phase2_span.update(output={"insights_count": len(insights)})

            yield {
                "type": "phase_complete",
                "data": {
                    "phase": 2,
                    "phase_name": "Context Investigation",
                    "insights_count": len(insights),
                    "insights": insights,
                },
            }

            # Fetch existing PR comments to avoid duplicates
            # Fetch with sorting, then filter and limit to prevent unbounded token growth
            # Fetch more total comments (100) to ensure we have enough review comments after filtering
            existing_review_comments: list[ExistingReviewComment] = []
            if ignore_existing_comments:
                yield {
                    "type": "status",
                    "data": "Skipping existing comments (--ignore-existing-comments flag set)",
                }
            else:
                yield {"type": "status", "data": "Fetching existing PR comments..."}
                try:
                    all_comments = await asyncio.to_thread(
                        self.github_client.get_pr_comments,
                        repo_spec,
                        pr_number,
                        direction="desc",
                        limit=100,  # Fetch more to ensure we get 25 review comments after filtering
                    )
                    # Filter to review comments only (those with path and line/position fields)
                    existing_review_comments = [
                        comment
                        for comment in all_comments
                        if comment.get("comment_type") == "review"
                        and comment.get("path")
                        and (
                            comment.get("line") is not None
                            or comment.get("lines") is not None
                            or comment.get("position") is not None
                        )
                    ]
                    # Limit to 25 most recent review comments
                    existing_review_comments = existing_review_comments[:25]
                    yield {
                        "type": "status",
                        "data": f"Found {len(existing_review_comments)} existing review comments to consider",
                    }
                except (RateLimitedError, GithubException) as e:
                    logger.warning(
                        f"Failed to fetch existing PR comments (rate limited or API error): {e}. "
                        "Proceeding without existing comments to avoid duplicates."
                    )
                    yield {
                        "type": "status",
                        "data": "Could not fetch existing comments; proceeding without duplicate checking",
                    }
                except Exception as e:
                    logger.warning(
                        f"Unexpected error fetching existing PR comments: {e}. "
                        "Proceeding without existing comments to avoid duplicates."
                    )
                    yield {
                        "type": "status",
                        "data": "Could not fetch existing comments; proceeding without duplicate checking",
                    }
            # Phase 3: Final review synthesis
            yield {"type": "status", "data": "📝 PHASE 3: Review Synthesis"}
            async with trace_span(
                name="pr_review_phase_3_synthesis",
                input_data={
                    "insights_count": len(insights),
                    "existing_comments_count": len(existing_review_comments),
                },
                metadata={"phase": 3, "phase_name": "Review Synthesis"},
            ) as phase3_span:
                review = await generate_final_review(
                    pr_data["pr"],
                    insights,
                    context,
                    repo_name=repo_spec,
                    diff_chunks=diff_chunks,
                    existing_comments=existing_review_comments,
                )
                phase3_span.update(
                    output={
                        "decision": review.get("decision"),
                        "comments_count": len(review.get("comments", [])),
                    }
                )

            yield {
                "type": "phase_complete",
                "data": {
                    "phase": 3,
                    "phase_name": "Review Synthesis",
                    "decision": review.get("decision"),
                    "comments_count": len(review.get("comments", [])),
                },
            }

            # Update top-level span with final results
            top_span.update(
                output={
                    "decision": review.get("decision"),
                    "comments_count": len(review.get("comments", [])),
                    "repo_spec": repo_spec,
                }
            )

            # Final review result
            yield {
                "type": "final_review",
                "data": review,
            }
