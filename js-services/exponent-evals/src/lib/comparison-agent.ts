/**
 * AI-powered operation comparison system
 *
 * This module uses an LLM to compare expected vs actual operations
 * using semantic matching instead of static fuzzy matching algorithms.
 */

import OpenAI from 'openai';
import type { LinearOperation } from './comparison';

/**
 * Comparison result for a single operation
 */
export interface OperationComparison {
  matched: boolean;
  expectedOp?: LinearOperation;
  actualOp?: LinearOperation;
  differences: string[];
  matchScore?: number;
  reasoning?: string;
  isExtra?: boolean; // True if this is an extra operation not in ground truth
}

/**
 * Overall comparison metrics
 */
export interface ComparisonMetrics {
  totalExpected: number;
  totalActual: number;
  correctOperations: number;
  missedOperations: number;
  extraOperations: number;
  precision: number;
  recall: number;
  f1Score: number;
  operationComparisons: OperationComparison[];
}

/**
 * Configuration for the comparison agent
 */
export interface ComparisonAgentConfig {
  model?: string;
  temperature?: number;
  matchThreshold?: number; // Minimum score to consider a match (0-1)
}

const DEFAULT_CONFIG: Required<ComparisonAgentConfig> = {
  model: 'gpt-4o',
  temperature: 0.0,
  matchThreshold: 0.5, // Lower threshold to allow semantic matches with different wording
};

/**
 * LLM response format for operation matching
 */
interface MatchingResult {
  matches: Array<{
    expectedIndex: number;
    actualIndex: number;
    score: number; // 0-1
    reasoning: string;
  }>;
  unmatchedExpected: Array<{
    expectedIndex: number;
    reasoning: string;
    closestActualIndex?: number;
    closestScore?: number;
  }>;
  unmatchedActual: number[]; // Indices of actual operations that didn't match
}

/**
 * Compare operations using an LLM agent
 *
 * The agent analyzes both expected and actual operations to determine:
 * 1. Which operations match (and how well)
 * 2. Which expected operations are missing
 * 3. Which actual operations are extra
 *
 * @param expected - Expected operations (ground truth)
 * @param actual - Actual operations (generated)
 * @param config - Optional configuration
 * @returns Comparison metrics in the standard format
 */
export async function compareOperationsWithAgent(
  expected: LinearOperation[],
  actual: LinearOperation[],
  config: ComparisonAgentConfig = {}
): Promise<ComparisonMetrics> {
  const finalConfig = { ...DEFAULT_CONFIG, ...config };

  // If either array is empty, return simple metrics
  if (expected.length === 0 || actual.length === 0) {
    return {
      totalExpected: expected.length,
      totalActual: actual.length,
      correctOperations: 0,
      missedOperations: expected.length,
      extraOperations: actual.length,
      precision: 0,
      recall: 0,
      f1Score: 0,
      operationComparisons: expected.map((op) => ({
        matched: false,
        expectedOp: op,
        actualOp: undefined,
        differences: ['No actual operations to compare'],
      })),
    };
  }

  const client = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY,
  });

  // Build the comparison prompt
  const prompt = buildComparisonPrompt(expected, actual, finalConfig);

  try {
    const response = await client.chat.completions.create({
      model: finalConfig.model,
      messages: [
        {
          role: 'system',
          content:
            'You are an expert at comparing Linear operations for task management. Your job is to accurately match expected operations with actual operations, determining which are correct, which are missing, and which are extra.',
        },
        { role: 'user', content: prompt },
      ],
      temperature: finalConfig.temperature,
      response_format: { type: 'json_object' },
    });

    const responseText = response.choices[0]?.message?.content?.trim() || '{}';
    const matchingResult = parseMatchingResult(responseText);

    // Convert LLM result to ComparisonMetrics
    return buildComparisonMetrics(expected, actual, matchingResult, finalConfig.matchThreshold);
  } catch (error) {
    console.error('Error during agent-based comparison:', error);
    // Fallback to empty metrics on error
    return {
      totalExpected: expected.length,
      totalActual: actual.length,
      correctOperations: 0,
      missedOperations: expected.length,
      extraOperations: actual.length,
      precision: 0,
      recall: 0,
      f1Score: 0,
      operationComparisons: expected.map((op) => ({
        matched: false,
        expectedOp: op,
        actualOp: undefined,
        differences: [`Comparison error: ${error}`],
      })),
    };
  }
}

