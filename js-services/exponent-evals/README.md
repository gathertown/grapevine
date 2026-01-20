# Exponent Evaluation Harness

Evaluation harness for triage strategies that runs test cases against real MCP/staging data and compares results with ground truth annotations.

## Overview

This service allows you to:

- Run triage strategies against curated test datasets
- Compare generated operations against ground truth
- Measure accuracy, precision, and iteration improvements
- Safely test against staging/production tenant data

## Architecture

```
exponent-evals/
├── src/
│   ├── run-evals.ts              # Main CLI runner (triage evals)
│   ├── run-checkpoints.ts        # Checkpoint evaluation runner
│   ├── run-description-evals.ts  # Description enhancement runner
│   ├── lib/
│   │   ├── mcp-client.ts         # MCP API calls with API key auth
│   │   ├── mock-tenant-app.ts    # Mock TenantSlackApp interface
│   │   ├── processor.ts          # Eval orchestration
│   │   ├── reporter.ts           # Results display
│   │   └── comparison.ts         # Ground truth comparison
│   ├── dataset/
│   │   ├── examples/             # Test cases with ground truth
│   │   ├── description-enhancement/  # Description enhancement evals
│   │   │   └── examples/         # LK-based example test cases
│   │   └── cases/                # Real Slack conversations
│   └── results/                  # Auto-generated outputs
├── .env.example
└── package.json
```

### MCP Tool Integration

The eval harness supports both MCP tools used by triage strategies:

- **`ask_agent`**: Analyzes conversations and searches for related tickets via API key authentication
- **`get_document`**: Fetches full document content for duplicate ticket descriptions
  - In production: Uses JWT authentication via `callGetDocumentViaMCP()`
  - In eval mode: Uses API key authentication via `MockTenantSlackApp.callGetDocument()`
  - Strategies automatically detect which method to use based on the app interface

## Setup

1. **Install dependencies:**

   ```bash
   cd js-services/exponent-evals
   yarn install
   ```

2. **Configure environment:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your credentials:

   ```bash
   EVAL_TENANT_ID=abc123def456        # Your tenant ID
   MCP_API_KEY=your-mcp-api-key       # MCP API key
   MCP_BASE_URL=https://mcp.your-domain.com  # No trailing slash!
   OPENAI_API_KEY=sk-...
   TASK_EXTRACTION_MODEL=gpt-5
   ```

## Usage

### Available Strategies

- `triage-agent` - Default triage agent strategy

### Run All Evals

```bash
# Run with default strategy (triage-agent)
yarn eval

# Run with specific strategy
yarn eval --strategy triage-agent
```

### Compare Against Ground Truth

```bash
yarn eval:compare
```

This compares generated operations against `*-truth.json` files and displays:

- Action match rate (CREATE/UPDATE/SKIP)
- Title similarity scores
- Description similarity scores
- Issue ID matches (for UPDATE operations)

### Run Specific Test

```bash
yarn eval --filter oauth-bug
```

### Verbose Output

```bash
yarn eval:verbose
```

Shows full reasoning for each operation.

### Custom Dataset

```bash
yarn eval --dataset ./src/dataset/cases --compare
```

## Dataset Format

### Test Case File (`oauth-bug.json`)

```json
{
  "id": "oauth-bug",
  "title": "OAuth fails with invalid_scope error",
  "date": "2025-01-15",
  "type": "slack",
  "content": "User: I'm getting an invalid_scope error...",
  "participants": ["user-feedback-bot"],
  "files": []
}
```

### Ground Truth File (`oauth-bug-truth.json`)

```json
{
  "operations": [
    {
      "action": "CREATE",
      "createData": {
        "title": "OAuth fails with invalid_scope error",
        "description": "## Summary\n\nUser reports...",
        "issueId": null
      },
      "confidence": 95,
      "reasoning": "Clear bug report..."
    }
  ]
}
```

## Creating Test Cases

### 1. Add New Test Case

Create a new JSON file in `src/dataset/examples/`:

```bash
touch src/dataset/examples/my-test.json
```

### 2. Add Ground Truth (Optional)

Create corresponding truth file:

```bash
touch src/dataset/examples/my-test-truth.json
```

### 3. Run Eval

```bash
yarn eval --filter my-test --compare
```

## Output

Results are saved to `src/results/<timestamp>/`:

