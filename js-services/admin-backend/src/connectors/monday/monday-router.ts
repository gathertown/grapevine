/**
 * Monday.com Router
 *
 * Handles OAuth flow, status checks, and disconnect for Monday.com integration.
 */

import { Router } from 'express';
import { SSMClient } from '@corporate-context/backend-common';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { logger } from '../../utils/logger.js';
import { getFrontendUrl } from '../../utils/config.js';
import { mondayService } from './monday-service.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { getConfigValue, deleteConfigValue } from '../../config/index.js';
import {
  MONDAY_CONFIG_KEYS,
  MONDAY_ACCESS_TOKEN_KEY,
  MONDAY_ACCOUNT_ID_KEY,
  MONDAY_ACCOUNT_NAME_KEY,
  resetMondayBackfillState,
} from './monday-config.js';
import { uninstallConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';

const mondayRouter = Router();

const MONDAY_INTEGRATION_PATH = '/integrations/monday';

/**
 * GET /api/monday/install
 *
 * Returns the OAuth authorization URL for connecting Monday.com.
 * Requires admin authentication.
 */
mondayRouter.get('/install', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const authUrl = mondayService.buildOAuthUrl(tenantId);
    res.json({ url: authUrl });
  } catch (error) {
    logger.error('Failed to build Monday.com OAuth URL', error, { tenant_id: tenantId });
    return res.status(500).json({ error: 'Failed to initiate Monday.com OAuth' });
  }
});

/**
 * GET /api/monday/oauth/callback
 *
 * OAuth callback handler for Monday.com.
 * Exchanges authorization code for access token and stores credentials.
 *
 * Query Parameters:
 * - code: Authorization code from Monday.com
 * - state: State parameter containing UUID and tenant ID
 * - error: Error code if authorization failed
 * - error_description: Human-readable error description
 */
mondayRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description } = req.query;

  // Extract tenant ID from state (base64url encoded JSON: { tenantId })
  let tenantId: string | undefined;
  try {
    if (state) {
      const decoded = JSON.parse(Buffer.from(String(state), 'base64url').toString());
      tenantId = decoded.tenantId;
    }
  } catch (parseError) {
    logger.error('Failed to parse Monday.com OAuth state', {
      error: parseError instanceof Error ? parseError.message : String(parseError),
    });
  }

  if (error) {
    logger.error('Monday.com OAuth error from provider', {
      error: String(error),
      error_description: String(error_description || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}${MONDAY_INTEGRATION_PATH}?error=true`);
  }

  if (!code || !state || !tenantId) {
    logger.error('Missing Monday.com OAuth callback parameters', {
      has_code: !!code,
      has_state: !!state,
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}${MONDAY_INTEGRATION_PATH}?error=true`);
  }

  try {
    await mondayService.exchangeCodeForTokens(String(code), tenantId);
    await handleMondayConnected(tenantId);
    return res.redirect(`${frontendUrl}${MONDAY_INTEGRATION_PATH}?success=true`);
  } catch (err) {
    logger.error('Error in Monday.com OAuth callback', err, { tenant_id: tenantId });
    return res.redirect(`${frontendUrl}${MONDAY_INTEGRATION_PATH}?error=true`);
  }
});

/**
 * Handle post-OAuth connection tasks
 * - Trigger initial data backfill via SQS
 */
async function handleMondayConnected(tenantId: string): Promise<void> {
  try {
    logger.info('Monday.com OAuth successful, triggering initial ingest', { tenant_id: tenantId });

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering Monday.com backfill job', { tenant_id: tenantId });
      await sqsClient.sendMondayBackfillIngestJob(tenantId);
      logger.info('Monday.com backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping Monday.com backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Monday.com backfill job', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the OAuth flow if post-processing fails
  }
}

/**
 * GET /api/monday/status
 * Check Monday.com integration status
 */
mondayRouter.get('/status', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const accessToken = await getConfigValue(MONDAY_ACCESS_TOKEN_KEY, tenantId);
    const accountId = await getConfigValue(MONDAY_ACCOUNT_ID_KEY, tenantId);
    const accountName = await getConfigValue(MONDAY_ACCOUNT_NAME_KEY, tenantId);

    return res.json({
      connected: !!accessToken,
      configured: !!accessToken,
      access_token_present: !!accessToken,
      account_id: accountId || null,
      account_name: accountName || null,
    });
  } catch (error) {
    logger.error('Failed to fetch Monday.com status', error);
    return res.status(500).json({ error: 'Failed to fetch Monday.com status' });
  }
});

/**
 * DELETE /api/monday/disconnect
 * Disconnect Monday.com integration by removing all config keys
 */
mondayRouter.delete('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    // Delete Monday.com signing secret from SSM (best effort)
    try {
      const ssmClient = new SSMClient();
      const parameterName = `/${tenantId}/signing-secret/monday`;
      await ssmClient.deleteParameter(parameterName);
      logger.info('Deleted Monday.com signing secret during disconnect', { tenant_id: tenantId });
    } catch (ssmError) {
      logger.warn('Failed to delete Monday.com signing secret during disconnect', {
        tenant_id: tenantId,
        error: ssmError instanceof Error ? ssmError.message : String(ssmError),
      });
      // Continue with disconnect even if SSM deletion fails
    }

    // Delete all Monday.com config keys
    await Promise.all(MONDAY_CONFIG_KEYS.map((key) => deleteConfigValue(key, tenantId)));

    // Reset backfill state to allow fresh sync on reconnect
    await resetMondayBackfillState(tenantId);

    // Mark connector as disconnected in connector_installations table
    await uninstallConnector(tenantId, ConnectorType.Monday);

    logger.info('Monday.com disconnected', { tenant_id: tenantId });
    return res.json({ success: true });
  } catch (error) {
    logger.error('Error disconnecting Monday.com', error, { tenant_id: tenantId });
    return res.status(500).json({ error: 'Failed to disconnect Monday.com' });
  }
});

export { mondayRouter };
