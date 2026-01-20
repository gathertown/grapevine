# GitHub PR Reviewer

This script uses Grapevine's AI-powered multi-agent system to automatically review GitHub pull requests and provide structured code review feedback with corporate context.

## Features

- Fetches PR diffs from GitHub using unified diff format
- Extracts line numbers and file changes automatically
- **3-phase multi-agent analysis**:
  - Phase 1: Initial Analysis - identifies specific code changes
  - Phase 2: Context Investigation - parallel agents search corporate context for relevant insights
  - Phase 3: Review Synthesis - generates final review with decision and comments
- **Corporate context access**: Agents search your organization's codebase, docs, Slack, Notion, and knowledge via MCP tools
- Returns structured JSON review with line-level feedback
- **Impact and confidence scoring**: Each comment includes severity assessment
- **Category tagging**: Comments tagged with correctness, performance, security, reliability, or other
- Identifies potential bugs, patterns, and improvements using corporate context

## Requirements

- Python 3.11+
- GitHub personal access token
- Remote MCP bearer token (for Grapevine access)
- `REMOTE_MCP_URL` must be set to your MCP server URL (e.g., `https://mcp.your-domain.com`)

## Installation

The script uses dependencies already installed in the project:

```bash
# From the project root
uv sync
```

## Usage

### Basic Usage

```bash
# Set tokens first
export GITHUB_TOKEN=ghp_your_token_here
export REMOTE_MCP_TOKEN=your_mcp_token_here

# Review PR #123 from the default repo
uv run python scripts/reviewer/pr_reviewer.py 123
```

### With Command-Line Arguments

```bash
uv run python scripts/reviewer/pr_reviewer.py 123 \
  --github-token ghp_your_token_here
```

### Review PR from Different Repo

```bash
GITHUB_TOKEN=<token> REMOTE_MCP_TOKEN=<api_key> REMOTE_MCP_URL=https://mcp.your-domain.com \
  uv run python -m scripts.reviewer.pr_reviewer 123 \
  --repo-url owner/other-repo
```

### Save Results to Custom Directory

```bash
GITHUB_TOKEN=<token> REMOTE_MCP_TOKEN=<api_key> REMOTE_MCP_URL=https://mcp.your-domain.com \
  uv run python -m scripts.reviewer.pr_reviewer 123 \
  --output-dir ./my_reviews
```

## Command-Line Options

| Option               | Description                                  | Default                                     |
| -------------------- | -------------------------------------------- | ------------------------------------------- |
| `pr_number`          | Pull request number (positional)             | Required                                    |
| `--repo-url`         | GitHub repository URL or `owner/repo` format | `gathertown/gather-town-v2-frozen-11-17-25` |
| `--github-token`     | GitHub personal access token                 | `$GITHUB_TOKEN`                             |
| `--output-dir`, `-o` | Output directory for review files            | `scripts/reviewer/reviews/`                 |

### Environment Variables

| Variable           | Description                      | Default                               |
| ------------------ | -------------------------------- | ------------------------------------- |
| `GITHUB_TOKEN`     | GitHub personal access token     | Required                              |
| `REMOTE_MCP_TOKEN` | Grapevine API key for MCP access | Required                              |
| `REMOTE_MCP_URL`   | MCP server URL                   | Required                              |

## Output Format

The script returns a JSON object with a review decision and line-level comments:

### Structure

```json
{
  "decision": "CHANGES_REQUESTED",
  "comments": [
    {
      "path": "src/services/UserService.ts",
      "line": 45,
      "body": "This change removes the user validation step that was added after the incident on 2024-03-15. See postmortem: https://notion.so/...",
      "categories": ["correctness"],
      "impact": 85,
      "impact_reason": "Removing validation could allow invalid user data to reach the database, similar to the March incident",
      "confidence": 90,
      "confidence_reason": "Found exact match with past incident report and the code pattern is identical"
    },
    {
      "path": "src/api/endpoints.ts",
      "lines": [23, 28],
      "body": "This endpoint change breaks backwards compatibility with v1 clients. Related discussion: https://slack.com/...",
      "categories": ["reliability"],
      "impact": 70,
      "impact_reason": "Breaking change will affect existing API consumers",
      "confidence": 75,
      "confidence_reason": "Found related Slack discussion about v1 client usage, but unclear how many clients are affected"
    }
  ]
}
```

### Fields

#### Decision

One of:

