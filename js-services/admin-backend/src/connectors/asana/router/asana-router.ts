import { Router } from 'express';
import { asanaOauthRouter } from './asana-oauth-router';
import { requireAdmin } from '../../../middleware/auth-middleware';
import { logger } from '../../../utils/logger';
import { saveAsanaServiceAccountToken } from '../asana-config';
import { triggerAsanaBackfill } from '../asana-jobs';
import { installAsanaConnector } from './asana-connector';

const asanaRouter = Router();

asanaRouter.use('', asanaOauthRouter);

interface ServiceAccountAuthReq {
  token: string;
}

asanaRouter.post('/service-account-auth', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  const { token } = req.body as ServiceAccountAuthReq;

  await saveAsanaServiceAccountToken(tenantId, token);
  await installAsanaConnector(tenantId, token);
  await triggerAsanaBackfill(tenantId);

  logger.info('Asana service account token saved completed successfully', {
    tenant_id: tenantId,
  });

  res.json({});
});

export { asanaRouter };