```
src/results/2025-01-15T14-30-00/
├── oauth-bug-generated.json
├── vague-report-generated.json
└── ...
```

Each generated file contains:

- Test case ID and title
- Generated operations
- Triage analysis
- Ask agent metrics (response times, token usage)

## Interpreting Results

### Summary Report

```
📊 EVALUATION SUMMARY
================================================================================

Total test cases: 2
  ✅ Passed: 2
  ❌ Failed: 0
  ⏱️  Average duration: 3245ms

--------------------------------------------------------------------------------
Ground Truth Comparison:
--------------------------------------------------------------------------------

  Action matches: 2/2
  Title matches: 2/2
  Average title similarity: 95.3%
  Average description similarity: 87.6%

--------------------------------------------------------------------------------
Operation Distribution:
--------------------------------------------------------------------------------

  CREATE: 1
  UPDATE: 0
  SKIP: 1
```

### Comparison Metrics

- **Action Match**: Did the strategy choose the correct operation (CREATE/UPDATE/SKIP)?
- **Title Similarity**: How similar is the generated title to ground truth? (0-100%)
- **Description Similarity**: How similar is the generated description? (0-100%)
- **Issue ID Match**: For UPDATE operations, did it identify the correct duplicate ticket?

## Best Practices

### Security

✅ **API Key auth** - Uses MCP API key (no JWT private key exposure)
✅ **Read-only** - No Linear writes (eval mode is read-only by default)
✅ **Rate limited** - 1 second delay between test cases
✅ **Non-billable** - Eval requests marked as non-billable in MCP calls

### Dataset Management

- ✅ Commit `examples/*.json` (synthetic test cases) to git
- ❌ Don't commit `cases/*.json` (real Slack data - may contain sensitive info)
- ✅ Commit `*-truth.json` ground truth annotations
- ❌ Don't commit `results/` directory (auto-generated)

### Iteration Workflow

1. **Baseline**: Run evals against current strategy
2. **Iterate**: Modify prompts/logic in your strategy implementation
3. **Re-evaluate**: Run evals again with `--compare`
4. **Measure**: Compare metrics to baseline
5. **Repeat**: Continue until metrics improve

## Troubleshooting

### "MCP request failed: 401"

Your `MCP_API_KEY` is invalid or expired. Check your `.env` file.

### "No test cases found"

Check that your dataset directory contains `*.json` files (not `*-truth.json` or `*-generated.json`).

### "Failed to parse JSON"

Ensure your test case JSON files are valid. Use a JSON validator or `jq`:

```bash
jq . src/dataset/examples/my-test.json
```

### Timeouts

Default timeout is 10 minutes per test case. If your evals are timing out, check:

- MCP server is responding
- OpenAI API is working
- Network connectivity is stable

## CLI Reference

```
tsx src/run-evals.ts [options]

Options:
  --dataset <path>   Path to dataset directory (default: src/dataset/examples)
  --compare          Compare against ground truth files
  --verbose          Show full reasoning for each operation
  --filter <pattern> Only run tests matching pattern
  --output <path>    Custom output directory (default: src/results)
  --help, -h         Show help message
```

## Checkpoint Evaluations

Checkpoint evaluations allow you to test the `SingleAgentStrategy` against chronological sequences of documents (meeting transcripts, Slack conversations) with frozen Linear state for reproducible results.

### Overview

Checkpoints differ from regular evals in that they:

- Process documents in chronological order
- Support multiple execution modes for different testing scenarios
- Use semantic (LLM-based) comparison by default for accurate matching

### Execution Modes

| Mode        | Flag           | Execution  | LinearState             | Use Case                              |
| ----------- | -------------- | ---------- | ----------------------- | ------------------------------------- |
| **Default** | none           | Sequential | Fresh per document      | Isolated evaluation of each document  |
| Accumulate  | `--accumulate` | Sequential | Accumulates across docs | Simulate real-world state progression |
| Parallel    | `--parallel`   | Concurrent | Fresh per document      | Fast evaluation of large datasets     |

**Default mode** processes each checkpoint with only its truth file's linearState, giving you isolated evaluation of each document.

**Accumulate mode** (`--accumulate`) maintains state between checkpoints, simulating how issues accumulate in a real project over time. Each checkpoint's operations modify the state for subsequent checkpoints.

**Parallel mode** (`--parallel`) processes all checkpoints concurrently for speed, with each using only its own truth state.

