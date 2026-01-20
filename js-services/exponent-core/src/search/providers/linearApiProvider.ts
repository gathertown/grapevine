/**
 * Linear API search provider implementation
 * Ported from @exponent/task-extraction/src/search/providers/linearApiProvider.ts
 */

import { LinearTaskResultSchema, type LinearTaskResult } from '../types';
import type { LinearTaskSearchOptions, LinearTaskSearchProvider } from '../provider';
import { createLogger } from '@corporate-context/backend-common';
const logger = createLogger('exponent-core');

const LINEAR_GRAPHQL_ENDPOINT = 'https://api.linear.app/graphql';

const SEARCH_ISSUES_QUERY = `
  query SearchIssues(
    $term: String!
    $limit: Int!
    $filter: IssueFilter
    $teamId: String
  ) {
    searchIssues(term: $term, first: $limit, filter: $filter, teamId: $teamId) {
      nodes {
        id
        identifier
        title
        url
        description
        priorityLabel
        state {
          name
        }
        assignee {
          name
        }
        team {
          id
          name
        }
        labels {
          nodes {
            name
          }
        }
      }
    }
  }
`;

interface LinearApiSearchResponse {
  data?: {
    searchIssues?: {
      nodes: IssueNode[];
    };
  };
  errors?: Array<{ message: string }>;
}

interface IssueNode {
  id: string;
  identifier: string;
  title: string;
  url: string;
  description?: string;
  priorityLabel?: string;
  state?: { name?: string | null } | null;
  assignee?: { name?: string | null } | null;
  team?: { id?: string | null; name?: string | null } | null;
  labels?: {
    nodes?: Array<{ name?: string | null } | null> | null;
  } | null;
}

export interface LinearApiSearchProviderConfig {
  linearApiKey: string;
  teamName?: string;
  teamId?: string;
}

export class LinearApiTaskSearchProvider implements LinearTaskSearchProvider {
  readonly name = 'linear-api' as const;

  private readonly apiKey: string;
  private readonly teamName?: string;
  private readonly teamId?: string;

  constructor(config: LinearApiSearchProviderConfig) {
    this.apiKey = config.linearApiKey;
    this.teamName = config.teamName;
    this.teamId = config.teamId;
  }

