import { Router, Request, Response } from 'express';
import axios from 'axios';
import { Readable } from 'stream';
import { logger } from '../utils/logger.js';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { generateInternalJWT } from '../jwt-generator.js';

export const mcpRouter = Router();

// Environment variable for MCP server URL with fallback
export const getMCPServerUrl = (): string => {
  return process.env.MCP_BASE_URL || 'http://localhost:8000';
};

/**
 * Proxy MCP JSON-RPC requests to the MCP server
 * Adds authentication headers and forwards the request
 */
mcpRouter.post('/', requireAdmin, async (req: Request, res: Response) => {
  try {
    const mcpServerUrl = getMCPServerUrl();

    // Validate JSON-RPC structure
    if (!req.body || !req.body.jsonrpc || !req.body.method) {
      return res.status(400).json({
        error: 'Invalid JSON-RPC request format',
      });
    }

    // Ensure we have a tenant ID from the user context
    if (!req.user?.tenantId) {
      return res.status(401).json({
        error: 'User tenant ID not available',
      });
    }

    // Generate internal JWT for MCP server authentication
    let bearerToken: string;
    try {
      bearerToken = await generateInternalJWT(req.user.tenantId, undefined, req.user.email);
      logger.debug('Generated internal JWT for MCP request', {
        tenantId: req.user.tenantId,
        email: req.user.email,
        operation: 'mcp-proxy-jwt-generation',
      });
    } catch (error) {
      logger.error('Failed to generate internal JWT', error, {
        tenantId: req.user.tenantId,
        operation: 'mcp-proxy-jwt-generation',
      });
      return res.status(500).json({
        error: 'Failed to generate authentication token',
      });
    }

    // Prepare headers for MCP server request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      Authorization: `Bearer ${bearerToken}`,
    };

    // Add org-id header if available from user context
    if (req.user?.tenantId) {
      headers['X-Org-ID'] = req.user.tenantId;
    }

    logger.debug('Proxying MCP request', {
      method: req.body.method,
      toolName: req.body.params?.name,
      tenantId: req.user?.tenantId,
      operation: 'mcp-proxy-request',
    });

    // Forward the request to MCP server with streaming support
    const response = await axios.post(`${mcpServerUrl}/`, req.body, {
      timeout: 300000, // 5 minute timeout
      headers,
      responseType: 'stream', // Get the response as a stream for real-time forwarding
    });

    // Set appropriate response headers for SSE
    res.set({
      'Content-Type': response.headers['content-type'] || 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
      'Access-Control-Allow-Origin': '*', // Allow CORS for SSE
      'Access-Control-Allow-Headers': 'Cache-Control',
    });

    // Set the response status
    res.status(response.status);

    // Cast response.data to Readable stream and pipe directly to the client for real-time streaming
    const stream = response.data as Readable;
    stream.pipe(res);

    // Handle stream completion
    stream.on('end', () => {
      logger.debug('MCP request completed successfully', {
        method: req.body.method,
        toolName: req.body.params?.name,
        responseStatus: response.status,
        tenantId: req.user?.tenantId,
        operation: 'mcp-proxy-success',
      });
    });

    // Handle stream errors
    stream.on('error', (streamError: Error) => {
      logger.error('MCP stream error', streamError, {
        method: req.body.method,
        toolName: req.body.params?.name,
        tenantId: req.user?.tenantId,
        operation: 'mcp-proxy-stream-error',
      });
      if (!res.headersSent) {
        res.status(500).json({
          error: 'Stream error during MCP request',
        });
      }
    });
  } catch (error) {
    logger.error('Error proxying MCP request', error, {
      method: req.body?.method,
      toolName: req.body?.params?.name,
      tenantId: req.user?.tenantId,
      operation: 'mcp-proxy-error',
    });

    // Only send error response if headers haven't been sent (streaming hasn't started)
    if (!res.headersSent) {
      // Check if this is an HTTP error from axios
      const httpError = error as { response?: { status?: number; data?: unknown } };
      if (httpError.response) {
        const status = httpError.response.status || 500;
        const errorData = httpError.response.data || (error as Error).message;

        return res.status(status).json({
          error: 'MCP server error',
          details: errorData,
        });
      }

      res.status(500).json({
        error: 'Internal server error while proxying MCP request',
      });
    } else {
      // If streaming has already started, we can't send a JSON error response
      // The client will handle the connection being terminated
      logger.error(
        'MCP proxy error after streaming started - client will handle connection termination',
        error,
        {
          method: req.body?.method,
          toolName: req.body?.params?.name,
          tenantId: req.user?.tenantId,
          operation: 'mcp-proxy-post-stream-error',
        }
      );
    }
  }
});
