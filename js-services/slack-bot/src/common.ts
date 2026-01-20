import { GenericMessageEvent } from '@slack/bolt';
import { getOpenAI } from './clients';
import { config } from './config';
import { Message, FileAttachment, PermissionAudience } from './types';
import { logger } from './utils/logger';
import { getSlackMessageStorage } from './services/slackMessageStorage';
import axios from 'axios';
import { MessageElement } from '@slack/web-api/dist/response/ConversationsHistoryResponse';
import type { TenantSlackApp } from './TenantSlackApp';
import { generateInternalJWT } from './jwt-generator';
import type { TranslatedPhrases } from './i18n/phrases';
import { DEFAULT_PHRASES_EN } from './i18n/phrases';

export const HEADER_MARKER_EMOJI = ':postbox:';

const ASK_AGENT_RESPONSE_COMPLETE_TIMEOUT_MS = 600_000; // 10min to match the visibility timeout on slackbot messages

/**
 * Validate that a message still exists and clean up processing reactions if it doesn't
 * @param tenantSlackApp - The tenant Slack app instance
 * @param msg - The original message event
 * @param contextType - Type of message context for logging
 * @param threadTs - Thread timestamp (optional, for threaded messages)
 * @returns Promise<boolean> - true if message exists, false if deleted
 */
export async function validateMessageExistsOrCleanup(
  tenantSlackApp: TenantSlackApp,
  msg: GenericMessageEvent,
  contextType: 'dm' | 'thread-mention' | 'channel-mention',
  threadTs?: string
): Promise<boolean> {
  const messageExists = await tenantSlackApp.checkMessageExists(msg.channel, msg.ts, threadTs);

  if (!messageExists) {
    logger.info(
      `${contextType}: Skipping response - original message was deleted during processing`,
      {
        tenantId: tenantSlackApp.tenantId,
        userId: msg.user,
        channelId: msg.channel,
        messageTs: msg.ts,
        threadTs,
        operation: `${contextType}-response-skipped-deleted-message`,
      }
    );

    // Remove processing reaction since we're not responding
    await tenantSlackApp.removeProcessingReaction(msg.channel, msg.ts);
    return false;
  }

  return true;
}

// Replace HTTP /ask streaming with MCP JSON-RPC call to ask_agent tool
type MCPTotalToolName = 'ask_agent' | 'ask_agent_fast' | 'get_document';

