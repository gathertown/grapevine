#!/usr/bin/env bash
# Posts a comment to a PR
#
# Required environment variables:
#   GH_TOKEN - GitHub token for gh CLI
#   PR_NUMBER - PR number
#
# Arguments:
#   $1 - Comment body OR path to file containing comment (if starts with @)
#
# Example:
#   post-pr-comment.sh "Hello world"
#   post-pr-comment.sh @test_plan.md

set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${PR_NUMBER:?PR_NUMBER is required}"

COMMENT_ARG="${1:?Comment body or @file is required}"

if [[ "$COMMENT_ARG" == @* ]]; then
  # Read from file
  FILE_PATH="${COMMENT_ARG:1}"
  if [ ! -f "$FILE_PATH" ]; then
    echo "Error: File not found: $FILE_PATH" >&2
    exit 1
  fi
  COMMENT=$(cat "$FILE_PATH")
else
  COMMENT="$COMMENT_ARG"
fi

gh pr comment "$PR_NUMBER" --body "$COMMENT"
echo "Posted comment to PR #$PR_NUMBER" >&2
