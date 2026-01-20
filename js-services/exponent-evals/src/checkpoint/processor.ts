/**
 * Checkpoint Processor
 *
 * Main processing logic for checkpoint-based evaluations.
 * Processes checkpoints sequentially with state accumulation,
 * or in parallel without state accumulation.
 */

import { readFileSync } from 'fs';
import {
  SingleAgentStrategy,
  type LinearContext,
  type TaskSourceMetadata,
  type SlackDocument,
  type MeetingTranscript,
} from '@corporate-context/exponent-core';
import { findCheckpointFiles } from './fileFinder';
import {
  loadTruthLinearState,
  loadTruthOperations,
  compareWithTruth,
  gradeWithTruth,
} from './comparison';
import { applyOperations, countOperations } from './stateRollup';
import type {
  CheckpointFile,
  CheckpointResult,
  CheckpointReport,
  CheckpointOptions,
  SimpleLinearIssue,
  LinearOperation,
  OperationCounts,
  GradingResult,
} from './types';

/**
 * Configuration for checkpoint processing
 */
export interface CheckpointConfig {
  linearApiKey: string;
  linearTeamId: string;
  linearTeamName: string;
  mcpApiKey: string;
  mcpBaseUrl: string;
  tenantId: string;
}

/**
 * Load a checkpoint file's content
 */
function loadCheckpointContent(checkpoint: CheckpointFile): {
  title?: string;
  type?: string;
  date?: string;
  content: string;
  participants?: string[];
  attendees?: string[];
} {
  const content = readFileSync(checkpoint.path, 'utf-8');
  return JSON.parse(content);
}

/**
 * Process a single checkpoint with frozen state
 */
