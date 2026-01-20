#!/usr/bin/env tsx
/**
 * Triage Evaluation CLI Runner
 *
 * Runs TriageAgentStrategy against test datasets and compares results
 * against ground truth annotations.
 *
 * Usage:
 *   tsx src/run-evals.ts [options]
 *
 * Options:
 *   --dataset <path>   Path to dataset directory (default: src/dataset/examples)
 *   --compare          Compare against ground truth files
 *   --verbose          Show full reasoning for each operation
 *   --filter <pattern> Only run tests matching pattern
 *   --output <path>    Custom output directory for results (default: src/results)
 *   --grade            Enable LLM grading of operations (requires OPENAI_API_KEY)
 *   --semantic         Use semantic comparison agent instead of Levenshtein distance
 *   --show-diffs       Display detailed truth diffs for each test case
 *
 * Environment variables:
 *   EVAL_TENANT_ID     Tenant ID to run evals against (required)
 *   MCP_API_KEY        MCP API key for authentication (required)
 *   MCP_BASE_URL       MCP server URL (required)
 *   OPENAI_API_KEY     OpenAI API key (required)
 *   TASK_EXTRACTION_MODEL  Model to use (default: gpt-5)
 */

import 'dotenv/config';
import { readdirSync, readFileSync, existsSync, statSync } from 'fs';
import { join, resolve, basename } from 'path';
import { TriageAgentStrategy } from '@corporate-context/slack-bot/triage';
import { SingleAgentStrategy } from '@corporate-context/exponent-core';
import { processEvals, type TestCase, type EvalConfig, type EvalOptions } from './lib/processor';
import { displayReport, displayTestCases } from './lib/reporter';

/**
 * Parse command line arguments
 */
interface ParsedArgs {
  dataset: string;
  compare: boolean;
  verbose: boolean;
  filter?: string;
  output: string;
  strategy: string;
  help: boolean;
  // New options for LLM grading and semantic comparison
  grade: boolean;
  semantic: boolean;
  showDiffs: boolean;
}

function parseArgs(): ParsedArgs {
  const args = process.argv.slice(2);

  if (args.includes('--help') || args.includes('-h')) {
    return {
      dataset: 'src/dataset/examples',
      compare: false,
      verbose: false,
      output: 'src/results',
      strategy: 'single-agent',
      help: true,
      grade: false,
      semantic: false,
      showDiffs: false,
    };
  }

  const datasetIdx = args.indexOf('--dataset');
  const filterIdx = args.indexOf('--filter');
  const outputIdx = args.indexOf('--output');
  const strategyIdx = args.indexOf('--strategy');

  const dataset: string = (datasetIdx >= 0 && args[datasetIdx + 1]) || 'src/dataset/examples';
  const output: string = (outputIdx >= 0 && args[outputIdx + 1]) || 'src/results';
  const strategy: string = (strategyIdx >= 0 && args[strategyIdx + 1]) || 'single-agent';
  const filter = filterIdx >= 0 ? args[filterIdx + 1] : undefined;

  // Validate filter pattern is not empty
  if (filter !== undefined && filter.trim() === '') {
    throw new Error('Filter pattern cannot be empty');
  }

  // Validate output path doesn't contain dangerous characters
  if (output.includes('..') || output.startsWith('/etc') || output.startsWith('/sys')) {
    throw new Error('Output path contains potentially dangerous characters');
  }

  return {
    dataset,
    compare: args.includes('--compare'),
    verbose: args.includes('--verbose'),
    filter,
    output,
    strategy,
    help: false,
    grade: args.includes('--grade'),
    semantic: args.includes('--semantic'),
    showDiffs: args.includes('--show-diffs'),
  };
}

/**
 * Display help message
 */
