/**
 * Pipedrive OAuth Service
 *
 * Handles OAuth 2.0 authorization code flow for Pipedrive.
 *
 * OAuth endpoints:
 * - Authorization: https://oauth.pipedrive.com/oauth/authorize
 * - Token exchange: https://oauth.pipedrive.com/oauth/token
 *
 * Token characteristics:
 * - Access tokens expire (expires_in is returned)
 * - Refresh tokens expire after 60 days of non-use
 * - api_domain is returned in token response
 *
 * Sources:
 * - https://pipedrive.readme.io/docs/marketplace-oauth-authorization
 * - https://developers.pipedrive.com/docs/api/v1/Oauth
 */

import { saveConfigValue, getConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { getFrontendUrl } from '../../utils/config.js';
import {
  PIPEDRIVE_ACCESS_TOKEN_KEY,
  PIPEDRIVE_REFRESH_TOKEN_KEY,
  PIPEDRIVE_API_DOMAIN_KEY,
  PIPEDRIVE_COMPANY_ID_KEY,
  PIPEDRIVE_COMPANY_NAME_KEY,
  PIPEDRIVE_TOKEN_EXPIRES_AT_KEY,
} from './pipedrive-config.js';

// Pipedrive OAuth URLs
const OAUTH_AUTHORIZE_URL = 'https://oauth.pipedrive.com/oauth/authorize';
const OAUTH_TOKEN_URL = 'https://oauth.pipedrive.com/oauth/token';

/**
 * Token response from Pipedrive OAuth
 */
interface PipedriveTokenResponse {
  access_token: string;
  token_type: 'Bearer';
  expires_in: number;
  refresh_token: string;
  scope: string;
  api_domain: string;
}

/**
 * User info from Pipedrive /users/me endpoint
 */
interface PipedriveUserInfo {
  id: number;
  name: string;
  email: string;
  company_id: number;
  company_name?: string;
}

/**
 * Get Pipedrive client ID from environment
 */
function getPipedriveClientId(): string {
  const value = process.env.PIPEDRIVE_CLIENT_ID;
  if (!value) {
    throw new Error('PIPEDRIVE_CLIENT_ID environment variable is required');
  }
  return value;
}

/**
 * Get Pipedrive client secret from environment
 */
function getPipedriveClientSecret(): string {
  const value = process.env.PIPEDRIVE_CLIENT_SECRET;
  if (!value) {
    throw new Error('PIPEDRIVE_CLIENT_SECRET environment variable is required');
  }
  return value;
}

/**
 * Build the OAuth redirect URI
 */
function buildPipedriveRedirectUri(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/pipedrive/oauth/callback`;
}

export class PipedriveService {
  /**
   * Build the OAuth authorization URL
   *
   * @param tenantId - Tenant ID to encode in state
   * @returns Authorization URL to redirect the user to
   */
  public buildOAuthUrl(tenantId: string): string {
    // Use base64url encoding for state to safely pass tenant ID
    const stateData = { tenantId };
    const state = Buffer.from(JSON.stringify(stateData)).toString('base64url');

    const clientId = getPipedriveClientId();
    const redirectUri = buildPipedriveRedirectUri();

    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      state,
    });

    return `${OAUTH_AUTHORIZE_URL}?${params.toString()}`;
  }

  /**
   * Parse the state parameter from OAuth callback
   *
   * @param state - Base64url encoded state string
   * @returns Parsed state object with tenantId
   */
  public parseOAuthState(state: string): { tenantId: string } {
    try {
      const decoded = Buffer.from(state, 'base64url').toString();
      const parsed = JSON.parse(decoded);
      if (!parsed.tenantId) {
        throw new Error('Missing tenantId in state');
      }
      return parsed;
    } catch (error) {
      logger.error('Failed to parse Pipedrive OAuth state', { state, error });
      throw new Error('Invalid OAuth state parameter');
    }
  }

  /**
   * Exchange authorization code for tokens
   *
   * @param code - Authorization code from OAuth callback
   * @param tenantId - Tenant ID for storing credentials
   */
  public async exchangeCodeForTokens(code: string, tenantId: string): Promise<void> {
    const clientId = getPipedriveClientId();
    const clientSecret = getPipedriveClientSecret();
    const redirectUri = buildPipedriveRedirectUri();

    // Pipedrive requires Basic auth with client_id:client_secret
    const basicAuth = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');

    const response = await fetch(OAUTH_TOKEN_URL, {
      method: 'POST',
      headers: {
        Authorization: `Basic ${basicAuth}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        code,
        redirect_uri: redirectUri,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Pipedrive token exchange failed', {
        status: response.status,
        error: errorText,
        tenant_id: tenantId,
      });
      throw new Error(`Pipedrive token exchange failed: ${response.status} - ${errorText}`);
    }

    const tokenResponse = (await response.json()) as PipedriveTokenResponse;

    // Get company info
    const userInfo = await this.getCurrentUser(
      tokenResponse.access_token,
      tokenResponse.api_domain
    );

    // Store credentials
    await this.storeCredentials(tenantId, {
      accessToken: tokenResponse.access_token,
      refreshToken: tokenResponse.refresh_token,
      expiresIn: tokenResponse.expires_in,
      apiDomain: tokenResponse.api_domain,
      companyId: String(userInfo.company_id),
      companyName: userInfo.company_name || userInfo.name,
    });

    await updateIntegrationStatus(tenantId, 'pipedrive', true);
  }

  /**
   * Get current user info from Pipedrive
   */
  private async getCurrentUser(accessToken: string, apiDomain: string): Promise<PipedriveUserInfo> {
    const response = await fetch(`${apiDomain}/api/v1/users/me`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to get Pipedrive user info', {
        status: response.status,
        error: errorText,
      });
      throw new Error(`Failed to get Pipedrive user info: ${response.status}`);
    }

    const data = await response.json();
    return data.data as PipedriveUserInfo;
  }

  /**
   * Store OAuth credentials
   */
  private async storeCredentials(
    tenantId: string,
    credentials: {
      accessToken: string;
      refreshToken: string;
      expiresIn: number;
      apiDomain: string;
      companyId: string;
      companyName: string;
    }
  ): Promise<void> {
    // Calculate expiration time
    const expiresAt = new Date(Date.now() + credentials.expiresIn * 1000).toISOString();

    // Store all credentials using unified config manager
    // Sensitive keys (tokens) auto-route to SSM, non-sensitive to DB
    await Promise.all([
      saveConfigValue(PIPEDRIVE_ACCESS_TOKEN_KEY, credentials.accessToken, tenantId),
      saveConfigValue(PIPEDRIVE_REFRESH_TOKEN_KEY, credentials.refreshToken, tenantId),
      saveConfigValue(PIPEDRIVE_API_DOMAIN_KEY, credentials.apiDomain, tenantId),
      saveConfigValue(PIPEDRIVE_COMPANY_ID_KEY, credentials.companyId, tenantId),
      saveConfigValue(PIPEDRIVE_COMPANY_NAME_KEY, credentials.companyName, tenantId),
      saveConfigValue(PIPEDRIVE_TOKEN_EXPIRES_AT_KEY, expiresAt, tenantId),
    ]);

    // Register connector installation
    await installConnector({
      tenantId,
      type: ConnectorType.Pipedrive,
      externalId: credentials.companyId,
    });

    logger.info('Stored Pipedrive credentials', {
      tenant_id: tenantId,
      company_id: credentials.companyId,
      company_name: credentials.companyName,
      api_domain: credentials.apiDomain,
    });
  }

  /**
   * Refresh access token using refresh token
   */
  public async refreshAccessToken(tenantId: string): Promise<void> {
    const refreshToken = await getConfigValue(PIPEDRIVE_REFRESH_TOKEN_KEY, tenantId);

    if (!refreshToken || typeof refreshToken !== 'string') {
      throw new Error('No refresh token found for tenant');
    }

    const clientId = getPipedriveClientId();
    const clientSecret = getPipedriveClientSecret();
    const basicAuth = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');

    const response = await fetch(OAUTH_TOKEN_URL, {
      method: 'POST',
      headers: {
        Authorization: `Basic ${basicAuth}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Pipedrive token refresh failed', {
        status: response.status,
        error: errorText,
        tenant_id: tenantId,
      });
      throw new Error(`Pipedrive token refresh failed: ${response.status}`);
    }

    const tokenResponse = (await response.json()) as PipedriveTokenResponse;

    // Update stored tokens using unified config manager
    // Note: Pipedrive only returns a new refresh_token if it has changed
    const expiresAt = new Date(Date.now() + tokenResponse.expires_in * 1000).toISOString();
    const savePromises = [
      saveConfigValue(PIPEDRIVE_ACCESS_TOKEN_KEY, tokenResponse.access_token, tenantId),
      saveConfigValue(PIPEDRIVE_TOKEN_EXPIRES_AT_KEY, expiresAt, tenantId),
    ];

    // Only update refresh token if a new one was provided
    if (tokenResponse.refresh_token) {
      savePromises.push(
        saveConfigValue(PIPEDRIVE_REFRESH_TOKEN_KEY, tokenResponse.refresh_token, tenantId)
      );
    }

    await Promise.all(savePromises);

    logger.info('Refreshed Pipedrive access token', { tenant_id: tenantId });
  }
}
