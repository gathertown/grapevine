import { Router } from 'express';
import crypto from 'crypto';
import { requireAdmin } from '../../../middleware/auth-middleware';
import { getFrontendUrl } from '../../../utils/config';
import { logger } from '../../../utils/logger';
import { installConnector, uninstallConnector } from '../../../dal/connector-utils.js';
import { ConnectorType } from '../../../types/connector.js';

// Constants for OAuth token validity
const SECONDS_PER_DAY = 86400;
const DEFAULT_REFRESH_TOKEN_VALIDITY_DAYS = 90;
const DEFAULT_REFRESH_TOKEN_VALIDITY_SECONDS =
  DEFAULT_REFRESH_TOKEN_VALIDITY_DAYS * SECONDS_PER_DAY; // 7776000
import {
  saveSnowflakeOauthToken,
  getSnowflakeOauthToken,
  saveSnowflakeAccountIdentifier,
  getSnowflakeAccountIdentifier,
  getSnowflakeClientId,
  getSnowflakeClientSecret,
  saveSnowflakeClientId,
  saveSnowflakeClientSecret,
  saveSnowflakeOAuthAuthorizationEndpoint,
  saveSnowflakeOAuthTokenEndpoint,
  getSnowflakeOAuthTokenEndpoint,
  getSnowflakeIntegrationName,
  saveSnowflakeIntegrationName,
  SNOWFLAKE_CONFIG_KEYS,
} from '../snowflake-config';
import { getOAuthRefreshTokenValidity } from '../snowflake-integration-query';
import { findIntegrationByClientId } from '../snowflake-integration-discovery';
import {
  getSnowflakeStages,
  getSnowflakeWarehouses,
  getSnowflakeDatabases,
  getSnowflakeSemanticViews,
  testSnowflakeConnection,
} from '../snowflake-service';

function buildSnowflakeRedirectUrl(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/snowflake/oauth/callback`;
}

function getSnowflakeScopes(): string {
  // Request refresh token only - uses user's default role
  // Note: session:role-any requires OAUTH_USE_SECONDARY_ROLES = IMPLICIT
  return 'refresh_token';
}

interface OAuthState {
  tenantId: string;
  accountIdentifier: string;
  codeVerifier: string;
}

interface SnowflakeTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  username: string;
}

function buildOAuthState(state: OAuthState): string {
  // Encode state as base64 JSON for simplicity
  return Buffer.from(JSON.stringify(state)).toString('base64url');
}

function parseState(state: string): Partial<OAuthState> {
  try {
    const decoded = Buffer.from(state, 'base64url').toString('utf-8');
    return JSON.parse(decoded) as OAuthState;
  } catch {
    return {};
  }
}

function generateCodeVerifier(): string {
  // Generate a random 128-character string for PKCE
  return crypto.randomBytes(96).toString('base64url');
}

function generateCodeChallenge(codeVerifier: string): string {
  // SHA256 hash of the code verifier
  return crypto.createHash('sha256').update(codeVerifier).digest('base64url');
}

function buildOAuthAuthUrl(accountIdentifier: string): string {
  return `https://${accountIdentifier}.snowflakecomputing.com/oauth/authorize`;
}

function buildOAuthTokenUrl(accountIdentifier: string): string {
  return `https://${accountIdentifier}.snowflakecomputing.com/oauth/token-request`;
}

async function exchangeCodeForToken(
  code: string,
  redirectUri: string,
  accountIdentifier: string,
  codeVerifier: string,
  clientId: string,
  clientSecret: string,
  tokenEndpoint?: string
): Promise<SnowflakeTokenResponse> {
  const credentials = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');

  const payload = {
    grant_type: 'authorization_code',
    code,
    redirect_uri: redirectUri,
    code_verifier: codeVerifier,
  };

  // Use custom token endpoint if provided, otherwise use standard format
  const tokenUrl = tokenEndpoint || buildOAuthTokenUrl(accountIdentifier);

  const response = await fetch(tokenUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Basic ${credentials}`,
      Accept: 'application/json',
    },
    body: new URLSearchParams(payload).toString(),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Snowflake code-token exchange failed: ${response.status} ${text}`);
  }

  return response.json();
}

