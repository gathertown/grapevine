#!/usr/bin/env tsx
/**
 * Description Enhancement Evaluation CLI Runner
 *
 * Runs enhanceTaskDescription against test datasets to evaluate
 * description enhancement quality.
 *
 * Usage:
 *   tsx src/run-description-evals.ts [options]
 *
 * Options:
 *   --dataset <path>   Path to dataset directory (default: src/dataset/description-enhancement)
 *   --verbose          Show full outputs in console
 *   --filter <pattern> Only run tests matching pattern
 *   --output <path>    Custom output directory for results
 *
 * Environment variables:
 *   EVAL_TENANT_ID     Tenant ID to run evals against (required)
 *   MCP_API_KEY        MCP API key for authentication (required)
 *   MCP_BASE_URL       MCP server URL (required)
 */

import 'dotenv/config';
import { readdirSync, readFileSync, writeFileSync, existsSync, mkdirSync, statSync } from 'fs';
import { join, resolve, basename } from 'path';
import {
  enhanceTaskDescription,
  LinearOperationExecutor,
  TaskAction,
} from '@corporate-context/exponent-core';
import { callMCPWithApiKey } from './lib/mcp-client';

// Graceful shutdown handling
let shutdownRequested = false;

function setupShutdownHandler(): void {
  process.on('SIGINT', () => {
    if (shutdownRequested) {
      console.log('\n\nForce quitting...');
      process.exit(1);
    }
    shutdownRequested = true;
    console.log('\n\nShutdown requested (Ctrl+C). Finishing current test and saving results...');
    console.log('Press Ctrl+C again to force quit.');
  });
}

// Types
interface DescriptionTestCase {
  id: string;
  type: 'slack' | 'meeting';
  sourceDescription: string;
  sourceLink?: string;
  sourceContent: string;
  operation: {
    action: string;
    createData: {
      title: string;
      description: string;
    };
  };
  groundTruth?: {
    enhancedDescription: string;
  };
  filePath: string;
}

interface DescriptionResult {
  id: string;
  input: {
    title: string;
    description: string;
  };
  output: {
    enhancedDescription: string;
  };
  grade: null; // Placeholder for future --grade support
  comparison: null; // Placeholder for future --semantic support
  linearIssue?: {
    id: string;
    identifier: string;
    url: string;
  };
}

interface EvalConfig {
  tenantId: string;
  mcpApiKey: string;
  mcpBaseUrl: string;
  linearApiKey?: string;
  linearTeamId?: string;
}

// Parse command line arguments
interface ParsedArgs {
  dataset: string;
  verbose: boolean;
  filter?: string;
  output: string;
  help: boolean;
  create: boolean;
  parallel: number; // 0 = sequential, >0 = concurrency limit
}

function parseArgs(): ParsedArgs {
  const args = process.argv.slice(2);

  const defaultDataset = 'src/dataset/description-enhancement';

  if (args.includes('--help') || args.includes('-h')) {
    return {
      dataset: defaultDataset,
      verbose: false,
      output: join(defaultDataset, 'results'),
      help: true,
      create: false,
      parallel: 0,
    };
  }

  const datasetIdx = args.indexOf('--dataset');
  const filterIdx = args.indexOf('--filter');
  const outputIdx = args.indexOf('--output');
  const parallelIdx = args.indexOf('--parallel');

  const dataset = (datasetIdx >= 0 && args[datasetIdx + 1]) || defaultDataset;

  // Parse --parallel [n] - defaults to 3 if no number provided
  let parallel = 0;
  if (parallelIdx >= 0) {
    const nextArg = args[parallelIdx + 1];
    if (nextArg && !nextArg.startsWith('--')) {
      parallel = parseInt(nextArg, 10) || 3;
    } else {
      parallel = 3; // Default concurrency
    }
  }

  return {
    dataset,
    verbose: args.includes('--verbose'),
    filter: filterIdx >= 0 ? args[filterIdx + 1] : undefined,
    output: (outputIdx >= 0 && args[outputIdx + 1]) || join(dataset, 'results'),
    help: false,
    create: args.includes('--create'),
    parallel,
  };
}

