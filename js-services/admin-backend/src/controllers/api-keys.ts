/**
 * API Keys Controller
 *
 * REST endpoints for managing API keys
 */

import { Router, Request, Response } from 'express';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { createApiKey, listApiKeys, deleteApiKey } from '../services/api-keys.js';
import { logger } from '../utils/logger.js';

const router = Router();

/**
 * POST /api/api-keys
 * Create a new API key for the authenticated user's tenant
 */
router.post('/', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(403).json({
        error: 'Tenant not found',
        details: 'User must belong to a provisioned tenant to create API keys',
      });
    }

    const { name } = req.body;
    if (!name || typeof name !== 'string' || name.trim().length === 0) {
      return res.status(400).json({
        error: 'Invalid request',
        details: 'name is required and must be a non-empty string',
      });
    }

    const createdBy = req.user?.id;
    const result = await createApiKey(tenantId, name.trim(), createdBy);

    logger.info('API key created via REST API', {
      tenantId,
      keyId: result.keyInfo.id,
      name: result.keyInfo.name,
      userId: req.user?.id,
    });

    res.status(201).json({
      apiKey: result.apiKey, // Full key returned only once
      keyInfo: result.keyInfo,
    });
  } catch (error) {
    logger.error('Failed to create API key', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
    });

    res.status(500).json({
      error: 'Failed to create API key',
      details: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

/**
 * GET /api/api-keys
 * List all API keys for the authenticated user's tenant
 */
router.get('/', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(403).json({
        error: 'Tenant not found',
        details: 'User must belong to a provisioned tenant to list API keys',
      });
    }

    const keys = await listApiKeys(tenantId);

    res.json({ keys });
  } catch (error) {
    logger.error('Failed to list API keys', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
    });

    res.status(500).json({
      error: 'Failed to list API keys',
      details: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

/**
 * DELETE /api/api-keys/:id
 * Delete an API key
 */
router.delete('/:id', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(403).json({
        error: 'Tenant not found',
        details: 'User must belong to a provisioned tenant to delete API keys',
      });
    }

    const { id } = req.params;
    if (!id) {
      return res.status(400).json({
        error: 'Invalid request',
        details: 'Key ID is required',
      });
    }

    const deleted = await deleteApiKey(tenantId, id);

    if (!deleted) {
      return res.status(404).json({
        error: 'API key not found',
        details: 'The specified API key does not exist',
      });
    }

    logger.info('API key deleted via REST API', {
      tenantId,
      keyId: id,
      userId: req.user?.id,
    });

    res.json({ success: true });
  } catch (error) {
    logger.error('Failed to delete API key', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      keyId: req.params.id,
    });

    res.status(500).json({
      error: 'Failed to delete API key',
      details: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

export { router as apiKeysRouter };
