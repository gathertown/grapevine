#!/usr/bin/env bash

set -euo pipefail

if [[ -z "$CI" ]]; then
  echo "This script must be ran in Github Actions" >&2
  exit 1
fi

status="${1:-"in_progress"}"
if [[ "$status" != "in_progress" ]] && [[ "$status" != "success" ]] && [[ "$status" != "failure" ]]; then
  echo "Unknown status option: $status" >&2
  exit 1
fi

# get_header returns a title acceptable summary for the current status
# of the devenv.
get_title() {
  case "$status" in
  "in_progress")
    echo "Application is being deployed to a devenv"
    ;;
  "success")
    echo "Application has been deployed to a devenv"
    ;;
  "failure")
    echo "Application failed to be deployed to a devenv"
    ;;
  esac
}

# get_title_emoji returns an emoji suitable for being displayed BEFORE
# the title.
get_title_emoji() {
  case "$status" in
  "in_progress")
    echo "⏳"
    ;;
  "success")
    echo "✅"
    ;;
  "failure")
    echo "❌"
    ;;
  esac
}

devenv_name="cc-devenv-$GITHUB_PR_NUMBER"
devenv_url="https://$devenv_name.stg.getgrapevine.ai"
mcp_url="https://mcp-$devenv_name.stg.getgrapevine.ai"
workflow_run_url="https://github.com/$GITHUB_REPOSITORY/actions/runs/$GITHUB_WORKFLOW_ID"
argocd_app_url="https://argocd.us-east-1-a.stg.aws.getgrapevine.ai/applications/argocd/$devenv_name"
current_time_gha_format=$(date -u +%Y-%m-%dT%H:%M:%SZ)

comment_body="## 🚀 Devenv Deployment Status

**$(get_title_emoji) $(get_title)**

**Application URLs:**
- 🌐 Admin UI: $devenv_url
- 🔧 Admin Backend API: $devenv_url/api
- 🔌 MCP API: $mcp_url

**Commit**: \`$GITHUB_PR_HEAD_SHA\`

[[ArgoCD Application URL]($argocd_app_url)] || [[Docker Image Builds]($workflow_run_url)]
"

# Create GitHub check
check_status="completed"
if [[ "$status" == "in_progress" ]]; then
  check_status="in_progress"
fi

check_create_fields=(
  --field "name=devenv deployment"
  --field "head_sha=$GITHUB_PR_HEAD_SHA"
  --field "status=$check_status"
  --field "details_url=$devenv_url"
  --field "output[title]=$(get_title)"
  --field "output[summary]=$comment_body"
)
if [[ "$check_status" == "completed" ]]; then
  check_create_fields+=(
    --field "completed_at=$current_time_gha_format"
    --field "conclusion=$status"
  )
else
  check_create_fields+=(--field "started_at=$current_time_gha_format")
fi

gh api \
  --method POST \
  --header "Accept: application/vnd.github+json" \
  "${check_create_fields[@]}" \
  "repos/$GITHUB_REPOSITORY/check-runs"

# Find existing devenv deployment comment by looking for the unique header
COMMENT_ID=$(gh api "/repos/$GITHUB_REPOSITORY/issues/$GITHUB_PR_NUMBER/comments" --jq '.[] | select(.body | contains("## 🚀 Devenv Deployment Status")) | .id' | head -n 1)

if [ -n "$COMMENT_ID" ]; then
  echo "Updating existing devenv deployment comment ID: $COMMENT_ID"
  gh api -X PATCH "/repos/$GITHUB_REPOSITORY/issues/comments/$COMMENT_ID" -f body="$comment_body"
else
  echo "Creating new devenv deployment comment"
  gh pr comment \
    --repo "$GITHUB_REPOSITORY" \
    --body "$comment_body" "$GITHUB_PR_NUMBER"
fi
