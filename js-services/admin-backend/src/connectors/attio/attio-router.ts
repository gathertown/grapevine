import { Router } from 'express';
import { SSMClient } from '@corporate-context/backend-common';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { logger } from '../../utils/logger.js';
import { getFrontendUrl } from '../../utils/config.js';
import { AttioService } from './attio-service.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { getConfigValue, deleteConfigValue } from '../../config/index.js';
import {
  ATTIO_CONFIG_KEYS,
  ATTIO_ACCESS_TOKEN_KEY,
  ATTIO_WORKSPACE_ID_KEY,
  ATTIO_WEBHOOK_ID_KEY,
} from './attio-config.js';
import { uninstallConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';

const attioRouter = Router();
const attioService = new AttioService();

const ATTIO_INTEGRATION_PATH = '/integrations/attio';

/**
 * GET /api/attio/install
 *
 * Returns the OAuth authorization URL for connecting Attio.
 * Requires admin authentication.
 */
attioRouter.get('/install', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }
  const authUrl = attioService.buildOAuthUrl(tenantId);
  res.json({ url: authUrl });
});

/**
 * GET /api/attio/oauth/callback
 *
 * OAuth callback handler for Attio.
 * Exchanges authorization code for access token and stores credentials.
 *
 * Query Parameters:
 * - code: Authorization code from Attio
 * - state: State parameter containing UUID and tenant ID
 * - error: Error code if authorization failed
 * - error_description: Human-readable error description
 */
attioRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description } = req.query;

  // Extract tenant ID from state (format: UUID_tenantId)
  const stateStr = state ? String(state) : '';
  const stateParts = stateStr.split('_');
  const tenantId = stateParts.length >= 2 ? stateParts[stateParts.length - 1] : undefined;

  if (error) {
    logger.error('Attio OAuth error from provider', {
      error: String(error),
      error_description: String(error_description || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}${ATTIO_INTEGRATION_PATH}?error=true`);
  }

  if (!code || !state || !tenantId) {
    return res.redirect(`${frontendUrl}${ATTIO_INTEGRATION_PATH}?error=true`);
  }

  try {
    await attioService.exchangeCodeForTokens(String(code), tenantId);
    await handleAttioConnected(tenantId);
    return res.redirect(`${frontendUrl}${ATTIO_INTEGRATION_PATH}?success=true`);
  } catch (err) {
    logger.error('Error in Attio OAuth callback', err);
    return res.redirect(`${frontendUrl}${ATTIO_INTEGRATION_PATH}?error=true`);
  }
});

/**
 * Handle post-OAuth connection tasks
 * - Trigger initial data backfill via SQS
 */
async function handleAttioConnected(tenantId: string): Promise<void> {
  try {
    logger.info('Attio OAuth successful, triggering initial ingest', { tenant_id: tenantId });

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering Attio backfill job', { tenant_id: tenantId });
      await sqsClient.sendAttioBackfillIngestJob(tenantId);
      logger.info('Attio backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping Attio backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Attio backfill job', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the OAuth flow if post-processing fails
  }
}

/**
 * GET /api/attio/status
 * Check Attio integration status
 */
attioRouter.get('/status', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const accessToken = await getConfigValue(ATTIO_ACCESS_TOKEN_KEY, tenantId);
    const workspaceId = await getConfigValue(ATTIO_WORKSPACE_ID_KEY, tenantId);

    return res.json({
      connected: !!accessToken,
      configured: !!accessToken,
      access_token_present: !!accessToken,
      workspace_id: workspaceId || null,
    });
  } catch (error) {
    logger.error('Failed to fetch Attio status', error);
    return res.status(500).json({ error: 'Failed to fetch Attio status' });
  }
});

/**
 * DELETE /api/attio/disconnect
 * Disconnect Attio integration by removing webhook and all config keys
 */
attioRouter.delete('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    // Get credentials before deleting to clean up webhook
    const accessToken = (await getConfigValue(ATTIO_ACCESS_TOKEN_KEY, tenantId)) as string | null;
    const webhookId = (await getConfigValue(ATTIO_WEBHOOK_ID_KEY, tenantId)) as string | null;

    // Delete webhook from Attio (best effort - don't fail disconnect if this fails)
    if (accessToken && webhookId) {
      try {
        await attioService.deleteWebhook(accessToken, webhookId);
        logger.info('Deleted Attio webhook during disconnect', {
          tenant_id: tenantId,
          webhook_id: webhookId,
        });
      } catch (webhookError) {
        logger.warn('Failed to delete Attio webhook during disconnect', {
          tenant_id: tenantId,
          webhook_id: webhookId,
          error: webhookError instanceof Error ? webhookError.message : String(webhookError),
        });
        // Continue with disconnect even if webhook deletion fails
      }
    }

    // Delete Attio signing secret from SSM (best effort)
    try {
      const ssmClient = new SSMClient();
      const parameterName = `/${tenantId}/signing-secret/attio`;
      await ssmClient.deleteParameter(parameterName);
      logger.info('Deleted Attio signing secret during disconnect', { tenant_id: tenantId });
    } catch (ssmError) {
      logger.warn('Failed to delete Attio signing secret during disconnect', {
        tenant_id: tenantId,
        error: ssmError instanceof Error ? ssmError.message : String(ssmError),
      });
      // Continue with disconnect even if SSM deletion fails
    }

    // Delete all Attio config keys
    await Promise.all(ATTIO_CONFIG_KEYS.map((key) => deleteConfigValue(key, tenantId)));

    // Mark connector as disconnected in connector_installations table
    await uninstallConnector(tenantId, ConnectorType.Attio);

    return res.json({ success: true });
  } catch (error) {
    logger.error('Error disconnecting Attio', error);
    return res.status(500).json({ error: 'Failed to disconnect Attio' });
  }
});

export { attioRouter };
