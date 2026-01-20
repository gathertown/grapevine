import { Router } from 'express';
import { z } from 'zod';

import { requireAdmin } from '../../middleware/auth-middleware.js';
import { logger } from '../../utils/logger.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import type { GongCallBackfillRootConfig } from '../../jobs/models.js';
import { getConfigValue, saveConfigValue } from '../../config/index.js';
import { getBaseDomain, getFrontendUrl } from '../../utils/config.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
/**
 * Gong OAuth configuration.
 * Gong currently supports authorization-code flows using the standard endpoints.
 */
const AUTH_URL = 'https://app.gong.io/oauth2/authorize';
const TOKEN_URL = 'https://app.gong.io/oauth2/generate-customer-token';

function getGongClientId(): string {
  const value = process.env.GONG_CLIENT_ID;
  if (!value) {
    throw new Error('GONG_CLIENT_ID environment variable is required for Gong OAuth');
  }
  return value;
}

function getGongClientSecret(): string {
  const value = process.env.GONG_CLIENT_SECRET;
  if (!value) {
    throw new Error('GONG_CLIENT_SECRET environment variable is required for Gong OAuth');
  }
  return value;
}

function getGongScopes(): string {
  return (
    process.env.GONG_SCOPES ||
    'api:calls:read:transcript api:users:read api:workspaces:read api:calls:read:extensive api:calls:read:basic api:library:read api:permission-profile:read'
  );
}

function buildGongRedirectUri(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/gong/oauth/callback`;
}

function buildOAuthState(tenantId: string): string {
  return `${tenantId}_${Date.now()}`;
}

function parseState(state: string | undefined): { tenantId: string | undefined } {
  if (!state) {
    return { tenantId: undefined };
  }
  const parts = state.split('_');
  return { tenantId: parts[0] };
}

async function exchangeCodeForToken(code: string, redirectUri: string) {
  const clientId = getGongClientId();
  const clientSecret = getGongClientSecret();
  const useBasicAuth = process.env.GONG_USE_BASIC_AUTH !== 'false';

  const data = {
    grant_type: 'authorization_code',
    code,
    redirect_uri: redirectUri,
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/x-www-form-urlencoded',
  };

  let payload: URLSearchParams;

  if (useBasicAuth) {
    payload = new URLSearchParams(data);
    headers.Authorization = `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString('base64')}`;
  } else {
    payload = new URLSearchParams({ ...data, client_id: clientId, client_secret: clientSecret });
  }

  const response = await fetch(TOKEN_URL, {
    method: 'POST',
    headers,
    body: payload.toString(),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Gong token request failed: ${response.status} ${text}`);
  }

  return response.json();
}

async function saveGongTokens(
  tenantId: string,
  tokenResponse: Record<string, unknown>
): Promise<void> {
  const entries: Array<[string, unknown]> = [
    ['GONG_ACCESS_TOKEN', tokenResponse.access_token],
    ['GONG_REFRESH_TOKEN', tokenResponse.refresh_token],
    ['GONG_SCOPE', tokenResponse.scope],
    ['GONG_TOKEN_TYPE', tokenResponse.token_type],
    ['GONG_TOKEN_EXPIRES_IN', tokenResponse.expires_in],
    ['GONG_API_BASE_URL', tokenResponse.api_base_url_for_customer],
  ];

  await Promise.all(
    entries
      .filter(([, value]) => value !== undefined && value !== null)
      .map(([key, value]) => saveConfigValue(key as never, value as never, tenantId))
  );
}

async function handleGongConnected(tenantId: string): Promise<void> {
  try {
    logger.info('Gong OAuth successful, triggering initial backfill', { tenant_id: tenantId });

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      await sqsClient.sendGongCallBackfillIngestJob(tenantId);
      logger.info('Gong backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping Gong backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Gong backfill job', error, { tenant_id: tenantId });
  }
}

export const gongRouter = Router();

