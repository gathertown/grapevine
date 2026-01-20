/**
 * Utility functions for deduplicating Linear operations
 * Ported from @exponent/task-extraction/src/utils/deduplication.ts
 *
 * Ensures that each issueId appears at most once in the operations array
 */

import type { LinearOperation } from '../types';
import { TaskAction } from '../types';

/**
 * Get the issueId from a Linear operation (if present)
 */
function getIssueId(operation: LinearOperation): string | null {
  if (operation.action === TaskAction.UPDATE && operation.updateData?.issueId) {
    return operation.updateData.issueId;
  }
  if (operation.action === TaskAction.SKIP && operation.skipData?.issueId) {
    return operation.skipData.issueId;
  }
  return null;
}

/**
 * Deduplicate operations to ensure each issueId appears at most once
 *
 * Strategy:
 * - CREATE operations are never deduplicated (they create new issues)
 * - For UPDATE/SKIP operations on the same issueId:
 *   - If any operation is UPDATE, keep the UPDATE (merge info if multiple UPDATEs)
 *   - Otherwise, keep the first SKIP
 *
 * @param operations - Array of operations to deduplicate
 * @returns Deduplicated array with at most one operation per issueId
 */
export function deduplicateOperations(operations: LinearOperation[]): LinearOperation[] {
  const deduplicated: LinearOperation[] = [];
  const seenIssueIds = new Map<string, LinearOperation>();

  for (const op of operations) {
    // CREATE operations always pass through (they don't have issueIds to conflict with)
    if (op.action === TaskAction.CREATE) {
      deduplicated.push(op);
      continue;
    }

    const issueId = getIssueId(op);

    // If no issueId (e.g., SKIP with null issueId), always include it
    if (!issueId) {
      deduplicated.push(op);
      continue;
    }

    // Check if we've seen this issueId before
    const existing = seenIssueIds.get(issueId);

    if (!existing) {
      // First time seeing this issueId - keep it
      seenIssueIds.set(issueId, op);
      deduplicated.push(op);
    } else if (op.action === TaskAction.UPDATE) {
      // If new operation is UPDATE and existing is SKIP, replace SKIP with UPDATE
      if (existing.action === TaskAction.SKIP) {
        const index = deduplicated.indexOf(existing);
        deduplicated[index] = op;
        seenIssueIds.set(issueId, op);
      }
      // If both are UPDATEs, merge them (keep the first one, but note in reasoning)
      else if (existing.action === TaskAction.UPDATE) {
        // Merge reasoning to note multiple extracted tasks
        const mergedReasoning = `${existing.reasoning}\n\nNOTE: Multiple operations were detected for this issue and have been consolidated.`;
        existing.reasoning = mergedReasoning;
      }
    }
    // If existing is UPDATE and new is SKIP, ignore the new SKIP
    // If both are SKIP, keep the first one
  }

  return deduplicated;
}

/**
 * Validate that no issueId appears more than once in the operations
 *
 * @param operations - Array of operations to validate
 * @returns Object with validation result and list of duplicate issueIds
 */
export function validateUniqueIssueIds(operations: LinearOperation[]): {
  isValid: boolean;
  duplicateIssueIds: string[];
  duplicateCount: number;
} {
  const issueIdCounts = new Map<string, number>();

  for (const op of operations) {
    const issueId = getIssueId(op);
    if (issueId) {
      issueIdCounts.set(issueId, (issueIdCounts.get(issueId) || 0) + 1);
    }
  }

  const duplicateIssueIds: string[] = [];
  let duplicateCount = 0;

  for (const [issueId, count] of issueIdCounts.entries()) {
    if (count > 1) {
      duplicateIssueIds.push(issueId);
      duplicateCount += count - 1; // Count extra occurrences
    }
  }

  return {
    isValid: duplicateIssueIds.length === 0,
    duplicateIssueIds,
    duplicateCount,
  };
}