function displayHelp(): void {
  console.log(`
Exponent Evaluation CLI

Usage:
  tsx src/run-evals.ts [options]

Options:
  --dataset <path>    Path to dataset directory (default: src/dataset/examples)
  --strategy <name>   Strategy to use (default: single-agent)
                      Available: single-agent, triage-agent
  --compare           Compare against ground truth files
  --verbose           Show full reasoning for each operation
  --filter <pattern>  Only run tests matching pattern
  --output <path>     Custom output directory for results (default: src/results)
  --grade             Enable LLM grading of operations (requires OPENAI_API_KEY)
  --semantic          Use semantic comparison agent instead of Levenshtein distance
  --show-diffs        Display detailed truth diffs for each test case
  --help, -h          Show this help message

Environment Variables (required for all strategies):
  EVAL_TENANT_ID            Tenant ID to run evals against
  MCP_API_KEY               MCP API key for authentication
  MCP_BASE_URL              MCP server URL
  OPENAI_API_KEY            OpenAI API key
  TASK_EXTRACTION_MODEL     Model to use (default: gpt-5 for triage-agent, gpt-4o for single-agent)

Environment Variables (required for single-agent strategy):
  LINEAR_API_KEY            Linear API key
  LINEAR_TEAM_ID            Linear team UUID
  LINEAR_TEAM_NAME          Linear team name (required for Grapevine search scoping)
  SEARCH_PROVIDER           Search provider: 'grapevine' (default) or 'linear-api'

Examples:
  # Run all evals with single-agent (default)
  tsx src/run-evals.ts

  # Run with single-agent using Linear API search instead of Grapevine
  SEARCH_PROVIDER=linear-api tsx src/run-evals.ts

  # Run with triage-agent strategy
  tsx src/run-evals.ts --strategy triage-agent

  # Compare against ground truth
  tsx src/run-evals.ts --compare

  # Run specific test
  tsx src/run-evals.ts --filter oauth-bug

  # Verbose output
  tsx src/run-evals.ts --verbose

  # Custom dataset
  tsx src/run-evals.ts --dataset ./src/dataset/cases

  # Enable LLM grading (uses GPT-4o to score operations 1-5)
  tsx src/run-evals.ts --compare --grade

  # Use semantic comparison (LLM-powered matching)
  tsx src/run-evals.ts --compare --semantic

  # Show detailed truth diffs
  tsx src/run-evals.ts --compare --show-diffs

  # Full evaluation with all features
  tsx src/run-evals.ts --compare --grade --semantic --show-diffs
`);
}

/**
 * Load test cases from dataset directory
 */
function loadTestCases(datasetPath: string, filter?: string): TestCase[] {
  const fullPath = resolve(datasetPath);

  // Validate dataset path exists
  if (!existsSync(fullPath)) {
    throw new Error(`Dataset directory not found: ${fullPath}`);
  }

  // Validate it's actually a directory
  const stats = statSync(fullPath);
  if (!stats.isDirectory()) {
    throw new Error(`Dataset path is not a directory: ${fullPath}`);
  }

  const files = readdirSync(fullPath);
  const testCaseFiles = files.filter(
    (f) => f.endsWith('.json') && !f.endsWith('-truth.json') && !f.endsWith('-generated.json')
  );

  let testCases: TestCase[] = [];

  for (const file of testCaseFiles) {
    const filePath = join(fullPath, file);
    const content = readFileSync(filePath, 'utf-8');

    try {
      const data = JSON.parse(content);
      const testCaseId = basename(file, '.json');

      // Check for ground truth file
      const truthFile = join(fullPath, `${testCaseId}-truth.json`);
      let groundTruth;

      if (existsSync(truthFile)) {
        const truthContent = readFileSync(truthFile, 'utf-8');
        groundTruth = JSON.parse(truthContent);
      }

      testCases.push({
        id: testCaseId,
        title: data.title || testCaseId,
        date: data.date,
        type: data.type,
        content: data.content,
        participants: data.participants,
        files: data.files,
        groundTruth,
        filePath,
      });
    } catch (error) {
      console.warn(`Warning: Failed to parse ${file}: ${error}`);
    }
  }

  // Apply filter if specified
  if (filter) {
    testCases = testCases.filter(
      (tc) =>
        tc.id.toLowerCase().includes(filter.toLowerCase()) ||
        tc.title.toLowerCase().includes(filter.toLowerCase())
    );
  }

  // Sort by date if available, otherwise by id
  testCases.sort((a, b) => {
    if (a.date && b.date) {
      return a.date.localeCompare(b.date);
    }
    return a.id.localeCompare(b.id);
  });

  return testCases;
}

/**
 * Create strategy instance based on name
 */
function createStrategy(
  strategyName: string,
  model: string
): TriageAgentStrategy | SingleAgentStrategy {
  switch (strategyName) {
    case 'triage-agent':
      return new TriageAgentStrategy({ model });
    case 'single-agent':
      return new SingleAgentStrategy();
    default:
      throw new Error(
        `Unknown strategy: ${strategyName}. Available strategies: triage-agent, single-agent`
      );
  }
}

/**
 * Validate required environment variables
 */
