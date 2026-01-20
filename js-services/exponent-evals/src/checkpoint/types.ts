/**
 * Checkpoint System Types
 *
 * Types for processing multiple test cases chronologically with state accumulation.
 */

import type { ComparisonMetrics } from '../lib/comparison';
import type { LLMGradeResult } from '../lib/grader';

/**
 * Simple Linear issue representation for frozen state
 */
export interface SimpleLinearIssue {
  id: string;
  title: string;
  description?: string;
  assigneeId?: string;
  assignee?: string;
  priority?: string;
  stateId?: string;
  [key: string]: unknown;
}

/**
 * Linear operation from truth or generated output
 */
export interface LinearOperation {
  action: 'CREATE' | 'UPDATE' | 'SKIP' | 'REQUEST_CLARIFICATION';
  createData?: {
    title: string;
    description?: string;
    issueId?: string | null;
    assigneeId?: string;
  };
  updateData?: {
    issueId: string;
    documentId?: string;
    description?: string;
    descriptionAppend?: string;
  };
  skipData?: {
    issueId?: string;
    title?: string;
    reason: string;
  };
  confidence?: number;
  reasoning?: string;
}

/**
 * Checkpoint file information
 */
export interface CheckpointFile {
  filename: string; // e.g., "2025-10-03_09-30-00_standup.json"
  date: string; // "2025-10-03"
  timestamp: string; // "09-30-00"
  path: string; // Full path to file
  description: string; // e.g., "standup"
}

/**
 * Truth file input structure
 */
export interface TruthInput {
  linearState: SimpleLinearIssue[];
  docs: string[];
}

/**
 * Truth file output structure
 */
export interface TruthOutput {
  operations: LinearOperation[];
}

/**
 * Truth file entry (from -truth.json files)
 */
export interface TruthEntry {
  input: TruthInput;
  output: TruthOutput;
}

/**
 * Grading results for a checkpoint
 */
export interface GradingResult {
  grades: LLMGradeResult[];
  averageScore: number;
  graderInfo: string;
}

/**
 * Result of processing a single checkpoint
 */
export interface CheckpointResult {
  checkpoint: CheckpointFile;
  operations: LinearOperation[];
  comparison?: ComparisonMetrics;
  grading?: GradingResult; // LLM grading results (when --grade is used)
  linearState: SimpleLinearIssue[]; // State used for this checkpoint
  truthEntry?: TruthEntry; // Ground truth if available
  duration: number;
  error?: string;
}

/**
 * Operation counts summary
 */
export interface OperationCounts {
  create: number;
  update: number;
  skip: number;
  requestClarification: number;
}

/**
 * Aggregated report for a checkpoint run
 */
export interface CheckpointReport {
  datasetId: string;
  strategy: string;
  runId: string;
  checkpoints: CheckpointResult[];
  summary: {
    totalCheckpoints: number;
    successfulCheckpoints: number;
    failedCheckpoints: number;
    totalOperations: OperationCounts;
    avgPrecision: number;
    avgRecall: number;
    avgF1: number;
    avgGrade?: number; // Average LLM grade (1-5) when grading is enabled
  };
  timestamp: string;
}

/**
 * CLI options for checkpoint processing
 */
export interface CheckpointOptions {
  dataset: string;
  strategy: string;
  from?: string; // Start date (YYYY-MM-DD)
  until?: string; // End date (YYYY-MM-DD)
  filter?: string; // Filter by filename substring
  parallel: boolean; // Process in parallel (no state accumulation)
  accumulate: boolean; // Accumulate state across checkpoints (sequential only)
  verbose: boolean;
  grade: boolean;
  semantic: boolean;
  showDiffs: boolean;
  output: string;
}