### Running Checkpoints

```bash
# Run all checkpoints (default: sequential, fresh state per document)
yarn checkpoints

# Run with state accumulation across documents
yarn checkpoints --accumulate

# Run in parallel (concurrent, no state accumulation)
yarn checkpoints --parallel

# With LLM grading (scores each operation 1-5)
yarn checkpoints --grade

# Fast mode (Levenshtein comparison, no LLM matching)
yarn checkpoints --fast

# Run specific date range
yarn checkpoints --from 2025-01-15 --until 2025-01-17

# Custom dataset
yarn checkpoints --dataset ./my-dataset
```

### Checkpoint Dataset Format

Checkpoint files should be placed in a dataset directory following this structure:

```
my-dataset/
├── 2025-01-15_09-00-00_standup.json       # Checkpoint 1
├── 2025-01-15_09-00-00_standup-truth.json # Ground truth for checkpoint 1
├── 2025-01-16_09-00-00_standup.json       # Checkpoint 2
├── 2025-01-16_09-00-00_standup-truth.json # Ground truth for checkpoint 2
└── results/                                # Auto-generated outputs (gitignored)
```

#### Checkpoint File (`YYYY-MM-DD_HH-MM-SS_description.json`)

```json
{
  "title": "Morning standup 2025-01-15",
  "type": "meeting",
  "date": "2025-01-15",
  "attendees": ["Sarah", "Tom", "Mike"],
  "content": "Sarah: I'm going to add dark mode to the dashboard this week..."
}
```

#### Truth File (`*-truth.json`)

```json
{
  "input": {
    "linearState": [],
    "docs": ["2025-01-15_09-00-00_standup.json"]
  },
  "output": {
    "operations": [
      {
        "action": "CREATE",
        "createData": {
          "title": "Add dark mode to dashboard",
          "description": "Sarah committed to adding dark mode...",
          "assigneeId": "sarah"
        },
        "confidence": 90,
        "reasoning": "Clear commitment from Sarah..."
      }
    ]
  }
}
```

The `linearState` field in the truth file specifies the frozen Linear issues that should exist when processing that checkpoint. This allows you to simulate different states of the issue tracker.

### Comparison Modes

| Mode               | Flag     | Description                                                  |
| ------------------ | -------- | ------------------------------------------------------------ |
| Semantic (default) | -        | LLM-based comparison that understands semantic equivalence   |
| Fast               | `--fast` | Levenshtein string distance (faster, cheaper, less accurate) |

Semantic comparison is recommended because it correctly matches operations with different wording but the same intent (e.g., "Add dark mode" ≈ "Implement dark mode feature").

### LLM Grading

The `--grade` flag enables LLM-based grading of each operation on a 1-5 scale:

| Score | Meaning                           |
| ----- | --------------------------------- |
| 5/5   | Perfect match                     |
| 4/5   | Mostly correct, minor differences |
| 3/5   | Partially correct, some gaps      |
| 2/5   | Major issues                      |
| 1/5   | Wrong action or target            |

Grading results are included in the output JSON:

```json
{
  "grading": {
    "llmGrades": [
      {
        "score": 4,
        "reasoning": "Correct action and target, minor wording differences",
        "grader_info": "Graded with gpt-4o using rubric v2"
      }
    ],
    "averageGrade": 4,
    "graderInfo": "Graded with gpt-4o using rubric v2"
  }
}
```

### CLI Reference

```
yarn checkpoints [options]

Options:
  --dataset <path>   Path to dataset directory (default: src/dataset/example-checkpoints)
  --strategy <name>  Strategy to use (default: single-agent)
  --from <date>      Start from date (YYYY-MM-DD)
  --until <date>     Process until date (YYYY-MM-DD)
  --parallel         Process in parallel (no state accumulation)
  --accumulate       Accumulate state across checkpoints (sequential only)
  --verbose          Show full reasoning
  --grade            Enable LLM grading (1-5 scores)
  --fast             Use Levenshtein instead of semantic comparison
  --show-diffs       Display detailed diffs
  --output <path>    Output directory (default: same as dataset)
  --help, -h         Show help message
```

### Environment Variables

```bash
LINEAR_API_KEY=lin_api_...        # Required
LINEAR_TEAM_ID=825a22b2-...       # Required (UUID)
LINEAR_TEAM_NAME=My Team          # Required
OPENAI_API_KEY=sk-...             # Required (for semantic comparison and grading)
```