function validateConfig(strategyName: string): EvalConfig {
  const tenantId = process.env.EVAL_TENANT_ID;
  const mcpApiKey = process.env.MCP_API_KEY;
  const mcpBaseUrl = process.env.MCP_BASE_URL;
  const openaiKey = process.env.OPENAI_API_KEY;

  if (!tenantId) {
    throw new Error('Missing required environment variable: EVAL_TENANT_ID');
  }

  if (!mcpApiKey) {
    throw new Error('Missing required environment variable: MCP_API_KEY');
  }

  if (!mcpBaseUrl) {
    throw new Error('Missing required environment variable: MCP_BASE_URL');
  }

  if (!openaiKey) {
    throw new Error('Missing required environment variable: OPENAI_API_KEY');
  }

  // For single-agent strategy, require Linear config
  if (strategyName === 'single-agent') {
    const linearApiKey = process.env.LINEAR_API_KEY;
    const linearTeamId = process.env.LINEAR_TEAM_ID;
    const linearTeamName = process.env.LINEAR_TEAM_NAME;
    const searchProviderEnv = process.env.SEARCH_PROVIDER;

    if (!linearApiKey) {
      throw new Error('Missing LINEAR_API_KEY for single-agent strategy');
    }
    if (!linearTeamId) {
      throw new Error('Missing LINEAR_TEAM_ID for single-agent strategy');
    }
    if (!linearTeamName) {
      throw new Error(
        'Missing LINEAR_TEAM_NAME for single-agent strategy (required for Grapevine)'
      );
    }

    // Validate search provider if specified
    const searchProvider =
      searchProviderEnv === 'linear-api' || searchProviderEnv === 'grapevine'
        ? searchProviderEnv
        : 'grapevine';

    return {
      tenantId,
      mcpApiKey,
      mcpBaseUrl,
      model: process.env.TASK_EXTRACTION_MODEL || 'gpt-5',
      linearApiKey,
      linearTeamId,
      linearTeamName,
      searchProvider,
    };
  }

  return {
    tenantId,
    mcpApiKey,
    mcpBaseUrl,
    model: process.env.TASK_EXTRACTION_MODEL || 'gpt-5',
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

  console.log('🚀 Triage Evaluation Runner\n');

  // Validate configuration
  let config: EvalConfig;
  try {
    config = validateConfig(args.strategy);
  } catch (error) {
    console.error(`❌ Configuration error: ${error instanceof Error ? error.message : error}`);
    console.log('\nRun with --help for usage information');
    process.exit(1);
  }

  console.log('Configuration:');
  console.log(`  Tenant ID: ${config.tenantId}`);
  console.log(`  MCP URL: ${config.mcpBaseUrl}`);
  console.log(`  Model: ${config.model}`);
  console.log(`  Strategy: ${args.strategy}`);
  if (config.searchProvider) {
    console.log(`  Search Provider: ${config.searchProvider}`);
  }
  console.log(`  Dataset: ${args.dataset}`);
  if (args.filter) {
    console.log(`  Filter: ${args.filter}`);
  }
  console.log(`  Compare: ${args.compare ? 'Yes' : 'No'}`);
  console.log(`  Verbose: ${args.verbose ? 'Yes' : 'No'}`);
  if (args.grade) {
    console.log(`  LLM Grading: Yes`);
  }
  if (args.semantic) {
    console.log(`  Semantic Comparison: Yes`);
  }
  if (args.showDiffs) {
    console.log(`  Show Diffs: Yes`);
  }

  // Load test cases
  let testCases: TestCase[];
  try {
    testCases = loadTestCases(args.dataset, args.filter);
  } catch (error) {
    console.error(
      `❌ Failed to load test cases: ${error instanceof Error ? error.message : error}`
    );
    process.exit(1);
  }

  if (testCases.length === 0) {
    console.log('\n⚠️  No test cases found');
    process.exit(0);
  }

  displayTestCases(testCases);

  // Create strategy
  let strategy: TriageAgentStrategy | SingleAgentStrategy;
  try {
    strategy = createStrategy(args.strategy, config.model ?? '');
  } catch (error) {
    console.error(`❌ Strategy error: ${error instanceof Error ? error.message : error}`);
    process.exit(1);
  }

  // Process evals
  const options: EvalOptions = {
    compare: args.compare,
    verbose: args.verbose,
    output: args.output,
    grade: args.grade,
    semantic: args.semantic,
    showDiffs: args.showDiffs,
  };

  const results = await processEvals(testCases, strategy, config, options);

  // Display summary report
  displayReport(results);

  // Exit with error code if any tests failed
  const failedCount = results.filter((r) => !r.success).length;
  process.exit(failedCount > 0 ? 1 : 0);
}

// Handle Ctrl+C and termination signals
process.on('SIGINT', () => {
  console.log('\n\n⚠️  Evaluation interrupted by user (Ctrl+C)');
  process.exit(130); // Standard exit code for SIGINT
});

process.on('SIGTERM', () => {
  console.log('\n\n⚠️  Evaluation terminated (SIGTERM)');
  process.exit(143); // Standard exit code for SIGTERM
});

// Run main function
main().catch((error) => {
  console.error(`❌ Unexpected error: ${error}`);
  process.exit(1);
});
