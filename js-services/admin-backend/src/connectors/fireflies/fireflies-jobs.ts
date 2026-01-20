import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client';
import { logger } from '../../utils/logger';

async function triggerFirefliesBackfill(tenantId: string): Promise<void> {
  try {
    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      await sqsClient.sendFirefliesBackfillIngestJob(tenantId);
      logger.info('Fireflies backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.error('SQS not configured - skipping Fireflies backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Fireflies backfill job', error, { tenant_id: tenantId });
  }
}

export { triggerFirefliesBackfill };