- **CHANGES_REQUESTED**: Serious issues found (bugs, security, breaking changes)
- **COMMENT**: Interesting context worth sharing but no blocking issues
- **APPROVE**: No relevant issues found

#### Comments Array

Each comment object contains:

- **path**: Path to the file
- **line** or **lines**: Single line number or `[start, end]` range
- **body**: Detailed comment with context and links to relevant documentation
- **categories**: Array of issue categories (`correctness`, `performance`, `security`, `reliability`, `other`)
- **impact**: 0-100 severity score (100 = most severe, e.g., could cause outage or data loss)
- **impact_reason**: Explanation of the severity assessment
- **confidence**: 0-100 confidence in the assessment (100 = strong evidence directly supports finding)
- **confidence_reason**: Explanation of evidence quality

## Examples

### Review a PR from the default repo (Gather)

```bash
# Reviews PR #12345 from default repo
GITHUB_TOKEN=<token> REMOTE_MCP_TOKEN=<api_key> REMOTE_MCP_URL=https://mcp.your-domain.com \
  uv run python -m scripts.reviewer.pr_reviewer 12345
```

### Review a PR from a different repository

```bash
GITHUB_TOKEN=<token> REMOTE_MCP_TOKEN=<api_key> REMOTE_MCP_URL=https://mcp.your-domain.com \
  uv run python -m scripts.reviewer.pr_reviewer 42 \
  --repo-url myorg/myrepo
```

### Review and save results

```bash
GITHUB_TOKEN=<token> REMOTE_MCP_TOKEN=<api_key> REMOTE_MCP_URL=https://mcp.your-domain.com \
  uv run python -m scripts.reviewer.pr_reviewer 99 \
  -o ./pr_reviews

# View the results
cat ./pr_reviews/pr-99-*.json | jq '.'
```

## GitHub Actions / CI/CD Integration

For using the PR Reviewer in GitHub Actions or other CI/CD pipelines, see the dedicated documentation:

**[GitHub Actions Integration Guide](../../src/pr_reviewer/gha/README.md)**

This includes:
- Docker container usage (`gathertown/grapevine-pr-reviewer:latest`)
- GitHub Action configuration
- Required secrets and variables
- Environment variable reference

## How It Works

The reviewer uses a 3-phase multi-agent architecture:

### Phase 1: Initial Analysis

- Fetches PR metadata and file diffs from GitHub
- Parses unified diff format to extract precise line ranges
- Identifies specific code changes (what changed, how it was implemented)
- Outputs a list of changes with file paths and line numbers

### Phase 2: Context Investigation

- Spawns parallel investigation agents for each change
- Agents search corporate context using MCP tools:
  - `keyword_search`: Find exact term matches in Slack, GitHub, Notion, etc.
  - `semantic_search`: Find conceptually similar content
  - `get_document`: Fetch full document content for deeper analysis
- Looks for relevant patterns, past incidents, documentation, and discussions
- Skips auto-generated files (lock files, build outputs, etc.)
- Returns insights with impact/confidence scoring

### Phase 3: Review Synthesis

- Aggregates all insights from investigation phase
- Generates structured review with decision and comments
- Preserves line numbers and evidence links from investigation
- Produces final JSON output

### Architecture

The script uses a **local agent loop with remote MCP tools** pattern:

- **Agent loop runs locally**: Full visibility into agent reasoning and tool calls
- **MCP tools execute remotely**: Search calls routed to `REMOTE_MCP_URL` (your self-hosted MCP server)
- **Tenant resolution**: Tenant ID is extracted from `REMOTE_MCP_TOKEN`
- **Event streaming**: All agent events captured for debugging and observability

## Error Handling

The script includes comprehensive error handling for:

- Invalid GitHub URLs or repository formats
- PR not found errors
- GitHub API rate limiting
- Network failures
- Invalid API responses
- JSON parsing errors
- Phase-level failures (attempts to continue with remaining phases)

## Limitations

- Binary files are skipped automatically
- Requires a valid Remote MCP bearer token with access to Grapevine
- Requires `REMOTE_MCP_URL` to be set to your MCP server
- Hardcoded default repo: `gathertown/gather-town-v2-frozen-11-17-25`
- Very large PRs may take longer due to multi-agent processing

## Contributing

When making changes to this script:

1. Maintain type hints for all functions
2. Add docstrings for new classes and methods
3. Update this README with new features or options
4. Run all code quality checks before committing
5. Test with real PRs to ensure functionality

## License

This script is part of the Corporate Context project and follows the same license.
