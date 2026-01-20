#!/usr/bin/env bash
# Creates a Devin session with the implementation prompt
#
# Required environment variables:
#   DEVIN_API_KEY - Devin API key
#   REPO - GitHub repository (owner/repo)
#   PR_NUMBER - PR number
#   PR_TITLE - PR title
#   PR_URL - PR URL
#   PR_BRANCH - PR branch name
#   LINEAR_URL - Linear ticket URL
#
# Optional environment variables:
#   TEST_PLAN_FILE - Path to test plan file (default: test_plan.md)
#   PROMPT_FILE - Path to prompt template (required)
#   SESSION_TAGS - Comma-separated tags for the session (default: linear-ticket,auto-assigned)
#   LINEAR_TICKET_CONTENT_FILE - Path to file with full ticket content (default: /tmp/ticket_content.txt)
#   REPO_RUNBOOK_FILE - Path to repo runbook file (default: .github/devin/runbook.md)
#
# Outputs (to GITHUB_OUTPUT if set, otherwise stdout):
#   session_id - Devin session ID
#   session_url - Devin session URL

set -euo pipefail

: "${DEVIN_API_KEY:?DEVIN_API_KEY is required}"
: "${REPO:?REPO is required}"
: "${PR_NUMBER:?PR_NUMBER is required}"
: "${PR_TITLE:?PR_TITLE is required}"
: "${PR_URL:?PR_URL is required}"
: "${PR_BRANCH:?PR_BRANCH is required}"
: "${LINEAR_URL:?LINEAR_URL is required}"

TEST_PLAN_FILE="${TEST_PLAN_FILE:-test_plan.md}"
: "${PROMPT_FILE:?PROMPT_FILE is required}"
SESSION_TAGS="${SESSION_TAGS:-linear-ticket,auto-assigned}"
LINEAR_TICKET_CONTENT_FILE="${LINEAR_TICKET_CONTENT_FILE:-/tmp/ticket_content.txt}"
REPO_RUNBOOK_FILE="${REPO_RUNBOOK_FILE:-.github/devin/runbook.md}"

# Read the prompt template
PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")

# Get test plan content
if [ -f "$TEST_PLAN_FILE" ]; then
  TEST_PLAN_CONTENT=$(cat "$TEST_PLAN_FILE")
else
  TEST_PLAN_CONTENT="No test plan available. Please review the PR description and implement accordingly."
fi

# Get Linear ticket content
if [ -f "$LINEAR_TICKET_CONTENT_FILE" ]; then
  LINEAR_TICKET_CONTENT=$(cat "$LINEAR_TICKET_CONTENT_FILE")
else
  LINEAR_TICKET_CONTENT="_No ticket content available. Please review the Linear ticket directly._"
fi

# Get repo runbook content
if [ -f "$REPO_RUNBOOK_FILE" ]; then
  REPO_RUNBOOK_CONTENT=$(cat "$REPO_RUNBOOK_FILE")
else
  REPO_RUNBOOK_CONTENT=$(
    cat <<'EOF'
_No repo runbook file found at `__REPO_RUNBOOK_FILE__`._

Before you start implementing/testing, determine:
- How to install dependencies
- How to start the local environment (UI/API/etc)
- How to run lint/typecheck/tests

Use `README.md`, `AGENTS.md`, repo scripts, and CI config to figure this out, then proceed.
EOF
  )
  REPO_RUNBOOK_CONTENT="${REPO_RUNBOOK_CONTENT//__REPO_RUNBOOK_FILE__/$REPO_RUNBOOK_FILE}"
fi

# Substitute variables in the template
# NOTE: $REPO is a prefix of placeholders like $REPO_RUNBOOK; only replace the exact
# $REPO token (not when it's part of a longer placeholder name).
PROMPT=$(
  echo "$PROMPT_TEMPLATE" |
    sed "s|\$LINEAR_URL|${LINEAR_URL}|g" |
    sed -E "s#\\\$REPO([^[:alnum:]_]|$)#${REPO}\\1#g" |
    sed "s|\$PR_NUMBER|$PR_NUMBER|g" |
    sed "s|\$PR_TITLE|$PR_TITLE|g" |
    sed "s|\$PR_URL|$PR_URL|g" |
    sed "s|\$PR_BRANCH|$PR_BRANCH|g"
)

# Handle multiline content separately using awk
echo "$PROMPT" | awk \
  -v test_plan="$TEST_PLAN_CONTENT" \
  -v ticket_content="$LINEAR_TICKET_CONTENT" \
  -v repo_runbook="$REPO_RUNBOOK_CONTENT" \
  '{
    gsub(/\$TEST_PLAN/, test_plan)
    gsub(/\$LINEAR_TICKET_CONTENT/, ticket_content)
    gsub(/\$REPO_RUNBOOK/, repo_runbook)
    print
  }' > /tmp/prompt.txt

# Convert tags to JSON array
TAGS_JSON=$(echo "$SESSION_TAGS" | jq -R 'split(",")')

# Create Devin session using v1 API
RESPONSE=$(curl -s -X POST "https://api.devin.ai/v1/sessions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEVIN_API_KEY" \
  -d "$(jq -n \
    --rawfile prompt /tmp/prompt.txt \
    --arg title "$PR_TITLE" \
    --argjson tags "$TAGS_JSON" \
    '{
      prompt: $prompt,
      title: $title,
      tags: $tags
    }')")

SESSION_ID=$(echo "$RESPONSE" | jq -r '.session_id')
SESSION_URL=$(echo "$RESPONSE" | jq -r '.url')

if [ "$SESSION_ID" == "null" ] || [ -z "$SESSION_ID" ]; then
  echo "Error: Failed to create Devin session" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

# Output for GitHub Actions or stdout
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "session_id=$SESSION_ID"
    echo "session_url=$SESSION_URL"
  } >> "$GITHUB_OUTPUT"
else
  echo "session_id=$SESSION_ID"
  echo "session_url=$SESSION_URL"
fi

echo "Devin session created successfully!" >&2
echo "Session ID: $SESSION_ID" >&2
echo "Session URL: $SESSION_URL" >&2
