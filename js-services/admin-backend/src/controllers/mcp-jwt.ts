/**
 * Agent JWT endpoint - generates internal JWT tokens for MCP agent chat
 */

import { Router, Request, Response } from 'express';
import { logger } from '../utils/logger.js';
import { generateInternalJWT } from '../jwt-generator.js';

const router = Router();

/**
 * POST /api/mcp/jwt
 * Generate an internal JWT token for MCP agent authentication
 */
router.post('/jwt', async (req: Request, res: Response) => {
  try {
    if (!req.user || !req.user.tenantId) {
      logger.warn('Unauthorized agent JWT request - no user or tenant ID', {
        hasUser: !!req.user,
        hasTenantId: !!req.user?.tenantId,
        operation: 'agent-jwt-unauthorized',
      });
      res.status(401).json({ error: 'Unauthorized - tenant ID required' });
      return;
    }

    const tenantId = req.user.tenantId;
    const email = req.user.email;
    const expiresIn = '1h'; // Token valid for 1 hour

    logger.debug('Generating agent JWT', {
      tenantId,
      userId: req.user.id,
      email,
      operation: 'agent-jwt-generation',
    });

    const token = await generateInternalJWT(tenantId, expiresIn, email);

    res.json({
      token,
      expiresIn,
    });
  } catch (error) {
    logger.error(
      'Failed to generate agent JWT',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId: req.user?.tenantId,
        operation: 'agent-jwt-error',
      }
    );
    res.status(500).json({ error: 'Failed to generate authentication token' });
  }
});

export { router as mcpJwtRouter };
