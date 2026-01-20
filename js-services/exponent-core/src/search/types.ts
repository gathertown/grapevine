/**
 * Linear task search types
 * Ported from @exponent/task-extraction/src/search/types.ts
 */

import { z } from 'zod';

/**
 * Shared schema for Linear task search results.
 *
 * This represents the normalized structure returned by any Linear search
 * provider (Grapevine MCP, direct Linear API, etc.).
 */
export const LinearTaskResultSchema = z.object({
  issue_id: z.string(),
  issue_title: z.string(),
  issue_url: z.string().optional(),
  team_id: z.string().optional(),
  team_name: z.string().optional(),
  status: z.string().optional(),
  priority: z.string().optional(),
  assignee: z.string().optional(),
  labels: z.array(z.string()).optional(),
  score: z.number().optional(),
  description: z.string().optional(),
});

export type LinearTaskResult = z.infer<typeof LinearTaskResultSchema>;
