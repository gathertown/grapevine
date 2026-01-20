#!/bin/bash
# Unified PR review orchestration script for GitHub Actions.
#
# This script orchestrates the PR review workflow:
# 1. Call MCP server to get the review
# 2. Post review to GitHub (optional)
# 3. Send to Slack (optional)
#
# All configuration is via environment variables.
#
# Required environment variables:
#   PR_NUMBER: Pull request number to review
#   REPO: Repository in owner/repo format
#   MCP_URL: Grapevine MCP server URL
#   MCP_API_KEY: MCP API key for authentication
#   GITHUB_TOKEN: GitHub token for posting review
#
# Optional environment variables:
#   POST_REVIEW: "true" to post review to GitHub (default: true)
#   ADMIN_BACKEND_URL: Admin backend URL for storing review metadata
#   GRAPEVINE_API_KEY: Grapevine API key for admin backend
#   SLACK_BOT_TOKEN: Slack bot token (if set, sends to Slack)
#   SLACK_CHANNEL: Slack channel ID
#   SLACK_TEAM_DOMAIN: Slack team domain for permalinks
#   PR_URL: Pull request URL for Slack message
#   PR_TITLE: Pull request title for Slack message
#   PR_AUTHOR: Pull request author for Slack message

set -euo pipefail

# Validate required environment variables
missing_vars=()
[[ -z "${PR_NUMBER:-}" ]] && missing_vars+=("PR_NUMBER")
[[ -z "${REPO:-}" ]] && missing_vars+=("REPO")
[[ -z "${MCP_URL:-}" ]] && missing_vars+=("MCP_URL")
[[ -z "${MCP_API_KEY:-}" ]] && missing_vars+=("MCP_API_KEY")
[[ -z "${GITHUB_TOKEN:-}" ]] && missing_vars+=("GITHUB_TOKEN")

if [[ ${#missing_vars[@]} -gt 0 ]]; then
    echo "❌ Missing required environment variables: ${missing_vars[*]}"
    exit 1
fi

# Temporary files for passing data between steps
REVIEW_JSON="/tmp/review_result.json"
REVIEW_OUTPUT="/tmp/review_output.txt"

# =============================================================================
# Step 1: Get PR Review from MCP Server
# =============================================================================
echo "============================================================"
echo "STEP 1: Get PR Review from MCP Server"
echo "============================================================"

python /app/gha/call_pr_review_tool.py "$PR_NUMBER" \
    --repo "$REPO" \
    --output-json "$REVIEW_JSON" \
    | tee "$REVIEW_OUTPUT"

# Check if review was successful
if [[ ! -f "$REVIEW_JSON" ]]; then
    echo ""
    echo "❌ Failed to get review from MCP server (no JSON output)"
    exit 1
fi

echo ""
echo "✅ Review completed successfully"

# =============================================================================
# Step 2: Post Review to GitHub (optional)
# =============================================================================
POST_REVIEW="${POST_REVIEW:-true}"

if [[ "$POST_REVIEW" == "true" ]]; then
    echo ""
    echo "============================================================"
    echo "STEP 2: Post Review to GitHub"
    echo "============================================================"

    python /app/gha/post_pr_review.py \
        --pr-number "$PR_NUMBER" \
        --repo "$REPO" \
        --review-file "$REVIEW_JSON"
else
    echo ""
    echo "⏭️ Skipping GitHub posting (POST_REVIEW != true)"
fi

# =============================================================================
# Step 3: Send to Slack (optional)
# =============================================================================
if [[ -n "${SLACK_BOT_TOKEN:-}" && -n "${SLACK_CHANNEL:-}" ]]; then
    echo ""
    echo "============================================================"
    echo "STEP 3: Send to Slack"
    echo "============================================================"

    python /app/gha/send_slack_review.py \
        --review-file "$REVIEW_OUTPUT" \
        --pr-url "${PR_URL:-}" \
        --pr-number "$PR_NUMBER" \
        --pr-title "${PR_TITLE:-}" \
        --pr-author "${PR_AUTHOR:-}" \
        --channel "$SLACK_CHANNEL" \
        ${SLACK_TEAM_DOMAIN:+--team-domain "$SLACK_TEAM_DOMAIN"}
else
    echo ""
    echo "⏭️ Skipping Slack (SLACK_BOT_TOKEN or SLACK_CHANNEL not set)"
fi

echo ""
echo "============================================================"
echo "✅ PR Review workflow completed successfully!"
echo "============================================================"

