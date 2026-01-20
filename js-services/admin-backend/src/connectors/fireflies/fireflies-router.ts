import { Router } from 'express';

import { requireAdmin } from '../../middleware/auth-middleware';
import { logger } from '../../utils/logger';
import { deleteFirefliesApiKey, saveFirefliesApiKey } from './fireflies-config';
import { installFirefliesConnector, uninstallFirefliesConnector } from './fireflies-connector';
import { triggerFirefliesBackfill } from './fireflies-jobs';

const firefliesRouter = Router();

interface ConnectReq {
  apiKey: string;
}

firefliesRouter.post('/connect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  const { apiKey } = req.body as ConnectReq;

  try {
    await installFirefliesConnector(tenantId, apiKey);
    await saveFirefliesApiKey(tenantId, apiKey);
    await triggerFirefliesBackfill(tenantId);
  } catch (error) {
    logger.error('Error connecting Fireflies', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error connecting Fireflies' });
  }

  logger.info('Fireflies API key saved and installed successfully', {
    tenant_id: tenantId,
  });

  res.json({});
});

firefliesRouter.post('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    await deleteFirefliesApiKey(tenantId);
    await uninstallFirefliesConnector(tenantId);
  } catch (error) {
    logger.error('Error disconnecting Fireflies', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error disconnecting Fireflies' });
  }

  logger.info('Fireflies API key deleted and uninstalled successfully', {
    tenant_id: tenantId,
  });

  res.json({});
});

export { firefliesRouter };