function displayHelp(): void {
  console.log(`
Description Enhancement Evaluation CLI

Usage:
  tsx src/run-description-evals.ts [options]

Options:
  --dataset <path>    Path to dataset directory (default: src/dataset/description-enhancement)
  --verbose           Show full outputs in console
  --filter <pattern>  Only run tests matching pattern
  --output <path>     Custom output directory for results
  --create            Create Linear tickets with enhanced descriptions
  --parallel [n]      Run tests in parallel (default: 3 concurrent)
  --help, -h          Show this help message

Environment Variables:
  EVAL_TENANT_ID      Tenant ID to run evals against (required)
  MCP_API_KEY         MCP API key for authentication (required)
  MCP_BASE_URL        MCP server URL (required)
  LINEAR_API_KEY      Linear API key (required for --create)
  LINEAR_TEAM_ID      Linear team UUID (required for --create)

Examples:
  # Run all description enhancement evals
  tsx src/run-description-evals.ts

  # Run specific test
  tsx src/run-description-evals.ts --filter slack-task-1

  # Verbose output
  tsx src/run-description-evals.ts --verbose

  # Custom dataset
  tsx src/run-description-evals.ts --dataset ./src/dataset/my-tests

  # Create Linear tickets with enhanced descriptions
  tsx src/run-description-evals.ts --dataset src/dataset/DE2 --filter hubspot --create

  # Run tests in parallel (3 concurrent by default)
  tsx src/run-description-evals.ts --dataset src/dataset/DE2 --parallel

  # Run tests with custom concurrency
  tsx src/run-description-evals.ts --dataset src/dataset/DE2 --parallel 5
`);
}

function loadTestCases(datasetPath: string, filter?: string): DescriptionTestCase[] {
  const fullPath = resolve(datasetPath);

  if (!existsSync(fullPath)) {
    throw new Error(`Dataset directory not found: ${fullPath}`);
  }

  const stats = statSync(fullPath);
  if (!stats.isDirectory()) {
    throw new Error(`Dataset path is not a directory: ${fullPath}`);
  }

  const files = readdirSync(fullPath);
  const testCaseFiles = files.filter(
    (f) =>
      f.endsWith('.json') &&
      !f.endsWith('-truth.json') &&
      !f.endsWith('-generated.json') &&
      f !== 'results'
  );

  let testCases: DescriptionTestCase[] = [];

  for (const file of testCaseFiles) {
    const filePath = join(fullPath, file);

    // Skip directories
    const fileStats = statSync(filePath);
    if (fileStats.isDirectory()) continue;

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
        type: data.type || 'slack',
        sourceDescription: data.sourceDescription || 'this conversation',
        sourceLink: data.sourceLink,
        sourceContent: data.sourceContent,
        operation: data.operation,
        groundTruth,
        filePath,
      });
    } catch (error) {
      console.warn(`Warning: Failed to parse ${file}: ${error}`);
    }
  }

  // Apply filter if specified
  if (filter) {
    testCases = testCases.filter((tc) => tc.id.toLowerCase().includes(filter.toLowerCase()));
  }

  testCases.sort((a, b) => a.id.localeCompare(b.id));

  return testCases;
}

function getConfig(requireLinear: boolean): EvalConfig {
  const tenantId = process.env.EVAL_TENANT_ID;
  const mcpApiKey = process.env.MCP_API_KEY;
  const mcpBaseUrl = process.env.MCP_BASE_URL;
  const linearApiKey = process.env.LINEAR_API_KEY;
  const linearTeamId = process.env.LINEAR_TEAM_ID;

  if (!tenantId || !mcpApiKey || !mcpBaseUrl) {
    console.error('Missing required environment variables:');
    if (!tenantId) console.error('  - EVAL_TENANT_ID');
    if (!mcpApiKey) console.error('  - MCP_API_KEY');
    if (!mcpBaseUrl) console.error('  - MCP_BASE_URL');
    process.exit(1);
  }

  if (requireLinear && (!linearApiKey || !linearTeamId)) {
    console.error('Missing required environment variables for --create:');
    if (!linearApiKey) console.error('  - LINEAR_API_KEY');
    if (!linearTeamId) console.error('  - LINEAR_TEAM_ID');
    process.exit(1);
  }

  return { tenantId, mcpApiKey, mcpBaseUrl, linearApiKey, linearTeamId };
}

