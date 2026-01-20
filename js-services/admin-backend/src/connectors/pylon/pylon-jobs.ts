import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client';
import { logger } from '../../utils/logger';

async function triggerPylonBackfill(tenantId: string): Promise<void> {
  try {
    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      await sqsClient.sendPylonBackfillIngestJob(tenantId);
      logger.info('Pylon backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.error('SQS not configured - skipping Pylon backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Pylon backfill job', error, { tenant_id: tenantId });
  }
}

/**
 * Trigger an incremental backfill for Pylon.
 * This syncs recently updated issues without doing a full backfill.
 */
async function triggerPylonIncrementalBackfill(
  tenantId: string,
  lookbackHours: number = 2
): Promise<void> {
  try {
    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      await sqsClient.sendPylonIncrementalBackfillJob(tenantId, lookbackHours);
      logger.info('Pylon incremental backfill job queued successfully', {
        tenant_id: tenantId,
        lookback_hours: lookbackHours,
      });
    } else {
      logger.error('SQS not configured - skipping Pylon incremental backfill', {
        tenant_id: tenantId,
      });
    }
  } catch (error) {
    logger.error('Failed to trigger Pylon incremental backfill job', error, {
      tenant_id: tenantId,
    });
  }
}

export { triggerPylonBackfill, triggerPylonIncrementalBackfill };
