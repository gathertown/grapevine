/**
 * MCP Client with API Key Authentication
 *
 * Direct MCP calls using API key authentication (no JWT generation needed).
 * This is simpler and more secure for evaluation purposes.
 */

import axios from 'axios';

export interface FileAttachment {
  url: string;
  name: string;
  mimeType?: string;
}

export interface MCPResponse {
  answer: string;
  response_id?: string;
}

interface MCPJsonRpcResponse {
  jsonrpc: string;
  id: string;
  result?: {
    content?: Array<{
      type: string;
      text: string;
    }>;
  };
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
}

export interface AskAgentOptions {
  /** Override the system prompt entirely */
  agentPromptOverride?: string;
  /** Reasoning effort level: 'minimal', 'low', 'medium', 'high' */
  reasoningEffort?: 'minimal' | 'low' | 'medium' | 'high';
  /** Verbosity level: 'low', 'medium', 'high' */
  verbosity?: 'low' | 'medium' | 'high';
}

/**
 * Call MCP server with API key authentication
 *
 * @param mcpBaseUrl - MCP server base URL (e.g., https://mcp.your-domain.com)
 * @param apiKey - MCP API key for authentication
 * @param _tenantId - Tenant ID (unused, kept for API compatibility)
 * @param query - User query/prompt
 * @param files - Optional file attachments
 * @param toolName - MCP tool to call (e.g., 'ask_agent', 'get_document')
 * @param outputFormat - Output format ('slack' or 'markdown')
 * @param additionalArgs - Additional tool-specific arguments
 * @param askAgentOptions - Options specific to ask_agent and ask_agent_fast tools
 * @returns MCPResponse with answer and optional response_id
 */
export async function callMCPWithApiKey(
  mcpBaseUrl: string,
  apiKey: string,
  _tenantId: string,
  query: string,
  files: FileAttachment[] = [],
  toolName: string = 'ask_agent',
  outputFormat: 'slack' | 'markdown' = 'markdown',
  additionalArgs?: Record<string, unknown>,
  askAgentOptions?: AskAgentOptions
): Promise<MCPResponse> {
  const baseArgs: Record<string, unknown> = {};

  // Only add query/files/output_format for ask_agent and ask_agent_fast
  if (toolName === 'ask_agent' || toolName === 'ask_agent_fast') {
    baseArgs.query = query;
    baseArgs.files = files;
    baseArgs.output_format = outputFormat;

    // Add optional ask_agent-specific arguments
    if (askAgentOptions?.agentPromptOverride) {
      baseArgs.agent_prompt_override = askAgentOptions.agentPromptOverride;
    }
    if (askAgentOptions?.reasoningEffort) {
      baseArgs.reasoning_effort = askAgentOptions.reasoningEffort;
    }
    if (askAgentOptions?.verbosity) {
      baseArgs.verbosity = askAgentOptions.verbosity;
    }
  }

  const payload = {
    jsonrpc: '2.0',
    id: '1',
    method: 'tools/call',
    params: {
      name: toolName,
      arguments: {
        ...baseArgs,
        ...additionalArgs,
      },
    },
  };

  const headers = {
    Authorization: `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
  };

  const url = `${mcpBaseUrl}/`;

  if (toolName === 'ask_agent' || toolName === 'ask_agent_fast') {
    console.log(`[callMCPWithApiKey] About to call ${toolName}`, {
      queryLength: query.length,
      filesCount: files.length,
    });
  } else if (toolName === 'get_document') {
    console.log('[callMCPWithApiKey] About to call get_document', {
      documentId: additionalArgs?.document_id,
    });
  }

  try {
    const response = await axios.post<string>(url, payload, {
      headers,
      responseType: 'text',
      timeout: 600000, // 10 minute timeout
    });

    return parseSSEResponse(response.data);
  } catch (error) {
    console.error('[MCP Client] Request failed:', error instanceof Error ? error.message : error);
    throw error;
  }
}

/**
 * Parse Server-Sent Events (SSE) response from MCP server
 *
 * MCP returns responses as SSE format with 'data: ' prefix
 */
function parseSSEResponse(responseText: string): MCPResponse {
  let jsonResponse: MCPJsonRpcResponse | null = null;

  // Extract JSON from SSE data field
  const lines = responseText.split('\n');
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      try {
        const jsonStr = line.slice(6); // Remove 'data: ' prefix
        jsonResponse = JSON.parse(jsonStr);
        break;
      } catch (e) {
        console.error('Failed to parse JSON from SSE line:', e);
        continue;
      }
    }
  }

  if (!jsonResponse) {
    throw new Error('No valid JSON found in SSE response');
  }

  // Check for JSON-RPC error response
  if (jsonResponse.error) {
    throw new Error(`MCP server error [${jsonResponse.error.code}]: ${jsonResponse.error.message}`);
  }

  // Extract the text content from the MCP response
  if (!jsonResponse.result?.content?.[0]?.text) {
    throw new Error('No content.text found in MCP response');
  }

  // Parse the text content which contains the actual answer
  try {
    const contentText = jsonResponse.result.content[0].text;
    const answerData = JSON.parse(contentText);
    return {
      answer: answerData.answer || '',
      response_id: answerData.response_id,
    };
  } catch (e) {
    const contentText = jsonResponse.result.content[0].text;
    console.error('Failed to parse answer data from MCP response:', {
      error: e,
      contentLength: contentText.length,
      contentPreview: contentText.substring(0, 200),
      fullContent: contentText.length < 500 ? contentText : '<content too long, see preview>',
    });
    throw new Error(`Failed to parse answer data from MCP response: ${e}`);
  }
}
