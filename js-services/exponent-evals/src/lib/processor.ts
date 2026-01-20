/**
 * Eval Processor
 *
 * Orchestrates running test cases through TriageAgentStrategy or
 * SingleAgentStrategy and comparing results against ground truth.
 */

import { writeFileSync, mkdirSync } from 'fs';
import { join } from 'path';
import type { TriageAgentStrategy } from '@corporate-context/slack-bot/triage';
import {
  SingleAgentStrategy,
  type LinearContext,
  type TaskSourceMetadata,
  type SlackDocument,
  type GithubPrDocument,
  type MeetingTranscript,
  type LinearOperation as ExponentLinearOperation,
} from '@corporate-context/exponent-core';
import { MockTenantSlackApp } from './mock-tenant-app';
import {
  compareOperations,
  compareAllOperations,
  type LinearOperation,
  type ComparisonResult,
  type ComparisonMetrics,
} from './comparison';
import { gradeOperations, validateGraderSetup, type LLMGradeResult } from './grader';

export interface TestCase {
  id: string;
  title: string;
  date?: string;
  type?: 'slack' | 'github' | 'meeting';
  content: string;
  participants?: string[];
  files?: Array<{ url: string; name: string; mimeType?: string }>;
  // GitHub-specific fields
  author?: string;
  repository?: string;
  prNumber?: number;
  groundTruth?: {
    operations: LinearOperation[];
  };
  filePath: string;
}

export interface EvalConfig {
  tenantId: string;
  mcpApiKey: string;
  mcpBaseUrl: string;
  model?: string;
  // For SingleAgentStrategy
  linearApiKey?: string;
  linearTeamId?: string;
  linearTeamName?: string;
  searchProvider?: 'grapevine' | 'linear-api';
}

export interface EvalOptions {
  compare?: boolean;
  verbose?: boolean;
  output?: string;
  // New options for LLM grading and semantic comparison
  grade?: boolean; // Enable LLM grading of operations
  semantic?: boolean; // Use semantic comparison agent instead of Levenshtein
  showDiffs?: boolean; // Display detailed truth diffs
}

export interface EvalResult {
  testCaseId: string;
  success: boolean;
  operations?: LinearOperation[];
  triageAnalysis?: unknown;
  askAgentMetrics?: unknown;
  duration: number;
  comparison?: ComparisonResult | null;
  // New fields for advanced comparison and grading
  comparisonMetrics?: ComparisonMetrics | null;
  llmGrades?: LLMGradeResult[];
  averageGrade?: number;
  error?: string;
  outputPath?: string;
}

/**
 * Sleep utility for rate limiting
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface TriageResult {
  operations: ExponentLinearOperation[];
  triageAnalysis?: unknown;
  askAgentMetrics?: unknown;
}

/**
 * Save eval result to JSON file
 */
function saveResult(testCase: TestCase, result: TriageResult, outputDir: string): string {
  // Create timestamped output directory
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
  const outputPath = join(outputDir, timestamp);

  try {
    mkdirSync(outputPath, { recursive: true });
  } catch (error) {
    console.error(`Failed to create output directory: ${error}`);
  }

  // Save generated operations
  const outputFile = join(outputPath, `${testCase.id}-generated.json`);
  const outputData = {
    testCaseId: testCase.id,
    title: testCase.title,
    date: testCase.date,
    operations: result.operations,
    triageAnalysis: result.triageAnalysis,
    askAgentMetrics: result.askAgentMetrics,
  };

  try {
    writeFileSync(outputFile, JSON.stringify(outputData, null, 2));
  } catch (error) {
    console.error(`Failed to write result file: ${error}`);
  }

  return outputFile;
}

/**
 * Process multiple test cases through TriageAgentStrategy or SingleAgentStrategy
 *
 * Runs each test case sequentially with rate limiting and optional
 * comparison against ground truth.
 */
