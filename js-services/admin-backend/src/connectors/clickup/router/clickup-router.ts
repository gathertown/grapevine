import { Router } from 'express';

import { requireAdmin } from '../../../middleware/auth-middleware';
import { logger } from '../../../utils/logger';

import { clickupOauthRouter } from './clickup-oauth-router';
import { deleteClickupOauthToken } from '../clickup-config';
import { uninstallClickupConnector } from '../clickup-connector';

const clickupRouter = Router();

clickupRouter.use('', clickupOauthRouter);

clickupRouter.post('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    await deleteClickupOauthToken(tenantId);
    await uninstallClickupConnector(tenantId);
  } catch (error) {
    logger.error('Error disconnecting ClickUp', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error disconnecting ClickUp' });
  }

  logger.info('ClickUp OAuth token deleted and uninstalled successfully', {
    tenant_id: tenantId,
  });

  res.json({});
});

export { clickupRouter };
