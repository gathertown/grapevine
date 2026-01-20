#!/usr/bin/env python3
"""Script to call the PR review MCP tool.

This script demonstrates how to call the review_pr_streaming MCP tool
via HTTP POST request to the MCP server.

Usage:
    python scripts/call_pr_review_tool.py <pr_number> [--repo owner/repo] [--token ghp_...]

Example:
    python scripts/call_pr_review_tool.py 123 --repo gathertown/gather-town --token ghp_abc123
"""

import argparse
import asyncio
import codecs
import json
import os
import sys

import httpx


async def call_pr_review_tool(
    pr_number: int,
    repo_url: str | None,
    github_token: str | None,
    api_key: str | None,
    mcp_url: str = "http://localhost:8000",
    output_json: str | None = None,
):
    """Call the review_pr_streaming MCP tool via HTTP.

    Args:
        pr_number: Pull request number to review
        repo_url: GitHub repository URL or owner/repo
        github_token: GitHub token
        mcp_url: MCP server URL (default: http://localhost:8000)
        api_key: MCP API key for authentication
    """
    # Prepare the MCP request
    # MCP tools are called via POST to /mcp with a JSON-RPC 2.0 request
    arguments: dict[str, str | int] = {"pr_number": pr_number}

    # Add optional parameters
    if repo_url:
        arguments["repo_url"] = repo_url
    if github_token:
        arguments["github_token"] = github_token

    request_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "review_pr_streaming",
            "arguments": arguments,
        },
    }

    # Set up authentication
    if not api_key:
        print("Error: MCP API key required (MCP_API_KEY env var or --api-key)")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    print(f"🔍 Calling review_pr_streaming tool for PR #{pr_number}")
    if repo_url:
        print(f"   Repository: {repo_url}")
    print(f"   MCP Server: {mcp_url}")
    print()

    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            # MCP endpoint is at root "/" not "/mcp"
            print("→ Opening streaming connection...")

            # Use stream() instead of post() to handle SSE properly
            async with client.stream(
                "POST",
                mcp_url,
                json=request_payload,
                headers=headers,
            ) as response:
                print("→ Got response, checking status...")
                response.raise_for_status()
                print(f"✓ Response status OK: {response.status_code}")

                # Check response content type
                content_type = response.headers.get("content-type", "")
                print(f"Response Content-Type: {content_type}")

                print("\n📡 Receiving streaming response...")
                print("-" * 60)

                events = []
                final_result = None
                buffer = ""
                # Use incremental decoder to handle multi-byte chars split across chunks
                decoder = codecs.getincrementaldecoder("utf-8")()

                # Read the stream byte by byte to avoid buffering issues
                print("→ Starting to read stream...")
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue

                    # Decode chunk using incremental decoder (handles split multi-byte chars)
                    buffer += decoder.decode(chunk)

                    # Process complete lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if not line:
                            continue

                        # SSE format: lines starting with "data: "
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            try:
                                # FastMCP wraps events in notification format
                                notification = json.loads(data)

                                # Extract the actual event from the notification
                                if (
                                    notification.get("method") == "notifications/message"
                                    and "params" in notification
                                ):
                                    params = notification["params"]
                                    msg = params.get("data", {}).get("msg")
                                    if msg:
                                        # The msg is a JSON string containing the actual event
                                        event = json.loads(msg)
                                        events.append(event)

                                        # Print progress
                                        if event.get("type") == "status":
                                            print(f"📌 {event.get('data')}")
                                        elif event.get("type") == "phase_complete":
                                            phase_data = event.get("data", {})
                                            print(
                                                f"✅ Phase {phase_data.get('phase')}: {phase_data.get('phase_name')} complete"
                                            )
                                        elif event.get("type") == "final_review":
                                            final_result = event.get("data")
                                            print("\n🎉 Received final review!")
                            except json.JSONDecodeError as e:
                                # Not JSON, might be metadata or error
                                print(f"⚠️  JSON decode error: {e}")
                                print(f"   Data: {data[:200]}")

                if final_result:
                    result = {"result": {"content": [{"text": json.dumps(final_result)}]}}
                else:
                    print("\n❌ No final result received from stream")
                    print(f"Total events received: {len(events)}")
                    if events:
                        print("Event types:", [e.get("type") for e in events])
                    sys.exit(1)

            # Check for JSON-RPC error
            if "error" in result:
                print("❌ Error from MCP server:")
                print(f"   Code: {result['error'].get('code')}")
                print(f"   Message: {result['error'].get('message')}")
                if "data" in result["error"]:
                    print(f"   Data: {result['error']['data']}")
                sys.exit(1)

            # Extract the tool result
            if "result" not in result:
                print("❌ Unexpected response format")
                print(json.dumps(result, indent=2))
                sys.exit(1)

            tool_result = result["result"]

            # The tool returns content array with text content
            if "content" in tool_result and len(tool_result["content"]) > 0:
                content_item = tool_result["content"][0]
                if hasattr(content_item, "text"):
                    review_data = json.loads(content_item.text)
                elif isinstance(content_item, dict) and "text" in content_item:
                    review_data = json.loads(content_item["text"])
                else:
                    review_data = content_item
            else:
                review_data = tool_result

            # Save raw JSON output if requested
            if output_json:
                with open(output_json, "w") as f:
                    json.dump(review_data, f, indent=2)
                print(f"💾 Saved review JSON to: {output_json}")

            # Print the review
            print("=" * 60)
            print("📝 PR REVIEW RESULT")
            print("=" * 60)
            print()

            if isinstance(review_data, dict):
                print(f"Decision: {review_data.get('decision', 'UNKNOWN')}")
                print()

                comments = review_data.get("comments", [])
                if comments:
                    print(f"Comments ({len(comments)}):")
                    print("-" * 60)
                    for i, comment in enumerate(comments, 1):
                        print(f"\n{i}. {comment.get('path', 'unknown')}:")
                        if "line" in comment:
                            print(f"   Line: {comment['line']}")
                        elif "lines" in comment:
                            lines = comment["lines"]
                            if isinstance(lines, list) and len(lines) >= 2:
                                print(f"   Lines: {lines[0]}-{lines[1]}")
                            elif isinstance(lines, list) and len(lines) == 1:
                                print(f"   Line: {lines[0]}")
                        if "position" in comment:
                            print(f"   Position: {comment['position']}")
                        if "category" in comment or "categories" in comment:
                            categories = comment.get("categories") or [comment.get("category")]
                            # Filter out None values to avoid TypeError in join
                            categories = [c for c in categories if c is not None]
                            if categories:
                                print(f"   Categories: {', '.join(categories)}")
                        if "impact" in comment:
                            print(f"   Impact: {comment['impact']}")
                        if "impact_reason" in comment:
                            print(f"   Impact Reason: {comment['impact_reason']}")
                        if "confidence" in comment:
                            print(f"   Confidence: {comment['confidence']}")
                        if "confidence_reason" in comment:
                            print(f"   Confidence Reason: {comment['confidence_reason']}")
                        print(f"\n   Comment: {comment.get('body', '')}")
                else:
                    print("No comments")
                print()

                # Print event summary if available
                events = review_data.get("events", [])
                if events:
                    print(f"Total events: {len(events)}")
                    # Count event types
                    event_types: dict[str, int] = {}
                    for event in events:
                        event_type = event.get("type", "unknown")
                        event_types[event_type] = event_types.get(event_type, 0) + 1
                    print("Event breakdown:")
                    for event_type, count in event_types.items():
                        print(f"  - {event_type}: {count}")
            else:
                print(json.dumps(review_data, indent=2))

            print()
            print("=" * 60)
            print("✅ Review completed successfully")

        except httpx.HTTPStatusError as e:
            print(f"\n❌ HTTP error: {e.response.status_code}")
            print(f"   Response: {e.response.text}")
            sys.exit(1)
        except httpx.TimeoutException as e:
            print("\n❌ Request timed out after 600 seconds")
            print(f"   Error: {e}")
            sys.exit(1)
        except httpx.ConnectError as e:
            print(f"\n❌ Connection error - cannot reach MCP server at {mcp_url}")
            print(f"   Error: {e}")
            print("   Make sure the MCP server is running!")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error calling MCP tool: {e}")
            print(f"   Type: {type(e).__name__}")
            import traceback

            traceback.print_exc()
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Call the PR review MCP tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Review PR #123 from default repo
  python scripts/call_pr_review_tool.py 123

  # Review PR from specific repo
  python scripts/call_pr_review_tool.py 123 --repo owner/repo

  # Provide GitHub token explicitly
  python scripts/call_pr_review_tool.py 123 --github-token ghp_abc123

  # Use custom MCP server URL
  python scripts/call_pr_review_tool.py 123 --mcp-url https://mcp.example.com
        """,
    )

    parser.add_argument("pr_number", type=int, help="Pull request number to review")

    parser.add_argument(
        "--repo",
        "--repo-url",
        dest="repo_url",
        help="GitHub repository URL or owner/repo format",
    )

    parser.add_argument(
        "--github-token",
        help="GitHub personal access token (defaults to GITHUB_TOKEN env var)",
    )

    parser.add_argument(
        "--mcp-url",
        default=None,
        help="MCP server URL (defaults to MCP_URL env var or http://localhost:8000)",
    )

    parser.add_argument(
        "--api-key",
        help="MCP API key for authentication (defaults to MCP_API_KEY env var)",
    )

    parser.add_argument(
        "--output-json",
        help="Path to save raw review JSON output",
    )

    args = parser.parse_args()

    # Get secrets from env vars (preferred) or CLI args (fallback)
    github_token = args.github_token or os.environ.get("GITHUB_TOKEN")
    api_key = args.api_key or os.environ.get("MCP_API_KEY")
    mcp_url = args.mcp_url or os.environ.get("MCP_URL", "http://localhost:8000")

    # Run the async function
    asyncio.run(
        call_pr_review_tool(
            pr_number=args.pr_number,
            repo_url=args.repo_url,
            github_token=github_token,
            api_key=api_key,
            mcp_url=mcp_url,
            output_json=args.output_json,
        )
    )


if __name__ == "__main__":
    main()
