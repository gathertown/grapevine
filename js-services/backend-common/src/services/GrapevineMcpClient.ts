/**
 * Grapevine MCP Client
 *
 * Provides access to Grapevine documents via MCP protocol
 * Uses mcp-remote to connect to Grapevine MCP server
 */

import { MCPServerStdio } from '@openai/agents';
import { createLogger } from '../logger';

const logger = createLogger('grapevine-mcp');

const MCP_REMOTE_PACKAGE = 'mcp-remote@0.1.29';
const DEFAULT_ALLOWED_TOOLS = [
  'semantic_search',
  'keyword_search',
  'get_document',
  'get_document_metadata',
];

export interface GrapevineMcpClientOptions {
  jwtToken: string;
  mcpUrl: string;
  tenantId: string;
  allowedTools?: string[];
}

export interface GrapevineDocument {
  document_id: string;
  content: string;
}

/**
 * Create an MCP server connection to Grapevine
 */
export async function createGrapevineMcpServer(
  options: GrapevineMcpClientOptions
): Promise<MCPServerStdio> {
  const { jwtToken, mcpUrl, tenantId, allowedTools = DEFAULT_ALLOWED_TOOLS } = options;

  const headers = {
    Authorization: `Bearer ${jwtToken}`,
    'X-Grapevine-Tenant-Id': tenantId,
  };

  const headerArgs: string[] = [];
  for (const [key, value] of Object.entries(headers)) {
    headerArgs.push('--header', `${key}: ${value}`);
  }

  const server = new MCPServerStdio({
    command: 'npx',
    args: ['--yes', `--package=${MCP_REMOTE_PACKAGE}`, '--', 'mcp-remote', mcpUrl, ...headerArgs],
    toolFilter: {
      allowedToolNames: allowedTools,
    },
    timeout: 180000, // 3 minutes
  });

  try {
    await server.connect();
    logger.info('Connected to Grapevine MCP server', { tenantId });
  } catch (error) {
    logger.error('Failed to connect to Grapevine MCP server', {
      error: error instanceof Error ? error : new Error(String(error)),
      tenantId,
    });
    await server.close().catch(() => undefined);
    throw error;
  }

  return server;
}

/**
 * Fetch a document from Grapevine using MCP
 */
export async function fetchGrapevineDocument(
  server: MCPServerStdio,
  documentId: string
): Promise<GrapevineDocument> {
  try {
    logger.info('Fetching document from Grapevine', { documentId });

    const result = await server.callTool('get_document', {
      document_id: documentId,
    });

    // MCP tools return an array of content blocks
    if (!Array.isArray(result)) {
      throw new Error('Invalid response from get_document: expected array');
    }

    // Extract text from the first text content block
    const textBlock = result.find(
      (block: unknown) =>
        typeof block === 'object' &&
        block !== null &&
        'type' in block &&
        block.type === 'text' &&
        'text' in block
    );

    if (!textBlock || typeof textBlock !== 'object' || !('text' in textBlock)) {
      throw new Error('No text content in get_document response');
    }

    // Parse the JSON response
    const content = JSON.parse(textBlock.text as string);

    if (!content.document_id || !content.content) {
      throw new Error('Missing document_id or content in response');
    }

    return {
      document_id: content.document_id as string,
      content: content.content as string,
    };
  } catch (error) {
    logger.error('Failed to fetch document from Grapevine', {
      error: error instanceof Error ? error : new Error(String(error)),
      documentId,
    });
    throw error;
  }
}
