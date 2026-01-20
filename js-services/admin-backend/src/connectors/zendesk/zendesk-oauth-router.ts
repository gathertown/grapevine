import { Router } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware';
import { getFrontendUrl } from '../../utils/config';
import { logger } from '../../utils/logger';
import { saveZendeskSubdomain, saveZendeskToken } from './zendesk-config';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { ZendeskOauthStore } from './zendesk-oauth-state';

function getZendeskMarketplaceHeaders(): Record<string, string> {
  const zendesk_app_name = process.env.ZENDESK_MARKETPLACE_APP_NAME;
  const zendesk_app_id = process.env.ZENDESK_MARKETPLACE_APP_ID;
  const zendesk_org_id = process.env.ZENDESK_MARKETPLACE_ORG_ID;

  return {
    'X-Zendesk-Marketplace-Name': zendesk_app_name || '',
    'X-Zendesk-Marketplace-App-Id': zendesk_app_id || '',
    'X-Zendesk-Marketplace-Organization-Id': zendesk_org_id || '',
  };
}

function getZendeskClientId(): string {
  const value = process.env.ZENDESK_CLIENT_ID;
  if (!value) {
    throw new Error('ZENDESK_CLIENT_ID environment variable is required for Zendesk OAuth');
  }
  return value;
}

function getZendeskClientSecret(): string {
  const value = process.env.ZENDESK_CLIENT_SECRET;
  if (!value) {
    throw new Error('ZENDESK_CLIENT_SECRET environment variable is required for Zendesk OAuth');
  }
  return value;
}

function buildZendeskRedirectUri(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/zendesk/oauth/callback`;
}

function getZendeskScopes(): string {
  return 'read';
}

function buildOauthAuthUrl(subdomain: string): string {
  return `https://${subdomain}.zendesk.com/oauth/authorizations/new`;
}

function buildTokenUrl(subdomain: string): string {
  return `https://${subdomain}.zendesk.com/oauth/tokens`;
}

async function handleZendeskConnected(tenantId: string): Promise<void> {
  try {
    logger.info('Zendesk OAuth successful, triggering initial backfill', { tenant_id: tenantId });

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      await sqsClient.sendZendeskBackfillIngestJob(tenantId);
      logger.info('Zendesk backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping Zendesk backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to trigger Zendesk backfill job', error, { tenant_id: tenantId });
  }
}

interface ZendeskTokenResponse {
  access_token: string;
  refresh_token: string;
}

interface ZendeskTokenExpiryTimesResponse {
  token: {
    expires_at: string | null;
    refresh_token_expires_at: string;
  };
}

async function exchangeCodeForToken({
  zendeskSubdomain,
  code,
  codeVerifier,
  redirectUri,
}: {
  zendeskSubdomain: string;
  code: string;
  codeVerifier: string;
  redirectUri: string;
}): Promise<ZendeskTokenResponse> {
  const payload = {
    grant_type: 'authorization_code',
    code,
    redirect_uri: redirectUri,
    client_id: getZendeskClientId(),
    client_secret: getZendeskClientSecret(),
    code_verifier: codeVerifier,
  };

  const response = await fetch(buildTokenUrl(zendeskSubdomain), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...getZendeskMarketplaceHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Zendesk token request failed: ${response.status} ${text}`);
  }

  return response.json();
}

async function getTokenExpiryTimes(
  zendeskSubdomain: string,
  accessToken: string
): Promise<ZendeskTokenExpiryTimesResponse> {
  const response = await fetch(
    `https://${zendeskSubdomain}.zendesk.com/api/v2/oauth/tokens/current`,
    {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
        ...getZendeskMarketplaceHeaders(),
      },
    }
  );

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to fetch token expiry times: ${response.status} ${text}`);
  }

  return response.json();
}

const zendeskOauthRouter = Router();

zendeskOauthRouter.get('/oauth/url', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  const { subdomain } = req.query;
  if (typeof subdomain !== 'string' || !subdomain.trim()) {
    return res.status(400).json({ error: 'Zendesk subdomain is required' });
  }

  try {
    const { stateString: state, codeChallenge } = await ZendeskOauthStore.generateOauthState({
      tenantId,
      subdomain,
    });

    const authUrl = new URL(buildOauthAuthUrl(subdomain));
    authUrl.searchParams.set('response_type', 'code');
    authUrl.searchParams.set('client_id', getZendeskClientId());
    authUrl.searchParams.set('redirect_uri', buildZendeskRedirectUri());
    authUrl.searchParams.set('scope', getZendeskScopes());
    authUrl.searchParams.set('state', state);
    authUrl.searchParams.set('code_challenge_method', 'S256');
    authUrl.searchParams.set('code_challenge', codeChallenge);

    return res.json({ url: authUrl.toString(), state });
  } catch (error) {
    logger.error('Failed to generate Zendesk OAuth URL', error, {
      tenant_id: req.user?.tenantId,
    });
    return res.status(500).json({ error: 'Failed to start Zendesk OAuth flow' });
  }
});

zendeskOauthRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description: errorDescription } = req.query;

  const storedState = await ZendeskOauthStore.retrieveOauthState(String(state));

  if (error) {
    logger.error('Zendesk OAuth error from provider', {
      error: String(error),
      error_description: String(errorDescription || 'No description provided'),
      tenant_id: storedState?.tenantId,
    });
    return res.redirect(
      `${frontendUrl}/integrations/zendesk?oauth-error=${encodeURIComponent(
        String(errorDescription || error)
      )}`
    );
  }

  if (!state || !code || !storedState) {
    logger.error('Missing Zendesk OAuth callback parameters', {
      has_code: !!code,
      state,
      tenant_id: storedState?.tenantId,
      zendesk_subdomain: storedState?.subdomain,
    });
    return res.redirect(
      `${frontendUrl}/integrations/zendesk?oauth-error=Missing required parameters`
    );
  }

  const { tenantId, subdomain: zendeskSubdomain, codeVerifier } = storedState;

  try {
    const redirectUri = buildZendeskRedirectUri();
    const { access_token, refresh_token } = await exchangeCodeForToken({
      zendeskSubdomain,
      code: String(code),
      redirectUri,
      codeVerifier,
    });

    const { token } = await getTokenExpiryTimes(zendeskSubdomain, access_token);

    await Promise.all([
      saveZendeskSubdomain(tenantId, zendeskSubdomain),
      saveZendeskToken(tenantId, {
        access_token,
        refresh_token,
        access_token_expires_at: token.expires_at,
        refresh_token_expires_at: token.refresh_token_expires_at,
      }),
    ]);

    await installConnector({
      tenantId,
      type: ConnectorType.Zendesk,
      externalId: zendeskSubdomain,
    });

    await handleZendeskConnected(tenantId);

    logger.info('Zendesk OAuth flow completed successfully', { tenant_id: tenantId });
    return res.redirect(`${frontendUrl}/integrations/zendesk?oauth-success=true`);
  } catch (error) {
    logger.error('Error handling Zendesk OAuth callback', error, {
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/integrations/zendesk?oauth-error=OAuth exchange failed`);
  }
});

export { zendeskOauthRouter };
