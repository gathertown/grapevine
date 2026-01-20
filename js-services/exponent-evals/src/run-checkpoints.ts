#!/usr/bin/env tsx
/**
 * Checkpoint Evaluation CLI Runner
 *
 * Runs SingleAgentStrategy against chronological checkpoint files with
 * frozen Linear state for reproducible evaluations.
 *
 * Usage:
 *   tsx src/run-checkpoints.ts [options]
 *
 * Options:
 *   --dataset <path>     Path to dataset directory (default: src/dataset/example-checkpoints)
 *   --strategy <name>    Strategy to use (default: single-agent)
 *   --from <date>        Start from date (YYYY-MM-DD)
 *   --until <date>       Process until date (YYYY-MM-DD)
 *   --filter <string>    Filter checkpoints by filename substring
 *   --parallel           Process checkpoints in parallel (no state accumulation)
 *   --accumulate         Accumulate state across checkpoints (sequential only)
 *   --verbose            Show full reasoning
 *   --grade              Enable LLM grading
 *   --fast               Use fast Levenshtein comparison instead of semantic (default: semantic)
 *   --show-diffs         Display detailed truth diffs
 *   --output <path>      Output directory for results
 *
 * Environment variables:
 *   LINEAR_API_KEY       Linear API key (required)
 *   LINEAR_TEAM_ID       Linear team UUID (required)
 *   LINEAR_TEAM_NAME     Linear team name (required)
 *   MCP_API_KEY          MCP API key (required for live mode)
 *   MCP_BASE_URL         MCP server URL (required for live mode)
 *   EVAL_TENANT_ID       Tenant ID (required for live mode)
 */

import 'dotenv/config';
import { resolve } from 'path';
import { processCheckpoints, type CheckpointConfig } from './checkpoint/processor';
import { displayCheckpointReport, saveCheckpointReport } from './checkpoint/reporter';
import type { CheckpointOptions } from './checkpoint/types';

/**
 * Parse command line arguments
 */
interface ParsedArgs extends CheckpointOptions {
  help: boolean;
}

function parseArgs(): ParsedArgs {
  const args = process.argv.slice(2);

  if (args.includes('--help') || args.includes('-h')) {
    return {
      dataset: 'src/dataset/example-checkpoints',
      strategy: 'single-agent',
      parallel: false,
      accumulate: false,
      verbose: false,
      grade: false,
      semantic: true, // semantic is default
      showDiffs: false,
      output: '',
      help: true,
    };
  }

  const getArgValue = (flag: string): string | undefined => {
    const idx = args.indexOf(flag);
    return idx >= 0 ? args[idx + 1] : undefined;
  };

  const dataset = getArgValue('--dataset') || 'src/dataset/example-checkpoints';

  // semantic is default, --fast disables it
  const useFast = args.includes('--fast');

  return {
    dataset: resolve(dataset),
    strategy: getArgValue('--strategy') || 'single-agent',
    from: getArgValue('--from'),
    until: getArgValue('--until'),
    filter: getArgValue('--filter'),
    parallel: args.includes('--parallel'),
    accumulate: args.includes('--accumulate'),
    verbose: args.includes('--verbose'),
    grade: args.includes('--grade'),
    semantic: !useFast, // semantic by default, disabled with --fast
    showDiffs: args.includes('--show-diffs'),
    output: getArgValue('--output') || dataset,
    help: false,
  };
}

/**
 * Display help message
 */
function displayHelp(): void {
  console.log(`
Checkpoint Evaluation CLI

Processes checkpoint files chronologically with frozen Linear state
for reproducible evaluations.

Usage:
  tsx src/run-checkpoints.ts [options]

Options:
  --dataset <path>     Path to dataset directory (default: src/dataset/example-checkpoints)
  --strategy <name>    Strategy to use (default: single-agent)
  --from <date>        Start from date (YYYY-MM-DD)
  --until <date>       Process until date (YYYY-MM-DD)
  --filter <string>    Filter checkpoints by filename substring
  --parallel           Process checkpoints in parallel (no state accumulation)
  --accumulate         Accumulate state across checkpoints (sequential only)
  --verbose            Show full reasoning for each operation
  --grade              Enable LLM grading of operations
  --fast               Use fast Levenshtein comparison (default: semantic/LLM comparison)
  --show-diffs         Display detailed truth diffs
  --output <path>      Output directory for results (default: same as dataset)
  --help, -h           Show this help message

Environment Variables:
  LINEAR_API_KEY       Linear API key (required)
  LINEAR_TEAM_ID       Linear team UUID (required)
  LINEAR_TEAM_NAME     Linear team name (required)
  MCP_API_KEY          MCP API key (optional, for Grapevine in live mode)
  MCP_BASE_URL         MCP server URL (optional, for Grapevine in live mode)
  EVAL_TENANT_ID       Tenant ID (optional, for Grapevine in live mode)
  OPENAI_API_KEY       OpenAI API key (required)

File Format:
  Checkpoint files must follow one of these patterns:
    - YYYY-MM-DD_HH-MM-SS_<description>.json (with timestamp)
    - YYYY-MM-DD_<description>.json (without timestamp)
  Truth files should be named: <checkpoint>-truth.json

Execution Modes:
  Default:       Sequential, fresh state per document (from truth files)
  --accumulate:  Sequential, state accumulates across documents
  --parallel:    Concurrent, fresh state per document

Examples:
  # Run all checkpoints (default: sequential, fresh state per document)
  tsx src/run-checkpoints.ts

  # Run with state accumulation across documents
  tsx src/run-checkpoints.ts --accumulate

  # Run in parallel (concurrent, no state accumulation)
  tsx src/run-checkpoints.ts --parallel

  # Run checkpoints from specific date range
  tsx src/run-checkpoints.ts --from 2025-01-15 --until 2025-01-17

  # Filter checkpoints by filename
  tsx src/run-checkpoints.ts --filter standup

  # With grading (semantic comparison is default)
  tsx src/run-checkpoints.ts --grade

  # Fast mode with Levenshtein comparison (no LLM calls for matching)
  tsx src/run-checkpoints.ts --fast

  # Custom dataset
  tsx src/run-checkpoints.ts --dataset ./my-checkpoints
`);
}

