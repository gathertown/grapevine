#!/usr/bin/env python3
"""Post PR review comments to GitHub.

This script takes the review JSON output from the PR review tool and posts
it as a formal GitHub PR review with inline comments.

Usage:
    python .github/scripts/post_pr_review.py \
        --pr-number 123 \
        --repo owner/repo \
        --github-token ghp_... \
        --review-file review_result.json
"""

import argparse
import json
import os
import sys
from typing import TypedDict

import httpx


class GitHubComment(TypedDict, total=False):
    """GitHub review comment structure."""

    path: str
    side: str
    body: str
    position: int
    line: int
    start_line: int
    start_side: str


class ReviewPayload(TypedDict, total=False):
    """GitHub review payload structure."""

    event: str
    body: str
    comments: list[GitHubComment]


def extract_comment_id_from_body(body: str) -> str | None:
    """Extract comment UUID from GitHub comment body.

    Args:
        body: GitHub comment body containing embedded UUID

    Returns:
        Comment UUID string or None if not found
    """
    import re

    # Match HTML comment pattern: <!-- grapevine-comment-id: <uuid> -->
    pattern = r"<!-- grapevine-comment-id: ([a-f0-9\-]+) -->"
    match = re.search(pattern, body)
    if match:
        return match.group(1)
    return None


def match_comments_to_ids(
    original_comments: list[dict],
    github_comments: list[dict],
) -> list[dict]:
    """Match original comments to GitHub comment IDs using embedded UUIDs.

    Matches based on comment_id UUID embedded in the comment body.
    Falls back to path + body matching if UUID is not found.

    Args:
        original_comments: Original comment dicts from review file (with impact, confidence, categories, comment_id)
        github_comments: GitHub API comment response data

    Returns:
        List of dicts with original comment data (including impact, confidence, categories)
        plus github_id and github_url
    """
    mappings = []

    for original in original_comments:
        # Extract identifying info from original comment
        orig_path = original.get("path")
        orig_line = original.get("line")
        orig_lines = original.get("lines")
        orig_position = original.get("position")
        orig_body = original.get("body", "")
        orig_comment_id = original.get("comment_id")

        # Find matching GitHub comment
        matched_github_comment = None

        # Match comments by UUID
        if not orig_comment_id:
            print(
                f"No original comment id found for comment: {orig_path} line={orig_line} position={orig_position}"
            )
            continue

        for gh_comment in github_comments:
            gh_body = gh_comment.get("body", "")
            gh_comment_id = extract_comment_id_from_body(gh_body)

            if gh_comment_id == orig_comment_id:
                matched_github_comment = gh_comment
                break

        if matched_github_comment is None:
            print(
                f"Warning: Could not match original comment to GitHub comment: {orig_path} line={orig_line} position={orig_position} comment_id={orig_comment_id}"
            )
            continue

        # Build mapping with all original data (impact, confidence, categories, etc.)
        mapping = {
            "path": orig_path,
            "line": orig_line,
            "lines": orig_lines,
            "position": orig_position,
            "body": orig_body,
            "impact": original.get("impact"),
            "confidence": original.get("confidence"),
            "categories": original.get("categories"),
            "comment_id": orig_comment_id,
            "github_id": matched_github_comment.get("id"),
            "github_url": matched_github_comment.get("html_url"),
        }
        mappings.append(mapping)

    return mappings


def format_comment_body(comment: dict) -> str:
    """Format a comment body with metadata (impact, confidence, categories).

    Args:
        comment: Comment dict with body, impact, confidence, categories, etc.

    Returns:
        Formatted comment body string with embedded UUID for matching
    """
    body = comment.get("body", "")
    parts = [body]

    # Build metadata line
    metadata = []

    impact = comment.get("impact")
    if impact is not None:
        metadata.append(f"Impact: {impact}/100")

    confidence = comment.get("confidence")
    if confidence is not None:
        metadata.append(f"Confidence: {confidence}/100")

    categories = comment.get("categories")
    if categories:
        # Filter out None values to avoid TypeError in join
        categories = [c for c in categories if c is not None]
        if categories:
            metadata.append(f"Categories: {', '.join(categories)}")

    if metadata:
        parts.append("")
        parts.append(f"*{' | '.join(metadata)}*")

    # Embed comment UUID as HTML comment for robust matching
    comment_id = comment.get("comment_id")
    if comment_id:
        parts.append("")
        parts.append(f"<!-- grapevine-comment-id: {comment_id} -->")

    return "\n".join(parts)