gongRouter.get('/status', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const accessToken = await getConfigValue('GONG_ACCESS_TOKEN', tenantId);
    const apiBaseUrl = await getConfigValue('GONG_API_BASE_URL', tenantId);
    const webhookPublicKey = await getConfigValue('GONG_WEBHOOK_PUBLIC_KEY', tenantId);
    const webhookUrl = await getConfigValue('GONG_WEBHOOK_URL', tenantId);
    const webhookVerified = await getConfigValue('GONG_WEBHOOK_VERIFIED', tenantId);
    const selectedWorkspacesRaw = await getConfigValue('GONG_SELECTED_WORKSPACE_IDS', tenantId);

    const configured = Boolean(accessToken && apiBaseUrl);

    // Parse workspace settings
    let selectedWorkspaces: string[] | 'none' = 'none';
    if (selectedWorkspacesRaw === 'none') {
      selectedWorkspaces = selectedWorkspacesRaw;
    } else if (typeof selectedWorkspacesRaw === 'string' && selectedWorkspacesRaw.trim()) {
      try {
        const parsed = JSON.parse(selectedWorkspacesRaw);
        if (Array.isArray(parsed)) {
          selectedWorkspaces = parsed;
        } else {
          selectedWorkspaces = 'none';
        }
      } catch {
        // Default to 'none' if parsing fails
        selectedWorkspaces = 'none';
      }
    }

    return res.json({
      configured,
      access_token_present: Boolean(accessToken),
      api_base_url_present: Boolean(apiBaseUrl),
      webhook_public_key_present: Boolean(webhookPublicKey),
      webhook_url: typeof webhookUrl === 'string' ? webhookUrl : null,
      webhook_verified: webhookVerified === 'true',
      workspace_settings_configured: Boolean(selectedWorkspacesRaw),
      selected_workspaces: selectedWorkspaces,
    });
  } catch (error) {
    logger.error('Failed to fetch Gong status', error);
    return res.status(500).json({ error: 'Failed to fetch Gong status' });
  }
});

/**
 * GET /api/gong/webhook
 * Get the webhook configuration (URL + whether a public key is stored).
 */
gongRouter.get('/webhook', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const baseDomain = getBaseDomain();
    const defaultWebhookUrl = `https://${tenantId}.ingest.${baseDomain}/webhooks/gong`;

    const storedWebhookUrl = await getConfigValue('GONG_WEBHOOK_URL', tenantId);
    const webhookPublicKey = await getConfigValue('GONG_WEBHOOK_PUBLIC_KEY', tenantId);

    res.json({
      url: typeof storedWebhookUrl === 'string' ? storedWebhookUrl : defaultWebhookUrl,
      publicKeyPresent: Boolean(webhookPublicKey),
      publicKey:
        typeof webhookPublicKey === 'string' && webhookPublicKey.length > 0
          ? webhookPublicKey
          : null,
    });
  } catch (error) {
    logger.error('Failed to fetch Gong webhook config', error);
    res.status(500).json({ error: 'Failed to fetch Gong webhook config' });
  }
});

const GongWebhookUpdateSchema = z.object({
  publicKey: z.string().min(1, 'Public key is required'),
  webhookUrl: z.string().url().optional(),
});

/**
 * Normalize a public key to PEM format.
 * If the key is just the base64 content, wrap it with PEM markers.
 */
function normalizePublicKeyToPEM(publicKey: string): string {
  const trimmed = publicKey.trim();

  // If already in PEM format, return as-is
  if (
    trimmed.includes('-----BEGIN PUBLIC KEY-----') &&
    trimmed.includes('-----END PUBLIC KEY-----')
  ) {
    return trimmed;
  }

  // Otherwise, wrap the key content with PEM markers
  // Remove any newlines from the key content and add proper formatting
  const keyContent = trimmed.replace(/\n/g, '');
  return `-----BEGIN PUBLIC KEY-----\n${keyContent}\n-----END PUBLIC KEY-----`;
}

/**
 * PUT /api/gong/webhook
 * Store the Gong webhook public key (and optional override URL).
 */
gongRouter.put('/webhook', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const parsed = GongWebhookUpdateSchema.safeParse(req.body);
    if (!parsed.success) {
      return res.status(400).json({ error: parsed.error.flatten() });
    }

    const { publicKey, webhookUrl } = parsed.data;

    // Normalize the public key to PEM format (add markers if missing)
    const trimmedKey = normalizePublicKeyToPEM(publicKey);

    const publicKeySaved = await saveConfigValue('GONG_WEBHOOK_PUBLIC_KEY', trimmedKey, tenantId);
    if (!publicKeySaved) {
      throw new Error('Failed to store Gong webhook public key');
    }

    const verificationFlagCleared = await saveConfigValue(
      'GONG_WEBHOOK_VERIFIED',
      'false',
      tenantId
    );
    if (!verificationFlagCleared) {
      throw new Error('Failed to reset Gong webhook verification status');
    }

    if (webhookUrl) {
      const urlSaved = await saveConfigValue('GONG_WEBHOOK_URL', webhookUrl, tenantId);
      if (!urlSaved) {
        throw new Error('Failed to store Gong webhook URL');
      }
    }

    logger.info('Gong webhook configuration updated', {
      tenant_id: tenantId,
      has_custom_url: Boolean(webhookUrl),
      verification_reset: true,
    });

    return res.json({ success: true });
  } catch (error) {
    logger.error('Failed to update Gong webhook config', error, {
      tenant_id: req.user?.tenantId,
    });
    return res.status(500).json({ error: 'Failed to update Gong webhook config' });
  }
});

