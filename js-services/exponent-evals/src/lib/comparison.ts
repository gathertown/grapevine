/**
 * Comparison utilities for evaluating generated operations against ground truth
 */

import {
  compareOperationsWithAgent,
  type ComparisonMetrics,
  type OperationComparison,
  type ComparisonAgentConfig,
} from './comparison-agent';

// Re-export types from comparison-agent for convenience
export type { ComparisonMetrics, OperationComparison, ComparisonAgentConfig };

/**
 * Similarity thresholds for comparison metrics
 */
const TITLE_SIMILARITY_THRESHOLD = 0.8; // 80% - Consider titles matching if similarity >= 80%
const DESCRIPTION_SIMILARITY_THRESHOLD = 0.7; // 70% - Flag descriptions with similarity < 70%

export interface LinearOperation {
  action: 'CREATE' | 'UPDATE' | 'SKIP';
  createData?: {
    title: string;
    description: string;
    issueId?: string | null;
  };
  updateData?: {
    issueId: string;
    documentId: string;
    descriptionAppend: string;
  };
  skipData?: {
    title: string;
    reason: string;
    issueId?: string | null;
  };
  confidence?: number;
  reasoning?: string;
}

export interface ComparisonResult {
  actionMatch: boolean;
  titleMatch?: boolean;
  titleSimilarity?: number;
  descriptionSimilarity?: number;
  issueIdMatch?: boolean;
  notes: string[];
}

export interface CompareOptions {
  semantic?: boolean; // Use LLM-based semantic comparison
  matchThreshold?: number; // Threshold for semantic matching (0-1)
}

/**
 * Compute string similarity using Levenshtein distance
 * Returns value between 0 (completely different) and 1 (identical)
 */
function computeSimilarity(str1: string | undefined, str2: string | undefined): number {
  if (!str1 || !str2) return 0;
  if (str1 === str2) return 1;

  const longer = str1.length > str2.length ? str1 : str2;
  const shorter = str1.length > str2.length ? str2 : str1;

  if (longer.length === 0) return 1;

  const editDistance = levenshteinDistance(longer, shorter);
  return (longer.length - editDistance) / longer.length;
}

/**
 * Calculate Levenshtein distance between two strings
 */
function levenshteinDistance(str1: string, str2: string): number {
  const matrix: number[][] = [];

  for (let i = 0; i <= str2.length; i++) {
    matrix[i] = [i];
  }

  for (let j = 0; j <= str1.length; j++) {
    const row0 = matrix[0];
    if (row0) {
      row0[j] = j;
    }
  }

  for (let i = 1; i <= str2.length; i++) {
    for (let j = 1; j <= str1.length; j++) {
      const currentRow = matrix[i];
      if (!currentRow) continue;

      if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
        currentRow[j] = matrix[i - 1]?.[j - 1] ?? 0;
      } else {
        currentRow[j] = Math.min(
          (matrix[i - 1]?.[j - 1] ?? 0) + 1,
          (currentRow[j - 1] ?? 0) + 1,
          (matrix[i - 1]?.[j] ?? 0) + 1
        );
      }
    }
  }

  return matrix[str2.length]?.[str1.length] ?? 0;
}

/**
 * Compare generated operations against ground truth
 *
 * Returns detailed comparison results including similarity scores
 */
