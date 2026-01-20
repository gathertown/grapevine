import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client';
import { logger } from '../../utils/logger';

async function triggerAsanaBackfill(tenantId: string): Promise<void> {
  try {
    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      await sqsClient.sendAsanaBackfillIngestJob(tenantId);
      logger.info('Asana backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping Asana backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Asana backfill job', error, { tenant_id: tenantId });
  }
}

export { triggerAsanaBackfill };
