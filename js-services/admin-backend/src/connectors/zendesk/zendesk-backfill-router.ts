import { Router } from 'express';

import { isSqsConfigured, getSqsClient } from '../../jobs/sqs-client';
import { requireAdmin } from '../../middleware/auth-middleware';
import { logger } from '../../utils/logger';

const zendeskBackfillRouter = Router();

zendeskBackfillRouter.post('/backfill', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    if (!isSqsConfigured()) {
      return res.status(500).json({ error: 'SQS not configured' });
    }

    const sqsClient = getSqsClient();
    await sqsClient.sendZendeskBackfillIngestJob(tenantId);

    logger.info('Queued Zendesk root backfill job', { tenant_id: tenantId });

    return res.json({
      success: true,
      message: 'Zendesk root backfill job triggered',
    });
  } catch (error) {
    logger.error('Failed to trigger Zendesk root backfill', error, {
      tenant_id: req.user?.tenantId,
    });
    return res.status(500).json({ error: 'Failed to trigger Zendesk root backfill' });
  }
});

export { zendeskBackfillRouter };
