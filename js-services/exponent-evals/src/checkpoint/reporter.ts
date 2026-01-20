/**
 * Checkpoint Reporter
 *
 * Displays checkpoint reports and saves results to disk.
 */

import { writeFileSync, mkdirSync, existsSync } from 'fs';
import { join } from 'path';
import type { CheckpointReport } from './types';

/**
 * Display a checkpoint report to the console
 */
export function displayCheckpointReport(report: CheckpointReport): void {
  console.log(`\n${'='.repeat(60)}`);
  console.log('📊 CHECKPOINT EVALUATION REPORT');
  console.log(`${'='.repeat(60)}\n`);

  console.log(`Dataset: ${report.datasetId}`);
  console.log(`Strategy: ${report.strategy}`);
  console.log(`Run ID: ${report.runId}`);
  console.log(`Timestamp: ${report.timestamp}`);
  console.log('');

  console.log('--- Summary ---');
  console.log(`Total Checkpoints: ${report.summary.totalCheckpoints}`);
  console.log(`  ✅ Successful: ${report.summary.successfulCheckpoints}`);
  console.log(`  ❌ Failed: ${report.summary.failedCheckpoints}`);
  console.log('');

  console.log('--- Operations ---');
  console.log(`  CREATE: ${report.summary.totalOperations.create}`);
  console.log(`  UPDATE: ${report.summary.totalOperations.update}`);
  console.log(`  SKIP: ${report.summary.totalOperations.skip}`);
  if (report.summary.totalOperations.requestClarification > 0) {
    console.log(`  REQUEST_CLARIFICATION: ${report.summary.totalOperations.requestClarification}`);
  }
  console.log('');

  if (report.summary.avgF1 > 0) {
    console.log('--- Comparison Metrics (Average) ---');
    console.log(`  Precision: ${(report.summary.avgPrecision * 100).toFixed(1)}%`);
    console.log(`  Recall: ${(report.summary.avgRecall * 100).toFixed(1)}%`);
    console.log(`  F1 Score: ${(report.summary.avgF1 * 100).toFixed(1)}%`);
    console.log('');
  }

  if (report.summary.avgGrade !== undefined) {
    console.log('--- LLM Grading (Average) ---');
    console.log(`  Grade: ${report.summary.avgGrade.toFixed(2)}/5`);
    console.log('');
  }

  // Display per-checkpoint details if there are failures or interesting results
  const failedCheckpoints = report.checkpoints.filter((c) => c.error);
  if (failedCheckpoints.length > 0) {
    console.log('--- Failed Checkpoints ---');
    for (const checkpoint of failedCheckpoints) {
      console.log(`  ${checkpoint.checkpoint.filename}: ${checkpoint.error}`);
    }
    console.log('');
  }

  console.log(`${'='.repeat(60)}\n`);
}

/**
 * Save a checkpoint report to a JSON file
 */
export function saveCheckpointReport(report: CheckpointReport, outputDir: string): string {
  // Create results directory within the dataset
  const resultsDir = join(outputDir, 'results');

  if (!existsSync(resultsDir)) {
    mkdirSync(resultsDir, { recursive: true });
  }

  const outputPath = join(resultsDir, `run-${report.runId}.json`);

  // Create a clean report for saving (without circular references)
  const cleanReport = {
    datasetId: report.datasetId,
    strategy: report.strategy,
    runId: report.runId,
    timestamp: report.timestamp,
    summary: report.summary,
    results: report.checkpoints.map((result) => ({
      // Important results first
      expected: result.comparison
        ? result.comparison.operationComparisons
            .filter((c) => c.expectedOp)
            .map((c) => c.expectedOp)
        : undefined,
      actual: result.operations,
      comparison: result.comparison
        ? {
            precision: result.comparison.precision,
            recall: result.comparison.recall,
            f1: result.comparison.f1Score,
            correct: result.comparison.correctOperations,
            missed: result.comparison.missedOperations,
            extra: result.comparison.extraOperations,
          }
        : undefined,
      grading: result.grading
        ? {
            llmGrades: result.grading.grades,
            averageGrade: result.grading.averageScore,
            graderInfo: result.grading.graderInfo,
          }
        : undefined,
      duration: result.duration,
      error: result.error,
      // Input context last (linearState is large)
      input: {
        docs: [result.checkpoint.filename],
        linearState: result.linearState,
      },
    })),
  };

  try {
    writeFileSync(outputPath, JSON.stringify(cleanReport, null, 2));
    console.log(`📄 Report saved to: ${outputPath}`);
  } catch (error) {
    console.error(`Failed to save report: ${error}`);
  }

  return outputPath;
}

/**
 * Generate a markdown summary of the report
 */
export function generateMarkdownSummary(report: CheckpointReport): string {
  const lines: string[] = [];

  lines.push(`# Checkpoint Evaluation Report`);
  lines.push('');
  lines.push(`**Dataset:** ${report.datasetId}`);
  lines.push(`**Strategy:** ${report.strategy}`);
  lines.push(`**Timestamp:** ${report.timestamp}`);
  lines.push('');
  lines.push(`## Summary`);
  lines.push('');
  lines.push(`| Metric | Value |`);
  lines.push(`|--------|-------|`);
  lines.push(`| Total Checkpoints | ${report.summary.totalCheckpoints} |`);
  lines.push(`| Successful | ${report.summary.successfulCheckpoints} |`);
  lines.push(`| Failed | ${report.summary.failedCheckpoints} |`);
  lines.push('');
  lines.push(`## Operations`);
  lines.push('');
  lines.push(`| Action | Count |`);
  lines.push(`|--------|-------|`);
  lines.push(`| CREATE | ${report.summary.totalOperations.create} |`);
  lines.push(`| UPDATE | ${report.summary.totalOperations.update} |`);
  lines.push(`| SKIP | ${report.summary.totalOperations.skip} |`);
  lines.push('');

  if (report.summary.avgF1 > 0) {
    lines.push(`## Comparison Metrics`);
    lines.push('');
    lines.push(`| Metric | Value |`);
    lines.push(`|--------|-------|`);
    lines.push(`| Avg Precision | ${(report.summary.avgPrecision * 100).toFixed(1)}% |`);
    lines.push(`| Avg Recall | ${(report.summary.avgRecall * 100).toFixed(1)}% |`);
    lines.push(`| Avg F1 | ${(report.summary.avgF1 * 100).toFixed(1)}% |`);
    if (report.summary.avgGrade !== undefined) {
      lines.push(`| Avg LLM Grade | ${report.summary.avgGrade.toFixed(2)}/5 |`);
    }
    lines.push('');
  }

  lines.push(`## Per-Checkpoint Results`);
  lines.push('');

  for (const result of report.checkpoints) {
    const status = result.error ? '❌' : '✅';
    lines.push(`### ${status} ${result.checkpoint.filename}`);
    lines.push('');

    if (result.error) {
      lines.push(`**Error:** ${result.error}`);
    } else {
      lines.push(`**Operations:** ${result.operations.length}`);
      if (result.comparison) {
        let metricsLine =
          `**F1:** ${(result.comparison.f1Score * 100).toFixed(0)}% | ` +
          `**Precision:** ${(result.comparison.precision * 100).toFixed(0)}% | ` +
          `**Recall:** ${(result.comparison.recall * 100).toFixed(0)}%`;
        if (result.grading) {
          metricsLine += ` | **Grade:** ${result.grading.averageScore.toFixed(2)}/5`;
        }
        lines.push(metricsLine);
      }
    }

    lines.push(`**Duration:** ${result.duration}ms`);
    lines.push('');
  }

  return lines.join('\n');
}