async function processCheckpoint(
  checkpoint: CheckpointFile,
  linearState: SimpleLinearIssue[],
  strategy: SingleAgentStrategy,
  config: CheckpointConfig,
  options: CheckpointOptions
): Promise<CheckpointResult> {
  const startTime = Date.now();

  try {
    // Load checkpoint content
    const data = loadCheckpointContent(checkpoint);

    // Build document for the strategy
    let document: SlackDocument | MeetingTranscript;

    if (data.type === 'meeting' || data.attendees) {
      // Meeting transcript
      document = {
        title: data.title || checkpoint.description,
        attendees: data.attendees || data.participants,
        date: data.date,
        content: data.content,
      };
    } else {
      // Default to Slack document
      document = {
        documentId: checkpoint.filename,
        channel: 'eval',
        date: data.date,
        content: data.content,
        participants: data.participants,
      };
    }

    // Build Linear context with frozen state
    const linearContext: LinearContext = {
      apiKey: config.linearApiKey,
      teamId: config.linearTeamId,
      teamName: config.linearTeamName,
      existingIssues: linearState, // FROZEN STATE - this is the key!
    };

    const metadata: TaskSourceMetadata = {
      source: data.type === 'meeting' || data.attendees ? 'gather' : 'slack',
      sourceId: checkpoint.filename,
    };

    // Process with strategy
    const result = await strategy.process(document, linearContext, metadata);

    const duration = Date.now() - startTime;

    // Load truth for comparison
    const expectedOperations = loadTruthOperations(checkpoint);

    // Compare if we have truth
    let comparison;
    if (expectedOperations.length > 0) {
      comparison = await compareWithTruth(
        result.operations as unknown as LinearOperation[],
        expectedOperations,
        { semantic: options.semantic }
      );
    }

    // Grade operations if requested and we have truth
    let grading: GradingResult | undefined;
    if (options.grade && expectedOperations.length > 0) {
      const gradingResult = await gradeWithTruth(
        result.operations as unknown as LinearOperation[],
        expectedOperations,
        data.content // Pass source content as context
      );
      grading = {
        grades: gradingResult.grades,
        averageScore: gradingResult.averageScore,
        graderInfo: gradingResult.grader_info,
      };
    }

    return {
      checkpoint,
      operations: result.operations as unknown as LinearOperation[],
      comparison,
      grading,
      linearState,
      duration,
    };
  } catch (error) {
    const duration = Date.now() - startTime;
    return {
      checkpoint,
      operations: [],
      linearState,
      duration,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

/**
 * Process checkpoints sequentially
 *
 * Default: Each checkpoint uses fresh state from its truth file (isolated evaluation)
 * With --accumulate: State accumulates across checkpoints (simulates real-world usage)
 */
async function processSequential(
  checkpoints: CheckpointFile[],
  strategy: SingleAgentStrategy,
  config: CheckpointConfig,
  options: CheckpointOptions
): Promise<CheckpointResult[]> {
  const results: CheckpointResult[] = [];
  let accumulatedState: SimpleLinearIssue[] = [];

  for (let i = 0; i < checkpoints.length; i++) {
    const checkpoint = checkpoints[i];
    if (!checkpoint) continue;

    console.log(`[${i + 1}/${checkpoints.length}] Processing: ${checkpoint.filename}`);

    // Load truth state for this checkpoint
    const truthState = loadTruthLinearState(checkpoint);

    // Determine which state to use
    let linearState: SimpleLinearIssue[];
    if (options.accumulate) {
      // ACCUMULATE MODE: Use truth state if available, else accumulated state
      linearState = truthState.length > 0 ? truthState : accumulatedState;
    } else {
      // DEFAULT MODE: Always use fresh state from truth file
      linearState = truthState;
    }

    // Process checkpoint
    const result = await processCheckpoint(checkpoint, linearState, strategy, config, options);

    results.push(result);

    // Display inline status
    if (result.error) {
      console.log(`  ❌ Error: ${result.error}`);
    } else {
      const opCounts = countOperations(result.operations);
      console.log(
        `  📝 Operations: ${opCounts.create} CREATE, ${opCounts.update} UPDATE, ${opCounts.skip} SKIP`
      );

      if (result.comparison) {
        console.log(
          `  📊 Precision: ${(result.comparison.precision * 100).toFixed(0)}% | ` +
            `Recall: ${(result.comparison.recall * 100).toFixed(0)}% | ` +
            `F1: ${(result.comparison.f1Score * 100).toFixed(0)}%`
        );
      }

      if (result.grading) {
        console.log(`  🎯 LLM Grade: ${result.grading.averageScore.toFixed(2)}/5`);
      }
    }

    console.log(`  ⏱️  ${result.duration}ms\n`);

    // Only accumulate state when --accumulate flag is used
    if (options.accumulate) {
      if (truthState.length === 0) {
        accumulatedState = applyOperations(accumulatedState, result.operations);
      } else {
        // When using truth state, apply operations to continue the chain
        accumulatedState = applyOperations(truthState, result.operations);
      }
    }
  }

  return results;
}

/**
 * Process checkpoints in parallel (no state accumulation)
 */
async function processParallel(
  checkpoints: CheckpointFile[],
  strategy: SingleAgentStrategy,
  config: CheckpointConfig,
  options: CheckpointOptions
): Promise<CheckpointResult[]> {
  console.log(`Processing ${checkpoints.length} checkpoints in parallel...\n`);

  const promises = checkpoints.map(async (checkpoint, i) => {
    // Each checkpoint uses only its truth state (no accumulation)
    const linearState = loadTruthLinearState(checkpoint);

    console.log(`[${i + 1}] Starting: ${checkpoint.filename}`);
    const result = await processCheckpoint(checkpoint, linearState, strategy, config, options);

    if (result.error) {
      console.log(`[${i + 1}] ❌ ${checkpoint.filename}: ${result.error}`);
    } else {
      const opCounts = countOperations(result.operations);
      console.log(
        `[${i + 1}] ✅ ${checkpoint.filename}: ${opCounts.create}C/${opCounts.update}U/${opCounts.skip}S (${result.duration}ms)`
      );
    }

    return result;
  });

  return Promise.all(promises);
}

/**
 * Aggregate results into a summary report
 */
function aggregateResults(
  results: CheckpointResult[],
  datasetId: string,
  strategy: string
): CheckpointReport {
  const totalOperations: OperationCounts = {
    create: 0,
    update: 0,
    skip: 0,
    requestClarification: 0,
  };

  let totalPrecision = 0;
  let totalRecall = 0;
  let totalF1 = 0;
  let comparisonCount = 0;

  let totalGrade = 0;
  let gradeCount = 0;

  for (const result of results) {
    const counts = countOperations(result.operations);
    totalOperations.create += counts.create;
    totalOperations.update += counts.update;
    totalOperations.skip += counts.skip;
    totalOperations.requestClarification += counts.requestClarification;

    if (result.comparison) {
      totalPrecision += result.comparison.precision;
      totalRecall += result.comparison.recall;
      totalF1 += result.comparison.f1Score;
      comparisonCount++;
    }

    if (result.grading && result.grading.averageScore > 0) {
      totalGrade += result.grading.averageScore;
      gradeCount++;
    }
  }

  const successfulCheckpoints = results.filter((r) => !r.error).length;
  const failedCheckpoints = results.filter((r) => r.error).length;

  return {
    datasetId,
    strategy,
    runId: new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5),
    checkpoints: results,
    summary: {
      totalCheckpoints: results.length,
      successfulCheckpoints,
      failedCheckpoints,
      totalOperations,
      avgPrecision: comparisonCount > 0 ? totalPrecision / comparisonCount : 0,
      avgRecall: comparisonCount > 0 ? totalRecall / comparisonCount : 0,
      avgF1: comparisonCount > 0 ? totalF1 / comparisonCount : 0,
      avgGrade: gradeCount > 0 ? totalGrade / gradeCount : undefined,
    },
    timestamp: new Date().toISOString(),
  };
}

/**
 * Main entry point for processing checkpoints
 */
export async function processCheckpoints(
  options: CheckpointOptions,
  config: CheckpointConfig
): Promise<CheckpointReport> {
  // Find checkpoint files
  const checkpoints = findCheckpointFiles(options.dataset, {
    from: options.from,
    until: options.until,
    filter: options.filter,
  });

  if (checkpoints.length === 0) {
    console.log('⚠️  No checkpoint files found');
    return aggregateResults([], options.dataset, options.strategy);
  }

  console.log(`\n📁 Found ${checkpoints.length} checkpoint files\n`);

  // Create strategy
  const strategy = new SingleAgentStrategy();

  // Process checkpoints
  let results: CheckpointResult[];

  if (options.parallel) {
    results = await processParallel(checkpoints, strategy, config, options);
  } else {
    results = await processSequential(checkpoints, strategy, config, options);
  }

  // Aggregate into report
  const report = aggregateResults(results, options.dataset, options.strategy);

  return report;
}