export async function processEvals(
  testCases: TestCase[],
  strategy: TriageAgentStrategy | SingleAgentStrategy,
  config: EvalConfig,
  options: EvalOptions
): Promise<EvalResult[]> {
  const results: EvalResult[] = [];
  const outputDir = options.output || 'src/results';

  // Validate grader setup if grading is enabled
  if (options.grade) {
    const graderValidation = validateGraderSetup();
    if (!graderValidation.valid) {
      console.error('❌ Grader setup validation failed:');
      graderValidation.errors.forEach((err) => console.error(`   ${err}`));
      console.error('   Grading will be skipped.\n');
      options.grade = false;
    } else {
      console.log('✅ LLM grading enabled\n');
    }
  }

  if (options.semantic) {
    console.log('✅ Semantic comparison enabled\n');
  }

  console.log(`\n🧪 Running ${testCases.length} test cases...\n`);

  for (let i = 0; i < testCases.length; i++) {
    const testCase = testCases[i];
    if (!testCase) continue;
    console.log(`[${i + 1}/${testCases.length}] Running: ${testCase.title}`);

    const startTime = Date.now();

    try {
      let result: TriageResult;

      if (strategy instanceof SingleAgentStrategy) {
        // SingleAgentStrategy path - use Grapevine search
        let document: SlackDocument | GithubPrDocument | MeetingTranscript;

        if (testCase.type === 'meeting') {
          // Meeting transcript document
          document = {
            title: testCase.title,
            attendees: testCase.participants,
            date: testCase.date,
            content: testCase.content,
          };
        } else if (testCase.type === 'github') {
          // GitHub PR document
          document = {
            documentId: testCase.id,
            title: testCase.title,
            author: testCase.author,
            repository: testCase.repository,
            prNumber: testCase.prNumber,
            date: testCase.date,
            content: testCase.content,
          };
        } else {
          // Default to Slack document
          document = {
            documentId: testCase.id,
            channel: 'eval',
            date: testCase.date,
            content: testCase.content,
            participants: testCase.participants,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            files: testCase.files as any,
          };
        }

        if (!config.linearApiKey || !config.linearTeamId || !config.linearTeamName) {
          throw new Error('Missing Linear config for SingleAgentStrategy');
        }

        const linearContext: LinearContext = {
          apiKey: config.linearApiKey,
          teamId: config.linearTeamId,
          teamName: config.linearTeamName,
          searchProvider: config.searchProvider ?? 'grapevine',
          grapevine:
            config.searchProvider === 'linear-api'
              ? undefined
              : {
                  apiKey: config.mcpApiKey,
                  mcpUrl: config.mcpBaseUrl,
                  tenantId: config.tenantId,
                },
        };

        const metadata: TaskSourceMetadata = {
          // 'gather' is the source type for meetings in SingleAgentStrategy
          source: testCase.type === 'meeting' ? 'gather' : testCase.type || 'slack',
          sourceId: testCase.id,
        };

        const singleAgentResult = await strategy.process(document, linearContext, metadata);

        result = {
          operations: singleAgentResult.operations,
          triageAnalysis: undefined,
          askAgentMetrics: undefined,
        };
      } else {
        // TriageAgentStrategy path (existing code)
        // Create mock app for this test case
        const mockApp = new MockTenantSlackApp(
          config.tenantId,
          config.mcpApiKey,
          config.mcpBaseUrl
        );

        result = await strategy.process(
          {
            content: testCase.content,
            // Type cast needed: test case files don't include all FileAttachment properties
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            files: (testCase.files as any) || [],
          },
          'eval-user',
          // Type cast needed: MockTenantSlackApp implements subset of TenantSlackApp interface
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          mockApp as any
        );
      }

      const duration = Date.now() - startTime;

      // Compare with ground truth if available and requested
      let comparison: ComparisonResult | null = null;
      let comparisonMetrics: ComparisonMetrics | null = null;
      let llmGrades: LLMGradeResult[] | undefined;
      let averageGrade: number | undefined;

      const generatedOps = result.operations as unknown as LinearOperation[];

      if (options.compare && testCase.groundTruth) {
        // Legacy single-operation comparison (for backwards compatibility)
        comparison = compareOperations(generatedOps, testCase.groundTruth.operations);

        // New multi-operation comparison with optional semantic matching
        comparisonMetrics = await compareAllOperations(
          generatedOps,
          testCase.groundTruth.operations,
          { semantic: options.semantic }
        );

        // Display comparison inline
        if (comparisonMetrics.correctOperations === comparisonMetrics.totalExpected) {
          console.log(
            `  ✅ All operations match (${comparisonMetrics.correctOperations}/${comparisonMetrics.totalExpected})`
          );
        } else {
          console.log(
            `  ⚠️  Partial match: ${comparisonMetrics.correctOperations}/${comparisonMetrics.totalExpected} operations`
          );
        }

        // Display precision/recall/F1
        console.log(
          `     Precision: ${(comparisonMetrics.precision * 100).toFixed(0)}% | ` +
            `Recall: ${(comparisonMetrics.recall * 100).toFixed(0)}% | ` +
            `F1: ${(comparisonMetrics.f1Score * 100).toFixed(0)}%`
        );

        // Show detailed diffs if requested
        if (options.showDiffs && comparisonMetrics.operationComparisons.length > 0) {
          console.log('     --- Truth Diff ---');
          for (const comp of comparisonMetrics.operationComparisons) {
            if (comp.matched) {
              const score = comp.matchScore ? `(${(comp.matchScore * 100).toFixed(0)}%)` : '';
              console.log(
                `     ✓ ${comp.expectedOp?.createData?.title || comp.expectedOp?.action} ${score}`
              );
            } else if (comp.isExtra) {
              console.log(
                `     + EXTRA: ${comp.actualOp?.createData?.title || comp.actualOp?.action}`
              );
            } else {
              console.log(
                `     ✗ MISSING: ${comp.expectedOp?.createData?.title || comp.expectedOp?.action}`
              );
              if (comp.differences.length > 0) {
                comp.differences.forEach((diff) => console.log(`       ${diff}`));
              }
            }
          }
        }

        // LLM grading if enabled
        if (options.grade && testCase.groundTruth.operations.length > 0) {
          console.log('     Grading with LLM...');
          const gradeResult = await gradeOperations(
            generatedOps,
            testCase.groundTruth.operations,
            testCase.content
          );
          llmGrades = gradeResult.grades;
          averageGrade = gradeResult.averageScore;

          if (averageGrade > 0) {
            const gradeEmoji = averageGrade >= 4 ? '🌟' : averageGrade >= 3 ? '👍' : '⚠️';
            console.log(`     ${gradeEmoji} Average grade: ${averageGrade.toFixed(1)}/5`);
          }
        }
      }

      // Save result
      const outputPath = saveResult(testCase, result, outputDir);

      // Display operation summary
      if (result.operations.length > 0) {
        const op = result.operations[0];
        if (!op) continue;
        console.log(`  📝 Operation: ${op.action}`);

        if (op.action === 'CREATE' && op.createData) {
          console.log(`     Title: ${op.createData.title.substring(0, 60)}...`);
        } else if (op.action === 'UPDATE' && op.updateData) {
          console.log(`     Issue: ${op.updateData.issueId}`);
        } else if (op.action === 'SKIP' && op.skipData) {
          console.log(`     Reason: ${op.skipData.reason.substring(0, 60)}...`);
        }

        if (options.verbose && op.reasoning) {
          console.log(`     Reasoning: ${op.reasoning}`);
        }
      }

      console.log(`  ⏱️  Completed in ${duration}ms\n`);

      results.push({
        testCaseId: testCase.id,
        success: true,
        operations: generatedOps,
        triageAnalysis: result.triageAnalysis,
        askAgentMetrics: result.askAgentMetrics,
        duration,
        comparison,
        comparisonMetrics,
        llmGrades,
        averageGrade,
        outputPath,
      });
    } catch (error) {
      const duration = Date.now() - startTime;
      const errorMessage = error instanceof Error ? error.message : String(error);

      console.log(`  ❌ Failed: ${errorMessage}`);
      console.log(`  ⏱️  Failed after ${duration}ms\n`);

      results.push({
        testCaseId: testCase.id,
        success: false,
        error: errorMessage,
        duration,
      });
    }

    // Rate limiting: 1 second between requests
    if (i < testCases.length - 1) {
      await sleep(1000);
    }
  }

  return results;
}
