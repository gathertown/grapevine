#!/usr/bin/env bash
# Generates a test plan using cursor-agent
#
# Required environment variables:
#   CURSOR_API_KEY - Cursor API key
#   GH_TOKEN - GitHub token for gh CLI
#   REPO - GitHub repository (owner/repo)
#   PR_NUMBER - PR number
#   LINEAR_TICKET_ID - Linear ticket identifier
#   LINEAR_TICKET_TITLE - Linear ticket title
#   LINEAR_TICKET_URL - Linear ticket URL
#
# Optional environment variables:
#   MODEL - Cursor model to use (default: auto)
#   PR_HEAD_SHA - PR head SHA
#   PR_BASE_SHA - PR base SHA
#   DEVENV_ADMIN_URL - Dev environment admin URL
#   DEVENV_MCP_URL - Dev environment MCP URL
#   PROMPT_FILE - Path to prompt template (required)
#   REPO_TESTING_ENTRY_POINTS_FILE - Path to repo-specific entry points guide (default: .github/test-plan/entrypoints.md)
#   OUTPUT_FILE - Path to output file (default: test_plan.md)
#
# Outputs (to GITHUB_OUTPUT if set):
#   has_test_plan - "true" if test plan was generated

set -euo pipefail

: "${CURSOR_API_KEY:?CURSOR_API_KEY is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPO:?REPO is required}"
: "${PR_NUMBER:?PR_NUMBER is required}"
: "${LINEAR_TICKET_ID:?LINEAR_TICKET_ID is required}"
: "${LINEAR_TICKET_TITLE:?LINEAR_TICKET_TITLE is required}"
: "${LINEAR_TICKET_URL:?LINEAR_TICKET_URL is required}"

MODEL="${MODEL:-auto}"
PR_HEAD_SHA="${PR_HEAD_SHA:-}"
PR_BASE_SHA="${PR_BASE_SHA:-}"
DEVENV_ADMIN_URL="${DEVENV_ADMIN_URL:-}"
DEVENV_MCP_URL="${DEVENV_MCP_URL:-}"
: "${PROMPT_FILE:?PROMPT_FILE is required}"
REPO_TESTING_ENTRY_POINTS_FILE="${REPO_TESTING_ENTRY_POINTS_FILE:-.github/test-plan/entrypoints.md}"
OUTPUT_FILE="${OUTPUT_FILE:-test_plan.md}"

# Load description from file if it exists
if [ -f /tmp/ticket_description.txt ]; then
  LINEAR_TICKET_DESCRIPTION=$(cat /tmp/ticket_description.txt)
  export LINEAR_TICKET_DESCRIPTION
else
  export LINEAR_TICKET_DESCRIPTION=""
fi

echo "Generating test plan for $LINEAR_TICKET_ID..." >&2

# Load repo-specific testing entry points guide (if present)
if [ -f "$REPO_TESTING_ENTRY_POINTS_FILE" ]; then
  # NOTE: envsubst does not recursively expand variables inside $REPO_TESTING_ENTRY_POINTS_GUIDE
  # when it's later injected into the prompt template. Expand devenv placeholders here so we
  # preserve the previous behavior when this guide was inline in the template.
  REPO_TESTING_ENTRY_POINTS_GUIDE=$(
    DEVENV_ADMIN_URL="$DEVENV_ADMIN_URL" DEVENV_MCP_URL="$DEVENV_MCP_URL" \
      envsubst "\$DEVENV_ADMIN_URL \$DEVENV_MCP_URL" < "$REPO_TESTING_ENTRY_POINTS_FILE"
  )
else
  REPO_TESTING_ENTRY_POINTS_GUIDE=$(
    cat <<'EOF'
_No repo-specific testing entry points guide found at `__REPO_TESTING_ENTRY_POINTS_FILE__`._

Before writing scenarios, determine the best testing entry points for this repo (UI URL, API URL, CLI commands, etc.) by reading `README.md` / `AGENTS.md` and inspecting the code/CI, then use those concrete entry points in each scenario's **Entry:** line.
EOF
  )
  REPO_TESTING_ENTRY_POINTS_GUIDE="${REPO_TESTING_ENTRY_POINTS_GUIDE//__REPO_TESTING_ENTRY_POINTS_FILE__/$REPO_TESTING_ENTRY_POINTS_FILE}"
fi
export REPO_TESTING_ENTRY_POINTS_GUIDE

# Export variables for envsubst
export REPO PR_NUMBER PR_HEAD_SHA PR_BASE_SHA DEVENV_ADMIN_URL DEVENV_MCP_URL
export LINEAR_TICKET_ID LINEAR_TICKET_TITLE LINEAR_TICKET_URL

cursor-agent -p "$(envsubst < "$PROMPT_FILE")" --force --model "$MODEL" --output-format=text | tee "$OUTPUT_FILE"

# Check if test plan was generated
if [ ! -f "$OUTPUT_FILE" ] || [ ! -s "$OUTPUT_FILE" ]; then
  echo "Error: $OUTPUT_FILE was not generated or is empty" >&2
  exit 1
fi

echo "Test plan generated successfully ($(wc -l < "$OUTPUT_FILE") lines)" >&2

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "has_test_plan=true" >> "$GITHUB_OUTPUT"
fi