export function compareOperations(
  generated: LinearOperation[],
  groundTruth: LinearOperation[]
): ComparisonResult {
  const notes: string[] = [];

  // Check if we have operations to compare
  if (generated.length === 0 && groundTruth.length === 0) {
    return {
      actionMatch: true,
      notes: ['Both generated and ground truth have no operations'],
    };
  }

  if (generated.length === 0) {
    return {
      actionMatch: false,
      notes: ['Generated no operations, but ground truth expected operations'],
    };
  }

  if (groundTruth.length === 0) {
    return {
      actionMatch: false,
      notes: ['Generated operations, but ground truth expected none'],
    };
  }

  // For now, just compare first operation (most common case)
  const gen = generated[0];
  const truth = groundTruth[0];

  if (!gen || !truth) {
    return {
      actionMatch: false,
      notes: ['Missing operations to compare'],
    };
  }

  const actionMatch = gen.action === truth.action;
  if (!actionMatch) {
    notes.push(`Action mismatch: generated ${gen.action}, expected ${truth.action}`);
  }

  let titleMatch: boolean | undefined;
  let titleSimilarity: number | undefined;
  let descriptionSimilarity: number | undefined;
  let issueIdMatch: boolean | undefined;

  // Compare based on action type
  if (gen.action === 'CREATE' && truth.action === 'CREATE') {
    const genTitle = gen.createData?.title;
    const truthTitle = truth.createData?.title;
    const genDesc = gen.createData?.description;
    const truthDesc = truth.createData?.description;

    titleSimilarity = computeSimilarity(genTitle, truthTitle);
    titleMatch = titleSimilarity > TITLE_SIMILARITY_THRESHOLD;

    descriptionSimilarity = computeSimilarity(genDesc, truthDesc);

    if (!titleMatch) {
      notes.push(`Title similarity: ${(titleSimilarity * 100).toFixed(1)}%`);
    }
    if (descriptionSimilarity < DESCRIPTION_SIMILARITY_THRESHOLD) {
      notes.push(`Description similarity: ${(descriptionSimilarity * 100).toFixed(1)}%`);
    }
  } else if (gen.action === 'UPDATE' && truth.action === 'UPDATE') {
    issueIdMatch = gen.updateData?.issueId === truth.updateData?.issueId;

    if (!issueIdMatch) {
      notes.push(
        `Issue ID mismatch: generated ${gen.updateData?.issueId}, expected ${truth.updateData?.issueId}`
      );
    }

    const genAppend = gen.updateData?.descriptionAppend;
    const truthAppend = truth.updateData?.descriptionAppend;
    descriptionSimilarity = computeSimilarity(genAppend, truthAppend);

    if (descriptionSimilarity < DESCRIPTION_SIMILARITY_THRESHOLD) {
      notes.push(`Description append similarity: ${(descriptionSimilarity * 100).toFixed(1)}%`);
    }
  } else if (gen.action === 'SKIP' && truth.action === 'SKIP') {
    const genTitle = gen.skipData?.title;
    const truthTitle = truth.skipData?.title;

    titleSimilarity = computeSimilarity(genTitle, truthTitle);
    titleMatch = titleSimilarity > TITLE_SIMILARITY_THRESHOLD;

    if (!titleMatch) {
      notes.push(`Title similarity: ${(titleSimilarity * 100).toFixed(1)}%`);
    }
  }

  return {
    actionMatch,
    titleMatch,
    titleSimilarity,
    descriptionSimilarity,
    issueIdMatch,
    notes,
  };
}

/**
 * Compare all operations (multi-operation comparison)
 *
 * This compares all generated operations against all ground truth operations,
 * computing precision, recall, and F1 score.
 *
 * @param generated - Generated operations
 * @param groundTruth - Expected operations (ground truth)
 * @param options - Comparison options (semantic mode, threshold)
 */
export async function compareAllOperations(
  generated: LinearOperation[],
  groundTruth: LinearOperation[],
  options: CompareOptions = {}
): Promise<ComparisonMetrics> {
  // Use semantic comparison if requested
  if (options.semantic) {
    // Only pass matchThreshold if explicitly provided (to preserve defaults)
    const agentConfig =
      options.matchThreshold !== undefined ? { matchThreshold: options.matchThreshold } : {};
    return compareOperationsWithAgent(groundTruth, generated, agentConfig);
  }

  // Fall back to Levenshtein-based comparison for all operations
  return compareOperationsLevenshtein(generated, groundTruth);
}

/**
 * Compare operations using Levenshtein distance (fast, local comparison)
 */
