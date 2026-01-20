/**
 * AI-powered operation grading system using GPT-4o
 *
 * This module provides automated grading functionality for evaluation results,
 * adapted from the original Exponent grader for Linear operations.
 */

import OpenAI from 'openai';
import type { LinearOperation } from './comparison';

// Grader configuration constants
export const GRADER_VERSION = 'v2';
export const GRADER_MODEL = 'gpt-4o';

// Grading rubric for operations
const OPERATION_RUBRIC = `
1/5 - The operation is completely wrong (wrong action type, wrong issue, or entirely incorrect task)
2/5 - The operation has major issues (right action but wrong target, or missing critical information)
3/5 - The operation is partially correct (right action and target, but title/description has significant gaps)
4/5 - The operation is mostly correct with minor issues (small wording differences, minor missing details)
5/5 - The operation is accurate, complete, and matches the expected output
`;

export interface GraderConfig {
  model: string;
  version: string;
  rubric: string;
  temperature: number;
}

export interface LLMGradeResult {
  score: number; // 1-5, or -1 if grading failed
  reasoning: string;
  grader_info: string;
}

/** Default grader configuration */
export const DEFAULT_GRADER_CONFIG: GraderConfig = {
  model: GRADER_MODEL,
  version: GRADER_VERSION,
  rubric: OPERATION_RUBRIC,
  temperature: 0.0,
};

/**
 * Format an operation for display in grading prompt
 */
function formatOperationForGrading(op: LinearOperation): string {
  let result = `Action: ${op.action}`;

  if (op.action === 'CREATE' && op.createData) {
    result += `\n  Title: "${op.createData.title}"`;
    if (op.createData.description) {
      const desc = op.createData.description;
      result += `\n  Description: "${desc.substring(0, 200)}${desc.length > 200 ? '...' : ''}"`;
    }
  } else if (op.action === 'UPDATE' && op.updateData) {
    result += `\n  Issue ID: ${op.updateData.issueId}`;
    if (op.updateData.descriptionAppend) {
      const desc = op.updateData.descriptionAppend;
      result += `\n  Description Append: "${desc.substring(0, 200)}${desc.length > 200 ? '...' : ''}"`;
    }
  } else if (op.action === 'SKIP' && op.skipData) {
    result += `\n  Title: "${op.skipData.title}"`;
    if (op.skipData.reason) {
      result += `\n  Reason: "${op.skipData.reason}"`;
    }
  }

  if (op.confidence !== undefined) {
    result += `\n  Confidence: ${op.confidence}%`;
  }

  if (op.reasoning) {
    const reasoning = op.reasoning;
    result += `\n  Reasoning: "${reasoning.substring(0, 150)}${reasoning.length > 150 ? '...' : ''}"`;
  }

  return result;
}

/**
 * Grade a generated operation against an expected operation using GPT-4o
 */
export async function gradeOperation(
  actualOp: LinearOperation,
  expectedOp: LinearOperation,
  context?: string,
  config: GraderConfig = DEFAULT_GRADER_CONFIG
): Promise<LLMGradeResult> {
  const client = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY,
  });

  const gradingPrompt = `
You are an expert evaluator for Linear task operations. Grade the generated operation against the expected operation.

RUBRIC: ${config.rubric}

${context ? `CONTEXT (source document): ${context.substring(0, 500)}${context.length > 500 ? '...' : ''}\n` : ''}

EXPECTED OPERATION:
${formatOperationForGrading(expectedOp)}

ACTUAL (GENERATED) OPERATION:
${formatOperationForGrading(actualOp)}

Evaluation criteria:

1. **Action Type Match:**
   - Is the action type correct (CREATE, UPDATE, or SKIP)?
   - This is critical - wrong action type is a major error.

2. **Target Accuracy:**
   - For CREATE: Is the title capturing the same task/work?
   - For UPDATE: Is the correct issue being updated?
   - For SKIP: Is the correct issue being skipped with valid reasoning?

3. **Content Quality:**
   - Is the title/description accurate and complete?
   - Are key details captured?
   - Is the wording appropriate (not too verbose, not too terse)?

4. **Semantic Equivalence:**
   - Even if wording differs, does the operation represent the same intent?
   - "Build eval harness" and "Create evaluation framework" are semantically similar.

Assign a score based on the rubric. Output ONLY a JSON object:
{
    "score": <integer from 1 to 5>,
    "reasoning": "<brief explanation of why you gave this score>"
}

Only output the JSON object, no additional text.
`;

  try {
    const response = await client.chat.completions.create({
      model: config.model,
      messages: [
        {
          role: 'system',
          content:
            'You are an expert evaluator for task management operations. Grade operations based on accuracy, completeness, and semantic equivalence.',
        },
        { role: 'user', content: gradingPrompt },
      ],
      temperature: config.temperature,
    });

    const responseText = response.choices[0]?.message?.content?.trim() || '';

    // Parse the JSON response
    try {
      // Strip markdown code blocks if present
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

      const gradingResult = JSON.parse(cleanedText);
      const score = gradingResult.score;
      const reasoning = gradingResult.reasoning || '';

      // Validate score is in range
      if (!Number.isInteger(score) || score < 1 || score > 5) {
        console.warn(`Invalid score returned: ${score}. Setting to -1.`);
        return {
          score: -1,
          reasoning: `Invalid score: ${score}`,
          grader_info: `Graded with ${config.model} using rubric ${config.version}`,
        };
      }

      return {
        score,
        reasoning,
        grader_info: `Graded with ${config.model} using rubric ${config.version}`,
      };
    } catch (parseError) {
      console.warn(`Failed to parse grading response as JSON: ${responseText.slice(0, 200)}...`);
      return {
        score: -1,
        reasoning: `JSON parse error: ${parseError}`,
        grader_info: `Graded with ${config.model} using rubric ${config.version}`,
      };
    }
  } catch (error) {
    console.error(`Error during grading: ${error}`);
    return {
      score: -1,
      reasoning: `Grading error: ${error}`,
      grader_info: `Graded with ${config.model} using rubric ${config.version}`,
    };
  }
}

/**
 * Grade multiple operations (grades each pair and returns aggregated results)
 */
export async function gradeOperations(
  actualOps: LinearOperation[],
  expectedOps: LinearOperation[],
  context?: string,
  config: GraderConfig = DEFAULT_GRADER_CONFIG
): Promise<{
  grades: LLMGradeResult[];
  averageScore: number;
  grader_info: string;
}> {
  const grades: LLMGradeResult[] = [];

  // Grade matched pairs (up to the shorter list length)
  const pairCount = Math.min(actualOps.length, expectedOps.length);

  for (let i = 0; i < pairCount; i++) {
    const actualOp = actualOps[i];
    const expectedOp = expectedOps[i];
    if (actualOp && expectedOp) {
      const grade = await gradeOperation(actualOp, expectedOp, context, config);
      grades.push(grade);
    }
  }

  // Calculate average (excluding failed grades with -1)
  const validGrades = grades.filter((g) => g.score > 0);
  const averageScore =
    validGrades.length > 0
      ? validGrades.reduce((sum, g) => sum + g.score, 0) / validGrades.length
      : 0;

  return {
    grades,
    averageScore,
    grader_info: `Graded with ${config.model} using rubric ${config.version}`,
  };
}

/**
 * Validate that the grading environment is properly configured
 */
export function validateGraderSetup(): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!process.env.OPENAI_API_KEY) {
    errors.push('OPENAI_API_KEY environment variable is not set');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
