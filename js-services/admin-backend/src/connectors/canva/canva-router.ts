/**
 * Canva connector routes for OAuth and configuration management.
 */

import { Router, type RequestHandler } from 'express';
import { CanvaService } from './canva-service.js';
import { deleteConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { uninstallConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { CANVA_CONFIG_KEYS } from './canva-config.js';
import { getFrontendUrl } from '../../utils/config.js';

/**
 * Trigger a Canva backfill for a tenant.
 */
async function sendCanvaBackfillIngestJob(tenantId: string): Promise<void> {
  if (isSqsConfigured()) {
    const sqsClient = getSqsClient();
    await sqsClient.sendCanvaBackfillIngestJob(tenantId);
    logger.info('Canva backfill job queued successfully', { tenant_id: tenantId });
  } else {
    logger.warn('SQS not configured - skipping Canva backfill', { tenant_id: tenantId });
  }
}

const router = Router();
const canvaService = new CanvaService();

/**
 * GET /oauth/initiate
 * Start the OAuth flow by redirecting to Canva authorization
 */
const initiateOAuth: RequestHandler = async (req, res) => {
  const { tenantId } = req.user ?? {};

  if (!tenantId) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }

  try {
    const authUrl = canvaService.buildOAuthUrl(tenantId);
    res.json({ authUrl });
  } catch (error) {
    logger.error(
      'Failed to initiate Canva OAuth',
      error instanceof Error ? error : new Error(String(error)),
      { tenant_id: tenantId }
    );
    res.status(500).json({ error: 'Failed to initiate OAuth' });
  }
};

/**
 * GET /oauth/callback
 * Handle OAuth callback from Canva
 */
const oauthCallback: RequestHandler = async (req, res) => {
  const { code, state, error: oauthError } = req.query;
  const frontendUrl = getFrontendUrl();

  // Handle error responses from Canva
  if (oauthError) {
    logger.error('Canva OAuth error response', undefined, {
      error: oauthError,
    });
    res.redirect(`${frontendUrl}/integrations/canva?error=true`);
    return;
  }

  // Validate required parameters
  if (typeof code !== 'string' || typeof state !== 'string') {
    logger.error('Missing code or state in Canva OAuth callback', undefined, {
      hasCode: typeof code === 'string',
      hasState: typeof state === 'string',
    });
    res.redirect(`${frontendUrl}/integrations/canva?error=true`);
    return;
  }

  try {
    // Parse state to get tenant ID
    const { tenantId } = canvaService.parseOAuthState(state);

    // Exchange code for tokens (includes PKCE verification)
    await canvaService.exchangeCodeForTokens(code, state, tenantId);

    logger.info('Canva OAuth completed successfully', { tenant_id: tenantId });

    // Trigger backfill for the new connection
    await sendCanvaBackfillIngestJob(tenantId);

    res.redirect(`${frontendUrl}/integrations/canva?success=true`);
  } catch (error) {
    logger.error(
      'Canva OAuth callback failed',
      error instanceof Error ? error : new Error(String(error))
    );
    res.redirect(`${frontendUrl}/integrations/canva?error=true`);
  }
};

/**
 * POST /disconnect
 * Disconnect Canva integration
 */
const disconnect: RequestHandler = async (req, res) => {
  const { tenantId } = req.user ?? {};

  if (!tenantId) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }

  try {
    // Delete all config values
    await Promise.all(CANVA_CONFIG_KEYS.map((key) => deleteConfigValue(key, tenantId)));

    // Reset backfill state for fresh reconnect
    await canvaService.resetBackfillState(tenantId);

    // Mark connector as disconnected
    await uninstallConnector(tenantId, ConnectorType.Canva);

    logger.info('Canva disconnected', { tenant_id: tenantId });
    res.json({ success: true });
  } catch (error) {
    logger.error(
      'Failed to disconnect Canva',
      error instanceof Error ? error : new Error(String(error)),
      { tenant_id: tenantId }
    );
    res.status(500).json({ error: 'Failed to disconnect' });
  }
};

/**
 * POST /backfill
 * Trigger a full backfill
 */
const triggerBackfill: RequestHandler = async (req, res) => {
  const { tenantId } = req.user ?? {};

  if (!tenantId) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }

  try {
    await sendCanvaBackfillIngestJob(tenantId);
    logger.info('Canva backfill triggered', { tenant_id: tenantId });
    res.json({ success: true });
  } catch (error) {
    logger.error(
      'Failed to trigger Canva backfill',
      error instanceof Error ? error : new Error(String(error)),
      { tenant_id: tenantId }
    );
    res.status(500).json({ error: 'Failed to trigger backfill' });
  }
};

/**
 * GET /install
 * Return OAuth initiation URL (called from frontend API)
 */
const install: RequestHandler = async (req, res) => {
  const { tenantId } = req.user ?? {};

  if (!tenantId) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }

  try {
    const url = canvaService.buildOAuthUrl(tenantId);
    res.json({ url });
  } catch (error) {
    logger.error(
      'Failed to generate Canva install URL',
      error instanceof Error ? error : new Error(String(error)),
      { tenant_id: tenantId }
    );
    res.status(500).json({ error: 'Failed to generate install URL' });
  }
};

// Register routes
router.get('/install', install);
router.get('/oauth/initiate', initiateOAuth);
router.get('/oauth/callback', oauthCallback);
router.post('/disconnect', disconnect);
router.delete('/disconnect', disconnect); // Support both POST and DELETE
router.post('/backfill', triggerBackfill);

export { router as canvaRouter };
