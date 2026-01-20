import { Router } from 'express';
import { requireUser } from '../../middleware/auth-middleware';
import { saveConfigValue, deleteConfigValue, getConfigValue } from '../../config';
import { logger } from '../../utils/logger';
import { installConnector, uninstallConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { isSqsConfigured, getSqsClient } from '../../jobs/sqs-client.js';

// Intercom OAuth configuration
const INTERCOM_TOKEN_URL = 'https://api.intercom.io/auth/eagle/token';

// Config keys for storing Intercom OAuth tokens
const INTERCOM_CONFIG_KEY_ACCESS_TOKEN = 'INTERCOM_ACCESS_TOKEN';
const INTERCOM_CONFIG_KEY_TOKEN_TYPE = 'INTERCOM_TOKEN_TYPE';

const intercomOAuthRouter = Router();

function getIntercomClientId(): string {
  const value = process.env.INTERCOM_CLIENT_ID;
  if (!value) {
    throw new Error('INTERCOM_CLIENT_ID environment variable is required for Intercom OAuth');
  }
  return value;
}

function getIntercomClientSecret(): string {
  const value = process.env.INTERCOM_CLIENT_SECRET;
  if (!value) {
    throw new Error('INTERCOM_CLIENT_SECRET environment variable is required for Intercom OAuth');
  }
  return value;
}

/**
 * POST /api/intercom/callback
 * Handles OAuth callback and exchanges code for tokens
 */
intercomOAuthRouter.post('/callback', requireUser, async (req, res) => {
  try {
    const { code, state } = req.body;
    const tenantId = req.user?.tenantId;

    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    if (!code || !state) {
      return res.status(400).json({ error: 'Missing code or state' });
    }

    logger.info('Processing Intercom OAuth callback', {
      tenantId,
      hasCode: !!code,
      hasState: !!state,
    });

    // Exchange code for tokens
    // Intercom uses JSON format for token exchange
    const tokenPayload = {
      code,
      client_id: getIntercomClientId(),
      client_secret: getIntercomClientSecret(),
    };

    const tokenResponse = await fetch(INTERCOM_TOKEN_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(tokenPayload),
    });

    if (!tokenResponse.ok) {
      const errorText = await tokenResponse.text();
      logger.error('Intercom token exchange failed', {
        status: tokenResponse.status,
        statusText: tokenResponse.statusText,
        error: errorText,
        tenantId,
      });
      throw new Error(`Failed to exchange code for tokens: ${tokenResponse.status}`);
    }

    const tokens = await tokenResponse.json();

    // Validate token response structure
    if (!tokens || typeof tokens !== 'object') {
      logger.error('Invalid token response from Intercom', { tenantId });
      throw new Error('Invalid token response structure');
    }

    if (!tokens.access_token || typeof tokens.access_token !== 'string') {
      logger.error('Missing or invalid access token in Intercom response', { tenantId });
      throw new Error('Missing access token in response');
    }

    // Log token response for debugging
    logger.info('Intercom token exchange response', {
      tenantId,
      hasAccessToken: !!tokens.access_token,
      tokenType: tokens.token_type,
      tokenKeys: Object.keys(tokens),
    });

    // Save tokens to SSM Parameter Store
    await saveConfigValue(INTERCOM_CONFIG_KEY_ACCESS_TOKEN, tokens.access_token, tenantId);

    if (tokens.token_type && typeof tokens.token_type === 'string') {
      await saveConfigValue(INTERCOM_CONFIG_KEY_TOKEN_TYPE, tokens.token_type, tenantId);
    }

    // Get app information from Intercom API for connector metadata
    // The app_id is required for consistent connector identification
    interface IntercomAppMetadata {
      app_id: string;
      app_name?: string;
      app_created_at?: number;
      admin_id?: string;
      admin_name?: string;
      admin_email?: string;
      token_type?: string;
      [key: string]: unknown; // Allow additional properties
    }

    const meResponse = await fetch('https://api.intercom.io/me', {
      headers: {
        Authorization: `Bearer ${tokens.access_token}`,
        Accept: 'application/json',
        'Intercom-Version': '2.10',
      },
    });

    if (!meResponse.ok) {
      const errorText = await meResponse.text();
      logger.error('Failed to retrieve Intercom app metadata', {
        tenantId,
        status: meResponse.status,
        statusText: meResponse.statusText,
        error: errorText,
      });
      throw new Error(`Failed to retrieve Intercom app metadata: ${meResponse.status}`);
    }

    const meData = await meResponse.json();
    const app = meData.app || {};
    const admin = meData.admin || meData;

    const appId = app.id_code || app.id;
    if (!appId) {
      logger.error('Intercom app_id not found in /me response', {
        tenantId,
        meDataKeys: Object.keys(meData),
        appKeys: Object.keys(app),
      });
      throw new Error('Intercom app_id not found in API response');
    }

    const appMetadata: IntercomAppMetadata = {
      app_id: appId,
      app_name: app.name,
      app_created_at: app.created_at,
      admin_id: admin.id,
      admin_name: admin.name,
      admin_email: admin.email,
      token_type: tokens.token_type,
    };

    logger.info('Retrieved Intercom app metadata', {
      tenantId,
      appId: appMetadata.app_id,
      appName: appMetadata.app_name,
    });

    // Create or update connector installation record
    const externalId = appMetadata.app_id;
    await installConnector({
      tenantId,
      type: ConnectorType.Intercom,
      externalId,
      externalMetadata: appMetadata,
      updateMetadataOnExisting: true,
    });

    // Trigger Intercom backfill and send Slack notification
    if (isSqsConfigured()) {
      try {
        const sqsClient = getSqsClient();
        await sqsClient.sendIntercomBackfillIngestJob(tenantId);
        logger.info('Intercom backfill job triggered', { tenantId });
      } catch (sqsError) {
        // Don't fail the OAuth flow if backfill trigger fails
        logger.error('Failed to trigger Intercom backfill job', sqsError, { tenantId });
      }
    } else {
      logger.warn('SQS not configured - skipping Intercom backfill', { tenantId });
    }

    logger.info('Intercom OAuth flow completed successfully', { tenantId, externalId });

    return res.json({ success: true, redirectTo: null });
  } catch (error) {
    logger.error('Intercom OAuth callback failed', error);
    return res.status(500).json({ error: 'OAuth callback failed' });
  }
});