async function callAskAgentViaMCP(
  userPrompt: string,
  files?: FileAttachment[],
  bearerToken?: string,
  previousResponseId?: string,
  reasoningEffort?: 'minimal' | 'low' | 'medium' | 'high',
  verbosity?: 'low' | 'medium' | 'high',
  toolName: MCPTotalToolName = 'ask_agent',
  disableTools?: boolean,
  writeTools?: string[],
  outputFormat: 'slack' | 'markdown' = 'slack',
  agentPromptOverride?: string
): Promise<{ answer: string; response_id?: string } | null> {
  const payload = {
    jsonrpc: '2.0',
    id: '1',
    method: 'tools/call',
    params: {
      name: toolName,
      arguments: {
        query: userPrompt,
        files: files || [],
        previous_response_id: previousResponseId || null,
        output_format: outputFormat,
        ...(reasoningEffort && { reasoning_effort: reasoningEffort }),
        ...(verbosity && { verbosity }),
        ...(disableTools !== undefined && { disable_tools: disableTools }),
        ...(writeTools !== undefined && { write_tools: writeTools }),
        ...(agentPromptOverride && { agent_prompt_override: agentPromptOverride }),
      },
    },
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
  };
  if (bearerToken) {
    headers['Authorization'] = `Bearer ${bearerToken}`;
  }

  // MCP app is mounted at '/'
  const backendUrl = config.backendUrl || process.env.MCP_BASE_URL;
  if (!backendUrl || backendUrl === 'undefined') {
    logger.error('Backend URL is not configured', undefined, {
      operation: 'ask-agent-setup-error',
    });
    throw new Error('Backend URL is not configured. Set MCP_BASE_URL environment variable.');
  }
  const url = `${backendUrl}/`;

  // Use AbortController for reliable timeout with SSE/streaming responses. Normal Axios timeout
  // doesn't work for streaming responses
  const controller = new AbortController();

  const timeoutId = setTimeout(() => {
    logger.warn('[callAskAgentViaMCP] Request timeout, aborting', {
      operation: 'mcp-call',
      timeoutMs: ASK_AGENT_RESPONSE_COMPLETE_TIMEOUT_MS,
    });
    controller.abort();
  }, ASK_AGENT_RESPONSE_COMPLETE_TIMEOUT_MS);

  const axiosConfig = {
    signal: controller.signal,
    headers,
    responseType: 'text' as const, // Expect text response for SSE
    // it seems axios-retry automatically retries ERR_CANCELED even for POST requests, so we have to
    // override the retry config and not retry if aborted.
    'axios-retry': {
      retries: 3,
      retryDelay: (retryCount: number) => {
        // Exponential backoff: 1s, 2s, 4s
        return Math.min(1000 * Math.pow(2, retryCount - 1), 4000);
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      retryCondition: (error: any) => {
        // Don't retry if aborted by our timeout controller
        if (controller.signal.aborted) {
          return false;
        }

        // Retry on network errors or 5xx server errors
        // this is the default behavior via axios-retry for
        return (
          error.response?.status >= 500 ||
          error.code === 'ECONNRESET' ||
          error.code === 'ETIMEDOUT' ||
          error.code === 'ENOTFOUND'
        );
      },
    },
  };

  let resp;
  try {
    resp = await axios.post<string>(url, payload, axiosConfig);
    clearTimeout(timeoutId);
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }

  interface MCPResponse {
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

  // Parse SSE response to extract JSON
  let jsonResponse: MCPResponse | null = null;
  const responseText = typeof resp.data === 'string' ? resp.data : JSON.stringify(resp.data);

  // Log first 500 chars of response for debugging
  logger.debug('[callAskAgentViaMCP] Raw response (first 500 chars)', {
    response: responseText.slice(0, 500),
    operation: 'mcp-call',
  });

  // Extract JSON from SSE data field
  const lines = responseText.split('\n');
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      try {
        const jsonStr = line.slice(6); // Remove 'data: ' prefix
        jsonResponse = JSON.parse(jsonStr);
        logger.debug('[callAskAgentViaMCP] Parsed JSON from SSE', { operation: 'mcp-call' });
        break;
      } catch (e) {
        logger.error(
          '[callAskAgentViaMCP] Failed to parse JSON from SSE line',
          e instanceof Error ? e : new Error(String(e)),
          { operation: 'mcp-call' }
        );
      }
    }
  }

  if (!jsonResponse) {
    logger.error('[callAskAgentViaMCP] No valid JSON found in SSE response', undefined, {
      operation: 'mcp-call',
    });
    return null;
  }

  // Check for JSON-RPC error response
  if (jsonResponse.error) {
    logger.error('[callAskAgentViaMCP] MCP server returned error', undefined, {
      operation: 'mcp-call',
      errorCode: jsonResponse.error.code,
      errorMessage: jsonResponse.error.message,
      errorData: jsonResponse.error.data,
    });
    return null;
  }

  // Extract the text content from the MCP response
  if (!jsonResponse.result?.content?.[0]?.text) {
    logger.error('[callAskAgentViaMCP] No content.text found in MCP response', undefined, {
      operation: 'mcp-call',
    });
    return null;
  }

  // Parse the text content which contains the actual answer
  let answerData: {
    answer?: string;
    response_id?: string;
    citations?: unknown;
    events?: unknown[];
  };
  try {
    const contentText = jsonResponse.result.content[0].text;
    answerData = JSON.parse(contentText);
  } catch (e) {
    const contentText = jsonResponse.result.content[0].text;
    logger.error(
      '[MCP] Failed to parse answer data from MCP response content',
      e instanceof Error ? e : new Error(String(e)),
      {
        operation: 'mcp-call',
        contentLength: contentText.length,
        contentPreview: contentText.substring(0, 200),
      }
    );
    return null;
  }

  if (process.env.DEBUG_MODE === 'true') {
    logger.debug('[MCP] Answer extracted', {
      answerLength: answerData.answer?.length || 0,
      hasResponseId: !!answerData.response_id,
      operation: 'mcp-call',
    });
  }

  return { answer: answerData.answer || '', response_id: answerData.response_id };
}

/**
 * Call the get_document MCP tool directly with the correct parameters (internal helper)
 */