/**
 * Build the prompt for the LLM to compare operations
 */
function buildComparisonPrompt(
  expected: LinearOperation[],
  actual: LinearOperation[],
  config: Required<ComparisonAgentConfig>
): string {
  return `You are an expert at comparing task management operations. Your goal is to determine if two operations represent THE SAME WORK, even if described differently.

**CRITICAL INSTRUCTION: Focus on SEMANTIC EQUIVALENCE, not exact wording.**

Two operations are the same if they describe:
- The same core action or deliverable
- The same general scope and outcome
- The same intended work, even if phrased differently

**EXAMPLES OF MATCHES:**
- "Build basic eval harness/agent for Linear Killer" ≈ "Build naive harness script to run agent against frozen tenant" (SAME: both are building the eval harness)
- "Set up Grapevine eval tenant (frozen E1)" ≈ "Create frozen evaluation environment for Grapevine" (SAME: both setting up frozen tenant)
- "Define ground truth task list in No Bots Allowed" ≈ "Create ground truth task list for evaluation" (SAME: both creating ground truth)

**EXAMPLES OF NON-MATCHES:**
- "Build eval harness" ≠ "Test eval harness" (DIFFERENT: building vs testing)
- "Set up dev environment" ≠ "Set up prod environment" (DIFFERENT: different environments)
- "Write unit tests" ≠ "Write integration tests" (DIFFERENT: different types of tests)

**MATCHING PROCESS:**

1. **Understand the core intent** of each operation - what is the actual work being done?
2. **Ignore superficial differences** in wording, phrasing, or technical jargon
3. **Focus on the deliverable** - if both operations would result in the same artifact or outcome, they match
4. **Action type must match** - CREATE, UPDATE, or SKIP must be the same

**SCORING GUIDELINES:**

For CREATE operations:
- **Core task similarity (80% weight)**: Do they describe the same work/deliverable?
  - 1.0 = Clearly the same task, just different wording
  - 0.8-0.9 = Same task with minor scope differences
  - 0.6-0.7 = Related tasks but somewhat different scope
  - <0.6 = Different tasks
- **Assignee match (10% weight)**: Same person assigned?
  - 1.0 = Same assignee
  - 0.5 = One has assignee, other doesn't (could be same task, just unassigned)
  - 0.0 = Different assignees
- **Description alignment (10% weight)**: Similar details if present?

**IMPORTANT**: If two operations describe the same core work, they should score at least 0.7-0.8 even if assignee differs or one lacks an assignee.

For UPDATE operations:
- Issue ID must be EXACTLY the same (score 1.0 if match, 0.0 if not)

For SKIP operations:
- If both have the same reason/intent (e.g., "no actionable content"), score 0.9-1.0
- SKIP operations may not have issue IDs - match based on the reason being semantically similar

**EXPECTED OPERATIONS:**
${expected.map((op, i) => `[${i}] ${formatOperation(op)}`).join('\n')}

**ACTUAL OPERATIONS:**
${actual.map((op, i) => `[${i}] ${formatOperation(op)}`).join('\n')}

**OUTPUT FORMAT:**

Return a JSON object with this exact structure:
{
  "matches": [
    {
      "expectedIndex": <number>,
      "actualIndex": <number>,
      "score": <number between 0.0 and 1.0>,
      "reasoning": "<Explain why these are the same task despite wording differences>"
    }
  ],
  "unmatchedExpected": [
    {
      "expectedIndex": <number>,
      "reasoning": "<Explain what's unique about the expected operation that wasn't found in actual>",
      "closestActualIndex": <number or null>,
      "closestScore": <number between 0.0 and 1.0, or null>
    }
  ],
  "unmatchedActual": [<indices of actual operations that didn't match any expected>]
}

**REASONING GUIDELINES:**
- For matches: Explain the semantic similarity (e.g., "Both are building the eval harness, just different phrasing")
- For unmatched: Explain what makes this unique (e.g., "This is about testing, not building" or "This is for prod, not dev")
- Be specific about the core deliverable or action that differs

**MATCHING RULES:**
- Each expected and actual operation can only be matched ONCE (bipartite matching)
- When multiple matches are possible, choose the highest scoring match
- Only include matches with score >= ${config.matchThreshold} in the "matches" array
- Operations below the threshold should appear in "unmatchedExpected" or "unmatchedActual"
- BE GENEROUS with semantic matching - if the core work is the same, they should match!
`;
}

