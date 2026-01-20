import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client';
import { logger } from '../../utils/logger';

async function triggerPostHogBackfill(tenantId: string): Promise<void> {
  try {
    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      await sqsClient.sendPostHogBackfillIngestJob(tenantId);
      logger.info('PostHog backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.error('SQS not configured - skipping PostHog backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger PostHog backfill job', error, { tenant_id: tenantId });
  }
}

export { triggerPostHogBackfill };
