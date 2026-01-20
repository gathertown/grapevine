import { saveConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { getFrontendUrl } from '../../utils/config.js';
import {
  TEAMWORK_ACCESS_TOKEN_KEY,
  TEAMWORK_API_DOMAIN_KEY,
  TEAMWORK_INSTALLATION_ID_KEY,
  TEAMWORK_USER_ID_KEY,
  TEAMWORK_USER_NAME_KEY,
} from './teamwork-config.js';

/**
 * Teamwork OAuth Configuration
 *
 * OAuth endpoints from Teamwork docs:
 * - Authorization: https://www.teamwork.com/launchpad/login/
 * - Token Exchange: https://www.teamwork.com/launchpad/v1/token.json
 * - User Info: https://www.teamwork.com/launchpad/v1/userinfo.json
 *
 * Note: Teamwork access tokens are long-lived (permanent), no refresh token needed.
 *
 * Source: https://apidocs.teamwork.com/guides/teamwork/authentication
 */

// Teamwork OAuth endpoints
const AUTH_URL = 'https://www.teamwork.com/launchpad/login/';
const TOKEN_URL = 'https://www.teamwork.com/launchpad/v1/token.json';
const USERINFO_URL = 'https://www.teamwork.com/launchpad/v1/userinfo.json';

/**
 * Token response from Teamwork OAuth
 * Access tokens are permanent, no refresh token.
 */
type TeamworkTokenResponse = {
  access_token: string;
  token_type: string;
  installation: {
    id: number;
    name: string;
    apiEndPoint: string;
    region: string;
  };
};

/**
 * User info response from Teamwork /launchpad/v1/userinfo.json
 */
type TeamworkUserInfoResponse = {
  id: number;
  email: string;
  firstName?: string;
  lastName?: string;
};

/**
 * Get Teamwork client ID from environment
 */
function getTeamworkClientId(): string {
  const value = process.env.TEAMWORK_CLIENT_ID;
  if (!value) {
    throw new Error('TEAMWORK_CLIENT_ID environment variable is required for Teamwork OAuth');
  }
  return value;
}

/**
 * Get Teamwork client secret from environment
 */
function getTeamworkClientSecret(): string {
  const value = process.env.TEAMWORK_CLIENT_SECRET;
  if (!value) {
    throw new Error('TEAMWORK_CLIENT_SECRET environment variable is required for Teamwork OAuth');
  }
  return value;
}

/**
 * Build Teamwork redirect URI from FRONTEND_URL
 */
function buildTeamworkRedirectUri(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/teamwork/oauth/callback`;
}

export class TeamworkService {
  /**
   * Build the OAuth authorization URL for Teamwork
   *
   * Authorization URL parameters:
   * - client_id: Your app's OAuth client ID
   * - redirect_uri: Must match configured redirect URI
   *
   * Source: https://apidocs.teamwork.com/guides/teamwork/app-login-flow
   */
  public buildOAuthUrl(tenantId: string): string {
    const clientId = getTeamworkClientId();
    const redirectUri = buildTeamworkRedirectUri();

    // Use base64url encoding for state to safely include tenant ID
    const stateData = { tenantId };
    const state = Buffer.from(JSON.stringify(stateData)).toString('base64url');

    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
    });

    return `${AUTH_URL}?${params.toString()}&state=${state}`;
  }

  /**
   * Exchange authorization code for access token
   *
   * Token exchange uses JSON body format.
   *
   * Source: https://apidocs.teamwork.com/guides/teamwork/app-login-flow
   */
  public async exchangeCodeForTokens(code: string, tenantId: string): Promise<void> {
    const clientId = getTeamworkClientId();
    const clientSecret = getTeamworkClientSecret();
    const redirectUri = buildTeamworkRedirectUri();

    const response = await fetch(TOKEN_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        code,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Teamwork token exchange failed', {
        status: response.status,
        error: errorText,
        redirect_uri: redirectUri,
        tenant_id: tenantId,
      });
      throw new Error(`Teamwork token exchange failed: ${response.status} - ${errorText}`);
    }

    const tokenResponse = (await response.json()) as TeamworkTokenResponse;

    logger.info('Teamwork token response received', {
      tenant_id: tenantId,
      has_access_token: !!tokenResponse.access_token,
      has_installation: !!tokenResponse.installation,
      installation_id: tokenResponse.installation?.id,
      api_endpoint: tokenResponse.installation?.apiEndPoint,
    });

    // Get user info for display name
    const userInfo = await this.getUserInfo(tokenResponse.access_token);

    logger.info('Teamwork user info received', {
      tenant_id: tenantId,
      user_id: userInfo.id,
      email: userInfo.email,
    });

    await this.storeTokensAndMetadata(tenantId, {
      accessToken: tokenResponse.access_token,
      apiDomain: tokenResponse.installation?.apiEndPoint || '',
      installationId: tokenResponse.installation?.id || 0,
      userId: userInfo.id || 0,
      userName:
        `${userInfo.firstName || ''} ${userInfo.lastName || ''}`.trim() ||
        userInfo.email ||
        'Unknown',
    });

    await updateIntegrationStatus(tenantId, 'teamwork', true);
  }

  /**
   * Get user info from Teamwork API
   */
  private async getUserInfo(accessToken: string): Promise<TeamworkUserInfoResponse> {
    const response = await fetch(USERINFO_URL, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to get Teamwork user info', {
        status: response.status,
        error: errorText,
      });
      throw new Error(`Failed to get Teamwork user info: ${response.status} ${errorText}`);
    }

    return (await response.json()) as TeamworkUserInfoResponse;
  }

  /**
   * Store tokens and metadata
   *
   * Note: Teamwork tokens are permanent, no expiry.
   */
  private async storeTokensAndMetadata(
    tenantId: string,
    authData: {
      accessToken: string;
      apiDomain: string;
      installationId: number;
      userId: number;
      userName: string;
    }
  ): Promise<void> {
    await Promise.all([
      saveConfigValue(TEAMWORK_ACCESS_TOKEN_KEY, authData.accessToken, tenantId),
      saveConfigValue(TEAMWORK_API_DOMAIN_KEY, authData.apiDomain, tenantId),
      saveConfigValue(TEAMWORK_INSTALLATION_ID_KEY, authData.installationId.toString(), tenantId),
      saveConfigValue(TEAMWORK_USER_ID_KEY, authData.userId.toString(), tenantId),
      saveConfigValue(TEAMWORK_USER_NAME_KEY, authData.userName, tenantId),
    ]);

    await installConnector({
      tenantId,
      type: ConnectorType.Teamwork,
      externalId: authData.installationId.toString(),
    });
  }
}