/**
 * Validate required environment variables
 */
function validateConfig(): CheckpointConfig {
  const linearApiKey = process.env.LINEAR_API_KEY;
  const linearTeamId = process.env.LINEAR_TEAM_ID;
  const linearTeamName = process.env.LINEAR_TEAM_NAME;
  const mcpApiKey = process.env.MCP_API_KEY || '';
  const mcpBaseUrl = process.env.MCP_BASE_URL || '';
  const tenantId = process.env.EVAL_TENANT_ID || '';

  if (!linearApiKey) {
    throw new Error('Missing required environment variable: LINEAR_API_KEY');
  }

  if (!linearTeamId) {
    throw new Error('Missing required environment variable: LINEAR_TEAM_ID');
  }

  if (!linearTeamName) {
    throw new Error('Missing required environment variable: LINEAR_TEAM_NAME');
  }

  if (!process.env.OPENAI_API_KEY) {
    throw new Error('Missing required environment variable: OPENAI_API_KEY');
  }

  return {
    linearApiKey,
    linearTeamId,
    linearTeamName,
    mcpApiKey,
    mcpBaseUrl,
    tenantId,
  };
}

/**
 * Main function
 */
async function main() {
  const args = parseArgs();

  if (args.help) {
    displayHelp();
    process.exit(0);
  }

  console.log('🚀 Checkpoint Evaluation Runner\n');

  // Validate configuration
  let config: CheckpointConfig;
  try {
    config = validateConfig();
  } catch (error) {
    console.error(`❌ Configuration error: ${error instanceof Error ? error.message : error}`);
    console.log('\nRun with --help for usage information');
    process.exit(1);
  }

  console.log('Configuration:');
  console.log(`  Linear Team: ${config.linearTeamName}`);
  console.log(`  Dataset: ${args.dataset}`);
  console.log(`  Strategy: ${args.strategy}`);
  const modeDesc = args.parallel
    ? 'Parallel (concurrent, fresh state per doc)'
    : args.accumulate
      ? 'Sequential (state accumulates across docs)'
      : 'Sequential (fresh state per doc)';
  console.log(`  Mode: ${modeDesc}`);
  if (args.from) console.log(`  From: ${args.from}`);
  if (args.until) console.log(`  Until: ${args.until}`);
  if (args.filter) console.log(`  Filter: ${args.filter}`);
  console.log(`  Comparison: ${args.semantic ? 'Semantic (LLM)' : 'Fast (Levenshtein)'}`);
  if (args.grade) console.log(`  LLM Grading: Yes`);
  if (args.showDiffs) console.log(`  Show Diffs: Yes`);

  // Process checkpoints
  try {
    const report = await processCheckpoints(args, config);

    // Display report
    displayCheckpointReport(report);

    // Save report
    saveCheckpointReport(report, args.output);

    // Exit with error code if any checkpoints failed
    const failedCount = report.summary.failedCheckpoints;
    process.exit(failedCount > 0 ? 1 : 0);
  } catch (error) {
    console.error(`❌ Processing error: ${error instanceof Error ? error.message : error}`);
    process.exit(1);
  }
}

// Handle Ctrl+C and termination signals
process.on('SIGINT', () => {
  console.log('\n\n⚠️  Evaluation interrupted by user (Ctrl+C)');
  process.exit(130);
});

process.on('SIGTERM', () => {
  console.log('\n\n⚠️  Evaluation terminated (SIGTERM)');
  process.exit(143);
});

// Run main function
main().catch((error) => {
  console.error(`❌ Unexpected error: ${error}`);
  process.exit(1);
});
