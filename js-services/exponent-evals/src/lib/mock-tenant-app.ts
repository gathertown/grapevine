/**
 * Mock TenantSlackApp for Evaluation
 *
 * Provides the minimal interface that TriageAgentStrategy expects,
 * using direct MCP API calls with API key authentication.
 *
 * This allows us to run TriageAgentStrategy in eval mode without
 * needing the full Slack bot infrastructure.
 */

import { callMCPWithApiKey, type FileAttachment } from './mcp-client';

interface Message {
  role: string;
  content: string;
  files?: FileAttachment[];
}

interface BackendRequestOptions {
  nonBillable?: boolean;
  outputFormat?: 'slack' | 'markdown';
}

interface GeneratedAnswer {
  answer: string;
  response_id?: string;
}

/**
 * Mock TenantSlackApp that implements the interface TriageAgentStrategy expects
 *
 * Instead of going through JWT generation and the full Slack bot flow,
 * this directly calls MCP with an API key.
 */
export class MockTenantSlackApp {
  constructor(
    public tenantId: string,
    private mcpApiKey: string,
    private mcpBaseUrl: string
  ) {}

  /**
   * Create triage runners - the only method TriageAgentStrategy calls
   *
   * Returns an object with a `run` method that executes MCP tool calls
   * and a `prepared` property for interface compatibility.
   */
  async createTriageRunners(
    message: Message,
    _userId: string,
    options: BackendRequestOptions = {}
  ): Promise<{
    prepared: { message: Message; options: BackendRequestOptions };
    run: (
      toolName: string,
      overrides?: Partial<BackendRequestOptions>
    ) => Promise<GeneratedAnswer | null>;
  }> {
    return {
      // Include prepared property to match TenantSlackApp interface
      prepared: { message, options },
      run: async (toolName: string, overrides: Partial<BackendRequestOptions> = {}) => {
        const finalOptions = { ...options, ...overrides };
        const outputFormat = finalOptions.outputFormat || 'markdown';

        try {
          const response = await callMCPWithApiKey(
            this.mcpBaseUrl,
            this.mcpApiKey,
            this.tenantId,
            message.content,
            message.files || [],
            toolName,
            outputFormat
          );

          return {
            answer: response.answer,
            response_id: response.response_id,
          };
        } catch (error) {
          console.error(`[MockTenantApp] MCP call failed for tool ${toolName}:`, error);
          console.error(
            '[MockTenantApp] Error details:',
            error instanceof Error ? error.message : error
          );
          console.error(
            '[MockTenantApp] Error stack:',
            error instanceof Error ? error.stack : 'No stack'
          );
          return null;
        }
      },
    };
  }

  /**
   * Call get_document via MCP with API key auth
   *
   * This method is called directly by TriageAgentStrategy's get_document tool.
   * In production, callGetDocumentViaMCP uses JWT auth. Here we use API key.
   */
  async callGetDocument(documentId: string): Promise<unknown> {
    try {
      const response = await callMCPWithApiKey(
        this.mcpBaseUrl,
        this.mcpApiKey,
        this.tenantId,
        '', // get_document doesn't use query
        [],
        'get_document',
        'markdown',
        { document_id: documentId } // Pass document_id as additional arg
      );

      return response.answer ? JSON.parse(response.answer) : null;
    } catch (error) {
      console.error(`[MockTenantApp.callGetDocument] MCP call failed for get_document:`, error);
      console.error(
        '[MockTenantApp.callGetDocument] Error details:',
        error instanceof Error ? error.message : error
      );
      return null;
    }
  }
}
