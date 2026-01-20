import { Router } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { logger, LogContext } from '../../utils/logger.js';
import { getConfigValue } from '../../config/index.js';
import { GATHER_API_URL } from '@corporate-context/backend-common';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';

const gatherRouter = Router();

/**
 * Trigger a Gather API backfill ingest job.
 */
gatherRouter.post('/backfill', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({
      error: 'No tenant found for organization',
    });
  }

  await LogContext.run(
    {
      operation: 'gather-backfill',
      tenant_id: tenantId,
    },
    async () => {
      try {
        logger.info('Triggering Gather API backfill');

        // Check if SQS is configured
        if (!isSqsConfigured()) {
          logger.error('SQS not configured - backfill cannot be started');
          return res.status(500).json({
            error: 'SQS not configured - missing AWS credentials or region',
          });
        }
        const apiKey = await getConfigValue('GATHER_API_KEY', tenantId);
        if (!apiKey) {
          logger.error('No Gather API key configured for tenant');
          return res.status(400).json({
            error: 'No Gather API key configured for organization',
          });
        }

        const response = await fetch(GATHER_API_URL, {
          method: 'GET',
          headers: {
            'x-api-key': apiKey as string,
          },
        });
        const data = await response.json();
        if (!response.ok) {
          logger.error('Error [handleGatherWebhookUpdate]: Gather API key validation failed', {
            tenant_id: tenantId,
            status: response.status,
          });
          throw new Error('Failed to get Gather space ID');
        }

        await installConnector({
          tenantId,
          type: ConnectorType.Gather,
          externalId: data.spaceId,
        });

        const sqsClient = getSqsClient();
        await sqsClient.sendGatherApiIngestJob(tenantId, data.spaceId);

        logger.info('Gather API backfill job queued successfully');

        res.json({
          success: true,
          message: 'Gather backfill job has been queued successfully',
        });
      } catch (error) {
        logger.error('Error triggering Gather backfill', error);
        res.status(500).json({
          error: `Failed to trigger Gather backfill: ${error.message}`,
        });
      }
    }
  );
});

export { gatherRouter };
