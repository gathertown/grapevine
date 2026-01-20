#!/usr/bin/env python3
"""Send PR review results to Slack with threading.

Posts a root message with PR info and decision summary,
then posts each review comment as a threaded reply.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field

import httpx

SLACK_API_URL = "https://slack.com/api/chat.postMessage"
MAX_CHUNK_SIZE = 2900  # Leave room under Slack's 3000 char limit


@dataclass
class ReviewResult:
    decision: str = "UNKNOWN"
    comment_count: int = 0
    comments: list[str] = field(default_factory=list)
    raw_header: str = ""


def parse_review_output(content: str) -> ReviewResult:
    """Parse the review output to extract decision and comments."""
    result = ReviewResult()

    # Extract decision
    decision_match = re.search(r"^Decision:\s*(.+)$", content, re.MULTILINE)
    if decision_match:
        result.decision = decision_match.group(1).strip()

    # Extract comment count
    count_match = re.search(r"^Comments\s*\((\d+)\):", content, re.MULTILINE)
    if count_match:
        result.comment_count = int(count_match.group(1))

    # Extract the header section (everything before first numbered comment)
    header_match = re.search(
        r"(={10,}.*?📝 PR REVIEW RESULT.*?={10,}.*?Comments\s*\(\d+\):.*?-{10,})",
        content,
        re.DOTALL,
    )
    if header_match:
        result.raw_header = header_match.group(1).strip()

    # Split into individual comments using numbered pattern at line start
    # Pattern matches "1. ", "2. ", etc. at the start of a line
    comment_pattern = re.compile(r"^(\d+)\.\s+", re.MULTILINE)
    matches = list(comment_pattern.finditer(content))

    for i, match in enumerate(matches):
        start = match.start()
        # End is either the next comment or the end marker
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            # Find the closing separator
            end_match = re.search(r"^={10,}", content[start:], re.MULTILINE)
            end = start + end_match.start() if end_match else len(content)

        comment_text = content[start:end].strip()
        if comment_text:
            result.comments.append(comment_text)

    return result


def chunk_text(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Split text into chunks, preferring newline boundaries."""
    if len(text) <= max_size:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_size:
            chunks.append(text)
            break

        # Find a newline near the limit
        chunk = text[:max_size]
        last_newline = chunk.rfind("\n")

        if last_newline > max_size // 2:
            # Split at newline
            chunks.append(text[: last_newline + 1].rstrip())
            text = text[last_newline + 1 :]
        else:
            # No good newline, split at max size
            chunks.append(chunk.rstrip())
            text = text[max_size:]

    return [c for c in chunks if c]


def send_slack_message(
    token: str,
    channel: str,
    text: str,
    blocks: list | None = None,
    thread_ts: str | None = None,
) -> dict:
    """Send a message to Slack."""
    payload = {
        "channel": channel,
        "text": text,
        "unfurl_links": False,
        "unfurl_media": False,
    }

    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts

    response = httpx.post(
        SLACK_API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30.0,
    )

    result = response.json()
    if not result.get("ok"):
        print(f"Slack API error: {result.get('error')}", file=sys.stderr)
        if "errors" in result:
            print(f"Details: {result['errors']}", file=sys.stderr)
    return result


def send_review_to_slack(
    review_file: str,
    pr_url: str,
    pr_number: str,
    pr_title: str,
    pr_author: str,
    channel: str,
    token: str,
    team_domain: str | None = None,
) -> None:
    """Send PR review results to Slack with threading."""
    # Read and parse review output
    with open(review_file, encoding="utf-8") as f:
        content = f.read()

    review = parse_review_output(content)

    # Build root message blocks
    decision_emoji = "✅" if review.decision == "APPROVE" else "⚠️"
    root_blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🤖 Grapevine PR Review"},
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*PR:*\n<{pr_url}|#{pr_number}: {pr_title}>",
                },
                {"type": "mrkdwn", "text": f"*Author:*\n{pr_author}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{decision_emoji} *Decision:* {review.decision}\n*Comments:* {review.comment_count}",
            },
        },
    ]

    # Send root message
    print(f"Sending root message to channel {channel}...")
    root_result = send_slack_message(
        token=token,
        channel=channel,
        text=f"PR Review: {pr_title} - {review.decision}",
        blocks=root_blocks,
    )

    if not root_result.get("ok"):
        print(f"Failed to send root message: {root_result}", file=sys.stderr)
        # Try fallback plain text
        print("Attempting fallback plain text message...")
        root_result = send_slack_message(
            token=token,
            channel=channel,
            text=f"🤖 *Grapevine PR Review*\n\nPR: <{pr_url}|#{pr_number}: {pr_title}>\nAuthor: {pr_author}\n\n{decision_emoji} Decision: {review.decision}\nComments: {review.comment_count}",
        )
        if not root_result.get("ok"):
            print("Fallback also failed, exiting", file=sys.stderr)
            return

    thread_ts = root_result.get("ts")
    if not thread_ts:
        print("No thread_ts in response, cannot post thread replies", file=sys.stderr)
        return

    print(f"Root message sent, thread_ts: {thread_ts}")

    # Generate thread permalink for CI logs if team_domain is provided
    if team_domain:
        # Format permalink: https://{team_domain}.slack.com/archives/{channel_id}/p{timestamp}
        # Remove decimal point from thread_ts for Slack permalink format
        permalink_ts = thread_ts.replace(".", "")
        thread_url = f"https://{team_domain}.slack.com/archives/{channel}/p{permalink_ts}"
        print(f"Thread link: {thread_url}")

    # Post each comment as a thread reply
    for i, comment in enumerate(review.comments, 1):
        print(f"Posting comment {i}/{len(review.comments)}...")

        # Split comment if too long
        chunks = chunk_text(comment)

        for j, chunk in enumerate(chunks):
            # No code fences - just post the text directly
            result = send_slack_message(
                token=token,
                channel=channel,
                text=chunk,
                thread_ts=thread_ts,
            )

            if not result.get("ok"):
                print(
                    f"Failed to send comment {i} chunk {j + 1}: {result}",
                    file=sys.stderr,
                )

    print(f"Done! Posted {len(review.comments)} comments to thread.")


def main():
    parser = argparse.ArgumentParser(description="Send PR review results to Slack")

    parser.add_argument(
        "--review-file",
        required=True,
        help="Path to review output file",
    )
    parser.add_argument(
        "--pr-url",
        required=True,
        help="Pull request URL",
    )
    parser.add_argument(
        "--pr-number",
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--pr-title",
        required=True,
        help="Pull request title",
    )
    parser.add_argument(
        "--pr-author",
        required=True,
        help="Pull request author",
    )
    parser.add_argument(
        "--channel",
        required=True,
        help="Slack channel ID",
    )
    parser.add_argument(
        "--team-domain",
        help="Slack team domain (e.g., 'gathertown') for creating thread permalink",
    )

    args = parser.parse_args()

    # Get token from environment
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("Error: SLACK_BOT_TOKEN environment variable required", file=sys.stderr)
        sys.exit(1)

    send_review_to_slack(
        review_file=args.review_file,
        pr_url=args.pr_url,
        pr_number=args.pr_number,
        pr_title=args.pr_title,
        pr_author=args.pr_author,
        channel=args.channel,
        token=token,
        team_domain=args.team_domain,
    )


if __name__ == "__main__":
    main()
