import { Router } from 'express';

import { requireAdmin } from '../../middleware/auth-middleware';
import { logger } from '../../utils/logger';
import { deletePylonApiKey, savePylonApiKey } from './pylon-config';
import { installPylonConnector, uninstallPylonConnector } from './pylon-connector';
import { triggerPylonBackfill, triggerPylonIncrementalBackfill } from './pylon-jobs';

const pylonRouter = Router();

interface ConnectReq {
  apiKey: string;
}

pylonRouter.post('/connect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  const { apiKey } = req.body as ConnectReq;

  try {
    // Save credentials FIRST - if this fails, we don't want to create an orphan installation
    await savePylonApiKey(tenantId, apiKey);
    await installPylonConnector(tenantId, apiKey);
    await triggerPylonBackfill(tenantId);
  } catch (error) {
    logger.error('Error connecting Pylon', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error connecting Pylon' });
  }

  logger.info('Pylon API key saved and installed successfully', {
    tenant_id: tenantId,
  });

  res.json({});
});

pylonRouter.post('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    await deletePylonApiKey(tenantId);
    await uninstallPylonConnector(tenantId);
  } catch (error) {
    logger.error('Error disconnecting Pylon', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error disconnecting Pylon' });
  }

  logger.info('Pylon API key deleted and uninstalled successfully', {
    tenant_id: tenantId,
  });

  res.json({});
});

interface SyncReq {
  lookbackHours?: number;
}

pylonRouter.post('/sync', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  const { lookbackHours } = req.body as SyncReq;

  try {
    await triggerPylonIncrementalBackfill(tenantId, lookbackHours ?? 2);
  } catch (error) {
    logger.error('Error triggering Pylon sync', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error triggering Pylon sync' });
  }

  logger.info('Pylon incremental sync triggered successfully', {
    tenant_id: tenantId,
    lookback_hours: lookbackHours ?? 2,
  });

  res.json({ message: 'Sync triggered successfully' });
});

export { pylonRouter };