/**
 * GET /api/gong/workspaces
 * Fetch list of workspaces from Gong API
 */
gongRouter.get('/workspaces', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const accessToken = await getConfigValue('GONG_ACCESS_TOKEN', tenantId);
    const apiBaseUrl = await getConfigValue('GONG_API_BASE_URL', tenantId);

    if (!accessToken || !apiBaseUrl) {
      return res.status(400).json({ error: 'Gong not configured. Please complete OAuth first.' });
    }

    // Call Gong API to get workspaces
    const response = await fetch(`${apiBaseUrl}/v2/workspaces`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: 'application/json',
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to fetch Gong workspaces', {
        status: response.status,
        error: errorText,
        tenant_id: tenantId,
      });
      return res.status(response.status).json({ error: 'Failed to fetch workspaces from Gong' });
    }

    const data = await response.json();
    const workspaces = data.workspaces || [];

    return res.json({ workspaces });
  } catch (error) {
    logger.error('Failed to fetch Gong workspaces', error, { tenant_id: req.user?.tenantId });
    return res.status(500).json({ error: 'Failed to fetch Gong workspaces' });
  }
});

/**
 * GET /api/gong/workspace-settings
 * Get current workspace selection settings
 */
gongRouter.get('/workspace-settings', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const selectedWorkspacesRaw = await getConfigValue('GONG_SELECTED_WORKSPACE_IDS', tenantId);

    // Parse the value - could be "none", JSON array, or undefined (not configured)
    let selectedWorkspaces: string[] | 'none' | undefined = undefined; // default to undefined

    if (selectedWorkspacesRaw === 'none') {
      selectedWorkspaces = selectedWorkspacesRaw;
    } else if (typeof selectedWorkspacesRaw === 'string' && selectedWorkspacesRaw.trim()) {
      try {
        const parsed = JSON.parse(selectedWorkspacesRaw);
        if (Array.isArray(parsed)) {
          selectedWorkspaces = parsed;
        } else {
          selectedWorkspaces = undefined;
        }
      } catch {
        // If parsing fails, default to undefined (not configured)
        logger.warn('Failed to parse GONG_SELECTED_WORKSPACE_IDS, defaulting to undefined', {
          tenant_id: tenantId,
          value: selectedWorkspacesRaw,
        });
        selectedWorkspaces = undefined;
      }
    }

    return res.json({ selectedWorkspaces });
  } catch (error) {
    logger.error('Failed to fetch Gong workspace settings', error, {
      tenant_id: req.user?.tenantId,
    });
    return res.status(500).json({ error: 'Failed to fetch workspace settings' });
  }
});

const GongWorkspaceSettingsSchema = z.object({
  // Accept explicit workspace IDs, 'none', or undefined (not configured yet)
  selectedWorkspaces: z.union([z.array(z.string().min(1)), z.literal('none'), z.undefined()]),
});

/**
 * PUT /api/gong/workspace-settings
 * Save workspace selection settings
 */
gongRouter.put('/workspace-settings', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const parsed = GongWorkspaceSettingsSchema.safeParse(req.body);
    if (!parsed.success) {
      return res.status(400).json({ error: parsed.error.flatten() });
    }

    const { selectedWorkspaces } = parsed.data;

    // Convert to storage format
    // Always store explicit workspace IDs (as JSON array), 'none', or don't store anything for undefined
    // Never store 'all' to ensure new workspaces aren't implicitly included
    let valueToStore: string | undefined;
    if (selectedWorkspaces === 'none') {
      valueToStore = 'none';
    } else if (selectedWorkspaces === undefined) {
      // Treat undefined as 'none' for backend storage
      valueToStore = 'none';
    } else {
      valueToStore = JSON.stringify(selectedWorkspaces);
    }

    const saved = await saveConfigValue('GONG_SELECTED_WORKSPACE_IDS', valueToStore, tenantId);
    if (!saved) {
      throw new Error('Failed to store Gong workspace settings');
    }

    logger.info('Gong workspace settings updated', {
      tenant_id: tenantId,
      selected_workspaces: selectedWorkspaces,
      workspace_count: Array.isArray(selectedWorkspaces) ? selectedWorkspaces.length : 0,
    });

    return res.json({ success: true });
  } catch (error) {
    logger.error('Failed to update Gong workspace settings', error, {
      tenant_id: req.user?.tenantId,
    });
    return res.status(500).json({ error: 'Failed to update workspace settings' });
  }
});