/**
 * Format an operation for display in the prompt
 */
function formatOperation(op: LinearOperation): string {
  let result = `Action: ${op.action}`;

  if (op.action === 'CREATE' && op.createData) {
    result += `\n  Title: "${op.createData.title}"`;
    if (op.createData.description) {
      const desc = op.createData.description;
      result += `\n  Description: "${desc.substring(0, 100)}${desc.length > 100 ? '...' : ''}"`;
    }
  } else if (op.action === 'UPDATE' && op.updateData) {
    result += `\n  Issue ID: ${op.updateData.issueId}`;
    if (op.updateData.descriptionAppend) {
      const desc = op.updateData.descriptionAppend;
      result += `\n  Description Append: "${desc.substring(0, 100)}${desc.length > 100 ? '...' : ''}"`;
    }
  } else if (op.action === 'SKIP' && op.skipData) {
    if (op.skipData.title) {
      result += `\n  Title: "${op.skipData.title}"`;
    }
    if (op.skipData.reason) {
      result += `\n  Reason: "${op.skipData.reason}"`;
    }
  }

  if (op.confidence !== undefined) {
    result += `\n  Confidence: ${op.confidence}%`;
  }

  return result;
}

/**
 * Parse the LLM response into a MatchingResult
 */
function parseMatchingResult(responseText: string): MatchingResult {
  try {
    // Remove markdown code blocks if present
    let cleanedText = responseText.trim();
    if (cleanedText.startsWith('```json')) {
      cleanedText = cleanedText.slice(7);
    } else if (cleanedText.startsWith('```')) {
      cleanedText = cleanedText.slice(3);
    }
    if (cleanedText.endsWith('```')) {
      cleanedText = cleanedText.slice(0, -3);
    }
    cleanedText = cleanedText.trim();

    const result = JSON.parse(cleanedText);

    // Validate structure
    if (!result.matches || !Array.isArray(result.matches)) {
      result.matches = [];
    }
    if (!result.unmatchedExpected || !Array.isArray(result.unmatchedExpected)) {
      result.unmatchedExpected = [];
    }
    if (!result.unmatchedActual || !Array.isArray(result.unmatchedActual)) {
      result.unmatchedActual = [];
    }

    return result as MatchingResult;
  } catch (error) {
    console.error('Failed to parse matching result:', error);
    return {
      matches: [],
      unmatchedExpected: [],
      unmatchedActual: [],
    };
  }
}

/**
 * Build ComparisonMetrics from the LLM matching result
 */
