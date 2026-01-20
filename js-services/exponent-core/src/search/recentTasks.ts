/**
 * Recent Linear tasks for prompt grounding
 * Ported from @exponent/task-extraction/src/search/recentTasks.ts
 */

import { z } from 'zod';

const LINEAR_GRAPHQL_ENDPOINT = 'https://api.linear.app/graphql';

const TEAM_RECENT_ISSUES_QUERY = `
  query TeamRecentIssues($teamId: String!, $limit: Int!) {
    team(id: $teamId) {
      issues(
        first: $limit
        orderBy: updatedAt
      ) {
        nodes {
          id
          identifier
          title
          description
          updatedAt
          url
          priorityLabel
          assignee {
            name
          }
          state {
            name
          }
        }
      }
    }
  }
`;

const IssueNodeSchema = z.object({
  id: z.string(),
  identifier: z.string(),
  title: z.string(),
  description: z.string().nullable().optional(),
  updatedAt: z.string(),
  url: z.string().nullable().optional(),
  priorityLabel: z.string().nullable().optional(),
  assignee: z
    .object({
      name: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
  state: z
    .object({
      name: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
});

const TeamRecentIssuesResponseSchema = z.object({
  data: z
    .object({
      team: z
        .object({
          issues: z.object({
            nodes: z.array(IssueNodeSchema),
          }),
        })
        .nullable(),
    })
    .nullable(),
  errors: z
    .array(
      z.object({
        message: z.string(),
      })
    )
    .optional(),
});

export interface RecentLinearTask {
  id: string;
  identifier: string;
  title: string;
  description?: string;
  updatedAt: string;
  url?: string;
  priority?: string;
  assignee?: string;
  state?: string;
}

export interface FetchRecentLinearTasksParams {
  apiKey: string;
  teamId: string;
  limit?: number;
}

export async function fetchRecentLinearTasks(
  params: FetchRecentLinearTasksParams
): Promise<RecentLinearTask[]> {
  const limit =
    typeof params.limit === 'number' && params.limit > 0 ? Math.min(params.limit, 100) : 20;

  const response = await fetch(LINEAR_GRAPHQL_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: buildAuthorizationHeader(params.apiKey),
    },
    body: JSON.stringify({
      query: TEAM_RECENT_ISSUES_QUERY,
      variables: {
        teamId: params.teamId,
        limit,
      },
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to fetch recent Linear tasks (status ${response.status}): ${text}`);
  }

  const json = await response.json();
  const parsed = TeamRecentIssuesResponseSchema.safeParse(json);

  if (!parsed.success) {
    throw new Error(`Failed to parse Linear API response for recent tasks: ${parsed.error}`);
  }

  if (parsed.data.errors && parsed.data.errors.length > 0) {
    throw new Error(
      `Linear API returned errors when fetching recent tasks: ${parsed.data.errors
        .map((err) => err.message)
        .join('; ')}`
    );
  }

  const nodes = parsed.data.data?.team?.issues.nodes ?? [];

  return nodes.map((node) => ({
    id: node.id,
    identifier: node.identifier,
    title: node.title,
    description: node.description ?? undefined,
    updatedAt: node.updatedAt,
    url: node.url ?? undefined,
    priority: node.priorityLabel ?? undefined,
    assignee: node.assignee?.name ?? undefined,
    state: node.state?.name ?? undefined,
  }));
}

function buildAuthorizationHeader(apiKey: string): string {
  const trimmed = apiKey.trim();
  if (trimmed.toLowerCase().startsWith('bearer ')) {
    return trimmed;
  }

  if (trimmed.startsWith('lin_api_') || trimmed.startsWith('pat_')) {
    return trimmed;
  }

  return `Bearer ${trimmed}`;
}

export function formatRecentLinearTasksForPrompt(
  tasks: RecentLinearTask[],
  options: { maxDescriptionLength?: number } = {}
): string {
  if (tasks.length === 0) {
    return 'No recent Linear tasks found.';
  }

  const maxDescriptionLength =
    options.maxDescriptionLength && options.maxDescriptionLength > 0
      ? options.maxDescriptionLength
      : 240;

  return tasks
    .map((task, index) => {
      const lines = [
        `${index + 1}. ${task.identifier} — ${task.title}`,
        `   Updated: ${task.updatedAt}`,
      ];

      if (task.state) {
        lines.push(`   State: ${task.state}`);
      }
      if (task.assignee) {
        lines.push(`   Assignee: ${task.assignee}`);
      }
      if (task.priority) {
        lines.push(`   Priority: ${task.priority}`);
      }
      if (task.description) {
        const normalized = task.description.replace(/\s+/g, ' ').trim();
        if (normalized.length > 0) {
          const trimmed =
            normalized.length > maxDescriptionLength
              ? `${normalized.slice(0, maxDescriptionLength).trimEnd()}…`
              : normalized;
          lines.push(`   Summary: ${trimmed}`);
        }
      }
      if (task.url) {
        lines.push(`   URL: ${task.url}`);
      }

      return lines.join('\n');
    })
    .join('\n');
}

export interface BuildRecentTasksPromptSectionParams {
  apiKey: string;
  teamId: string;
  limit?: number;
  maxDescriptionLength?: number;
  header?: string;
}

export async function buildRecentTasksPromptSection(
  params: BuildRecentTasksPromptSectionParams
): Promise<string | null> {
  try {
    const tasks = await fetchRecentLinearTasks({
      apiKey: params.apiKey,
      teamId: params.teamId,
      limit: params.limit,
    });

    if (tasks.length === 0) {
      return null;
    }

    const formatted = formatRecentLinearTasksForPrompt(tasks, {
      maxDescriptionLength: params.maxDescriptionLength,
    });

    const header =
      params.header ?? `RECENT LINEAR TASKS (latest ${Math.min(tasks.length, params.limit ?? 20)})`;

    return `** ${header} **
${formatted}

Use these existing tasks to ground your reasoning before deciding on new operations.`;
  } catch (error) {
    console.warn('[recentTasks] Failed to build recent tasks prompt section', error);
    return null;
  }
}