gongRouter.post('/backfill', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    if (!isSqsConfigured()) {
      return res.status(500).json({ error: 'SQS not configured' });
    }

    const { workspaceIds, fromDatetime, toDatetime, callLimit, batchSize } = req.body ?? {};

    const config: GongCallBackfillRootConfig = {
      message_type: 'backfill',
      source: 'gong_call_backfill_root',
      tenant_id: tenantId,
      workspace_ids: Array.isArray(workspaceIds) ? workspaceIds : undefined,
      from_datetime: typeof fromDatetime === 'string' ? fromDatetime : undefined,
      to_datetime: typeof toDatetime === 'string' ? toDatetime : undefined,
      call_limit: typeof callLimit === 'number' ? callLimit : undefined,
      batch_size: typeof batchSize === 'number' ? batchSize : undefined,
    };

    const sqsClient = getSqsClient();
    await sqsClient.sendGongCallBackfillIngestJob(tenantId, {
      workspaceIds: config.workspace_ids,
      fromDatetime: config.from_datetime,
      toDatetime: config.to_datetime,
      callLimit: config.call_limit,
      batchSize: config.batch_size,
    });

    logger.info('Queued Gong call backfill job', { tenant_id: tenantId });

    return res.json({
      success: true,
      message: 'Gong call backfill job triggered',
    });
  } catch (error) {
    logger.error('Failed to trigger Gong backfill', error, {
      tenant_id: req.user?.tenantId,
    });
    return res.status(500).json({ error: 'Failed to trigger Gong backfill' });
  }
});

gongRouter.get('/oauth/url', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const state = buildOAuthState(tenantId);
    const authUrl = new URL(AUTH_URL);
    authUrl.searchParams.set('response_type', 'code');
    authUrl.searchParams.set('client_id', getGongClientId());
    authUrl.searchParams.set('redirect_uri', buildGongRedirectUri());
    authUrl.searchParams.set('scope', getGongScopes());
    authUrl.searchParams.set('state', state);

    return res.json({ url: authUrl.toString(), state });
  } catch (error) {
    logger.error('Failed to generate Gong OAuth URL', error, {
      tenant_id: req.user?.tenantId,
    });
    return res.status(500).json({ error: 'Failed to start Gong OAuth flow' });
  }
});

gongRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description: errorDescription } = req.query;

  const { tenantId } = parseState(typeof state === 'string' ? state : undefined);

  if (error) {
    logger.error('Gong OAuth error from provider', {
      error: String(error),
      error_description: String(errorDescription || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(
      `${frontendUrl}/gong/oauth/complete?error=${encodeURIComponent(
        String(errorDescription || error)
      )}`
    );
  }

  if (!code || !tenantId) {
    logger.error('Missing Gong OAuth callback parameters', {
      has_code: !!code,
      has_state: !!state,
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/gong/oauth/complete?error=Missing required parameters`);
  }

  try {
    const redirectUri = buildGongRedirectUri();
    const tokenResponse = await exchangeCodeForToken(String(code), redirectUri);

    await saveGongTokens(tenantId, tokenResponse);

    // Use api_base_url_for_customer as external_id since it's customer-specific
    const apiBaseUrl = tokenResponse.api_base_url_for_customer;
    if (!apiBaseUrl || typeof apiBaseUrl !== 'string' || apiBaseUrl.trim().length === 0) {
      throw new Error('Gong OAuth response missing required api_base_url_for_customer');
    }

    await installConnector({
      tenantId,
      type: ConnectorType.Gong,
      externalId: apiBaseUrl,
    });

    logger.info('Gong OAuth completed with API base URL', { tenantId, apiBaseUrl });

    await handleGongConnected(tenantId);

    logger.info('Gong OAuth flow completed successfully', { tenant_id: tenantId });
    return res.redirect(`${frontendUrl}/gong/oauth/complete?success=true`);
  } catch (error) {
    logger.error('Error handling Gong OAuth callback', error, {
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/gong/oauth/complete?error=OAuth exchange failed`);
  }
});