const snowflakeOauthRouter = Router();

snowflakeOauthRouter.get('/status', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const token = await getSnowflakeOauthToken(tenantId);
    const accountIdentifier = await getSnowflakeAccountIdentifier(tenantId);
    const clientId = await getSnowflakeClientId(tenantId);
    const clientSecret = await getSnowflakeClientSecret(tenantId);

    // Check if access token is expired
    const now = new Date();
    const expiresAt = token ? new Date(token.access_token_expires_at) : null;
    const isExpired = expiresAt ? expiresAt <= now : false;

    const isConfigured = !!(token && accountIdentifier && clientId && clientSecret);
    const connected = !!token;

    // Determine appropriate status message
    let message: string;
    if (isConfigured) {
      message = 'Snowflake is connected and configured';
    } else if (connected) {
      message = 'Snowflake is partially configured (missing required fields)';
    } else {
      message = 'Snowflake is not connected';
    }

    return res.json({
      connected,
      isConfigured,
      accountIdentifier: accountIdentifier || undefined,
      username: token?.username || undefined,
      tokenExpiry: token?.access_token_expires_at || undefined,
      accessTokenExpired: isExpired,
      hasRefreshToken: !!token?.refresh_token,
      message,
    });
  } catch (error) {
    logger.error('Failed to get Snowflake status', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to get Snowflake status' });
  }
});

snowflakeOauthRouter.post('/test-connection', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const result = await testSnowflakeConnection(tenantId);
    return res.json(result);
  } catch (error) {
    logger.error('Failed to test Snowflake connection', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({
      success: false,
      message: 'Failed to test Snowflake connection',
    });
  }
});

snowflakeOauthRouter.get('/oauth/url', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    // Get parameters from query
    const accountIdentifier = req.query.account_identifier as string | undefined;
    const clientId = req.query.client_id as string | undefined;
    const clientSecret = req.query.client_secret as string | undefined;
    const authorizationEndpoint = req.query.authorization_endpoint as string | undefined;
    const tokenEndpoint = req.query.token_endpoint as string | undefined;

    // Validate required parameters
    if (!accountIdentifier) {
      return res.status(400).json({ error: 'account_identifier is required' });
    }
    if (!clientId) {
      return res.status(400).json({ error: 'client_id is required' });
    }
    if (!clientSecret) {
      return res.status(400).json({ error: 'client_secret is required' });
    }

    // Save credentials for future use (during callback)
    await saveSnowflakeAccountIdentifier(tenantId, accountIdentifier);
    await saveSnowflakeClientId(tenantId, clientId);
    await saveSnowflakeClientSecret(tenantId, clientSecret);

    // Save optional endpoints if provided
    if (authorizationEndpoint) {
      await saveSnowflakeOAuthAuthorizationEndpoint(tenantId, authorizationEndpoint);
    }
    if (tokenEndpoint) {
      await saveSnowflakeOAuthTokenEndpoint(tenantId, tokenEndpoint);
    }

    // Generate PKCE values
    const codeVerifier = generateCodeVerifier();
    const codeChallenge = generateCodeChallenge(codeVerifier);

    const state = buildOAuthState({ tenantId, accountIdentifier, codeVerifier });
    // Use custom authorization endpoint if provided, otherwise use standard format
    const authUrlBase = authorizationEndpoint || buildOAuthAuthUrl(accountIdentifier);
    const authUrl = new URL(authUrlBase);
    authUrl.searchParams.set('response_type', 'code');
    authUrl.searchParams.set('client_id', clientId);
    authUrl.searchParams.set('redirect_uri', buildSnowflakeRedirectUrl());
    authUrl.searchParams.set('scope', getSnowflakeScopes());
    authUrl.searchParams.set('state', state);
    authUrl.searchParams.set('code_challenge', codeChallenge);
    authUrl.searchParams.set('code_challenge_method', 'S256');

    return res.json({ url: authUrl.toString() });
  } catch (error) {
    logger.error('Failed to generate Snowflake OAuth URL', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to start Snowflake OAuth flow' });
  }
});

snowflakeOauthRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description: errorDescription } = req.query;

  const parsedState = parseState(typeof state === 'string' ? state : '');
  const { tenantId, accountIdentifier, codeVerifier } = parsedState;

  if (error) {
    logger.error('Snowflake OAuth error from provider', {
      error: String(error),
      error_description: String(errorDescription || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(
      `${frontendUrl}/integrations/snowflake?oauth-error=${encodeURIComponent(
        String(errorDescription || error)
      )}`
    );
  }

  if (!code || !tenantId || !accountIdentifier || !codeVerifier) {
    logger.error('Missing Snowflake OAuth callback parameters', {
      has_code: !!code,
      has_tenant_id: !!tenantId,
      has_account_identifier: !!accountIdentifier,
      has_code_verifier: !!codeVerifier,
      state,
    });
    return res.redirect(
      `${frontendUrl}/integrations/snowflake?oauth-error=Missing required parameters`
    );
  }

  try {
    // Retrieve tenant's OAuth credentials
    const clientId = await getSnowflakeClientId(tenantId);
    const clientSecret = await getSnowflakeClientSecret(tenantId);

    if (!clientId || !clientSecret) {
      logger.error('Missing Snowflake OAuth credentials for tenant', {
        tenant_id: tenantId,
        has_client_id: !!clientId,
        has_client_secret: !!clientSecret,
      });
      return res.redirect(
        `${frontendUrl}/integrations/snowflake?oauth-error=Missing OAuth credentials`
      );
    }

    // Retrieve custom token endpoint if configured
    const tokenEndpoint = await getSnowflakeOAuthTokenEndpoint(tenantId);

    const redirectUri = buildSnowflakeRedirectUrl();
    const response = await exchangeCodeForToken(
      String(code),
      redirectUri,
      accountIdentifier,
      codeVerifier,
      clientId,
      clientSecret,
      tokenEndpoint || undefined
    );

    const now = Date.now();
    const expiresInMs = response.expires_in * 1000;
    const expiresAtEpoch = now + expiresInMs;
    const expiresAt = new Date(expiresAtEpoch).toISOString();

    // Calculate refresh token expiry
    // Try to auto-discover and query the actual OAUTH_REFRESH_TOKEN_VALIDITY from Snowflake
    let refreshTokenValiditySeconds = DEFAULT_REFRESH_TOKEN_VALIDITY_SECONDS;
    let integrationName = await getSnowflakeIntegrationName(tenantId);

    // If integration name not saved, try to auto-discover it
    if (!integrationName) {
      logger.info('Integration name not configured, attempting auto-discovery', {
        tenant_id: tenantId,
      });

      try {
        const discoveredName = await findIntegrationByClientId(
          accountIdentifier,
          response.access_token,
          clientId
        );

        if (discoveredName) {
          integrationName = discoveredName;
          // Save it for future use
          await saveSnowflakeIntegrationName(tenantId, discoveredName);
          logger.info('Auto-discovered and saved integration name', {
            tenant_id: tenantId,
            integration_name: discoveredName,
          });
        } else {
          logger.warn('Could not auto-discover integration name', {
            tenant_id: tenantId,
          });
        }
      } catch (error) {
        logger.error('Error auto-discovering integration name', {
          tenant_id: tenantId,
          error,
        });
      }
    }

    // Now try to get the actual refresh token validity if we have an integration name
    if (integrationName) {
      try {
        const actualValidity = await getOAuthRefreshTokenValidity(
          accountIdentifier,
          integrationName,
          response.access_token
        );
        if (actualValidity) {
          refreshTokenValiditySeconds = actualValidity;
          logger.info('Using actual OAUTH_REFRESH_TOKEN_VALIDITY from Snowflake', {
            tenant_id: tenantId,
            integration_name: integrationName,
            validity_seconds: actualValidity,
            validity_days: Math.floor(actualValidity / SECONDS_PER_DAY),
          });
        } else {
          logger.warn('Could not query OAUTH_REFRESH_TOKEN_VALIDITY, using default', {
            tenant_id: tenantId,
            integration_name: integrationName,
            default_days: 90,
          });
        }
      } catch (error) {
        logger.error('Error querying OAUTH_REFRESH_TOKEN_VALIDITY, using default', {
          tenant_id: tenantId,
          integration_name: integrationName,
          error,
          default_days: 90,
        });
      }
    } else {
      logger.info('No integration name found, using default refresh token validity', {
        tenant_id: tenantId,
        default_days: 90,
      });
    }

    const refreshTokenExpiresAtEpoch = now + refreshTokenValiditySeconds * 1000;
    const refreshTokenExpiresAt = new Date(refreshTokenExpiresAtEpoch).toISOString();

    // Save token with validity seconds for future refreshes
    // This ensures the cron job knows the correct validity period (30, 60, or 90 days)
    // If we couldn't query the actual value, refreshTokenValiditySeconds defaults to 90 days
    await saveSnowflakeOauthToken(tenantId, {
      access_token: response.access_token,
      refresh_token: response.refresh_token,
      access_token_expires_at: expiresAt,
      refresh_token_expires_at: refreshTokenExpiresAt,
      refresh_token_validity_seconds: refreshTokenValiditySeconds,
      username: response.username,
    });

    // Record connector installation
    await installConnector({
      tenantId,
      type: ConnectorType.Snowflake,
      externalId: accountIdentifier,
      externalMetadata: {
        username: response.username,
        integration_name: integrationName || null,
      },
    });

    logger.info('Snowflake OAuth flow completed successfully', {
      tenant_id: tenantId,
      account_identifier: accountIdentifier,
      username: response.username,
      refresh_token_validity_days: Math.floor(refreshTokenValiditySeconds / SECONDS_PER_DAY),
      integration_name: integrationName || 'not_configured',
    });

    return res.redirect(`${frontendUrl}/integrations/snowflake?oauth-success=true`);
  } catch (error) {
    logger.error('Error handling Snowflake OAuth callback', error, {
      tenant_id: tenantId,
      account_identifier: accountIdentifier,
    });
    return res.redirect(`${frontendUrl}/integrations/snowflake?oauth-error=OAuth exchange failed`);
  }
});

snowflakeOauthRouter.get('/stages', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const stages = await getSnowflakeStages(tenantId);
    return res.json({ stages });
  } catch (error) {
    logger.error('Failed to fetch Snowflake stages', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to fetch Snowflake stages' });
  }
});

