/**
 * Linear task lookup MCP tool
 * Ported from @exponent/task-extraction/src/mcp/linearTaskLookup.ts
 */

import { tool } from '@openai/agents';
import { z } from 'zod';
import type { LinearTaskSearchProvider, LinearTaskSearchOptions } from '../search/provider';
import type { LinearTaskResult } from '../search/types';
import type { SimpleLinearIssue } from '../SingleAgentStrategy';
import { createLogger } from '@corporate-context/backend-common';
const logger = createLogger('exponent-core');

export interface LinearTaskLookupConfig {
  provider: LinearTaskSearchProvider;
  teamName?: string;
}

export async function searchLinearTasks(
  config: LinearTaskLookupConfig,
  query: string,
  limit = 20
): Promise<LinearTaskResult[]> {
  const options: LinearTaskSearchOptions = { limit };
  return config.provider.search(query, options);
}

export function createLinearTaskLookupTool(config: LinearTaskLookupConfig) {
  return tool({
    name: 'linear_task_lookup',
    description: `Search for Linear tasks using the configured provider. This tool is pre-scoped to your Linear workspace${
      config.teamName ? ` (team: ${config.teamName})` : ''
    }.

Supports advanced query syntax when available:
- Field filters like status:open, priority:high, assignee:alice
- Boolean operators (AND, OR, NOT)
- Exact phrases ("customer feedback")
- Wildcards (config*)
- Grouping: (error OR warning) AND api

Examples:
- "status:open priority:high" - Open high-priority tasks
- "assignee:alice status:in_progress" - Alice's in-progress tasks
- "authentication AND security" - Tasks about auth and security
- "\\"payment processing\\"" - Exact phrase match`,
    parameters: z.object({
      query: z
        .string()
        .describe(
          'Search query for matching Linear issues. Supports provider-specific advanced syntax.'
        ),
      limit: z
        .number()
        .min(1)
        .max(100)
        .default(20)
        .describe('Maximum number of results to return (1-100)'),
    }),
    execute: async (args: { query: string; limit: number }) => {
      // Log at debug level since query and results may contain PII
      logger.debug('Linear task lookup', {
        provider: config.provider.name,
        team: config.teamName ?? '(not specified)',
        query: args.query,
        limit: args.limit,
      });

      const results = await searchLinearTasks(config, args.query, args.limit);

      // Log at debug level since results contain task titles and details
      logger.debug('Linear task lookup results', {
        resultCount: results.length,
        topResults: results.slice(0, 5).map((task) => ({
          issueId: task.issue_id,
          title: task.issue_title,
          status: task.status,
          priority: task.priority,
          team: task.team_name,
          score: task.score,
        })),
      });

      return {
        count: results.length,
        tasks: results.map((task) => ({
          id: task.issue_id,
          title: task.issue_title,
          url: task.issue_url,
          team: task.team_name,
          status: task.status,
          priority: task.priority,
          assignee: task.assignee,
          labels: task.labels,
          description_snippet: task.description,
          relevance_score: task.score,
        })),
      };
    },
  });
}

/**
 * Create a mock linear_task_lookup tool for frozen state evals.
 * Returns all frozen state issues regardless of query, simulating the tool interface
 * without requiring live Linear API access.
 */
export function createMockLinearTaskLookupTool(frozenState: SimpleLinearIssue[]) {
  return tool({
    name: 'linear_task_lookup',
    description: `Search for Linear tasks. This tool is pre-scoped to your Linear workspace.

Supports advanced query syntax when available:
- Field filters like status:open, priority:high, assignee:alice
- Boolean operators (AND, OR, NOT)
- Exact phrases ("customer feedback")
- Wildcards (config*)
- Grouping: (error OR warning) AND api

Examples:
- "status:open priority:high" - Open high-priority tasks
- "assignee:alice status:in_progress" - Alice's in-progress tasks
- "authentication AND security" - Tasks about auth and security
- "\\"payment processing\\"" - Exact phrase match`,
    parameters: z.object({
      query: z
        .string()
        .describe(
          'Search query for matching Linear issues. Supports provider-specific advanced syntax.'
        ),
      limit: z
        .number()
        .min(1)
        .max(100)
        .default(20)
        .describe('Maximum number of results to return (1-100)'),
    }),
    execute: async (args: { query: string; limit: number }) => {
      logger.debug('Mock linear task lookup (frozen state)', {
        query: args.query,
        limit: args.limit,
        frozenStateCount: frozenState.length,
      });

      // Return all frozen state issues (simple mock - no actual search filtering)
      const results = frozenState.slice(0, args.limit);

      logger.debug('Mock linear task lookup results', {
        resultCount: results.length,
      });

      return {
        count: results.length,
        tasks: results.map((issue) => ({
          id: issue.id,
          title: issue.title,
          // Handle both state (from eval-capture) and stateId (from legacy/other sources)
          status: issue.state || issue.stateId,
          priority: issue.priority,
          assignee: issue.assignee || issue.assigneeId,
          description_snippet: issue.description,
        })),
      };
    },
  });
}