def post_pr_review(
    pr_number: int,
    repo: str,
    github_token: str,
    review_file: str,
) -> dict | None:
    """Post a PR review to GitHub.

    Args:
        pr_number: Pull request number
        repo: Repository in "owner/repo" format
        github_token: GitHub token with PR write permissions
        review_file: Path to JSON file containing the review

    Returns:
        Dict with review_id and comment_ids if successful, None otherwise
    """
    # Load review data
    try:
        with open(review_file) as f:
            review_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Review file not found: {review_file}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in review file: {e}")
        return None

    # Extract decision and comments
    decision = review_data.get("decision", "COMMENT")
    comments = review_data.get("comments", [])

    # Always post as COMMENT to avoid affecting PR mergeability
    # The decision is still included in the review body for context
    event = "COMMENT"

    # Build GitHub API comments array
    # Filter to high-value comments: impact >= 60 AND impact + confidence >= 125
    github_comments: list[GitHubComment] = []
    filtered_comments = []  # Keep original comments for fallback body
    skipped_low_value = 0
    for comment in comments:
        path = comment.get("path")
        body = comment.get("body")

        # Handle both "line" (single) and "lines" (array) formats
        line = comment.get("line")
        lines_array = comment.get("lines")
        start_line = None

        if lines_array and isinstance(lines_array, list) and len(lines_array) > 0:
            # Multi-line comment: lines = [start, end]
            if len(lines_array) >= 2:
                start_line = lines_array[0]
                line = lines_array[-1]  # GitHub uses "line" for end line
            else:
                line = lines_array[0]

        # Get position (diff-relative) - preferred over line
        position = comment.get("position")

        # Accept comments with either line OR position
        if not path or (not line and not position) or not body:
            print(f"Warning: Skipping comment with missing fields: {comment}")
            continue

        # Filter by impact and confidence thresholds
        impact = comment.get("impact") or 0
        confidence = comment.get("confidence") or 0
        if impact < 60 or (impact + confidence) < 125:
            skipped_low_value += 1
            continue

        filtered_comments.append(comment)

        # Build GitHub comment object
        # Note: position and line/side are mutually exclusive in GitHub API
        github_comment: GitHubComment = {
            "path": path,
            "body": format_comment_body(comment),
        }

        # Prefer position (diff-relative), fall back to line (file line number)
        # position is used alone; line requires side
        if position is not None:
            github_comment["position"] = position
        elif line is not None:
            github_comment["line"] = line
            github_comment["side"] = "RIGHT"
            # Add start_line for multi-line comments
            if start_line is not None and start_line != line:
                github_comment["start_line"] = start_line
                github_comment["start_side"] = "RIGHT"

        github_comments.append(github_comment)

    if skipped_low_value > 0:
        print(
            f"  Filtered out {skipped_low_value} low-value comments (impact < 60 or impact + confidence < 125)"
        )

    # Build review summary for the body
    # Total findings = comments that passed basic validation (have path, line/position, body)
    # This excludes comments skipped due to missing fields
    total_findings = len(filtered_comments) + skipped_low_value
    posted_count = len(filtered_comments)
    filtered_count = skipped_low_value

    # Build request payload
    payload: ReviewPayload = {
        "event": event,
        "body": build_review_summary(total_findings, posted_count, filtered_count),
    }

    # Only include comments if we have any
    if github_comments:
        payload["comments"] = github_comments

    # Post to GitHub API
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    print(f"Posting review to PR #{pr_number} in {repo}")
    print(f"  Decision: {decision} -> Event: {event}")
    print(f"  Comments: {len(github_comments)}")

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=30.0)

        if response.status_code in (200, 201):
            print("Successfully posted review to PR")
            review_response = response.json()
            review_id = review_response.get("id")

            # Fetch review comments to get their IDs and match them to originals
            comment_mappings = []
            if review_id:
                comments_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews/{review_id}/comments"
                try:
                    comments_response = httpx.get(comments_url, headers=headers, timeout=30.0)
                    if comments_response.status_code == 200:
                        github_comments_data = comments_response.json()

                        # Match GitHub comments back to filtered_comments
                        comment_mappings = match_comments_to_ids(
                            filtered_comments, github_comments_data
                        )

                        print(f"  Review ID: {review_id}")
                        print(f"  Matched {len(comment_mappings)} comments to IDs")
                        for mapping in comment_mappings:
                            print(
                                f"    - {mapping['path']}:{mapping.get('line', mapping.get('position', '?'))} -> ID: {mapping['github_id']}"
                            )
                except Exception as e:
                    print(f"  Warning: Could not fetch comment IDs: {e}")

            return {
                "review_id": review_id,
                "review_url": review_response.get("html_url"),
                "comments": comment_mappings,
            }
        elif response.status_code == 422:
            # Validation error - likely a comment on a line not in the diff
            error_data = response.json()
            print(f"Validation error from GitHub: {error_data}")

            # Try posting without comments if they caused the error
            # Check for both "comments" and "line" errors (e.g., "Line could not be resolved")
            error_str = str(error_data).lower()
            if github_comments and ("comments" in error_str or "line" in error_str):
                print("Retrying without inline comments...")
                payload_no_comments = {
                    "event": event,
                    "body": build_fallback_body(decision, filtered_comments),
                }
                response = httpx.post(url, json=payload_no_comments, headers=headers, timeout=30.0)
                if response.status_code in (200, 201):
                    print("Successfully posted review without inline comments")
                    review_response = response.json()
                    review_id = review_response.get("id")
                    return {
                        "review_id": review_id,
                        "review_url": review_response.get("html_url"),
                        "comments": [],  # No inline comments in fallback
                    }

            print(f"Failed to post review: {response.status_code}")
            print(f"Response: {response.text}")
            return None
        else:
            print(f"Failed to post review: {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except httpx.TimeoutException:
        print("Error: Request timed out")
        return None
    except httpx.RequestError as e:
        print(f"Error: Request failed: {e}")
        return None


def build_review_summary(
    total_findings: int,
    posted_count: int,
    filtered_count: int,
) -> str:
    """Build a summary of review findings for the review body.

    This ensures the review body is never empty, even when no comments
    meet the impact/confidence thresholds.

    Args:
        total_findings: Total number of findings from the review
        posted_count: Number of comments that met thresholds and were posted
        filtered_count: Number of comments filtered out due to low impact/confidence

    Returns:
        Formatted summary string
    """
    lines = ["**Grapevine Automated Review**", ""]

    if total_findings == 0:
        lines.append("No findings were identified in this review.")
    else:
        lines.append(f"**Summary:** {total_findings} total finding(s)")
        lines.append(f"- {posted_count} comment(s) posted as inline review comments")
        lines.append(
            f"- {filtered_count} comment(s) filtered (impact < 60 or impact + confidence < 125)"
        )

    return "\n".join(lines)


def build_fallback_body(decision: str, filtered_comments: list[dict]) -> str:
    """Build a fallback review body with all comments inline.

    Used when inline comments fail to post.

    Args:
        decision: The review decision (APPROVE, CHANGES_REQUESTED, COMMENT)
        filtered_comments: Pre-filtered list of high-value comments to include
    """
    lines = [
        "**Grapevine Automated Review**",
        "",
        f"**Decision:** {decision}",
        "",
    ]

    if filtered_comments:
        lines.append("**Comments:**")
        lines.append("")
        for i, comment in enumerate(filtered_comments, 1):
            path = comment.get("path", "unknown")
            # Handle "line", "lines", and "position" formats for display
            line_num = comment.get("line")
            lines_array = comment.get("lines")
            position = comment.get("position")
            if lines_array and isinstance(lines_array, list) and len(lines_array) > 0:
                if len(lines_array) >= 2:
                    line_display = f"{lines_array[0]}-{lines_array[-1]}"
                else:
                    line_display = str(lines_array[0])
            elif line_num:
                line_display = str(line_num)
            elif position:
                line_display = f"pos:{position}"
            else:
                line_display = "?"
            lines.append(f"**{i}. `{path}:{line_display}`**")
            lines.append(format_comment_body(comment))
            lines.append("")

    return "\n".join(lines)


def store_comments_in_database(
    repo: str,
    pr_number: int,
    review_result: dict,
    admin_backend_url: str,
    api_key: str,
) -> bool:
    """Store review comments in the database via admin backend API.

    Args:
        repo: Repository in "owner/repo" format
        pr_number: Pull request number
        review_result: Result from post_pr_review() containing review_id and comments
        admin_backend_url: Base URL for admin backend API
        api_key: Grapevine API key for authentication

    Returns:
        True if all comments stored successfully, False otherwise
    """
    # Hard-coded tenant ID for MVP
    tenant_id = "878f6fb522b441d1"

    review_id = review_result.get("review_id")
    review_url = review_result.get("review_url")
    comments = review_result.get("comments", [])

    if not comments:
        print("No comments to store in database")
        return True

    # Parse repo owner and name
    owner, repo_name = repo.split("/")

    print(f"\nStoring {len(comments)} comments in database...")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    success_count = 0
    error_count = 0

    for comment in comments:
        # Build request payload matching CreatePrReviewCommentRequest schema
        payload = {
            "tenantId": tenant_id,
            "githubCommentId": comment.get("github_id"),
            "githubReviewId": review_id,
            "githubPrNumber": pr_number,
            "githubRepoOwner": owner,
            "githubRepoName": repo_name,
            "filePath": comment.get("path"),
            "githubCommentUrl": comment.get("github_url"),
            "githubReviewUrl": review_url,
        }

        # Add optional fields if present
        if comment.get("line") is not None:
            payload["lineNumber"] = comment.get("line")
        if comment.get("position") is not None:
            payload["position"] = comment.get("position")
        if comment.get("impact") is not None:
            payload["impact"] = comment.get("impact")
        if comment.get("confidence") is not None:
            payload["confidence"] = comment.get("confidence")
        if comment.get("categories"):
            payload["categories"] = comment.get("categories")

        try:
            url = f"{admin_backend_url}/api/pr-review/comments"
            response = httpx.post(url, json=payload, headers=headers, timeout=30.0)

            if response.status_code == 201:
                success_count += 1
                print(f"  ✓ Stored comment {comment.get('github_id')}")
            elif response.status_code == 409:
                # Comment already exists - not an error
                success_count += 1
                print(f"  ✓ Comment {comment.get('github_id')} already exists")
            else:
                error_count += 1
                print(
                    f"  ✗ Failed to store comment {comment.get('github_id')}: {response.status_code}"
                )
                print(f"    Response: {response.text}")

        except httpx.TimeoutException:
            error_count += 1
            print(f"  ✗ Timeout storing comment {comment.get('github_id')}")
        except httpx.RequestError as e:
            error_count += 1
            print(f"  ✗ Request error storing comment {comment.get('github_id')}: {e}")
        except Exception as e:
            error_count += 1
            print(f"  ✗ Unexpected error storing comment {comment.get('github_id')}: {e}")

    print(f"\nDatabase storage complete: {success_count} succeeded, {error_count} failed")
    return error_count == 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Post PR review to GitHub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--pr-number",
        type=int,
        required=True,
        help="Pull request number",
    )

    parser.add_argument(
        "--repo",
        required=True,
        help="Repository in owner/repo format",
    )

    parser.add_argument(
        "--github-token",
        required=False,
        default=None,
        help="GitHub token with PR write permissions (defaults to GITHUB_TOKEN env var)",
    )

    parser.add_argument(
        "--review-file",
        required=True,
        help="Path to JSON file containing the review",
    )

    args = parser.parse_args()

    # Get GitHub token from arg or environment
    github_token = args.github_token or os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("Error: GitHub token required. Set GITHUB_TOKEN env var or use --github-token")
        sys.exit(1)

    result = post_pr_review(
        pr_number=args.pr_number,
        repo=args.repo,
        github_token=github_token,
        review_file=args.review_file,
    )

    if result:
        # Output results as JSON for easy parsing by CI
        print("\nReview posted successfully!")
        print(json.dumps(result, indent=2))

        # Store comments in database if configured
        admin_backend_url = os.environ.get("ADMIN_BACKEND_URL")
        grapevine_api_key = os.environ.get("GRAPEVINE_API_KEY")

        if admin_backend_url and grapevine_api_key:
            try:
                db_success = store_comments_in_database(
                    repo=args.repo,
                    pr_number=args.pr_number,
                    review_result=result,
                    admin_backend_url=admin_backend_url,
                    api_key=grapevine_api_key,
                )
                if not db_success:
                    print(
                        "\nWarning: Some comments failed to store in database, but review was posted successfully"
                    )
            except Exception as e:
                print(f"\nWarning: Failed to store comments in database: {e}")
                print("Review was posted successfully to GitHub")
        else:
            print("\nSkipping database storage (ADMIN_BACKEND_URL or GRAPEVINE_API_KEY not set)")

        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
