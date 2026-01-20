/**
 * Linear task search provider abstraction
 * Ported from @exponent/task-extraction/src/search/provider.ts
 */

import type { LinearTaskResult } from './types';
import { LinearApiTaskSearchProvider } from './providers/linearApiProvider';
import { GrapevineLinearTaskSearchProvider } from './providers/grapevineProvider';
import { createGrapevineMcpServer } from '@corporate-context/backend-common';

export type LinearTaskSearchProviderName = 'grapevine' | 'linear-api';

export interface LinearTaskSearchOptions {
  limit?: number;
}

export interface LinearTaskSearchProvider {
  readonly name: LinearTaskSearchProviderName;
  search(query: string, options?: LinearTaskSearchOptions): Promise<LinearTaskResult[]>;
  close(): Promise<void>;
}

export interface CreateLinearTaskSearchProviderParams {
  provider?: LinearTaskSearchProviderName;
  teamName: string;
  teamId?: string;
  linearApiKey: string;
  grapevineApiKey?: string;
  grapevineMcpUrl?: string;
}

export async function createLinearTaskSearchProvider(
  params: CreateLinearTaskSearchProviderParams
): Promise<LinearTaskSearchProvider> {
  const providerName = params.provider ?? 'linear-api';

  switch (providerName) {
    case 'linear-api':
      return new LinearApiTaskSearchProvider({
        linearApiKey: params.linearApiKey,
        teamName: params.teamName,
        teamId: params.teamId,
      });
    case 'grapevine': {
      if (!params.grapevineApiKey || !params.grapevineMcpUrl) {
        throw new Error('Grapevine API key and MCP URL are required for Grapevine search provider');
      }

      // Create MCP server connection for Grapevine search
      const grapevineMcp = await createGrapevineMcpServer({
        jwtToken: params.grapevineApiKey,
        mcpUrl: params.grapevineMcpUrl,
        tenantId: '', // Not used for search, only for document fetching
      });

      return new GrapevineLinearTaskSearchProvider({
        grapevineMcp,
        teamName: params.teamName,
      });
    }
    default:
      throw new Error(`Unsupported Linear search provider: ${providerName}`);
  }
}