// Helper to process a single test case
async function processTestCase(
  testCase: DescriptionTestCase,
  index: number,
  total: number,
  askAgentFast: (options: { query: string; systemPrompt?: string }) => Promise<{ answer: string }>,
  linearExecutor: LinearOperationExecutor | undefined,
  linearTeamId: string | undefined,
  verbose: boolean
): Promise<DescriptionResult> {
  console.log(`\n[${index + 1}/${total}] Processing: ${testCase.id}`);

  try {
    const enhanced = await enhanceTaskDescription(
      {
        title: testCase.operation.createData.title,
        description: testCase.operation.createData.description,
        sourceContent: testCase.sourceContent,
        sourceDescription: testCase.sourceDescription,
        sourceLink: testCase.sourceLink,
      },
      askAgentFast
    );

    const result: DescriptionResult = {
      id: testCase.id,
      input: {
        title: testCase.operation.createData.title,
        description: testCase.operation.createData.description,
      },
      output: {
        enhancedDescription: enhanced.description,
      },
      grade: null,
      comparison: null,
    };

    // Create Linear ticket if --create flag is set
    if (linearExecutor && linearTeamId) {
      console.log(`  [${testCase.id}] Creating Linear ticket...`);
      const execResult = await linearExecutor.executeOperation({
        action: TaskAction.CREATE,
        confidence: 100,
        reasoning: 'Created via description enhancement eval with --create flag',
        createData: {
          title: testCase.operation.createData.title,
          description: enhanced.description,
          teamId: linearTeamId,
        },
      });

      if (execResult.success && execResult.linearIssueId) {
        result.linearIssue = {
          id: execResult.linearIssueId,
          identifier: execResult.linearIssueIdentifier || '',
          url: execResult.linearIssueUrl || '',
        };
        console.log(
          `  [${testCase.id}] ✓ Created: ${execResult.linearIssueIdentifier} - ${execResult.linearIssueUrl}`
        );
      } else {
        console.error(`  [${testCase.id}] ✗ Failed to create Linear ticket: ${execResult.error}`);
      }
    }

    if (verbose) {
      console.log(`\n--- [${testCase.id}] Input ---`);
      console.log(`Title: ${result.input.title}`);
      console.log(`Description: ${result.input.description}`);
      console.log(`\n--- [${testCase.id}] Enhanced Output ---`);
      console.log(result.output.enhancedDescription);
    } else {
      console.log(
        `  [${testCase.id}] ✓ Enhanced description generated (${enhanced.description.length} chars)`
      );
    }

    return result;
  } catch (error) {
    console.error(`  [${testCase.id}] ✗ Error: ${error instanceof Error ? error.message : error}`);
    return {
      id: testCase.id,
      input: {
        title: testCase.operation.createData.title,
        description: testCase.operation.createData.description,
      },
      output: {
        enhancedDescription: `ERROR: ${error instanceof Error ? error.message : error}`,
      },
      grade: null,
      comparison: null,
    };
  }
}

// Run tasks with concurrency limit
async function runWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  fn: (item: T, index: number) => Promise<R>
): Promise<R[]> {
  const results: R[] = [];
  let currentIndex = 0;

  async function worker(): Promise<void> {
    while (currentIndex < items.length && !shutdownRequested) {
      const index = currentIndex++;
      const item = items[index];
      if (item) {
        results[index] = await fn(item, index);
      }
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, items.length) }, () => worker());
  await Promise.all(workers);

  return results.filter((r) => r !== undefined);
}

