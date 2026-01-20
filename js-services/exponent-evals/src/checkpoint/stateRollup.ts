/**
 * State Rollup
 *
 * Manages state accumulation across checkpoints.
 * Applies operations to a linear state to compute the resulting state.
 */

import type { SimpleLinearIssue, LinearOperation } from './types';

/**
 * Generate a unique ID for new issues
 */
function generateIssueId(): string {
  return `issue-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Apply a single operation to the linear state
 *
 * @param state - Current state (will be mutated)
 * @param operation - Operation to apply
 * @returns Updated state
 */
export function applyOperation(
  state: SimpleLinearIssue[],
  operation: LinearOperation
): SimpleLinearIssue[] {
  switch (operation.action) {
    case 'CREATE': {
      if (!operation.createData) {
        return state;
      }

      const newIssue: SimpleLinearIssue = {
        id: operation.createData.issueId || generateIssueId(),
        title: operation.createData.title,
        description: operation.createData.description,
        assigneeId: operation.createData.assigneeId,
      };

      return [...state, newIssue];
    }

    case 'UPDATE': {
      if (!operation.updateData?.issueId) {
        return state;
      }

      const issueId = operation.updateData.issueId;
      const existingIdx = state.findIndex((issue) => issue.id === issueId);

      if (existingIdx === -1) {
        // Issue not found, no change
        return state;
      }

      const existingIssue = state[existingIdx];
      if (!existingIssue) {
        return state;
      }

      // Create updated issue
      const updatedIssue: SimpleLinearIssue = {
        ...existingIssue,
      };

      // Apply description update
      if (operation.updateData.description) {
        updatedIssue.description = operation.updateData.description;
      } else if (operation.updateData.descriptionAppend) {
        const currentDesc = existingIssue.description || '';
        updatedIssue.description = currentDesc
          ? `${currentDesc}\n\n${operation.updateData.descriptionAppend}`
          : operation.updateData.descriptionAppend;
      }

      // Replace in state
      const newState = [...state];
      newState[existingIdx] = updatedIssue;
      return newState;
    }

    case 'SKIP':
    case 'REQUEST_CLARIFICATION':
      // No state change for these actions
      return state;

    default:
      return state;
  }
}

/**
 * Apply multiple operations to the linear state
 *
 * @param initialState - Starting state
 * @param operations - Operations to apply (in order)
 * @returns Resulting state after all operations
 */
export function applyOperations(
  initialState: SimpleLinearIssue[],
  operations: LinearOperation[]
): SimpleLinearIssue[] {
  let state = [...initialState];

  for (const operation of operations) {
    state = applyOperation(state, operation);
  }

  return state;
}

/**
 * Count operations by type
 */
export function countOperations(operations: LinearOperation[]): {
  create: number;
  update: number;
  skip: number;
  requestClarification: number;
} {
  const counts = {
    create: 0,
    update: 0,
    skip: 0,
    requestClarification: 0,
  };

  for (const op of operations) {
    switch (op.action) {
      case 'CREATE':
        counts.create++;
        break;
      case 'UPDATE':
        counts.update++;
        break;
      case 'SKIP':
        counts.skip++;
        break;
      case 'REQUEST_CLARIFICATION':
        counts.requestClarification++;
        break;
    }
  }

  return counts;
}