async function callGetDocumentViaMCPInternal(
  documentId: string,
  bearerToken: string
): Promise<{ document_id: string; content: string } | null> {
  const payload = {
    jsonrpc: '2.0',
    id: '1',
    method: 'tools/call',
    params: {
      name: 'get_document',
      arguments: {
        document_id: documentId,
      },
    },
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
    Authorization: `Bearer ${bearerToken}`,
  };

  const backendUrl = config.backendUrl || process.env.MCP_BASE_URL;
  if (!backendUrl || backendUrl === 'undefined') {
    logger.error('Backend URL is not configured', undefined, {
      operation: 'get-document-setup-error',
    });
    throw new Error('Backend URL is not configured. Set MCP_BASE_URL environment variable.');
  }
  const url = `${backendUrl}/`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    logger.warn('[callGetDocumentViaMCPInternal] Request timeout, aborting', {
      operation: 'mcp-get-document-call',
      timeoutMs: ASK_AGENT_RESPONSE_COMPLETE_TIMEOUT_MS,
    });
    controller.abort();
  }, ASK_AGENT_RESPONSE_COMPLETE_TIMEOUT_MS);

  const axiosConfig = {
    signal: controller.signal,
    headers,
    responseType: 'text' as const,
    'axios-retry': {
      retries: 3,
      retryDelay: (retryCount: number) => {
        return Math.min(1000 * Math.pow(2, retryCount - 1), 4000);
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      retryCondition: (error: any) => {
        if (controller.signal.aborted) {
          return false;
        }
        return (
          error.response?.status >= 500 ||
          error.code === 'ECONNRESET' ||
          error.code === 'ETIMEDOUT' ||
          error.code === 'ENOTFOUND'
        );
      },
    },
  };

  let resp;
  try {
    resp = await axios.post<string>(url, payload, axiosConfig);
    clearTimeout(timeoutId);
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }

  interface MCPResponse {
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

  let jsonResponse: MCPResponse | null = null;
  const responseText = typeof resp.data === 'string' ? resp.data : JSON.stringify(resp.data);

  logger.debug('[callGetDocumentViaMCPInternal] Raw response (first 500 chars)', {
    response: responseText.slice(0, 500),
    operation: 'mcp-get-document-call',
  });

  // Extract JSON from SSE data field
  const lines = responseText.split('\n');
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      try {
        const jsonStr = line.slice(6);
        jsonResponse = JSON.parse(jsonStr);
        logger.debug('[callGetDocumentViaMCPInternal] Parsed JSON from SSE', {
          operation: 'mcp-get-document-call',
        });
        break;
      } catch (e) {
        logger.error(
          '[callGetDocumentViaMCPInternal] Failed to parse JSON from SSE line',
          e instanceof Error ? e : new Error(String(e)),
          { operation: 'mcp-get-document-call' }
        );
      }
    }
  }

  if (!jsonResponse) {
    logger.error('[callGetDocumentViaMCPInternal] No valid JSON found in SSE response', undefined, {
      operation: 'mcp-get-document-call',
    });
    return null;
  }

  if (jsonResponse.error) {
    logger.error('[callGetDocumentViaMCPInternal] MCP error response', undefined, {
      error: jsonResponse.error,
      operation: 'mcp-get-document-call',
    });
    throw new Error(`MCP error: ${jsonResponse.error.message}`);
  }

  if (!jsonResponse.result?.content || jsonResponse.result.content.length === 0) {
    logger.error('[callGetDocumentViaMCPInternal] Missing result.content in response', undefined, {
      operation: 'mcp-get-document-call',
    });
    return null;
  }

  // Parse the text content which should be a JSON string with document_id and content
  const textContent = jsonResponse.result.content[0].text;
  try {
    const documentData = JSON.parse(textContent);
    logger.info('[callGetDocumentViaMCPInternal] Successfully retrieved document', {
      document_id: documentData.document_id,
      contentLength: documentData.content?.length || 0,
      operation: 'mcp-get-document-call',
    });
    return documentData;
  } catch (e) {
    logger.error(
      '[callGetDocumentViaMCPInternal] Failed to parse document data',
      e instanceof Error ? e : new Error(String(e)),
      { operation: 'mcp-get-document-call' }
    );
    return null;
  }
}

/**
 * Export wrapper for callGetDocumentViaMCP that handles JWT generation
 */
export async function callGetDocumentViaMCP(
  tenantId: string,
  documentId: string
): Promise<{ document_id: string; content: string } | null> {
  if (!tenantId) {
    logger.error('No tenant ID provided for get_document call', undefined, {
      operation: 'get-document-setup-error',
    });
    throw new Error('Tenant ID is required for authentication');
  }

  let bearerToken: string;
  try {
    bearerToken = generateInternalJWT(
      tenantId,
      undefined, // No user email needed for internal tool call
      config.internalJwtExpiry,
      undefined, // No permission audience
      true // Non-billable internal tool call
    );
    logger.debug(`[callGetDocumentViaMCP] Generated JWT for tenant`, {
      tenantId,
      operation: 'jwt-generation',
    });
  } catch (error) {
    logger.error(
      '[callGetDocumentViaMCP] Failed to generate JWT token',
      error instanceof Error ? error : new Error(String(error)),
      { tenantId, operation: 'jwt-generation' }
    );
    throw new Error(
      `JWT generation failed: ${error instanceof Error ? error.message : String(error)}`
    );
  }

  return callGetDocumentViaMCPInternal(documentId, bearerToken);
}

/**
 * Make MCP request to backend using ask_agent tool
 */
export async function makeBackendRequest(
  tenantId: string,
  userPrompt: string,
  userEmail?: string,
  files?: FileAttachment[],
  previousResponseId?: string,
  permissionAudience?: PermissionAudience,
  nonBillable: boolean = false,
  reasoningEffort?: 'minimal' | 'low' | 'medium' | 'high',
  verbosity?: 'low' | 'medium' | 'high',
  toolName: MCPTotalToolName = 'ask_agent',
  disableTools?: boolean,
  writeTools?: string[],
  outputFormat?: 'slack' | 'markdown',
  agentPromptOverride?: string
): Promise<{ answer: string; response_id?: string } | null> {
  const { generateInternalJWT } = await import('./jwt-generator');

  // Get tenant ID for JWT generation
  if (!tenantId) {
    logger.error('No tenant ID set for current processing context', undefined, {
      operation: 'backend-request-setup-error',
    });
    throw new Error('Tenant ID is required for authentication, did you pass it?');
  }

  // Generate JWT token for MCP authentication
  let bearerToken: string;
  try {
    bearerToken = generateInternalJWT(
      tenantId,
      userEmail,
      config.internalJwtExpiry,
      permissionAudience,
      nonBillable
    );
    logger.debug(`[makeBackendRequest] Generated JWT for tenant with email`, {
      tenantId,
      userEmail,
      permissionAudience,
      nonBillable,
      operation: 'jwt-generation',
    });
  } catch (error) {
    logger.error(
      '[makeBackendRequest] Failed to generate JWT token',
      error instanceof Error ? error : new Error(String(error)),
      { tenantId, operation: 'jwt-generation' }
    );
    throw new Error(
      `JWT generation failed: ${error instanceof Error ? error.message : String(error)}`
    );
  }

  const res = await callAskAgentViaMCP(
    userPrompt,
    files,
    bearerToken,
    previousResponseId,
    reasoningEffort,
    verbosity,
    toolName,
    disableTools,
    writeTools,
    outputFormat,
    agentPromptOverride
  );
  if (!res) {
    logger.error('[Backend] MCP call returned null', undefined, {
      tenantId,
      operation: 'backend-request',
    });
    return null;
  }

  if (process.env.DEBUG_MODE === 'true') {
    logger.debug('[Backend] Got answer', {
      answerLength: res.answer?.length || 0,
      hasResponseId: !!res.response_id,
      tenantId,
      operation: 'backend-request',
    });
  }

  // Return the full result object
  return res;
}