async function runEvals(
  testCases: DescriptionTestCase[],
  config: EvalConfig,
  verbose: boolean,
  createTickets: boolean,
  parallel: number
): Promise<DescriptionResult[]> {
  // Create Linear executor if --create flag is set
  let linearExecutor: LinearOperationExecutor | undefined;
  if (createTickets && config.linearApiKey && config.linearTeamId) {
    linearExecutor = new LinearOperationExecutor(config.linearApiKey, config.linearTeamId);
    console.log(`\nLinear ticket creation enabled (team: ${config.linearTeamId})`);
  }

  // Create askAgentFast function using MCP client
  const askAgentFast = async (options: {
    query: string;
    systemPrompt?: string;
  }): Promise<{ answer: string }> => {
    const result = await callMCPWithApiKey(
      config.mcpBaseUrl,
      config.mcpApiKey,
      config.tenantId,
      options.query,
      [],
      'ask_agent_fast',
      'markdown',
      undefined,
      {
        agentPromptOverride: options.systemPrompt,
      }
    );
    return { answer: result.answer };
  };

  const total = testCases.length;

  // Parallel execution
  if (parallel > 0) {
    console.log(`\nRunning ${total} tests with concurrency: ${parallel}`);
    return runWithConcurrency(testCases, parallel, async (testCase, index) => {
      return processTestCase(
        testCase,
        index,
        total,
        askAgentFast,
        linearExecutor,
        config.linearTeamId,
        verbose
      );
    });
  }

  // Sequential execution
  const results: DescriptionResult[] = [];
  for (let i = 0; i < testCases.length; i++) {
    // Check for graceful shutdown
    if (shutdownRequested) {
      console.log(`\nStopping early (processed ${i}/${testCases.length} test cases)`);
      break;
    }

    const testCase = testCases[i];
    if (!testCase) continue;

    const result = await processTestCase(
      testCase,
      i,
      total,
      askAgentFast,
      linearExecutor,
      config.linearTeamId,
      verbose
    );
    results.push(result);

    // Rate limiting - 1 second between calls (only for sequential)
    if (i < testCases.length - 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  return results;
}

function saveResults(results: DescriptionResult[], outputPath: string): string {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const runDir = join(outputPath, `run-${timestamp}`);

  mkdirSync(runDir, { recursive: true });

  // Save individual results
  for (const result of results) {
    const resultPath = join(runDir, `${result.id}-generated.json`);
    writeFileSync(resultPath, JSON.stringify(result, null, 2));
  }

  // Save summary
  const summary = {
    timestamp,
    totalTests: results.length,
    successful: results.filter((r) => !r.output.enhancedDescription.startsWith('ERROR:')).length,
    failed: results.filter((r) => r.output.enhancedDescription.startsWith('ERROR:')).length,
    results: results.map((r) => ({
      id: r.id,
      inputLength: r.input.description.length,
      outputLength: r.output.enhancedDescription.length,
      success: !r.output.enhancedDescription.startsWith('ERROR:'),
    })),
  };

  writeFileSync(join(runDir, 'summary.json'), JSON.stringify(summary, null, 2));

  return runDir;
}

async function main(): Promise<void> {
  setupShutdownHandler();

  const args = parseArgs();

  if (args.help) {
    displayHelp();
    return;
  }

  console.log('='.repeat(60));
  console.log('Description Enhancement Evaluation');
  console.log('='.repeat(60));

  const config = getConfig(args.create);
  console.log(`\nTenant ID: ${config.tenantId}`);
  console.log(`MCP URL: ${config.mcpBaseUrl}`);
  if (args.create) {
    console.log(`Linear Team: ${config.linearTeamId}`);
  }

  const testCases = loadTestCases(args.dataset, args.filter);
  console.log(`\nLoaded ${testCases.length} test case(s) from ${args.dataset}`);

  if (testCases.length === 0) {
    console.log('\nNo test cases found. Create test case JSON files in the dataset directory.');
    console.log('Expected format:');
    console.log(`{
  "id": "test-1",
  "type": "slack",
  "sourceDescription": "this Slack conversation",
  "sourceContent": "...",
  "operation": {
    "action": "CREATE",
    "createData": {
      "title": "Task title",
      "description": "Original description"
    }
  }
}`);
    return;
  }

  console.log('\nTest cases:');
  testCases.forEach((tc, i) => {
    console.log(`  ${i + 1}. ${tc.id} (${tc.type})`);
  });

  const results = await runEvals(testCases, config, args.verbose, args.create, args.parallel);

  const outputDir = saveResults(results, args.output);

  console.log(`\n${'='.repeat(60)}`);
  console.log('Summary');
  console.log('='.repeat(60));
  console.log(`Total: ${results.length}`);
  console.log(
    `Successful: ${results.filter((r) => !r.output.enhancedDescription.startsWith('ERROR:')).length}`
  );
  console.log(
    `Failed: ${results.filter((r) => r.output.enhancedDescription.startsWith('ERROR:')).length}`
  );
  if (args.create) {
    const created = results.filter((r) => r.linearIssue).length;
    console.log(`Linear tickets created: ${created}`);
  }
  console.log(`\nResults saved to: ${outputDir}`);
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