function compareOperationsLevenshtein(
  generated: LinearOperation[],
  groundTruth: LinearOperation[]
): ComparisonMetrics {
  const operationComparisons: OperationComparison[] = [];
  const matchedGenIndices = new Set<number>();
  const matchedTruthIndices = new Set<number>();

  // For each expected operation, find the best matching generated operation
  for (let truthIdx = 0; truthIdx < groundTruth.length; truthIdx++) {
    const truth = groundTruth[truthIdx];
    if (!truth) continue;

    let bestMatchIdx = -1;
    let bestMatchScore = 0;
    let bestMatchNotes: string[] = [];

    for (let genIdx = 0; genIdx < generated.length; genIdx++) {
      if (matchedGenIndices.has(genIdx)) continue; // Already matched

      const gen = generated[genIdx];
      if (!gen) continue;

      // Action must match
      if (gen.action !== truth.action) continue;

      // Calculate similarity based on action type
      let score = 0;
      const notes: string[] = [];

      if (gen.action === 'CREATE' && truth.action === 'CREATE') {
        const titleSim = computeSimilarity(gen.createData?.title, truth.createData?.title);
        const descSim = computeSimilarity(
          gen.createData?.description,
          truth.createData?.description
        );
        score = titleSim * 0.7 + descSim * 0.3; // Weight title more heavily
        notes.push(`Title similarity: ${(titleSim * 100).toFixed(0)}%`);
        if (descSim < 1) {
          notes.push(`Description similarity: ${(descSim * 100).toFixed(0)}%`);
        }
      } else if (gen.action === 'UPDATE' && truth.action === 'UPDATE') {
        // For UPDATE, issue ID must match exactly
        if (gen.updateData?.issueId === truth.updateData?.issueId) {
          const descSim = computeSimilarity(
            gen.updateData?.descriptionAppend,
            truth.updateData?.descriptionAppend
          );
          score = 1.0; // Issue ID match is primary
          notes.push(`Issue ID match: ${gen.updateData?.issueId}`);
          if (descSim < 1) {
            notes.push(`Description similarity: ${(descSim * 100).toFixed(0)}%`);
          }
        }
      } else if (gen.action === 'SKIP' && truth.action === 'SKIP') {
        // For SKIP, match on reason similarity (title is optional)
        const reasonSim = computeSimilarity(gen.skipData?.reason, truth.skipData?.reason);
        const titleSim = computeSimilarity(gen.skipData?.title, truth.skipData?.title);
        // Use reason as primary, title as secondary if both exist
        score = reasonSim > 0 ? reasonSim : titleSim;
        if (score === 0 && gen.action === 'SKIP' && truth.action === 'SKIP') {
          // Both are SKIP, give base score for action match
          score = 0.8;
        }
        notes.push(`Reason similarity: ${(reasonSim * 100).toFixed(0)}%`);
      }

      if (score > bestMatchScore) {
        bestMatchScore = score;
        bestMatchIdx = genIdx;
        bestMatchNotes = notes;
      }
    }

    // Threshold for matching
    const matchThreshold = TITLE_SIMILARITY_THRESHOLD;

    if (bestMatchIdx >= 0 && bestMatchScore >= matchThreshold) {
      matchedGenIndices.add(bestMatchIdx);
      matchedTruthIndices.add(truthIdx);

      operationComparisons.push({
        matched: true,
        expectedOp: truth,
        actualOp: generated[bestMatchIdx],
        matchScore: bestMatchScore,
        differences: bestMatchNotes,
      });
    } else {
      // Unmatched expected operation
      operationComparisons.push({
        matched: false,
        expectedOp: truth,
        actualOp: bestMatchIdx >= 0 ? generated[bestMatchIdx] : undefined,
        matchScore: bestMatchScore > 0 ? bestMatchScore : undefined,
        differences:
          bestMatchScore > 0
            ? [`Best match score: ${(bestMatchScore * 100).toFixed(0)}%`, ...bestMatchNotes]
            : ['No matching operation found'],
      });
    }
  }

  // Add extra generated operations (those that didn't match any expected)
  for (let genIdx = 0; genIdx < generated.length; genIdx++) {
    if (!matchedGenIndices.has(genIdx)) {
      const gen = generated[genIdx];
      operationComparisons.push({
        matched: false,
        expectedOp: undefined,
        actualOp: gen,
        isExtra: true,
        differences: ['Extra operation not in ground truth'],
      });
    }
  }

  // Calculate metrics
  const correctOperations = matchedTruthIndices.size;
  const totalExpected = groundTruth.length;
  const totalActual = generated.length;
  const missedOperations = totalExpected - correctOperations;
  const extraOperations = totalActual - matchedGenIndices.size;

  const precision = totalActual > 0 ? correctOperations / totalActual : 0;
  const recall = totalExpected > 0 ? correctOperations / totalExpected : 0;
  const f1Score = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;

  return {
    totalExpected,
    totalActual,
    correctOperations,
    missedOperations,
    extraOperations,
    precision,
    recall,
    f1Score,
    operationComparisons,
  };
}