  async search(query: string, options: LinearTaskSearchOptions = {}): Promise<LinearTaskResult[]> {
    const limit =
      typeof options.limit === 'number' && options.limit > 0 ? Math.min(options.limit, 100) : 20;

    const filter = this.buildFilter();

    logger.debug('[LinearAPI Provider] Starting search', {
      query,
      limit,
      teamId: this.teamId,
      teamName: this.teamName,
    });

    const response = await fetch(LINEAR_GRAPHQL_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: this.buildAuthorizationHeader(),
      },
      body: JSON.stringify({
        query: SEARCH_ISSUES_QUERY,
        variables: this.buildVariables(query, limit, filter),
      }),
    });

    this.logRateLimitHeaders(response);

    if (!response.ok) {
      const text = await response.text();
      logger.error('[LinearSearch:LinearAPI] Request failed', {
        query,
        limit,
        teamId: this.teamId,
        teamName: this.teamName,
        status: response.status,
        statusText: response.statusText,
        bodyPreview: text.slice(0, 500),
      });
      throw new Error(`Linear API search failed with status ${response.status}: ${text}`);
    }

    const json = (await response.json()) as LinearApiSearchResponse;
    if (json.errors && json.errors.length > 0) {
      logger.error('[LinearSearch:LinearAPI] GraphQL errors returned', {
        query,
        limit,
        teamId: this.teamId,
        teamName: this.teamName,
        errors: json.errors,
      });
      throw new Error(
        `Linear API search returned errors: ${json.errors.map((err) => err.message).join('; ')}`
      );
    }

    const nodes = json.data?.searchIssues?.nodes ?? [];
    const rawResults = nodes
      .map((node) => {
        try {
          return LinearTaskResultSchema.parse({
            issue_id: node.id,
            issue_title: node.title || node.identifier,
            issue_url: node.url,
            team_id: node.team?.id ?? undefined,
            team_name: node.team?.name ?? this.teamName,
            status: node.state?.name ?? undefined,
            priority: node.priorityLabel ?? undefined,
            assignee: node.assignee?.name ?? undefined,
            labels:
              node.labels?.nodes
                ?.map((label) => label?.name)
                .filter((name): name is string => Boolean(name)) ?? undefined,
            score: undefined,
            description: node.description ?? undefined,
          });
        } catch (error) {
          logger.warn('Failed to normalize Linear API search result', {
            error,
            node,
          });
          return null;
        }
      })
      .filter((item): item is LinearTaskResult => item !== null && item !== undefined);

    const results = this.filterByTeamScope(rawResults);

    this.logResults({ query, limit }, results, rawResults.length);

    return results;
  }

  async close(): Promise<void> {
    // No persistent resources to release for direct API calls.
  }

  private buildVariables(
    term: string,
    limit: number,
    filter: Record<string, unknown> | null
  ): Record<string, unknown> {
    const variables: Record<string, unknown> = {
      term,
      limit,
    };

    if (filter && Object.keys(filter).length > 0) {
      variables.filter = filter;
    }

    if (this.teamId) {
      variables.teamId = this.teamId;
    }

    return variables;
  }

  private buildAuthorizationHeader(): string {
    const trimmed = this.apiKey.trim();
    if (trimmed.toLowerCase().startsWith('bearer ')) {
      return trimmed;
    }

    // Linear personal API keys and workspace keys typically start with lin_api_ or pat_
    if (trimmed.startsWith('lin_api_') || trimmed.startsWith('pat_')) {
      return trimmed;
    }

    // Fallback for OAuth-style tokens where "Bearer" is expected
    return `Bearer ${trimmed}`;
  }

  private buildFilter(): Record<string, unknown> | null {
    if (this.teamId) {
      return {
        team: { id: { eq: this.teamId } },
      };
    }

    if (this.teamName) {
      return {
        team: { name: { eq: this.teamName } },
      };
    }

    return null;
  }

  private logRateLimitHeaders(response: globalThis.Response): void {
    const headers = response.headers;
    const remaining = headers.get('x-ratelimit-remaining') ?? headers.get('ratelimit-remaining');
    const limit = headers.get('x-ratelimit-limit') ?? headers.get('ratelimit-limit');
    const reset = headers.get('x-ratelimit-reset') ?? headers.get('ratelimit-reset');

    if (remaining || limit) {
      logger.debug('[LinearSearch] Rate limit status', {
        limit,
        remaining,
        reset,
      });
    }
  }

  private filterByTeamScope(results: LinearTaskResult[]): LinearTaskResult[] {
    if (!this.teamId && !this.teamName) {
      return results;
    }

    const normalizedTeamName = this.teamName?.trim().toLowerCase();

    const filtered = results.filter((result) => {
      if (this.teamId && result.team_id) {
        return result.team_id === this.teamId;
      }

      if (normalizedTeamName && result.team_name) {
        return result.team_name.trim().toLowerCase() === normalizedTeamName;
      }

      // If we expected a teamId but Linear did not return it, drop the result.
      return !this.teamId;
    });

    if (filtered.length !== results.length) {
      logger.debug('[LinearAPI Provider] Filtered search results by team scope', {
        requestedTeamId: this.teamId,
        requestedTeamName: this.teamName,
        droppedResults: results.length - filtered.length,
      });
    }

    return filtered;
  }

  private logResults(
    _context: { query: string; limit: number },
    results: LinearTaskResult[],
    rawCount: number
  ): void {
    const sample = results.slice(0, 5).map((result) => ({
      issueId: result.issue_id,
      title: result.issue_title,
      url: result.issue_url,
      team: result.team_name,
      status: result.status,
      score: result.score,
    }));

    logger.debug('[LinearAPI Provider] Search results', {
      returned: results.length,
      filteredFrom: rawCount,
      sample,
    });
  }
}