/**
 * Event types from the streaming endpoint
 */
export interface StreamEvent {
  type:
    | 'status'
    | 'tool_call'
    | 'tool_result'
    | 'final_answer'
    | 'message'
    | 'trace_info'
    | 'error'
    | 'agent_decision';
  data?: unknown;
}

/**
 * Make streaming request to backend using /v1/ask/stream endpoint
 * Logs each event as it arrives and returns the final answer
 */
export async function makeBackendRequestStreaming(
  tenantId: string,
  userPrompt: string,
  userEmail?: string,
  files?: FileAttachment[],
  previousResponseId?: string,
  permissionAudience?: PermissionAudience,
  nonBillable: boolean = false,
  onEvent?: (event: StreamEvent) => void
): Promise<{ answer: string; response_id?: string } | null> {
  const { generateInternalJWT } = await import('./jwt-generator');

  if (!tenantId) {
    logger.error('No tenant ID set for streaming request', undefined, {
      operation: 'streaming-request-setup-error',
    });
    throw new Error('Tenant ID is required for authentication');
  }

  // Generate JWT token
  let bearerToken: string;
  try {
    bearerToken = generateInternalJWT(
      tenantId,
      userEmail,
      config.internalJwtExpiry,
      permissionAudience,
      nonBillable
    );
    logger.debug('[makeBackendRequestStreaming] Generated JWT for tenant', {
      tenantId,
      userEmail,
      operation: 'jwt-generation',
    });
  } catch (error) {
    logger.error(
      '[makeBackendRequestStreaming] Failed to generate JWT token',
      error instanceof Error ? error : new Error(String(error)),
      { tenantId, operation: 'jwt-generation' }
    );
    throw error;
  }

  const backendUrl = config.backendUrl || process.env.MCP_BASE_URL;
  if (!backendUrl || backendUrl === 'undefined') {
    logger.error('Backend URL is not configured', undefined, {
      operation: 'streaming-request-setup-error',
    });
    throw new Error('Backend URL is not configured. Set MCP_BASE_URL environment variable.');
  }

  const url = `${backendUrl}/v1/ask/stream`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    logger.warn('[makeBackendRequestStreaming] Request timeout, aborting', {
      operation: 'streaming-request',
      timeoutMs: ASK_AGENT_RESPONSE_COMPLETE_TIMEOUT_MS,
    });
    controller.abort();
  }, ASK_AGENT_RESPONSE_COMPLETE_TIMEOUT_MS);

  try {
    logger.info('[makeBackendRequestStreaming] Starting streaming request', {
      tenantId,
      operation: 'streaming-request-start',
    });

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${bearerToken}`,
      },
      body: JSON.stringify({
        query: userPrompt,
        previous_response_id: previousResponseId || null,
        files: files || [],
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      logger.error('[makeBackendRequestStreaming] HTTP error', undefined, {
        status: response.status,
        statusText: response.statusText,
        operation: 'streaming-request-error',
      });
      return null;
    }

    if (!response.body) {
      logger.error('[makeBackendRequestStreaming] No response body', undefined, {
        operation: 'streaming-request-error',
      });
      return null;
    }

    // Parse SSE stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalAnswer: { answer: string; response_id?: string } | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim() || !line.startsWith('data: ')) continue;

        const data = line.slice(6);
        if (data === '[DONE]') {
          logger.info('[makeBackendRequestStreaming] Stream completed', {
            tenantId,
            operation: 'streaming-done',
          });
          continue;
        }

        try {
          const event: StreamEvent = JSON.parse(data);

          // Log each event
          logger.info('[makeBackendRequestStreaming] Event received', {
            tenantId,
            eventType: event.type,
            operation: 'streaming-event',
          });

          // Call the event callback if provided
          if (onEvent) {
            onEvent(event);
          }

          // Extract final answer
          if (event.type === 'final_answer' && event.data && typeof event.data === 'object') {
            const eventData = event.data as { answer?: string; response_id?: string };
            finalAnswer = {
              answer: eventData.answer || '',
              response_id: eventData.response_id,
            };
          }

          // Handle error events
          if (event.type === 'error') {
            logger.error('[makeBackendRequestStreaming] Error event received', undefined, {
              tenantId,
              errorData: event.data,
              operation: 'streaming-error-event',
            });
          }
        } catch (_parseError) {
          logger.warn('[makeBackendRequestStreaming] Failed to parse SSE event', {
            line: data.slice(0, 100),
            operation: 'streaming-parse-error',
          });
        }
      }
    }

    if (finalAnswer) {
      logger.info('[makeBackendRequestStreaming] Streaming complete with answer', {
        tenantId,
        answerLength: finalAnswer.answer.length,
        hasResponseId: !!finalAnswer.response_id,
        operation: 'streaming-complete',
      });
    } else {
      logger.warn('[makeBackendRequestStreaming] Streaming complete without final answer', {
        tenantId,
        operation: 'streaming-no-answer',
      });
    }

    return finalAnswer;
  } catch (error) {
    clearTimeout(timeoutId);

    if (error instanceof Error && error.name === 'AbortError') {
      logger.error('[makeBackendRequestStreaming] Request aborted (timeout)', undefined, {
        tenantId,
        operation: 'streaming-timeout',
      });
    } else {
      logger.error(
        '[makeBackendRequestStreaming] Request failed',
        error instanceof Error ? error : new Error(String(error)),
        { tenantId, operation: 'streaming-error' }
      );
    }

    return null;
  }
}

/**
 * Handle backend API errors with detailed logging
 */
export function handleBackendError(error: unknown) {
  logger.error(
    '[generateAnswerFromBackend] Error in backend request',
    error instanceof Error ? error : new Error(String(error)),
    { operation: 'backend-error' }
  );

  // Log detailed error information
  if (error && typeof error === 'object' && 'response' in error && 'config' in error) {
    const axiosError = error as {
      response?: { status?: number; statusText?: string; headers?: unknown; data?: unknown };
      config?: { url?: string; method?: string };
      message?: string;
    };
    logger.error('[generateAnswerFromBackend] Axios error details', undefined, {
      operation: 'backend-error',
      status: axiosError.response?.status,
      statusText: axiosError.response?.statusText,
      url: axiosError.config?.url,
      method: axiosError.config?.method,
      errorMessage: axiosError.message,
      data: axiosError.response?.data,
    });

    if (axiosError.response?.status === 409) {
      logger.info('[generateAnswerFromBackend] Backend returned 409, skipping', {
        operation: 'backend-error',
        status: 409,
      });
    }
  } else {
    logger.error(
      '[generateAnswerFromBackend] Non-Axios error',
      error instanceof Error ? error : new Error(String(error)),
      { operation: 'backend-error' }
    );
  }
}

export async function getTenantStateToAnswerQuestions(tenantId: string) {
  try {
    const storage = getSlackMessageStorage();

    const stats = await storage.getSourcesStats(tenantId);

    let state: 'ready' | 'processing' | 'insufficient-data' = 'ready';

    if (!stats || Object.keys(stats).length === 0) {
      state = 'insufficient-data';
    }

    if (stats) {
      const totalIndexed = Object.values(stats).reduce((sum, source) => sum + source.indexed, 0);
      const totalDiscovered = Object.values(stats).reduce(
        (sum, source) => sum + Object.values(source.discovered).reduce((s, count) => s + count, 0),
        0
      );

      // If we have less than 5% of discovered items indexed, we're still processing
      if (totalDiscovered > 50 && totalIndexed / totalDiscovered < 0.05) {
        state = 'processing';
      }
    }

    return {
      state,
      stats,
      tasksLeftToDo: [
        ...(Object.values(stats || {}).length < 3 ? ['Setting up 3 integrations'] : []),
      ],
    };
  } catch (error) {
    logger.error(
      'Error getting tenant state',
      error instanceof Error ? error : new Error(String(error)),
      { tenantId, operation: 'tenant-state' }
    );
    return {
      state: 'ready' as const, // assume ready on error to not block
      stats: {},
      tasksLeftToDo: [],
    };
  }
}

export async function storeMessage(
  tenantId: string,
  messageId: string,
  channelId: string,
  userId: string,
  question: string,
  answer: string,
  threadTs?: string,
  responseId?: string,
  botResponseMessageId?: string,
  isProactive?: boolean
): Promise<void> {
  try {
    const storage = getSlackMessageStorage();
    const success = await storage.storeMessage(tenantId, {
      messageId,
      channelId,
      userId,
      question,
      answer,
      threadTs,
      responseId,
      botResponseMessageId,
      isProactive,
    });

    if (success) {
      logger.info('Successfully stored Slack message', {
        tenantId,
        messageId,
        channelId,
        userId,
        hasThreadTs: !!threadTs,
        hasResponseId: !!responseId,
        operation: 'message-storage',
      });
    } else {
      logger.warn('Failed to store Slack message', {
        tenantId,
        messageId,
        channelId,
        userId,
        operation: 'message-storage',
      });
    }
  } catch (error) {
    // Don't throw - we don't want storage failures to break bot responses
    logger.error(
      'Error in storeMessage wrapper',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId,
        messageId,
        channelId,
        userId,
        operation: 'message-storage',
      }
    );
  }
}

/**
 * Store a reaction in the database
 */
export async function storeReaction(
  tenantId: string,
  messageId: string,
  channelId: string,
  userId: string,
  reaction: string
): Promise<void> {
  const storage = getSlackMessageStorage();
  const success = await storage.storeReaction(tenantId, {
    messageId,
    channelId,
    userId,
    reaction,
  });

  if (!success) {
    logger.error('Failed to store reaction in database', {
      tenantId,
      messageId,
      channelId,
      userId,
      reaction,
      operation: 'reaction-storage',
    });
  }
}

/**
 * Remove a reaction from the database
 */
export async function removeReaction(
  tenantId: string,
  messageId: string,
  userId: string,
  reaction: string
): Promise<void> {
  const storage = getSlackMessageStorage();
  const success = await storage.removeReaction(tenantId, messageId, userId, reaction);

  if (!success) {
    logger.error('Failed to remove reaction from database', {
      tenantId,
      messageId,
      userId,
      reaction,
      operation: 'reaction-removal',
    });
  }
}

export interface SlackFile {
  name: string;
  url_private_download: string;
  mimetype: string;
  size: number;
}

/**
 * Download files from Slack and prepare them for backend processing
 */
export async function downloadSlackFiles(
  files: SlackFile[],
  slackBotToken: string
): Promise<FileAttachment[]> {
  const attachments: FileAttachment[] = [];

  for (const file of files) {
    try {
      // Only process files that are not too large (max 10MB)
      if (file.size > 10 * 1024 * 1024) {
        logger.warn(`Skipping large file: ${file.name} (${file.size} bytes)`, {
          fileName: file.name,
          fileSize: file.size,
          operation: 'file-download',
        });
        continue;
      }

      // Download the file content
      const response = await axios.get(file.url_private_download, {
        headers: {
          Authorization: `Bearer ${slackBotToken}`,
        },
        responseType: 'arraybuffer',
        timeout: 30000,
      });

      // Convert to base64 for transmission
      const buffer = Buffer.from(response.data as ArrayBuffer);
      const attachment: FileAttachment = {
        name: file.name,
        mimetype: file.mimetype,
        content: buffer.toString('base64'),
      };

      logger.debug(`Downloaded file: ${file.name} (${file.mimetype})`, {
        fileName: file.name,
        mimetype: file.mimetype,
        size: buffer.length,
        operation: 'file-download',
      });

      attachments.push(attachment);
    } catch (error) {
      logger.error(
        `Error downloading file ${file.name}`,
        error instanceof Error ? error : new Error(String(error)),
        { fileName: file.name, operation: 'file-download' }
      );
      // Continue with other files even if one fails
    }
  }

  return attachments;
}

/**
 * Strips the header from mirrored messages
 * Header format is typically ":postbox: *Original message from user* • <link|View original> :postbox:\n\n"
 */
export function stripMessageHeader(content: string): string {
  if (!content || !content.includes(HEADER_MARKER_EMOJI)) return content;

  const emojiPattern = HEADER_MARKER_EMOJI.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const headerPattern = `${emojiPattern}.*?${emojiPattern}\\s*\\n\\n`;
  return content.replace(new RegExp(headerPattern, 's'), '').trim();
}

/**
 * Standardized error handler for consistent logging and error recovery
 */
export function handleError(
  context: string,
  error: unknown,
  options: {
    level?: 'error' | 'warn' | 'info';
    shouldThrow?: boolean;
    fallbackValue?: unknown;
    tenantId?: string;
    operation?: string;
    metadata?: Record<string, unknown>;
  } = {}
): unknown {
  const {
    level = 'error',
    shouldThrow = false,
    fallbackValue,
    tenantId,
    operation,
    metadata = {},
  } = options;

  const logContext = {
    context,
    tenantId,
    operation: operation || context,
    ...metadata,
  };

  const errorMessage = error instanceof Error ? error.message : String(error);
  const message = `Error in ${context}: ${errorMessage}`;

  // Use structured logging instead of console
  switch (level) {
    case 'error':
      logger.error(message, error instanceof Error ? error : new Error(String(error)), logContext);
      break;
    case 'warn':
      logger.warn(message, logContext);
      break;
    case 'info':
      logger.info(message, logContext);
      break;
  }

  // Handle throwing vs returning
  if (shouldThrow) {
    throw error;
  }

  return fallbackValue;
}

/**
 * Extract source names from stats
 * @param stats - The sources stats from getSourcesStats()
 * @returns Array of source names that have indexed data or discovered artifacts
 */
export function getConfiguredSourceNames(
  stats?: Record<string, { indexed: number; discovered: Record<string, number> }> | null
): string[] {
  if (!stats || Object.keys(stats).length === 0) {
    return [];
  }

  return Object.keys(stats).filter((source) => stats[source].indexed > 0);
}

/**
 * Get a human-readable description of configured sources from source names
 * @param sources - Array of source names (e.g., ['github', 'slack', 'notion'])
 * @returns A formatted string describing the available sources
 */
function formatSourcesDescription(sources?: string[]): string {
  if (!sources || sources.length === 0) {
    return '- Company knowledge and documentation';
  }

  const sourceDescriptions: Record<string, string> = {
    github: 'Github',
    slack: 'Slack',
    notion: 'Notion',
    linear: 'Linear',
    google_drive: 'Google Drive',
    hubspot: 'HubSpot',
    salesforce: 'Salesforce',
  };

  const configuredSources = sources
    .map((source) => `- ${sourceDescriptions[source] || source}`)
    .join('\n');

  return configuredSources || '- Company knowledge and documentation';
}

export interface ShouldAnswerResponse {
  shouldAnswer: boolean;
  reasoning: string;
}

/**
 * Determines if a Slack message is a company knowledge question that should be answered by the bot
 * @param messageText - The text content of the Slack message
 * @param configuredSources - Optional array of configured source names (e.g., ['github', 'slack'])
 * @returns Promise<ShouldAnswerResponse> - Object with shouldAnswer boolean and reasoning string
 */
export async function shouldTryToAnswerMessage(
  messageText: string,
  configuredSources?: string[]
): Promise<ShouldAnswerResponse> {
  try {
    if (!messageText || messageText.trim().length === 0) {
      return { shouldAnswer: false, reasoning: 'Empty message' };
    }

    // Format sources description
    const sourcesDescription = formatSourcesDescription(configuredSources);

    const response = await getOpenAI().chat.completions.create({
      model: 'gpt-4o',
      messages: [
        {
          role: 'system',
          content: `You are a classifier that determines if a message is a question that should be answered by an AI assistant.

The AI assistant has access to realtime and historical information from the following sources:
${sourcesDescription}

Some examples of what the AI assistant should not attempt to answer:
- Questions which are product or strategy decisions
- External/personal questions unrelated to work
- Questions seeking personal opinions or subjective views from specific individuals
- Commands or statements rather than information-seeking questions
- Casual conversation or social chatter

Some examples of what the AI assistant might be able to answer well:
- A question seeking factual information about the company, products, or processes
- A request for help with company tools, systems, or procedures
- A question about team members, projects, or organizational matters
- A technical question about code, systems, or tools
- A question that could be answered by synthesizing documented company knowledge

If you're unsure, it's better that the AI not answer than answer poorly.

Respond with a JSON object in this exact format and no additional formatting:
{
  "shouldAnswer": true or false,
  "reasoning": "Brief explanation (max 1000 characters)"
}`,
        },
        {
          role: 'user',
          content: messageText,
        },
      ],
      temperature: 0.1,
      max_tokens: 300,
    });

    const content = response.choices[0].message.content?.trim();
    if (!content) {
      logger.warn('[shouldTryToAnswerMessage] Empty response from OpenAI', {
        operation: 'should-answer-check',
      });
      return { shouldAnswer: false, reasoning: 'Empty response from OpenAI' };
    }

    // Parse JSON response with validation
    let parsed: ShouldAnswerResponse;
    try {
      parsed = JSON.parse(content);

      // Validate the parsed object has the expected structure
      if (typeof parsed.shouldAnswer !== 'boolean' || typeof parsed.reasoning !== 'string') {
        logger.error(
          `[shouldTryToAnswerMessage] Invalid response format from OpenAI: ${content.substring(0, 200)}`,
          {
            operation: 'should-answer-check',
            parsedType: typeof parsed,
            hasShouldAnswer: 'shouldAnswer' in parsed,
            hasReasoning: 'reasoning' in parsed,
          }
        );
        return { shouldAnswer: false, reasoning: 'Invalid response format from OpenAI' };
      }
    } catch (parseError) {
      logger.error(
        `[shouldTryToAnswerMessage] Failed to parse JSON response from OpenAI: ${content.substring(0, 200)}`,
        {
          operation: 'should-answer-check',
          errorMessage: parseError instanceof Error ? parseError.message : String(parseError),
        }
      );
      return { shouldAnswer: false, reasoning: 'Failed to parse OpenAI response' };
    }

    return parsed;
  } catch (error) {
    handleError('shouldTryToAnswerMessage', error, {
      fallbackValue: false,
      level: 'warn',
    });
    return { shouldAnswer: false, reasoning: 'Error during classification' };
  }
}

/**
 * Determines if an AI-generated answer is of good quality for the given question
 * Used for post-processing to filter out low-quality proactive responses
 * @param question - The original question that was asked
 * @param answer - The AI-generated answer to evaluate
 * @returns Promise<boolean> - True if the answer is high-quality and should be posted
 */
export async function isGoodAnswerToQuestion(question: string, answer: string): Promise<boolean> {
  try {
    if (!question || question.trim().length === 0 || !answer || answer.trim().length === 0) {
      return false;
    }

    const response = await getOpenAI().chat.completions.create({
      model: 'gpt-4o',
      messages: [
        {
          role: 'system',
          content: `You are evaluating whether an AI assistant's answer is of good quality for a given question.

Consider the answer HIGH QUALITY (respond "true") if it:
- Directly addresses the specific question asked
- Provides concrete, actionable information
- Contains relevant details, examples, or step-by-step guidance
- Would genuinely help the person who asked the question

Consider the answer LOW QUALITY (respond "false") if it:
- Suggests the user should look elsewhere or ask other people because the bot couldn't find high quality information or didn't have access to the right sources
- Contains disclaimers that undermine confidence in the answer
- Is clearly incomplete or cut off

The goal is to only send proactive responses that provide real value to the channel. When in doubt about quality, err on the side of caution and respond "false".

Respond with only "true" or "false".`,
        },
        {
          role: 'user',
          content: `Question: ${question}\n\nAnswer: ${answer}`,
        },
      ],
      temperature: 0.1,
      max_tokens: 10,
    });

    const result = response.choices[0].message.content?.trim().toLowerCase();
    return result === 'true';
  } catch (error) {
    return handleError('isGoodAnswerToQuestion', error, {
      fallbackValue: false,
      level: 'warn',
    }) as boolean;
  }
}

/**
 * Check if a message contains a mention of the bot
 */
export function isBotMentioned(messageText: string, botId: string): boolean {
  logger.debug('Checking bot mention', { botId, operation: 'bot-mention-check' });
  if (!botId) {
    logger.warn('[isBotMentioned] Bot ID not available yet', { operation: 'bot-mention-check' });
    return false;
  }

  // Check for direct mention: <@USERID>
  const mentionPattern = new RegExp(`<@${botId}>`, 'i');
  return mentionPattern.test(messageText);
}

/**
 * Check if a message is in a direct message channel
 */
export function isDMChannel(message: { channel_type: string }): boolean {
  return message.channel_type === 'im';
}

/**
 * Get the standard fallback message when the bot cannot answer a question
 */
export function getFallbackAnswer(phrases: TranslatedPhrases = DEFAULT_PHRASES_EN): string {
  return phrases.fallbackAnswer;
}

/**
 * Check if bot has responded to a thread and extract the most recent response_id
 * Phase 3: Reads from database first, falls back to text parsing for old messages
 * @param messageElements - Array of messages in the thread
 * @param botId - The bot's user ID
 * @param tenantId - The tenant ID for database lookup
 * @returns the bot's most recent response ID, or null
 */
export async function getBotResponseFromThread(
  messageElements: MessageElement[],
  botId: string,
  tenantId: string
): Promise<string | null> {
  if (!botId) {
    logger.warn('[getBotResponseFromThread] Bot ID not available', {
      operation: 'thread-response-check',
    });
    return null;
  }

  // Find the most recent bot message
  const botMessages = messageElements
    .filter((msg) => msg.bot_id === botId || msg.user === botId)
    .sort((a, b) => parseFloat(b.ts || '0') - parseFloat(a.ts || '0'));

  if (botMessages.length === 0) {
    return null;
  }

  const latestBotMessage = botMessages[0];
  const botMessageTs = latestBotMessage.ts;

  if (!botMessageTs) {
    logger.warn('[getBotResponseFromThread] Bot message has no timestamp', {
      tenantId,
      operation: 'thread-response-check',
    });
    return null;
  }

  // Phase 3: Try to get response ID from database first
  try {
    const storage = getSlackMessageStorage();
    const responseId = await storage.getResponseId(tenantId, botMessageTs);

    if (responseId) {
      logger.debug('[getBotResponseFromThread] Found response ID in database', {
        tenantId,
        botMessageTs,
        responseId,
        operation: 'thread-response-check',
      });
      return responseId;
    }

    // Database lookup returned null - fall back to text parsing
    logger.warn(
      '[getBotResponseFromThread] Response ID not found in database, falling back to text parsing',
      {
        tenantId,
        botMessageTs,
        operation: 'thread-response-check-fallback',
      }
    );
  } catch (error) {
    // If database query fails, log error and fall back to text parsing
    logger.error(
      '[getBotResponseFromThread] Database query failed, falling back to text parsing',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId,
        botMessageTs,
        operation: 'thread-response-check-fallback',
      }
    );
  }

  // Fallback: Extract response_id from message text (for old messages)
  const messageText = latestBotMessage.text || '';
  const responseIdMatch = messageText.match(
    /_Response ID \(for conversation continuation\): ([\w-]+)_/
  );

  const responseIdFromText = responseIdMatch?.[1] ?? null;

  if (responseIdFromText) {
    logger.info('[getBotResponseFromThread] Found response ID in message text (legacy)', {
      tenantId,
      botMessageTs,
      responseId: responseIdFromText,
      operation: 'thread-response-check-text-fallback',
    });
  }

  return responseIdFromText;
}

/**
 * Format a question with thread context for AI processing
 */
export function formatQuestionWithContext(question: string, contextMessages: Message[]): string {
  if (contextMessages.length === 0) {
    return question;
  }

  // Format context messages for AI processing
  const contextText = contextMessages
    .map((msg) => `${msg.role === 'assistant' ? 'Bot' : 'User'}: ${msg.content}`)
    .join('\n');

  const formattedQuestion = `<context>\n${contextText}\n</context>\n\n<question>${question}</question>`;

  logger.debug('Formatted question with context', {
    contextLength: contextText.length,
    questionLength: question.length,
    formattedLength: formattedQuestion.length,
    operation: 'question-formatting',
  });

  return formattedQuestion;
}
