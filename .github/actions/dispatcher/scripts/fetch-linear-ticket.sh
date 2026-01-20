#!/usr/bin/env bash
# Fetches Linear ticket details and outputs them for GitHub Actions
#
# Required environment variables:
#   LINEAR_API_KEY - Linear API key for authentication
#   LINEAR_TICKET_ID - Linear ticket identifier (e.g., ENG-123 or UUID)
#
# Outputs (to GITHUB_OUTPUT if set, otherwise stdout):
#   identifier - Ticket identifier (e.g., ENG-123)
#   title - Ticket title
#   url - Ticket URL
#
# Also writes ticket description to /tmp/ticket_description.txt

set -euo pipefail

: "${LINEAR_API_KEY:?LINEAR_API_KEY is required}"
: "${LINEAR_TICKET_ID:?LINEAR_TICKET_ID is required}"

# Linear API accepts both identifier (ENG-123) and UUID formats
# Fetch full ticket details including comments, labels, state, priority, and parent info
QUERY='{"query": "query { issue(id: \"'"$LINEAR_TICKET_ID"'\") { id identifier title description url priority priorityLabel state { name } labels { nodes { name } } parent { identifier title } comments { nodes { body user { name } createdAt } } } }"}'

RESPONSE=$(curl -s -X POST https://api.linear.app/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: $LINEAR_API_KEY" \
  -d "$QUERY")

ISSUE=$(echo "$RESPONSE" | jq -r '.data.issue')

if [ "$ISSUE" == "null" ] || [ -z "$ISSUE" ]; then
  echo "Error: Could not fetch Linear ticket $LINEAR_TICKET_ID" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

IDENTIFIER=$(echo "$ISSUE" | jq -r '.identifier')
TITLE=$(echo "$ISSUE" | jq -r '.title')
DESCRIPTION=$(echo "$ISSUE" | jq -r '.description // ""')
URL=$(echo "$ISSUE" | jq -r '.url')
STATE=$(echo "$ISSUE" | jq -r '.state.name // "Unknown"')
PRIORITY_LABEL=$(echo "$ISSUE" | jq -r '.priorityLabel // "No priority"')
LABELS=$(echo "$ISSUE" | jq -r '[.labels.nodes[].name] | join(", ") // ""')
PARENT_IDENTIFIER=$(echo "$ISSUE" | jq -r '.parent.identifier // ""')
PARENT_TITLE=$(echo "$ISSUE" | jq -r '.parent.title // ""')

# Format comments into readable text
COMMENTS_TEXT=$(echo "$ISSUE" | jq -r '
  if .comments.nodes and (.comments.nodes | length) > 0 then
    .comments.nodes | map("**\(.user.name)** (\(.createdAt | split("T")[0])):\n\(.body)") | join("\n\n---\n\n")
  else
    ""
  end
')

# Build full ticket content for Devin
{
  echo "### $IDENTIFIER: $TITLE"
  echo ""
  echo "**Status:** $STATE"
  echo "**Priority:** $PRIORITY_LABEL"
  if [ -n "$LABELS" ]; then
    echo "**Labels:** $LABELS"
  fi
  if [ -n "$PARENT_IDENTIFIER" ]; then
    echo "**Parent:** $PARENT_IDENTIFIER - $PARENT_TITLE"
  fi
  echo ""
  echo "### Description"
  echo ""
  if [ -n "$DESCRIPTION" ]; then
    echo "$DESCRIPTION"
  else
    echo "_No description provided_"
  fi
  if [ -n "$COMMENTS_TEXT" ]; then
    echo ""
    echo "### Comments"
    echo ""
    echo "$COMMENTS_TEXT"
  fi
} > /tmp/ticket_content.txt

# Output for GitHub Actions or stdout
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "identifier=$IDENTIFIER"
    echo "title=$TITLE"
    echo "url=$URL"
  } >> "$GITHUB_OUTPUT"
else
  echo "identifier=$IDENTIFIER"
  echo "title=$TITLE"
  echo "url=$URL"
fi

# Store description in a file to handle multiline (for backwards compatibility)
echo "$DESCRIPTION" > /tmp/ticket_description.txt

echo "Fetched ticket: $IDENTIFIER - $TITLE" >&2