function buildComparisonMetrics(
  expected: LinearOperation[],
  actual: LinearOperation[],
  matchingResult: MatchingResult,
  matchThreshold: number
): ComparisonMetrics {
  const operationComparisons: OperationComparison[] = [];
  const matchedExpectedIndices = new Set<number>();
  const matchedActualIndices = new Set<number>();

  // Process matched operations
  for (const match of matchingResult.matches) {
    if (match.score >= matchThreshold) {
      matchedExpectedIndices.add(match.expectedIndex);
      matchedActualIndices.add(match.actualIndex);

      const expectedOp = expected[match.expectedIndex];
      const actualOp = actual[match.actualIndex];

      operationComparisons.push({
        matched: true,
        expectedOp,
        actualOp,
        matchScore: match.score,
        reasoning: match.reasoning,
        differences:
          match.score < 1.0
            ? [`Match score: ${(match.score * 100).toFixed(0)}%`, match.reasoning]
            : [`Match score: ${(match.score * 100).toFixed(0)}%`],
      });
    }
  }

  // Process unmatched expected operations
  for (const unmatched of matchingResult.unmatchedExpected) {
    const expectedOp = expected[unmatched.expectedIndex];
    const closestOp =
      unmatched.closestActualIndex !== undefined && unmatched.closestActualIndex !== null
        ? actual[unmatched.closestActualIndex]
        : undefined;

    // Mark the closest match as used so it doesn't get added as an "extra" operation later
    if (unmatched.closestActualIndex !== undefined && unmatched.closestActualIndex !== null) {
      matchedActualIndices.add(unmatched.closestActualIndex);
    }

    const differences = [unmatched.reasoning];
    if (closestOp && unmatched.closestScore !== undefined) {
      differences.unshift(`Best match score: ${(unmatched.closestScore * 100).toFixed(0)}%`);
    }

    operationComparisons.push({
      matched: false,
      expectedOp,
      actualOp: closestOp,
      matchScore: unmatched.closestScore,
      reasoning: unmatched.reasoning,
      differences,
    });
  }

  // Add extra actual operations (those that didn't match any expected)
  for (const actualIndex of matchingResult.unmatchedActual) {
    if (!matchedActualIndices.has(actualIndex)) {
      const actualOp = actual[actualIndex];
      operationComparisons.push({
        matched: false,
        expectedOp: undefined,
        actualOp,
        isExtra: true,
        differences: ['Extra operation not in ground truth'],
      });
    }
  }

  // Ensure ALL expected operations are represented in operationComparisons
  // (in case LLM didn't return them in unmatchedExpected)
  for (let i = 0; i < expected.length; i++) {
    if (!matchedExpectedIndices.has(i)) {
      // Check if this expected op was already added via unmatchedExpected
      const alreadyAdded = operationComparisons.some(
        (c) => c.expectedOp === expected[i] && !c.matched
      );
      if (!alreadyAdded) {
        operationComparisons.push({
          matched: false,
          expectedOp: expected[i],
          actualOp: undefined,
          differences: ['Expected operation not found in actual operations'],
        });
      }
    }
  }

  // Sort comparisons: matched first, then unmatched expected, then extras
  operationComparisons.sort((a, b) => {
    // Matched operations first
    if (a.matched && !b.matched) return -1;
    if (!a.matched && b.matched) return 1;

    // Then unmatched expected (has expectedOp but no match)
    if (a.expectedOp && !a.isExtra && (!b.expectedOp || b.isExtra)) return -1;
    if ((!a.expectedOp || a.isExtra) && b.expectedOp && !b.isExtra) return 1;

    // Sort by expected index if both have expectedOp
    if (a.expectedOp && b.expectedOp) {
      const aIndex = expected.indexOf(a.expectedOp);
      const bIndex = expected.indexOf(b.expectedOp);
      return aIndex - bIndex;
    }

    return 0;
  });

  // Calculate metrics
  const correctOperations = matchedExpectedIndices.size;
  const totalExpected = expected.length;
  const totalActual = actual.length;
  const missedOperations = totalExpected - correctOperations;
  const extraOperations = totalActual - matchedActualIndices.size;

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

/**
 * Validate that the comparison agent environment is properly configured
 */
export function validateComparisonAgentSetup(): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  if (!process.env.OPENAI_API_KEY) {
    errors.push('OPENAI_API_KEY environment variable is not set');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
