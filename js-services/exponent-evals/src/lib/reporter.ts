/**
 * Reporter utilities for displaying eval results
 */

import type { EvalResult } from './processor';

/**
 * Display final summary report for all eval results
 */
export function displayReport(results: EvalResult[]): void {
  console.log(`\n${'='.repeat(80)}`);
  console.log('📊 EVALUATION SUMMARY');
  console.log(`${'='.repeat(80)}\n`);

  const successful = results.filter((r) => r.success);
  const failed = results.filter((r) => !r.success);

  console.log(`Total test cases: ${results.length}`);
  console.log(`  ✅ Passed: ${successful.length}`);
  console.log(`  ❌ Failed: ${failed.length}`);

  if (successful.length > 0) {
    const avgDuration = successful.reduce((sum, r) => sum + r.duration, 0) / successful.length;
    console.log(`  ⏱️  Average duration: ${avgDuration.toFixed(0)}ms`);
  }

  // Display comparison stats if available
  const withComparison = results.filter((r) => r.comparison);
  if (withComparison.length > 0) {
    console.log(`\n${'-'.repeat(80)}`);
    console.log('Ground Truth Comparison (Legacy):');
    console.log(`${'-'.repeat(80)}\n`);

    const actionMatches = withComparison.filter((r) => r.comparison?.actionMatch).length;
    const titleMatches = withComparison.filter((r) => r.comparison?.titleMatch).length;

    console.log(`  Action matches: ${actionMatches}/${withComparison.length}`);

    if (titleMatches > 0) {
      console.log(`  Title matches: ${titleMatches}/${withComparison.length}`);
    }

    // Calculate average similarities
    const titleSimilarities = withComparison
      .map((r) => r.comparison?.titleSimilarity)
      .filter((s): s is number => s !== undefined);

    const descSimilarities = withComparison
      .map((r) => r.comparison?.descriptionSimilarity)
      .filter((s): s is number => s !== undefined);

    if (titleSimilarities.length > 0) {
      const avgTitleSim =
        titleSimilarities.reduce((sum, s) => sum + s, 0) / titleSimilarities.length;
      console.log(`  Average title similarity: ${(avgTitleSim * 100).toFixed(1)}%`);
    }

    if (descSimilarities.length > 0) {
      const avgDescSim = descSimilarities.reduce((sum, s) => sum + s, 0) / descSimilarities.length;
      console.log(`  Average description similarity: ${(avgDescSim * 100).toFixed(1)}%`);
    }
  }

  // Display advanced comparison metrics (precision/recall/F1)
  const withMetrics = results.filter((r) => r.comparisonMetrics);
  if (withMetrics.length > 0) {
    console.log(`\n${'-'.repeat(80)}`);
    console.log('Multi-Operation Comparison Metrics:');
    console.log(`${'-'.repeat(80)}\n`);

    // Aggregate metrics
    let totalExpected = 0;
    let totalActual = 0;
    let totalCorrect = 0;
    let totalMissed = 0;
    let totalExtra = 0;

    for (const r of withMetrics) {
      if (r.comparisonMetrics) {
        totalExpected += r.comparisonMetrics.totalExpected;
        totalActual += r.comparisonMetrics.totalActual;
        totalCorrect += r.comparisonMetrics.correctOperations;
        totalMissed += r.comparisonMetrics.missedOperations;
        totalExtra += r.comparisonMetrics.extraOperations;
      }
    }

    const overallPrecision = totalActual > 0 ? totalCorrect / totalActual : 0;
    const overallRecall = totalExpected > 0 ? totalCorrect / totalExpected : 0;
    const overallF1 =
      overallPrecision + overallRecall > 0
        ? (2 * overallPrecision * overallRecall) / (overallPrecision + overallRecall)
        : 0;

    console.log(`  Total expected operations: ${totalExpected}`);
    console.log(`  Total actual operations: ${totalActual}`);
    console.log(`  Correct matches: ${totalCorrect}`);
    console.log(`  Missed operations: ${totalMissed}`);
    console.log(`  Extra operations: ${totalExtra}`);
    console.log();
    console.log(`  📈 Overall Precision: ${(overallPrecision * 100).toFixed(1)}%`);
    console.log(`  📈 Overall Recall: ${(overallRecall * 100).toFixed(1)}%`);
    console.log(`  📈 Overall F1 Score: ${(overallF1 * 100).toFixed(1)}%`);
  }

  // Display LLM grading stats if available
  const withGrades = results.filter((r) => r.llmGrades && r.llmGrades.length > 0);
  if (withGrades.length > 0) {
    console.log(`\n${'-'.repeat(80)}`);
    console.log('LLM Grading Results:');
    console.log(`${'-'.repeat(80)}\n`);

    // Collect all grades
    const allGrades: number[] = [];
    for (const r of withGrades) {
      if (r.llmGrades) {
        for (const g of r.llmGrades) {
          if (g.score > 0) {
            allGrades.push(g.score);
          }
        }
      }
    }

    if (allGrades.length > 0) {
      const avgGrade = allGrades.reduce((sum, g) => sum + g, 0) / allGrades.length;
      const minGrade = Math.min(...allGrades);
      const maxGrade = Math.max(...allGrades);

      // Grade distribution
      const distribution: [number, number, number, number, number] = [0, 0, 0, 0, 0]; // scores 1-5
      for (const g of allGrades) {
        if (g >= 1 && g <= 5) {
          const idx = g - 1;
          distribution[idx] = (distribution[idx] ?? 0) + 1;
        }
      }

      console.log(`  Total graded operations: ${allGrades.length}`);
      console.log(`  Average grade: ${avgGrade.toFixed(2)}/5`);
      console.log(`  Min grade: ${minGrade}/5`);
      console.log(`  Max grade: ${maxGrade}/5`);
      console.log();
      console.log('  Grade Distribution:');
      console.log(`    1/5 (Wrong):    ${'█'.repeat(distribution[0])} ${distribution[0]}`);
      console.log(`    2/5 (Major):    ${'█'.repeat(distribution[1])} ${distribution[1]}`);
      console.log(`    3/5 (Partial):  ${'█'.repeat(distribution[2])} ${distribution[2]}`);
      console.log(`    4/5 (Minor):    ${'█'.repeat(distribution[3])} ${distribution[3]}`);
      console.log(`    5/5 (Perfect):  ${'█'.repeat(distribution[4])} ${distribution[4]}`);
    }
  }

  // Display failures if any
  if (failed.length > 0) {
    console.log(`\n${'-'.repeat(80)}`);
    console.log('Failed Test Cases:');
    console.log(`${'-'.repeat(80)}\n`);

    failed.forEach((result) => {
      console.log(`  ❌ ${result.testCaseId}`);
      console.log(`     Error: ${result.error}`);
    });
  }

  // Display operation distribution
  console.log(`\n${'-'.repeat(80)}`);
  console.log('Operation Distribution:');
  console.log(`${'-'.repeat(80)}\n`);

  const createOps = successful.filter(
    (r) => r.operations && r.operations[0]?.action === 'CREATE'
  ).length;
  const updateOps = successful.filter(
    (r) => r.operations && r.operations[0]?.action === 'UPDATE'
  ).length;
  const skipOps = successful.filter(
    (r) => r.operations && r.operations[0]?.action === 'SKIP'
  ).length;

  console.log(`  CREATE: ${createOps}`);
  console.log(`  UPDATE: ${updateOps}`);
  console.log(`  SKIP: ${skipOps}`);

  console.log(`\n${'='.repeat(80)}\n`);
}

/**
 * Display brief summary of test cases to be run
 */
export function displayTestCases(testCases: Array<{ id: string; title: string }>): void {
  console.log('\n📋 Test Cases:');
  testCases.forEach((tc, i) => {
    console.log(`  ${i + 1}. ${tc.title}`);
  });
  console.log();
}