## Description Enhancement Evaluations

Description enhancement evals test the `enhanceTaskDescription` function in isolation, which takes basic task information extracted from meetings or Slack and generates structured Linear ticket descriptions.

### Overview

The description enhancer:

- Takes a CREATE operation with basic title/description + source content
- Calls `ask_agent_fast` to generate a structured description
- Outputs sections: Summary, Context, Requirements, Technical Considerations (optional), References

### Running Description Enhancement Evals

```bash
# Run all description enhancement evals
yarn eval:description

# Run with verbose output (shows full enhanced descriptions)
yarn eval:description --verbose

# Filter by test case name
yarn eval:description --filter meeting

# Custom dataset directory
yarn eval:description --dataset src/dataset/description-enhancement/examples

# Combined
yarn eval:description --dataset src/dataset/description-enhancement/examples --filter lk5 --verbose
```

### Dataset Format

#### Input File (`my-test.json`)

```json
{
  "id": "my-test",
  "type": "slack",
  "sourceDescription": "this Slack conversation",
  "sourceLink": "https://slack.com/...",
  "sourceContent": "... raw Slack messages or meeting transcript ...",
  "operation": {
    "action": "CREATE",
    "createData": {
      "title": "Fix login bug",
      "description": "Users are getting logged out randomly"
    }
  }
}
```

- `type`: Either `"slack"` or `"meeting"`
- `sourceDescription`: Human-readable description (e.g., "this Slack conversation", "this meeting transcript")
- `sourceContent`: The raw source content (Slack messages or meeting transcript)
- `operation`: The CREATE operation with basic title/description to enhance

#### Ground Truth File (optional, `my-test-truth.json`)

```json
{
  "enhancedDescription": "## Summary\n..."
}
```

### Output Format

Results are saved to `src/dataset/description-enhancement/results/run-<timestamp>/`:

```
results/run-2025-12-08T23-35-12/
├── lk2-meeting-board-routing-generated.json
├── lk5-slack-ssm-conflict-generated.json
└── summary.json
```

Each generated file:

```json
{
  "id": "lk2-meeting-board-routing",
  "input": {
    "title": "Investigate Exponent board routing bug",
    "description": "Original basic description..."
  },
  "output": {
    "enhancedDescription": "## Summary\n..."
  },
  "grade": null,
  "comparison": null
}
```

### Example Output

A successful enhancement transforms a basic description:

**Input:**

```
Investigate why unrelated issues are appearing on the Exponent board.
- Verify routing/search scoping
- Karen: review logs
```

**Enhanced Output:**

```markdown
## Summary

Investigate and fix a routing/search scoping bug causing unrelated issues to appear on the Exponent board.

## Context

In the LK standup, the team saw an unrelated task on the Exponent board. Multiple participants suspect routing isn't limited to the selected team.

## Requirements

- Verify routing and search are strictly scoped to the Exponent team/board
- Review logs to trace how the item was added
- Reproduce in staging if possible
- Add diagnostics to make future occurrences easier to debug

## References

- Meeting: LK standup (2025-12-02 18:00–18:35 UTC)
```

### CLI Reference

```
yarn eval:description [options]

Options:
  --dataset <path>    Path to dataset directory (default: src/dataset/description-enhancement)
  --verbose           Show full enhanced descriptions in console
  --filter <pattern>  Only run tests matching pattern (case-insensitive)
  --output <path>     Custom output directory for results
  --help, -h          Show help message
```

### Environment Variables

```bash
EVAL_TENANT_ID=abc123def456        # Required
MCP_API_KEY=your-mcp-api-key       # Required
MCP_BASE_URL=https://mcp.your-domain.com  # Required
```

### Example Test Cases

Two example test cases are provided from the LK datasets:

- `examples/lk5-slack-ssm-conflict.json` - Slack thread about devenv vs staging SSM conflict
- `examples/lk2-meeting-board-routing.json` - Meeting discussion about board routing bug

Run them with:

```bash
yarn eval:description --dataset src/dataset/description-enhancement/examples --verbose
```

## Related

- **Triage Strategies**: `../slack-bot/src/triage/`
- **SingleAgentStrategy**: `../exponent-core/src/SingleAgentStrategy.ts`
- **Exponent Evals**: `~/Documents/exponent/apps/experiments/` (reference implementation)
