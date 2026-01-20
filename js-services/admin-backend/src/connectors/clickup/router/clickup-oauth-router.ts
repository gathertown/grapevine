import { Router } from 'express';
import { requireAdmin } from '../../../middleware/auth-middleware';
import { getFrontendUrl } from '../../../utils/config';
import { logger } from '../../../utils/logger';
import { getClickupClientId, getClickupClientSecret } from '../clickup-env';
import { installClickupConnector } from '../clickup-connector';
import { saveClickupOauthToken } from '../clickup-config';

function buildClickupRedirectUrl(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/clickup/oauth/callback`;
}

interface OAuthState {
  tenantId: string;
}

interface ClickupTokenResponse {
  // No expiration info provided
  access_token: string;
}

function buildOAuthState(state: OAuthState): string {
  return `${state.tenantId}_${Date.now()}`;
}

function oauthAuthUrl(): string {
  return 'https://app.clickup.com/api';
}

function oauthTokenUrl(): string {
  return 'https://api.clickup.com/api/v2/oauth/token';
}

function parseState(state: string): Partial<OAuthState> {
  const [tenantId, _date] = state.split('_');
  return { tenantId };
}

async function exchangeCodeForToken(
  code: string,
  redirectUri: string
): Promise<ClickupTokenResponse> {
  const payload = {
    grant_type: 'authorization_code',
    code,
    redirect_uri: redirectUri,
    client_id: getClickupClientId(),
    client_secret: getClickupClientSecret(),
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
    throw new Error(`Clickup code-token exchange failed: ${response.status} ${text}`);
  }

  return response.json();
}

const clickupOauthRouter = Router();

clickupOauthRouter.get('/oauth/url', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const state = buildOAuthState({ tenantId });
    const authUrl = new URL(oauthAuthUrl());
    authUrl.searchParams.set('response_type', 'code');
    authUrl.searchParams.set('client_id', getClickupClientId());
    authUrl.searchParams.set('redirect_uri', buildClickupRedirectUrl());
    authUrl.searchParams.set('state', state);

    return res.json({ url: authUrl.toString() });
  } catch (error) {
    logger.error('Failed to generate Clickup OAuth URL', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to start Clickup OAuth flow' });
  }
});

clickupOauthRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description: errorDescription } = req.query;

  const { tenantId } = parseState(typeof state === 'string' ? state : '');

  if (error) {
    logger.error('Clickup OAuth error from provider', {
      error: String(error),
      error_description: String(errorDescription || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(
      `${frontendUrl}/integrations/clickup?oauth-error=${encodeURIComponent(
        String(errorDescription || error)
      )}`
    );
  }

  if (!code || !tenantId) {
    logger.error('Missing Clickup OAuth callback parameters', {
      has_code: !!code,
      state,
      tenant_id: tenantId,
    });
    return res.redirect(
      `${frontendUrl}/integrations/clickup?oauth-error=Missing required parameters`
    );
  }

  try {
    const redirectUri = buildClickupRedirectUrl();
    const response = await exchangeCodeForToken(String(code), redirectUri);

    await saveClickupOauthToken(tenantId, response.access_token);
    await installClickupConnector(tenantId, response.access_token);
    // TODO: kick off initial backfill

    logger.info('Clickup OAuth flow completed successfully', {
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/integrations/clickup?oauth-success=true`);
  } catch (error) {
    logger.error('Error handling Clickup OAuth callback', error, {
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/integrations/clickup?oauth-error=OAuth exchange failed`);
  }
});

export { clickupOauthRouter };