/**
 * GET /api/intercom/status
 * Get Intercom connection status
 */
intercomOAuthRouter.get('/status', requireUser, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    // Check if we have an access token stored
    const accessToken = await getConfigValue(INTERCOM_CONFIG_KEY_ACCESS_TOKEN, tenantId);
    const hasAccessToken = !!accessToken;

    return res.json({
      connected: hasAccessToken,
      configured: hasAccessToken,
    });
  } catch (error) {
    logger.error('Failed to fetch Intercom status', error);
    return res.status(500).json({ error: 'Failed to fetch status' });
  }
});

/**
 * DELETE /api/intercom/disconnect
 * Disconnect Intercom
 */
intercomOAuthRouter.delete('/disconnect', requireUser, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    // Delete all Intercom-related config values
    await deleteConfigValue(INTERCOM_CONFIG_KEY_ACCESS_TOKEN, tenantId);
    await deleteConfigValue(INTERCOM_CONFIG_KEY_TOKEN_TYPE, tenantId);

    // Mark connector as disconnected in connector_installations table
    await uninstallConnector(tenantId, ConnectorType.Intercom);

    logger.info('Intercom disconnected', { tenantId });
    return res.json({ success: true });
  } catch (error) {
    logger.error('Failed to disconnect Intercom', error);
    return res.status(500).json({ error: 'Failed to disconnect' });
  }
});

export { intercomOAuthRouter };
