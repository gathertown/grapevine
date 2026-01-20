import { Router } from 'express';
import { requireUser } from '../../middleware/auth-middleware.js';
import { logger } from '../../utils/logger.js';
import { saveConfigValue, getConfigValue, deleteConfigValue } from '../../config/index.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { ssmConfigManager } from '../../config/ssm-config-manager.js';
import { installConnector, uninstallConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { linearService } from '../../services/linear-service.js';

export const linearOAuthRouter = Router();

// Linear OAuth configuration
const LINEAR_AUTH_URL = 'https://linear.app/oauth/authorize';
const LINEAR_TOKEN_URL = 'https://api.linear.app/oauth/token';
const LINEAR_OAUTH_SCOPE = 'read';
const LINEAR_GRANT_TYPE_AUTH_CODE = 'authorization_code';
const LINEAR_RESPONSE_TYPE = 'code';

// Config keys for storing Linear OAuth tokens
const LINEAR_CONFIG_KEY_ACCESS_TOKEN = 'LINEAR_ACCESS_TOKEN';
const LINEAR_CONFIG_KEY_REFRESH_TOKEN = 'LINEAR_REFRESH_TOKEN';
const LINEAR_CONFIG_KEY_TOKEN_EXPIRES_AT = 'LINEAR_TOKEN_EXPIRES_AT';

// Milliseconds multiplier for converting seconds to milliseconds
const SECONDS_TO_MILLISECONDS = 1000;

function getLinearClientId(): string {
  const value = process.env.LINEAR_CLIENT_ID;
  if (!value) {
    throw new Error('LINEAR_CLIENT_ID environment variable is required for Linear OAuth');
  }
  return value;
}

function getLinearClientSecret(): string {
  const value = process.env.LINEAR_CLIENT_SECRET;
  if (!value) {
    throw new Error('LINEAR_CLIENT_SECRET environment variable is required for Linear OAuth');
  }
  return value;
}

function buildLinearRedirectUri(): string {
  const frontendUrl = process.env.FRONTEND_URL;
  if (!frontendUrl) {
    throw new Error('FRONTEND_URL environment variable is required for Linear OAuth');
  }
  return `${frontendUrl}/integrations/linear/callback`;
}

/**
 * Fetch Linear organization information using access token
 */
async function fetchLinearOrganization(accessToken: string): Promise<string | null> {
  try {
    const query = `
      query {
        organization {
          id
          name
        }
      }
    `;

    const response = await fetch('https://api.linear.app/graphql', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      logger.error('Failed to fetch Linear organization', { status: response.status });
      return null;
    }

    const data = await response.json();
    const organizationId = data?.data?.organization?.id;

    if (organizationId) {
      logger.info('Fetched Linear organization', { organizationId });
      return organizationId;
    }

    logger.warn('No organization ID in Linear API response');
    return null;
  } catch (error) {
    logger.error('Error fetching Linear organization', error);
    return null;
  }
}

/**
 * GET /api/linear/install
 * Returns Linear OAuth URL for client-side redirect
 */
linearOAuthRouter.get('/install', requireUser, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found' });
  }

  // Check if write scope is requested (for triage bot)
  const requestWrite = req.query.write === 'true';
  const scope = requestWrite ? 'read,write' : LINEAR_OAUTH_SCOPE;

  // Get redirect destination (e.g., '/apps/triage' for triage bot flow)
  const redirectTo = typeof req.query.redirect === 'string' ? req.query.redirect : null;

  // State for CSRF protection (store tenantId and redirect destination)
  const state = Buffer.from(JSON.stringify({ tenantId, redirectTo })).toString('base64url');

  const authUrl = new URL(LINEAR_AUTH_URL);
  authUrl.searchParams.set('client_id', getLinearClientId());
  authUrl.searchParams.set('redirect_uri', buildLinearRedirectUri());
  authUrl.searchParams.set('scope', scope);
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('response_type', LINEAR_RESPONSE_TYPE);
  authUrl.searchParams.set('prompt', 'consent'); // Force re-authorization

  return res.json({ url: authUrl.toString() });
});

/**
 * POST /api/linear/oauth/callback
 * Handles OAuth callback and exchanges code for tokens
 */
