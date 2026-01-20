import { Router } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { logger } from '../../utils/logger.js';
import { getFrontendUrl } from '../../utils/config.js';
import { HubSpotService } from './hubspot-service.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';

const hubspotRouter = Router();
const hubspotService = new HubSpotService();

hubspotRouter.get('/install', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }
  const authUrl = hubspotService.buildOAuthUrl(tenantId);
  res.json({ url: authUrl });
});

hubspotRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description } = req.query;

  // Extract tenant ID from state if present
  const tenantId = state ? String(state).split('_')[1] : undefined;

  if (error) {
    logger.error('HubSpot OAuth error from provider', {
      error: String(error),
      error_description: String(error_description || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/integrations/hubspot?error=true`);
  }

  if (!code || !state || !tenantId) {
    logger.error('Missing required OAuth callback parameters', {
      has_code: !!code,
      has_state: !!state,
      has_tenant_id: !!tenantId,
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/integrations/hubspot?error=true`);
  }

  try {
    await hubspotService.exchangeCodeForTokens(String(code), tenantId);

    // Trigger HubSpot data backfill after successful OAuth
    await handleHubSpotConnected(tenantId);

    return res.redirect(`${frontendUrl}/integrations/hubspot?success=true`);
  } catch (error) {
    logger.error('Error in HubSpot OAuth callback', {
      error,
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/integrations/hubspot?error=true`);
  }
});

async function handleHubSpotConnected(tenantId: string): Promise<void> {
  try {
    logger.info('HubSpot OAuth successful, triggering initial ingest', { tenant_id: tenantId });

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering HubSpot backfill job', { tenant_id: tenantId });
      await sqsClient.sendHubSpotBackfillIngestJob(tenantId);
      logger.info('HubSpot backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping HubSpot backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger HubSpot backfill job', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the OAuth flow if post-processing fails
  }
}

export { hubspotRouter };
