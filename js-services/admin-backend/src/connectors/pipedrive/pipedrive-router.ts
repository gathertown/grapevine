/**
 * Pipedrive OAuth Router
 *
 * Handles OAuth authorization flow and connector management.
 */

import { Router } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { logger } from '../../utils/logger.js';
import { getFrontendUrl } from '../../utils/config.js';
import { PipedriveService } from './pipedrive-service.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { getConfigValue, deleteConfigValue } from '../../config/index.js';
import {
  PIPEDRIVE_CONFIG_KEYS,
  PIPEDRIVE_ACCESS_TOKEN_KEY,
  PIPEDRIVE_API_DOMAIN_KEY,
  PIPEDRIVE_COMPANY_NAME_KEY,
} from './pipedrive-config.js';
import { uninstallConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';

const pipedriveRouter = Router();
const pipedriveService = new PipedriveService();

const PIPEDRIVE_INTEGRATION_PATH = '/integrations/pipedrive';

/**
 * GET /api/pipedrive/install
 *
 * Returns the OAuth authorization URL for connecting Pipedrive.
 * Requires admin authentication.
 */
pipedriveRouter.get('/install', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const authUrl = pipedriveService.buildOAuthUrl(tenantId);
    res.json({ url: authUrl });
  } catch (error) {
    logger.error('Failed to build Pipedrive OAuth URL', error);
    return res.status(500).json({ error: 'Failed to build OAuth URL' });
  }
});

/**
 * GET /api/pipedrive/oauth/callback
 *
 * OAuth callback handler for Pipedrive.
 * Exchanges authorization code for access token and stores credentials.
 *
 * Query Parameters:
 * - code: Authorization code from Pipedrive
 * - state: State parameter containing tenant ID (base64url encoded)
 * - error: Error code if authorization failed
 * - error_description: Human-readable error description
 */
pipedriveRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description } = req.query;

  // Parse tenant ID from state
  let tenantId: string | undefined;
  try {
    if (state) {
      const parsed = pipedriveService.parseOAuthState(String(state));
      tenantId = parsed.tenantId;
    }
  } catch {
    logger.error('Invalid Pipedrive OAuth state', { state });
    return res.redirect(`${frontendUrl}${PIPEDRIVE_INTEGRATION_PATH}?error=invalid_state`);
  }

  if (error) {
    logger.error('Pipedrive OAuth error from provider', {
      error: String(error),
      error_description: String(error_description || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}${PIPEDRIVE_INTEGRATION_PATH}?error=true`);
  }

  if (!code || !tenantId) {
    return res.redirect(`${frontendUrl}${PIPEDRIVE_INTEGRATION_PATH}?error=missing_params`);
  }

  try {
    await pipedriveService.exchangeCodeForTokens(String(code), tenantId);
    await handlePipedriveConnected(tenantId);
    return res.redirect(`${frontendUrl}${PIPEDRIVE_INTEGRATION_PATH}?success=true`);
  } catch (err) {
    logger.error('Error in Pipedrive OAuth callback', err);
    return res.redirect(`${frontendUrl}${PIPEDRIVE_INTEGRATION_PATH}?error=true`);
  }
});

/**
 * Handle post-OAuth connection tasks
 * - Reset backfill state
 * - Trigger initial data backfill via SQS
 */
async function handlePipedriveConnected(tenantId: string): Promise<void> {
  try {
    logger.info('Pipedrive OAuth successful, triggering initial ingest', { tenant_id: tenantId });

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering Pipedrive backfill job', { tenant_id: tenantId });
      await sqsClient.sendPipedriveBackfillIngestJob(tenantId);
      logger.info('Pipedrive backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping Pipedrive backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Pipedrive backfill job', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the OAuth flow if post-processing fails
  }
}

/**
 * GET /api/pipedrive/status
 * Check Pipedrive integration status
 */
pipedriveRouter.get('/status', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    // Use unified config manager - it auto-routes to SSM for sensitive keys
    const accessToken = await getConfigValue(PIPEDRIVE_ACCESS_TOKEN_KEY, tenantId);
    const apiDomain = await getConfigValue(PIPEDRIVE_API_DOMAIN_KEY, tenantId);
    const companyName = await getConfigValue(PIPEDRIVE_COMPANY_NAME_KEY, tenantId);

    return res.json({
      connected: !!accessToken,
      configured: !!accessToken,
      access_token_present: !!accessToken,
      api_domain: apiDomain || null,
      company_name: companyName || null,
    });
  } catch (error) {
    logger.error('Failed to fetch Pipedrive status', error);
    return res.status(500).json({ error: 'Failed to fetch Pipedrive status' });
  }
});

/**
 * DELETE /api/pipedrive/disconnect
 * Disconnect Pipedrive integration by removing all config keys
 */
pipedriveRouter.delete('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    // Delete all Pipedrive config keys using unified config manager
    // Sensitive keys auto-route to SSM, non-sensitive to DB
    await Promise.all(PIPEDRIVE_CONFIG_KEYS.map((key) => deleteConfigValue(key, tenantId)));

    // Mark connector as disconnected
    await uninstallConnector(tenantId, ConnectorType.Pipedrive);

    logger.info('Disconnected Pipedrive', { tenant_id: tenantId });
    return res.json({ success: true });
  } catch (error) {
    logger.error('Error disconnecting Pipedrive', error);
    return res.status(500).json({ error: 'Failed to disconnect Pipedrive' });
  }
});

/**
 * POST /api/pipedrive/refresh-token
 * Manually refresh the Pipedrive access token
 */
pipedriveRouter.post('/refresh-token', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    await pipedriveService.refreshAccessToken(tenantId);
    return res.json({ success: true });
  } catch (error) {
    logger.error('Failed to refresh Pipedrive token', error);
    return res.status(500).json({ error: 'Failed to refresh token' });
  }
});

export { pipedriveRouter };
