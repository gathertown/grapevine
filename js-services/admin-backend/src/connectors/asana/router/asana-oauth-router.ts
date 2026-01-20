import { Router } from 'express';
import { requireAdmin } from '../../../middleware/auth-middleware';
import { getFrontendUrl } from '../../../utils/config';
import { logger } from '../../../utils/logger';
import { getAsanaClientId, getAsanaClientSecret } from '../asana-env';
import { saveAsanaOauthToken } from '../asana-config';
import { triggerAsanaBackfill } from '../asana-jobs';
import { installAsanaConnector } from './asana-connector';

function buildAsanaRedirectUrl(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/asana/oauth/callback`;
}

interface OAuthState {
  tenantId: string;
}

interface AsanaTokenResponse {
  access_token: string;
  expires_in: number;
  // No expiry on refresh tokens
  refresh_token: string;
}

function buildOAuthState(state: OAuthState): string {
  return `${state.tenantId}_${Date.now()}`;
}

function oauthAuthUrl(): string {
  return 'https://app.asana.com/-/oauth_authorize';
}

function oauthTokenUrl(): string {
  return 'https://app.asana.com/-/oauth_token';
}

function parseState(state: string): Partial<OAuthState> {
  const [tenantId, _date] = state.split('_');
  return { tenantId };
}

async function exchangeCodeForToken(
  code: string,
  redirectUri: string
): Promise<AsanaTokenResponse> {
  const payload = {
    grant_type: 'authorization_code',
    code,
    redirect_uri: redirectUri,
    client_id: getAsanaClientId(),
    client_secret: getAsanaClientSecret(),
  };

  const response = await fetch(oauthTokenUrl(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body: new URLSearchParams(payload).toString(),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Asana code-token exchange failed: ${response.status} ${text}`);
  }

  return response.json();
}

const asanaOauthRouter = Router();

asanaOauthRouter.get('/oauth/url', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const state = buildOAuthState({ tenantId });
    const authUrl = new URL(oauthAuthUrl());
    authUrl.searchParams.set('response_type', 'code');
    authUrl.searchParams.set('client_id', getAsanaClientId());
    authUrl.searchParams.set('redirect_uri', buildAsanaRedirectUrl());
    authUrl.searchParams.set('state', state);

    return res.json({ url: authUrl.toString() });
  } catch (error) {
    logger.error('Failed to generate Asana OAuth URL', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to start Asana OAuth flow' });
  }
});

asanaOauthRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description: errorDescription } = req.query;

  const { tenantId } = parseState(typeof state === 'string' ? state : '');

  if (error) {
    logger.error('Asana OAuth error from provider', {
      error: String(error),
      error_description: String(errorDescription || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(
      `${frontendUrl}/integrations/asana?oauth-error=${encodeURIComponent(
        String(errorDescription || error)
      )}`
    );
  }

  if (!code || !tenantId) {
    logger.error('Missing Asana OAuth callback parameters', {
      has_code: !!code,
      state,
      tenant_id: tenantId,
    });
    return res.redirect(
      `${frontendUrl}/integrations/asana?oauth-error=Missing required parameters`
    );
  }

  try {
    const redirectUri = buildAsanaRedirectUrl();
    const response = await exchangeCodeForToken(String(code), redirectUri);

    const now = Date.now();
    const expiresInMs = response.expires_in * 1000;
    const expiresAtEpoch = now + expiresInMs;
    const expiresAt = new Date(expiresAtEpoch).toISOString();

    await saveAsanaOauthToken(tenantId, {
      access_token: response.access_token,
      refresh_token: response.refresh_token,
      access_token_expires_at: expiresAt,
    });

    await installAsanaConnector(tenantId, response.access_token);
    await triggerAsanaBackfill(tenantId);

    logger.info('Asana OAuth flow completed successfully', { tenant_id: tenantId });
    return res.redirect(`${frontendUrl}/integrations/asana?oauth-success=true`);
  } catch (error) {
    logger.error('Error handling Asana OAuth callback', error, {
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/integrations/asana?oauth-error=OAuth exchange failed`);
  }
});

export { asanaOauthRouter };
