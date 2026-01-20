/**
 * Checkpoint Comparison
 *
 * Loads truth files and compares generated operations against expected.
 */

import { readFileSync, existsSync } from 'fs';
import { getTruthFilePath } from './fileFinder';
import type { CheckpointFile, TruthEntry, SimpleLinearIssue, LinearOperation } from './types';
import { compareAllOperations, type ComparisonMetrics } from '../lib/comparison';
import { gradeOperations as gradeOpsLib, type LLMGradeResult } from '../lib/grader';

/**
 * Load a truth file for a checkpoint
 *
 * @param checkpoint - Checkpoint file info
 * @returns Truth entry array, or null if no truth file exists
 */
export function loadTruthFile(checkpoint: CheckpointFile): TruthEntry[] | null {
  const truthPath = getTruthFilePath(checkpoint);

  if (!existsSync(truthPath)) {
    return null;
  }

  try {
    const content = readFileSync(truthPath, 'utf-8');
    const data = JSON.parse(content);

    // Handle both array format and single object format
    if (Array.isArray(data)) {
      return data as TruthEntry[];
    } else if (data.operations) {
      // Legacy format: { operations: [...] }
      return [
        {
          input: {
            linearState: data.input?.linearState || [],
            docs: data.input?.docs || [checkpoint.filename],
          },
          output: {
            operations: data.operations,
          },
        },
      ];
    } else if (data.input && data.output) {
      // Single truth entry
      return [data as TruthEntry];
    }

    return null;
  } catch (error) {
    console.warn(`Warning: Failed to parse truth file ${truthPath}: ${error}`);
    return null;
  }
}

/**
 * Get the linear state from a truth file
 *
 * @param checkpoint - Checkpoint file
 * @returns Linear state from truth file, or empty array if not available
 */
export function loadTruthLinearState(checkpoint: CheckpointFile): SimpleLinearIssue[] {
  const truthEntries = loadTruthFile(checkpoint);

  if (!truthEntries || truthEntries.length === 0) {
    return [];
  }

  // Use the first entry's linear state
  const firstEntry = truthEntries[0];
  return firstEntry?.input?.linearState || [];
}

/**
 * Get expected operations from a truth file
 *
 * @param checkpoint - Checkpoint file
 * @returns Expected operations, or empty array if not available
 */
export function loadTruthOperations(checkpoint: CheckpointFile): LinearOperation[] {
  const truthEntries = loadTruthFile(checkpoint);

  if (!truthEntries || truthEntries.length === 0) {
    return [];
  }

  // Combine operations from all entries
  const operations: LinearOperation[] = [];
  for (const entry of truthEntries) {
    if (entry.output?.operations) {
      operations.push(...entry.output.operations);
    }
  }

  return operations;
}

/**
 * Compare generated operations against truth
 *
 * @param generated - Generated operations
 * @param expected - Expected operations from truth file
 * @param options - Comparison options
 * @returns Comparison metrics
 */
export async function compareWithTruth(
  generated: LinearOperation[],
  expected: LinearOperation[],
  options: {
    semantic?: boolean;
  } = {}
): Promise<ComparisonMetrics> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return compareAllOperations(generated as any, expected as any, {
    semantic: options.semantic,
  });
}

/**
 * Grade generated operations against expected using LLM
 *
 * @param generated - Generated operations
 * @param expected - Expected operations from truth file
 * @param context - Optional context (source document content)
 * @returns Grading results with scores and reasoning
 */
export async function gradeWithTruth(
  generated: LinearOperation[],
  expected: LinearOperation[],
  context?: string
): Promise<{
  grades: LLMGradeResult[];
  averageScore: number;
  grader_info: string;
}> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return gradeOpsLib(generated as any, expected as any, context);
}