snowflakeOauthRouter.get('/warehouses', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const warehouses = await getSnowflakeWarehouses(tenantId);
    return res.json({ warehouses });
  } catch (error) {
    logger.error('Failed to fetch Snowflake warehouses', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to fetch Snowflake warehouses' });
  }
});

snowflakeOauthRouter.get('/databases', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const databases = await getSnowflakeDatabases(tenantId);
    return res.json({ databases });
  } catch (error) {
    logger.error('Failed to fetch Snowflake databases', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to fetch Snowflake databases' });
  }
});

snowflakeOauthRouter.get('/semantic-views', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const semanticViews = await getSnowflakeSemanticViews(tenantId);
    return res.json({ semanticViews });
  } catch (error) {
    logger.error('Failed to fetch Snowflake semantic views', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to fetch Snowflake semantic views' });
  }
});

snowflakeOauthRouter.delete('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    // Import deleteConfigValue from config
    const { deleteConfigValue } = await import('../../../config/index.js');

    // Delete all Snowflake config keys
    await Promise.all(SNOWFLAKE_CONFIG_KEYS.map((key) => deleteConfigValue(key, tenantId)));

    // Mark connector as disconnected
    await uninstallConnector(tenantId, ConnectorType.Snowflake);

    logger.info('Snowflake disconnected successfully', {
      tenant_id: tenantId,
    });

    return res.json({ success: true });
  } catch (error) {
    logger.error('Error disconnecting Snowflake', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to disconnect Snowflake' });
  }
});

export { snowflakeOauthRouter };
