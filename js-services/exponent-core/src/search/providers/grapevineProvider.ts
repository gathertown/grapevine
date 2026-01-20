import type { MCPServerStdio } from '@openai/agents';
import { LinearTaskResultSchema, type LinearTaskResult } from '../types';
import type { LinearTaskSearchOptions, LinearTaskSearchProvider } from '../provider';
import { createLogger } from '@corporate-context/backend-common';

const logger = createLogger('exponent-core');
const RAW_RESPONSE_LOG_LIMIT = 4096;

interface GrapevineKeywordSearchResult {
  results: Array<{
    document_id: string;
    score: number;
    metadata: {
      issue_id?: string;
      issue_title?: string;
      issue_url?: string;
      team_name?: string;
      status?: string;
      priority?: string;
      assignee?: string;
      labels?: string[];
      description?: string;
    };
    snippets?: Array<{ field: string; text: string }>;
  }>;
  count: number;
}

export interface GrapevineSearchProviderConfig {
  grapevineMcp: MCPServerStdio;
  teamName: string;
}

export class GrapevineLinearTaskSearchProvider implements LinearTaskSearchProvider {
  readonly name = 'grapevine' as const;

  private readonly grapevineMcp: MCPServerStdio;
  private readonly teamName: string;

  constructor(config: GrapevineSearchProviderConfig) {
    this.grapevineMcp = config.grapevineMcp;
    this.teamName = config.teamName;
  }

  async search(query: string, options: LinearTaskSearchOptions = {}): Promise<LinearTaskResult[]> {
    const limit =
      typeof options.limit === 'number' && options.limit > 0 ? Math.min(options.limit, 100) : 20;

    const filters: Record<string, unknown> = {
      sources: ['linear'],
      provenance: this.teamName,
      date_from: null,
      date_to: null,
      document_id: null,
    };

    logger.debug('[Grapevine Provider] Starting search', {
      query,
      limit,
      teamName: this.teamName,
    });

    try {
      const response = await this.grapevineMcp.callTool('keyword_search', {
        query,
        filters,
        limit,
        advanced: true,
      });

      const parsed = this.parseResponse(response, {
        query,
        limit,
        filters,
      });

      this.logResults({ query, limit }, parsed);

      return parsed;
    } catch (error) {
      logger.error('Error searching Linear tasks via Grapevine', {
        error,
      });
      throw new Error(
        `Failed to search Linear tasks via Grapevine: ${
          error instanceof Error ? error.message : 'Unknown error'
        }`
      );
    }
  }

  async close(): Promise<void> {
    await this.grapevineMcp.close();
  }

  private parseResponse(
    response: unknown,
    context: { query: string; limit: number; filters: Record<string, unknown> }
  ): LinearTaskResult[] {
    let payload: unknown;

    if (Array.isArray(response) && response.length > 0) {
      let parsed = false;
      const rawChunks: string[] = [];
      for (const item of response) {
        if (item && typeof item === 'object' && 'text' in item) {
          const text = String((item as { text?: unknown }).text ?? '').trim();
          if (!text) continue;

          const isTruncated = text.length > RAW_RESPONSE_LOG_LIMIT;
          const loggedResponse = isTruncated
            ? `${text.slice(0, RAW_RESPONSE_LOG_LIMIT)}…[truncated ${
                text.length - RAW_RESPONSE_LOG_LIMIT
              } chars]`
            : text;
          rawChunks.push(loggedResponse);

          if (/^Input validation failed/i.test(text)) {
            logger.error('Grapevine keyword_search validation error', {
              query: context.query,
              limit: context.limit,
              filters: context.filters,
              response: loggedResponse,
              responseLength: text.length,
              responseTruncated: isTruncated,
            });
            throw new Error(`Grapevine keyword_search validation error: ${text}`);
          }

          try {
            payload = JSON.parse(text);
            parsed = true;
            break;
          } catch {
            logger.warn('Skipping non-JSON Grapevine MCP response chunk', {
              query: context.query,
              limit: context.limit,
              filters: context.filters,
              rawResponse: loggedResponse,
              responseLength: text.length,
              responseTruncated: isTruncated,
            });
          }
        }
      }

      if (!parsed) {
        logger.error('No JSON payload found in Grapevine MCP response', {
          query: context.query,
          limit: context.limit,
          filters: context.filters,
          rawChunks,
          rawChunkCount: rawChunks.length,
        });
        return [];
      }
    } else if (typeof response === 'object' && response !== null) {
      payload = response;
    } else {
      logger.error('Unexpected Grapevine response format', {
        query: context.query,
        limit: context.limit,
        filters: context.filters,
        response,
      });
      return [];
    }

    return this.transformResults(payload);
  }

  private transformResults(payload: unknown): LinearTaskResult[] {
    if (!payload || typeof payload !== 'object') {
      logger.warn('Invalid Grapevine response: not an object');
      return [];
    }

    const result = payload as GrapevineKeywordSearchResult;
    if (!Array.isArray(result.results)) {
      logger.warn('Invalid Grapevine response: missing results array');
      return [];
    }

    return result.results
      .map((item) => {
        const metadata = item.metadata ?? {};
        const snippets = item.snippets ?? [];

        const descriptionSnippets = snippets
          .filter((snippet) => snippet.field === 'content')
          .map((snippet) => snippet.text)
          .join('\n\n');

        try {
          return LinearTaskResultSchema.parse({
            issue_id: metadata.issue_id ?? item.document_id,
            issue_title: metadata.issue_title ?? 'Untitled',
            issue_url: metadata.issue_url,
            team_name: metadata.team_name ?? this.teamName,
            status: metadata.status,
            priority: metadata.priority,
            assignee: metadata.assignee,
            labels: metadata.labels,
            score: item.score,
            description: descriptionSnippets || metadata.description,
          });
        } catch (error) {
          logger.warn('Failed to normalize Grapevine search result', {
            error,
            metadata,
            snippets,
          });
          return null;
        }
      })
      .filter((item): item is LinearTaskResult => item !== null && item !== undefined);
  }

  private logResults(
    _context: { query: string; limit: number },
    results: LinearTaskResult[]
  ): void {
    const sample = results.slice(0, 5).map((result) => ({
      issueId: result.issue_id,
      title: result.issue_title,
      url: result.issue_url,
      team: result.team_name,
      status: result.status,
      score: result.score,
    }));

    logger.debug('[Grapevine Provider] Search results', {
      returned: results.length,
      sample,
    });
  }
}
