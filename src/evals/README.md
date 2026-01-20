# Corporate Context CLI

A command-line interface for querying the corporate knowledge base and running evaluations.

## Installation

Make sure you have the MCP server running before using the CLI:

```bash
python -m src.mcp.server
```

## Usage

The CLI is accessed through the module path:
```bash
python -m src.evals.cli <command> [options]
```

## Commands

### 1. Query - Search the Knowledge Base

Run a single query against the corporate knowledge base:

```bash
# Basic query
python -m src.evals.cli query "What are the recent updates?"

# With specific model
python -m src.evals.cli query "Show me GitHub issues" --model o3

# With verbose output (shows tool calls and reasoning)
python -m src.evals.cli query "What discussions happened about deployment?" --verbose

# Extract search queries and results
python -m src.evals.cli query "What are the AI team updates?" --extract-search
```

**Options:**
- `--model, -m`: Model to use (default: o3)
- `--verbose, -v`: Show detailed agent reasoning and tool calls
- `--extract-search`: Save search queries and results to JSON file

### 2. Run Experiment - Evaluate Agent Performance

Run evaluation experiments on a set of test questions:

```bash
# Run with default settings
python -m src.evals.cli run-experiment

# With custom concurrency and experiment name
python -m src.evals.cli run-experiment --concurrency 5 --experiment-name "baseline-test"

# Disable tracing for faster execution
python -m src.evals.cli run-experiment --no-tracing

# Extract all search data from the experiment
python -m src.evals.cli run-experiment --extract-search --concurrency 5
```

**Options:**
- `--model, -m`: Model to use for evaluation (default: o3)
- `--concurrency, -c`: Number of questions to process in parallel (default: 10)
- `--experiment-name, -e`: Name to append to output directory
- `--no-tracing`: Disable Langfuse tracing
- `--extract-search`: Extract and save all search queries/results
- `--verbose, -v`: Show detailed output

**Output:**
- Results saved to `runs/experiment_YYYYMMDD_HHMMSS-{model}/`
- Files created:
  - `results.jsonl`: Detailed results for each question
  - `summary.json`: Aggregate statistics
  - `search_extracts.json`: Search data (if --extract-search used)

### 3. Stats - Analyze Experiment Results

Analyze results from a previous evaluation run:

```bash
# Analyze the latest experiment
python -m src.evals.cli stats

# Analyze a specific experiment
python -m src.evals.cli stats runs/experiment_20240101_120000-o3
```

**Output:**
- Grade distribution (1-5 scores)
- Average score and accuracy
- Processing time statistics
- Error analysis
- Tool usage patterns

### 4. Review - Interactive Result Review

Step through experiment results question by question:

```bash
# Review the latest experiment
python -m src.evals.cli review

# Review a specific experiment
python -m src.evals.cli review runs/experiment_20240101_120000-o3
```

**Features:**
- Navigate through questions with arrow keys
- View question, expected answer, actual answer
- See grading details and scores
- Review tool calls made for each question

### 5. Search Eval - Evaluate Search Queries

Process search queries from an evaluation JSONL file and compare results:

```bash
# Basic usage
python -m src.evals.cli search-eval /path/to/eval.jsonl

# Specify output file
python -m src.evals.cli search-eval eval.jsonl -o results.jsonl

# Show detailed progress
python -m src.evals.cli search-eval eval.jsonl --verbose
```

**Options:**
- `eval_file`: Path to the evaluation JSONL file (required)
- `--output, -o`: Output file path (default: timestamped filename)
- `--verbose, -v`: Show detailed progress information

**Input Format:**
The evaluation file should contain queries in JSONL format with:
- `type`: Tool type (semantic_search or keyword_search)
- `query`: The search query text
- `provenance`: Optional filters (dates, sources, etc.)
- `gather_results`: Original results (optional)
- `glean_results`: Original glean results (optional)

**Output:**
- JSONL file with comparison results
- Summary statistics showing total queries, results counts, and sources found

### 6. View - Interactive Results Viewer

View search evaluation results in an interactive web browser interface:

```bash
# View results file
python -m src.evals.cli view search_eval_results.jsonl

# Use a different port
python -m src.evals.cli view results.jsonl --port 9000
```

**Options:**
- `jsonl_file`: Path to the JSONL results file to view (required)
- `--port, -p`: Port to run the local server on (default: 8888)

**Features:**
- Interactive web-based visualization
- Filter by search type (keyword/semantic)
- Search within queries
- Source distribution charts
- Side-by-side comparison of original vs new results
- Automatic browser launch

## Search Extraction Feature

The `--extract-search` flag captures all search tool usage:

```bash
# For single queries
python -m src.evals.cli query "your question" --extract-search

# For experiments
python -m src.evals.cli run-experiment --extract-search
```

**Extracted data includes:**
- Search tool used (semantic_search, keyword_search)
- Query parameters and filters
- Number of results found
- Sample of results (id, score, source, metadata only)

**Output files:**
- Single query: `search_extract_YYYYMMDD_HHMMSS.json`
- Experiment: `runs/experiment_*/search_extracts.json`

## Environment Variables

Set these in your `.env` file:

```bash
OPENAI_API_KEY=sk-...  # Required for o3 model and grading
```

## Examples

### Finding Recent Updates
```bash
python -m src.evals.cli query "What are the recent updates in the engineering channel?" --extract-search
```

### Running a Quick Evaluation
```bash
python -m src.evals.cli run-experiment --concurrency 5 --experiment-name "quick-test"
python -m src.evals.cli stats  # View results
```

### Debugging Search Performance
```bash
python -m src.evals.cli query "complex technical question" --verbose --extract-search
# Check search_extract_*.json to see what queries were generated
```

### Batch Evaluation with Search Analysis
```bash
python -m src.evals.cli run-experiment --extract-search --concurrency 20
# Analyze search patterns across all questions in search_extracts.json
```

## Tips

1. **Always start the MCP server first** - The CLI makes HTTP calls to the server
2. **Use --verbose for debugging** - Shows all tool calls and agent reasoning
3. **Use --extract-search for analysis** - Understand how the agent searches
4. **Adjust concurrency for performance** - Lower values for stability, higher for speed
5. **Name experiments meaningfully** - Use --experiment-name for organization