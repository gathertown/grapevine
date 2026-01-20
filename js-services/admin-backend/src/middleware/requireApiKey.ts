/**
 * API Key Authentication Middleware
 * Verifies API key from Authorization header for external REST API access
 */

import type { Request, Response, NextFunction } from 'express';
import { verifyApiKey } from '../services/api-key-auth.js';
import { logger } from '../utils/logger.js';

// Extend Express Request to include tenantId from API key auth
declare global {
  namespace Express {
    interface Request {
      tenantId?: string;
    }
  }
}

/**
 * Middleware that verifies API key and injects tenant ID into request
 */
export async function requireApiKey(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const authHeader = req.headers.authorization;

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      logger.debug('Missing or invalid Authorization header');
      res.status(401).json({
        error: 'Authentication required. Please provide a valid API key.',
      });
      return;
    }

    const apiKey = authHeader.substring(7); // Remove "Bearer " prefix

    // Verify the API key
    const tenantId = await verifyApiKey(apiKey);

    if (!tenantId) {
      logger.debug('API key verification failed');
      res.status(401).json({
        error: 'Invalid API key',
      });
      return;
    }

    // Attach tenant ID to request
    req.tenantId = tenantId;

    next();
  } catch (error) {
    logger.error('Error in requireApiKey middleware', {
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    res.status(500).json({
      error: 'Internal server error',
    });
  }
}