linearOAuthRouter.post('/callback', async (req, res) => {
  try {
    const { code, state } = req.body;

    if (!code || !state) {
      return res.status(400).json({ error: 'Missing code or state' });
    }

    // Decode state to get tenantId and redirectTo
    let tenantId: string;
    let redirectTo: string | null = null;
    try {
      const decoded = JSON.parse(Buffer.from(state, 'base64url').toString());
      tenantId = decoded.tenantId;
      redirectTo = decoded.redirectTo || null;
      if (!tenantId || typeof tenantId !== 'string') {
        throw new Error('Invalid tenant ID in state');
      }
    } catch (error) {
      logger.error('Failed to decode OAuth state', error);
      return res.status(400).json({ error: 'Invalid state parameter' });
    }

    // Exchange code for tokens
    // Linear requires application/x-www-form-urlencoded format
    const params = new URLSearchParams({
      grant_type: LINEAR_GRANT_TYPE_AUTH_CODE,
      code,
      redirect_uri: buildLinearRedirectUri(),
      client_id: getLinearClientId(),
      client_secret: getLinearClientSecret(),
    });

    const tokenResponse = await fetch(LINEAR_TOKEN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: params.toString(),
    });

    if (!tokenResponse.ok) {
      logger.error('Linear token exchange failed', { status: tokenResponse.status });
      throw new Error('Failed to exchange code for tokens');
    }

    const tokens = await tokenResponse.json();

    // Validate token response structure
    if (!tokens || typeof tokens !== 'object') {
      logger.error('Invalid token response from Linear', { tenantId });
      throw new Error('Invalid token response structure');
    }

    if (!tokens.access_token || typeof tokens.access_token !== 'string') {
      logger.error('Missing or invalid access token in Linear response', { tenantId });
      throw new Error('Missing access token in response');
    }

    if (
      tokens.expires_in !== undefined &&
      (typeof tokens.expires_in !== 'number' || tokens.expires_in <= 0)
    ) {
      logger.error('Invalid expires_in value in Linear response', {
        tenantId,
        expires_in: tokens.expires_in,
      });
      throw new Error('Invalid expires_in in token response');
    }

    // Log token response to check if org ID is included (for debugging)
    logger.info('Linear token exchange response', {
      tenantId,
      hasAccessToken: !!tokens.access_token,
      hasRefreshToken: !!tokens.refresh_token,
      tokenKeys: Object.keys(tokens),
    });

    await saveConfigValue(LINEAR_CONFIG_KEY_ACCESS_TOKEN, tokens.access_token, tenantId);
    if (tokens.refresh_token && typeof tokens.refresh_token === 'string') {
      await saveConfigValue(LINEAR_CONFIG_KEY_REFRESH_TOKEN, tokens.refresh_token, tenantId);
    }

    if (tokens.expires_in && typeof tokens.expires_in === 'number') {
      const expiresAt = new Date(
        Date.now() + tokens.expires_in * SECONDS_TO_MILLISECONDS
      ).toISOString();
      await saveConfigValue(LINEAR_CONFIG_KEY_TOKEN_EXPIRES_AT, expiresAt, tenantId);
    }

    // Clean up legacy credentials if they exist (auto-upgrade path)
    await deleteConfigValue('LINEAR_API_KEY', tenantId);
    await deleteConfigValue('LINEAR_WEBHOOK_SECRET', tenantId);

    // Fetch and store organization ID for webhook routing
    const organizationId = await fetchLinearOrganization(tokens.access_token);
    if (organizationId && organizationId.trim().length > 0) {
      await installConnector({
        tenantId,
        type: ConnectorType.Linear,
        externalId: organizationId,
      });
      logger.info('Linear OAuth completed with organization ID', { tenantId, organizationId });
    } else {
      logger.warn('Linear OAuth completed but failed to fetch organization ID', { tenantId });
    }

    // Save global OAuth webhook secret to tenant's SSM
    // This follows the Trello pattern where all tenants get the same application-level secret
    const globalWebhookSecret = process.env.LINEAR_OAUTH_WEBHOOK_SECRET;
    if (globalWebhookSecret) {
      const webhookSecretSaved = await ssmConfigManager.saveConfigValue(
        'LINEAR_WEBHOOK_SECRET',
        globalWebhookSecret,
        tenantId
      );
      if (webhookSecretSaved) {
        logger.info('Saved Linear OAuth webhook secret to SSM', { tenantId });
      } else {
        logger.warn('Failed to save Linear OAuth webhook secret to SSM', { tenantId });
      }
    } else {
      logger.warn('LINEAR_OAUTH_WEBHOOK_SECRET not configured in environment', { tenantId });
    }

    // Trigger Linear data backfill after successful OAuth
    await handleLinearConnected(tenantId);

    // If this is for the triage bot, save connection status
    if (redirectTo === '/apps/triage') {
      await saveConfigValue('TRIAGE_BOT_LINEAR_CONNECTED', 'true', tenantId);
      logger.info('Triage bot Linear connection saved', { tenantId });
    }

    return res.json({ success: true, redirectTo });
  } catch (error) {
    logger.error('Linear OAuth callback failed', error);
    return res.status(500).json({ error: 'OAuth callback failed' });
  }
});

