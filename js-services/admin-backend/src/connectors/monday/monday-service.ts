/**
 * Monday.com Service
 *
 * Handles OAuth flow, token management, and API interactions for Monday.com.
 *
 * OAuth endpoints from Monday.com docs:
 * - Authorization: https://auth.monday.com/oauth2/authorize
 * - Token Exchange: https://auth.monday.com/oauth2/token
 *
 * Token characteristics:
 * - Tokens do NOT expire
 * - No refresh token mechanism
 *
 * Sources:
 * - OAuth: https://developer.monday.com/apps/docs/oauth
 * - API: https://developer.monday.com/api-reference/docs/introduction-to-graphql
 */

import { SSMClient } from '@corporate-context/backend-common';
import { getConfigValue, saveConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { getFrontendUrl } from '../../utils/config.js';
import {
  MONDAY_ACCESS_TOKEN_KEY,
  MONDAY_ACCOUNT_ID_KEY,
  MONDAY_ACCOUNT_NAME_KEY,
  MONDAY_ACCOUNT_SLUG_KEY,
} from './monday-config.js';
import { getMondayClientId, getMondayClientSecret, getMondaySigningSecret } from './monday-env.js';

/**
 * Token response from Monday.com OAuth
 * Note: Monday.com does NOT return refresh_token or expires_in
 * Source: https://developer.monday.com/apps/docs/oauth
 */
interface MondayTokenResponse {
  access_token: string;
  token_type: 'Bearer';
}

/**
 * Account info from Monday.com GraphQL API /me endpoint
 */
interface MondayAccountInfo {
  id: string;
  name: string;
  slug: string;
}

// Monday.com OAuth endpoints
const AUTH_URL = 'https://auth.monday.com/oauth2/authorize';
const TOKEN_URL = 'https://auth.monday.com/oauth2/token';
const API_URL = 'https://api.monday.com/v2';

/**
 * Build Monday.com redirect URI from FRONTEND_URL
 * Follows the same pattern as other OAuth connectors
 */
function buildMondayRedirectUri(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/monday/oauth/callback`;
}

export class MondayService {
  /**
   * Build the OAuth authorization URL for Monday.com
   *
   * Authorization URL parameters (from docs):
   * - client_id: Your app's OAuth client ID
   * - redirect_uri: Must match configured redirect URI
   * - state: Recommended for CSRF protection
   *
   * Note: Monday.com OAuth does not require scope parameter - permissions
   * are configured in the app settings in Monday.com Developer Center.
   *
   * Source: https://developer.monday.com/apps/docs/oauth
   */
  public buildOAuthUrl(tenantId: string): string {
    // Use base64url JSON encoding for state to safely encode tenantId
    // This avoids issues with underscores or special characters in tenant IDs
    const state = Buffer.from(JSON.stringify({ tenantId })).toString('base64url');
    const clientId = getMondayClientId();
    const redirectUri = buildMondayRedirectUri();

    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      state,
    });

    return `${AUTH_URL}?${params.toString()}`;
  }

  /**
   * Exchange authorization code for access token
   *
   * Token exchange uses application/x-www-form-urlencoded format.
   * Response only includes access_token and token_type (no refresh token).
   *
   * Source: https://developer.monday.com/apps/docs/oauth
   */
  public async exchangeCodeForTokens(code: string, tenantId: string): Promise<void> {
    const clientId = getMondayClientId();
    const clientSecret = getMondayClientSecret();
    const redirectUri = buildMondayRedirectUri();

    const response = await fetch(TOKEN_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        code,
        redirect_uri: redirectUri,
        client_id: clientId,
        client_secret: clientSecret,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Monday.com token exchange failed', {
        status: response.status,
        error: errorText,
        redirect_uri: redirectUri,
        tenant_id: tenantId,
      });
      throw new Error(`Monday.com token exchange failed: ${response.status} - ${errorText}`);
    }

    const tokenResponse = (await response.json()) as MondayTokenResponse;
    const accountInfo = await this.getAccountInfo(tokenResponse.access_token);

    await this.storeTokensAndMetadata(tenantId, {
      accessToken: tokenResponse.access_token,
      accountId: accountInfo.id,
      accountName: accountInfo.name,
      accountSlug: accountInfo.slug,
    });

    // Store signing secret for webhook verification
    await this.storeSigningSecret(tenantId);

    await updateIntegrationStatus(tenantId, 'monday', true);
  }

  /**
   * Get account info from Monday.com GraphQL API
   * Uses the /me query to get current user and account details
   */
  private async getAccountInfo(accessToken: string): Promise<MondayAccountInfo> {
    const query = `
      query {
        me {
          account {
            id
            name
            slug
          }
        }
      }
    `;

    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        Authorization: accessToken,
        'Content-Type': 'application/json',
        'API-Version': '2024-01',
      },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to get Monday.com account info', {
        status: response.status,
        error: errorText,
      });
      throw new Error(`Failed to get Monday.com account info: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    const account = data?.data?.me?.account;

    if (!account?.id) {
      throw new Error('Monday.com API response missing account ID');
    }

    return {
      id: String(account.id),
      name: account.name || 'Unknown Account',
      slug: account.slug || '',
    };
  }

  /**
   * Store tokens and metadata
   *
   * Note: Monday.com tokens do not expire per documentation, so we don't store expiry.
   */
  private async storeTokensAndMetadata(
    tenantId: string,
    authData: {
      accessToken: string;
      accountId: string;
      accountName: string;
      accountSlug: string;
    }
  ): Promise<void> {
    await Promise.all([
      saveConfigValue(MONDAY_ACCESS_TOKEN_KEY, authData.accessToken, tenantId),
      saveConfigValue(MONDAY_ACCOUNT_ID_KEY, authData.accountId, tenantId),
      saveConfigValue(MONDAY_ACCOUNT_NAME_KEY, authData.accountName, tenantId),
      saveConfigValue(MONDAY_ACCOUNT_SLUG_KEY, authData.accountSlug, tenantId),
    ]);

    await installConnector({
      tenantId,
      type: ConnectorType.Monday,
      externalId: authData.accountId,
    });
  }

  /**
   * Store signing secret for webhook verification
   * The secret is global per app, stored per tenant for verification
   */
  private async storeSigningSecret(tenantId: string): Promise<void> {
    try {
      const signingSecret = getMondaySigningSecret();
      const ssmClient = new SSMClient();
      const stored = await ssmClient.storeSigningSecret(tenantId, 'monday', signingSecret);
      if (stored) {
        logger.info('Stored Monday.com signing secret', { tenant_id: tenantId });
      } else {
        logger.warn('Failed to store Monday.com signing secret', { tenant_id: tenantId });
      }
    } catch (error) {
      logger.warn('Failed to store Monday.com signing secret', {
        tenant_id: tenantId,
        error: error instanceof Error ? error.message : String(error),
      });
      // Don't throw - signing secret storage failure shouldn't block OAuth
    }
  }

  /**
   * Get valid access token for API calls
   * Monday.com tokens don't expire, so we just return the stored token
   */
  public async getValidAccessToken(tenantId: string): Promise<string | null> {
    const accessToken = await getConfigValue(MONDAY_ACCESS_TOKEN_KEY, tenantId);
    return typeof accessToken === 'string' ? accessToken : null;
  }

  /**
   * Verify Monday.com is connected for a tenant
   */
  public async isConnected(tenantId: string): Promise<boolean> {
    const token = await this.getValidAccessToken(tenantId);
    return !!token;
  }
}

export const mondayService = new MondayService();
