#!/usr/bin/env bash
# Creates a feature branch and draft PR for a Linear ticket
#
# Required environment variables:
#   GH_TOKEN - GitHub token for gh CLI
#   IDENTIFIER - Linear ticket identifier (e.g., ENG-123)
#   TITLE - Ticket title
#   URL - Linear ticket URL
#   BASE_BRANCH - Base branch for the PR (default: main)
#
# Outputs (to GITHUB_OUTPUT if set, otherwise stdout):
#   branch_name - Name of the created/existing branch
#   existing_pr - "true" if PR already exists, "false" otherwise
#   pr_number - PR number
#   pr_url - PR URL

set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${IDENTIFIER:?IDENTIFIER is required}"
: "${TITLE:?TITLE is required}"
: "${URL:?URL is required}"
BASE_BRANCH="${BASE_BRANCH:-main}"

BRANCH_NAME="feature/${IDENTIFIER}"

output() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "$1" >> "$GITHUB_OUTPUT"
  else
    echo "$1"
  fi
}

# Check if branch already exists remotely
if git ls-remote --exit-code --heads origin "$BRANCH_NAME" > /dev/null 2>&1; then
  echo "Branch $BRANCH_NAME already exists remotely" >&2

  # Check if there's already a PR for this branch
  EXISTING_PR=$(gh pr list --head "$BRANCH_NAME" --json number,url --jq '.[0]')
  if [ -n "$EXISTING_PR" ] && [ "$EXISTING_PR" != "null" ]; then
    PR_NUMBER=$(echo "$EXISTING_PR" | jq -r '.number')
    PR_URL=$(echo "$EXISTING_PR" | jq -r '.url')
    echo "PR already exists: #$PR_NUMBER - $PR_URL" >&2
    output "branch_name=$BRANCH_NAME"
    output "existing_pr=true"
    output "pr_number=$PR_NUMBER"
    output "pr_url=$PR_URL"
    exit 0
  fi

  # Branch exists but no PR - checkout existing branch
  git fetch origin "$BRANCH_NAME"
  git checkout "$BRANCH_NAME"
  output "existing_pr=false"
else
  # Create new branch
  git checkout "$BASE_BRANCH"
  git pull origin "$BASE_BRANCH"
  git checkout -b "$BRANCH_NAME"
  git commit --allow-empty -m "chore: placeholder for $IDENTIFIER"
  git push -u origin "$BRANCH_NAME"
  output "existing_pr=false"
fi

output "branch_name=$BRANCH_NAME"
echo "Branch ready: $BRANCH_NAME" >&2

# Create draft PR if we don't have one yet
if [ "$(git branch --show-current)" == "$BRANCH_NAME" ]; then
  # Check again if PR exists (in case of race condition)
  EXISTING_PR=$(gh pr list --head "$BRANCH_NAME" --json number,url --jq '.[0]')
  if [ -z "$EXISTING_PR" ] || [ "$EXISTING_PR" == "null" ]; then
    PR_URL=$(gh pr create \
      --draft \
      --title "$IDENTIFIER: $TITLE" \
      --body "Linear: $URL" \
      --base "$BASE_BRANCH" \
      --label "vibework")

    PR_NUMBER=$(echo "$PR_URL" | grep -oE '[0-9]+$')
    echo "Created draft PR #$PR_NUMBER: $PR_URL" >&2
    output "pr_number=$PR_NUMBER"
    output "pr_url=$PR_URL"
  else
    # PR was created by another process - output its details
    PR_NUMBER=$(echo "$EXISTING_PR" | jq -r '.number')
    PR_URL=$(echo "$EXISTING_PR" | jq -r '.url')
    echo "PR found (race condition): #$PR_NUMBER - $PR_URL" >&2
    output "pr_number=$PR_NUMBER"
    output "pr_url=$PR_URL"
  fi
fi