/**
 * Handle post-OAuth actions: update integration status and trigger backfill
 */
async function handleLinearConnected(tenantId: string): Promise<void> {
  try {
    logger.info('Linear OAuth successful, triggering initial ingest', { tenant_id: tenantId });

    // Update Notion CRM - Linear integration connected
    await updateIntegrationStatus(tenantId, 'linear', true);

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering Linear backfill job', { tenant_id: tenantId });
      await sqsClient.sendLinearApiIngestJob(tenantId);
      logger.info('Linear backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping Linear backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Linear backfill job', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the OAuth flow if post-processing fails
  }
}

/**
 * GET /api/linear/status
 * Check if Linear is connected and which auth method is in use
 */
linearOAuthRouter.get('/status', requireUser, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    const accessToken = await getConfigValue(LINEAR_CONFIG_KEY_ACCESS_TOKEN, tenantId);
    const hasOAuth = !!accessToken;

    const apiKey = await getConfigValue('LINEAR_API_KEY', tenantId);
    const hasLegacyAuth = !!apiKey;

    return res.json({
      configured: hasOAuth || hasLegacyAuth,
      authMethod: hasOAuth ? 'oauth' : hasLegacyAuth ? 'api_key' : null,
      hasLegacyAuth,
    });
  } catch (error) {
    logger.error('Failed to fetch Linear status', error);
    return res.status(500).json({ error: 'Failed to fetch status' });
  }
});

/**
 * GET /api/linear/teams
 * Fetch Linear teams using valid (potentially refreshed) access token
 */
linearOAuthRouter.get('/teams', requireUser, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    // Get valid access token (automatically refreshes if needed)
    const accessToken = await linearService.getValidAccessToken(tenantId);
    if (!accessToken) {
      return res.status(401).json({ error: 'Linear not connected' });
    }

    // Fetch teams from Linear API
    const query = `
      query {
        teams(filter: { private: { eq: false } }) {
          nodes {
            id
            name
            key
          }
        }
      }
    `;

    const response = await fetch('https://api.linear.app/graphql', {
      method: 'POST',
      headers: {
        Authorization: accessToken,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      logger.error('Failed to fetch Linear teams', { status: response.status, tenantId });
      return res.status(response.status).json({ error: 'Failed to fetch Linear teams' });
    }

    const data = await response.json();
    const teams = data?.data?.teams?.nodes || [];

    logger.info('Fetched Linear teams', { tenantId, teamCount: teams.length });
    return res.json({ teams });
  } catch (error) {
    logger.error('Failed to fetch Linear teams', error);
    return res.status(500).json({ error: 'Failed to fetch Linear teams' });
  }
});

/**
 * DELETE /api/linear/disconnect
 * Disconnect Linear
 */
linearOAuthRouter.delete('/disconnect', requireUser, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    await deleteConfigValue(LINEAR_CONFIG_KEY_ACCESS_TOKEN, tenantId);
    await deleteConfigValue(LINEAR_CONFIG_KEY_REFRESH_TOKEN, tenantId);
    await deleteConfigValue(LINEAR_CONFIG_KEY_TOKEN_EXPIRES_AT, tenantId);
    await deleteConfigValue('LINEAR_API_KEY', tenantId);
    await deleteConfigValue('LINEAR_WEBHOOK_SECRET', tenantId);
    await deleteConfigValue('TRIAGE_BOT_LINEAR_CONNECTED', tenantId);
    await deleteConfigValue('LINEAR_TEAM_SLACK_CHANNEL_MAPPINGS', tenantId);

    // Mark connector as disconnected
    await uninstallConnector(tenantId, ConnectorType.Linear);

    // Delete webhook secret from SSM
    await ssmConfigManager.deleteConfigValue('LINEAR_WEBHOOK_SECRET', tenantId);

    logger.info('Linear disconnected', { tenantId });
    return res.json({ success: true });
  } catch (error) {
    logger.error('Failed to disconnect Linear', error);
    return res.status(500).json({ error: 'Failed to disconnect' });
  }
});
