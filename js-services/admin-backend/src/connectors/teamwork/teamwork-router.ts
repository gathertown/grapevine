import { Router } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { logger } from '../../utils/logger.js';
import { getFrontendUrl } from '../../utils/config.js';
import { TeamworkService } from './teamwork-service.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { getConfigValue, deleteConfigValue } from '../../config/index.js';
import {
  TEAMWORK_CONFIG_KEYS,
  TEAMWORK_ACCESS_TOKEN_KEY,
  TEAMWORK_API_DOMAIN_KEY,
  TEAMWORK_USER_NAME_KEY,
  TEAMWORK_INSTALLATION_ID_KEY,
} from './teamwork-config.js';
import { uninstallConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';

const teamworkRouter = Router();
const teamworkService = new TeamworkService();

const TEAMWORK_INTEGRATION_PATH = '/integrations/teamwork';

/**
 * GET /api/teamwork/install
 *
 * Returns the OAuth authorization URL for connecting Teamwork.
 * Requires admin authentication.
 */
teamworkRouter.get('/install', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  const authUrl = teamworkService.buildOAuthUrl(tenantId);
  res.json({ url: authUrl });
});

/**
 * GET /api/teamwork/oauth/callback
 *
 * OAuth callback handler for Teamwork.
 * Exchanges authorization code for access token and stores credentials.
 *
 * Query Parameters:
 * - code: Authorization code from Teamwork
 * - state: State parameter containing base64url-encoded tenant ID
 * - error: Error code if authorization failed
 */
teamworkRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error } = req.query;

  // Extract tenant ID from state (base64url-encoded JSON)
  let tenantId: string | undefined;
  try {
    if (state) {
      const stateData = JSON.parse(Buffer.from(String(state), 'base64url').toString());
      tenantId = stateData.tenantId;
    }
  } catch (e) {
    logger.error('Failed to parse Teamwork OAuth state', { state, error: e });
  }

  if (error) {
    logger.error('Teamwork OAuth error from provider', {
      error: String(error),
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}${TEAMWORK_INTEGRATION_PATH}?error=true`);
  }

  if (!code || !state || !tenantId) {
    return res.redirect(`${frontendUrl}${TEAMWORK_INTEGRATION_PATH}?error=true`);
  }

  try {
    await teamworkService.exchangeCodeForTokens(String(code), tenantId);
    await handleTeamworkConnected(tenantId);
    return res.redirect(`${frontendUrl}${TEAMWORK_INTEGRATION_PATH}?success=true`);
  } catch (err) {
    logger.error('Error in Teamwork OAuth callback', err);
    return res.redirect(`${frontendUrl}${TEAMWORK_INTEGRATION_PATH}?error=true`);
  }
});

/**
 * Handle post-OAuth connection tasks
 * - Trigger initial data backfill via SQS
 */
async function handleTeamworkConnected(tenantId: string): Promise<void> {
  try {
    logger.info('Teamwork OAuth successful, triggering initial ingest', { tenant_id: tenantId });

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering Teamwork backfill job', { tenant_id: tenantId });
      await sqsClient.sendTeamworkBackfillIngestJob(tenantId);
      logger.info('Teamwork backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping Teamwork backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Teamwork backfill job', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the OAuth flow if post-processing fails
  }
}

/**
 * GET /api/teamwork/status
 * Check Teamwork integration status
 */
teamworkRouter.get('/status', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const accessToken = await getConfigValue(TEAMWORK_ACCESS_TOKEN_KEY, tenantId);
    const apiDomain = await getConfigValue(TEAMWORK_API_DOMAIN_KEY, tenantId);
    const userName = await getConfigValue(TEAMWORK_USER_NAME_KEY, tenantId);
    const installationId = await getConfigValue(TEAMWORK_INSTALLATION_ID_KEY, tenantId);

    return res.json({
      connected: !!accessToken,
      configured: !!accessToken,
      access_token_present: !!accessToken,
      api_domain: apiDomain || null,
      user_name: userName || null,
      installation_id: installationId || null,
    });
  } catch (error) {
    logger.error('Failed to fetch Teamwork status', error);
    return res.status(500).json({ error: 'Failed to fetch Teamwork status' });
  }
});

/**
 * DELETE /api/teamwork/disconnect
 * Disconnect Teamwork integration by removing all config keys
 */
teamworkRouter.delete('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    // Delete all Teamwork config keys
    await Promise.all(TEAMWORK_CONFIG_KEYS.map((key) => deleteConfigValue(key, tenantId)));

    // Mark connector as disconnected in connector_installations table
    await uninstallConnector(tenantId, ConnectorType.Teamwork);

    return res.json({ success: true });
  } catch (error) {
    logger.error('Error disconnecting Teamwork', error);
    return res.status(500).json({ error: 'Failed to disconnect Teamwork' });
  }
});

export { teamworkRouter };
