import { Router } from 'express';
import { getControlDbPool } from '../control-db.js';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { logger } from '../utils/logger.js';
import { PsqlFeatureStore } from '../features/feature-store.js';
import { FeatureService } from '../features/feature-service.js';

export const featuresRouter = Router();

const getFeatures = (tenantId: string) => {
  const pool = getControlDbPool();
  if (!pool) {
    throw new Error('Failed to acquire control database pool');
  }

  const service = new FeatureService(new PsqlFeatureStore(pool));
  return service.getAllFeaturesForTenant(tenantId);
};

/**
 * GET /api/features
 * Get the feature enablement status for the current tenant
 */
featuresRouter.get('/', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const features = await getFeatures(tenantId);

    return res.json({ tenantId, features });
  } catch (error) {
    logger.error('Failed to fetch features', error, {
      tenant_id: req.user?.tenantId,
    });
    return res.status(500).json({ error: 'Failed to fetch features' });
  }
});
