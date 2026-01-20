# Grapevine PR Reviewer - GitHub Actions Integration

This directory contains the GitHub Actions integration for the Grapevine PR Reviewer. It provides a Docker container and GitHub Action for easy integration into CI/CD pipelines.

## Container Image

```
gathertown/grapevine-pr-reviewer:latest
```

The container runs a unified orchestration script (`run_review.sh`) that handles the complete review workflow:

1. Calls the MCP server to generate a PR review
2. Posts review comments to GitHub (optional)
3. Sends review results to Slack (optional)

All configuration is via environment variables.

## Using in Your Repository

### Option 1: Using the Docker Container Action (Recommended)

Use the Docker container action from corporate-context:

```yaml
name: Grapevine PR Review
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_PASSWORD }}

      - uses: gathertown/grapevine/.github/actions/grapevine-pr-review@main
        with:
          pr_number: ${{ github.event.pull_request.number }}
          repo: ${{ github.repository }}
          mcp_url: ${{ vars.GRAPEVINE_MCP_URL }}
          mcp_api_key: ${{ secrets.GRAPEVINE_MCP_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
          # Optional: Admin backend for storing review metadata
          admin_backend_url: ${{ vars.ADMIN_BACKEND_URL }}
          grapevine_api_key: ${{ secrets.GRAPEVINE_MCP_API_KEY }}
          # Optional: Slack notifications
          slack_bot_token: ${{ secrets.GRAPEVINE_REVIEWER_SLACK_BOT_TOKEN }}
          slack_channel: "C0A1HMDP63E"
          pr_url: ${{ github.event.pull_request.html_url }}
          pr_title: ${{ github.event.pull_request.title }}
          pr_author: ${{ github.event.pull_request.user.login }}
```

### Option 2: Direct Container Usage (Job Container)

Run the container as a job container with environment variables:

```yaml
name: Grapevine PR Review
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    container:
      image: gathertown/grapevine-pr-reviewer:latest
      credentials:
        username: ${{ secrets.DOCKERHUB_USERNAME }}
        password: ${{ secrets.DOCKERHUB_PASSWORD }}
    steps:
      - name: Run PR Review
        run: /app/gha/run_review.sh
        env:
          PR_NUMBER: ${{ github.event.pull_request.number }}
          REPO: ${{ github.repository }}
          MCP_URL: ${{ vars.GRAPEVINE_MCP_URL }}
          MCP_API_KEY: ${{ secrets.GRAPEVINE_MCP_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          POST_REVIEW: "true"
          # Optional: Slack
          SLACK_BOT_TOKEN: ${{ secrets.GRAPEVINE_REVIEWER_SLACK_BOT_TOKEN }}
          SLACK_CHANNEL: "C0A1HMDP63E"
          PR_URL: ${{ github.event.pull_request.html_url }}
          PR_TITLE: ${{ github.event.pull_request.title }}
          PR_AUTHOR: ${{ github.event.pull_request.user.login }}
```

## Required Configuration

### Secrets (in target repository)

| Secret | Required | Description |
|--------|----------|-------------|
| `DOCKERHUB_USERNAME` | Yes | Docker Hub username for pulling the container image |
| `DOCKERHUB_PASSWORD` | Yes | Docker Hub password/token for pulling the container image |
| `GRAPEVINE_MCP_API_KEY` | Yes | API key for your Grapevine MCP server |
| `GRAPEVINE_REVIEWER_SLACK_BOT_TOKEN` | No | For Slack notifications |

### Variables (in target repository)

| Variable | Required | Description |
|----------|----------|-------------|
| `GRAPEVINE_MCP_URL` | Yes | URL of your Grapevine MCP server (e.g., `https://mcp.your-domain.com`) |
| `ADMIN_BACKEND_URL` | No | For storing review metadata |

## Environment Variables

The container accepts the following environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `PR_NUMBER` | Yes | Pull request number to review |
| `REPO` | Yes | Repository in `owner/repo` format |
| `MCP_URL` | Yes | Grapevine MCP server URL |
| `MCP_API_KEY` | Yes | MCP API key for authentication |
| `GITHUB_TOKEN` | Yes | GitHub token for posting review comments |
| `POST_REVIEW` | No | Set to `"true"` to post review to GitHub (default: `"true"`) |
| `ADMIN_BACKEND_URL` | No | Admin backend URL for storing review metadata |
| `GRAPEVINE_API_KEY` | No | Grapevine API key for admin backend |
| `SLACK_BOT_TOKEN` | No | Slack bot token (enables Slack notifications) |
| `SLACK_CHANNEL` | No | Slack channel ID |
| `SLACK_TEAM_DOMAIN` | No | Slack team domain for permalinks |
| `PR_URL` | No | Pull request URL for Slack message |
| `PR_TITLE` | No | Pull request title for Slack message |
| `PR_AUTHOR` | No | Pull request author for Slack message |

## Scripts

The container includes these scripts:

| Script | Description |
|--------|-------------|
| `run_review.sh` | Main orchestration script - runs the complete workflow |
| `call_pr_review_tool.py` | Calls MCP server to get PR review |
| `post_pr_review.py` | Posts review comments to GitHub |
| `send_slack_review.py` | Sends review results to Slack |

## Building the Container Locally

```bash
# From the repository root
docker build -t grapevine-pr-reviewer -f Dockerfile.pr-reviewer .

# Test it (will fail without env vars, but verifies the container runs)
docker run --rm grapevine-pr-reviewer
```

## Architecture

The container uses a thin-client architecture:

1. **Orchestration script** (`run_review.sh`) coordinates the workflow
2. **MCP client** (`call_pr_review_tool.py`) calls the remote Grapevine MCP server
3. **GitHub integration** (`post_pr_review.py`) posts review comments via GitHub API
4. **Slack integration** (`send_slack_review.py`) sends notifications via Slack API

All heavy processing (AI agents, context search, review generation) happens on the Grapevine MCP server - the container is just a lightweight client.

