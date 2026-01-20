/**
 * Canva OAuth Service
 *
 * Handles OAuth 2.0 authorization code flow with PKCE for Canva.
 *
 * OAuth endpoints:
 * - Authorization: https://www.canva.com/api/oauth/authorize
 * - Token exchange: https://api.canva.com/rest/v1/oauth/token
 *
 * Token characteristics:
 * - Access tokens expire after ~4 hours (14400 seconds)
 * - Refresh tokens can only be used once (they rotate)
 *
 * Required Scopes:
 * - profile:read - Read user profile (display_name) via /users/me/profile
 * - design:meta:read - Read access to design metadata (title, dates, owner)
 * - design:content:read - Read access to design content
 * - folder:read - Read access to folders
 * - asset:read - Read access to assets (for future use)
 *
 * Note: /users/me endpoint (user_id, team_id) requires no scope
 *
 * Sources:
 * - https://www.canva.dev/docs/connect/authentication/
 * - https://www.canva.dev/docs/connect/api-reference/users/users-me/
 * - https://www.canva.dev/docs/connect/api-reference/users/users-profile/
 */

import crypto from 'crypto';
import { saveConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { getFrontendUrl } from '../../utils/config.js';
import {
  CANVA_ACCESS_TOKEN_KEY,
  CANVA_REFRESH_TOKEN_KEY,
  CANVA_USER_ID_KEY,
  CANVA_USER_DISPLAY_NAME_KEY,
  CANVA_TOKEN_EXPIRES_AT_KEY,
  CANVA_FULL_BACKFILL_COMPLETE_KEY,
  CANVA_DESIGNS_SYNCED_UNTIL_KEY,
} from './canva-config.js';

// Canva OAuth URLs
const OAUTH_AUTHORIZE_URL = 'https://www.canva.com/api/oauth/authorize';
const OAUTH_TOKEN_URL = 'https://api.canva.com/rest/v1/oauth/token';
const CANVA_API_URL = 'https://api.canva.com/rest/v1';

// PKCE code verifier storage (in-memory, short-lived)
// In production, consider using Redis with TTL for distributed systems
const codeVerifiers = new Map<string, { verifier: string; createdAt: number }>();

// Clean up old verifiers every 5 minutes
setInterval(
  () => {
    const now = Date.now();
    for (const [key, value] of codeVerifiers) {
      // Remove verifiers older than 10 minutes
      if (now - value.createdAt > 10 * 60 * 1000) {
        codeVerifiers.delete(key);
      }
    }
  },
  5 * 60 * 1000
);

/**
 * Token response from Canva OAuth
 */
interface CanvaTokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
  scope: string;
}

/**
 * User info from Canva /users/me endpoint
 * Response is wrapped: { team_user: { user_id, team_id } }
 */
interface CanvaTeamUser {
  user_id: string;
  team_id?: string;
}

interface CanvaUserInfoResponse {
  team_user: CanvaTeamUser;
}

/**
 * User profile from Canva /users/me/profile endpoint
 * Response is wrapped: { profile: { display_name } }
 */
interface CanvaProfile {
  display_name?: string;
}

interface CanvaUserProfileResponse {
  profile: CanvaProfile;
}

/**
 * Get Canva client ID from environment
 */
function getCanvaClientId(): string {
  const value = process.env.CANVA_CLIENT_ID;
  if (!value) {
    throw new Error('CANVA_CLIENT_ID environment variable is required');
  }
  return value;
}

/**
 * Get Canva client secret from environment
 */
function getCanvaClientSecret(): string {
  const value = process.env.CANVA_CLIENT_SECRET;
  if (!value) {
    throw new Error('CANVA_CLIENT_SECRET environment variable is required');
  }
  return value;
}

/**
 * Build the OAuth redirect URI
 * Note: Canva requires 127.0.0.1 instead of localhost for local development
 */
function buildCanvaRedirectUri(): string {
  const frontendUrl = getFrontendUrl();
  // Canva requires 127.0.0.1, not localhost, for local development
  const canvaCompatibleUrl = frontendUrl.replace('://localhost:', '://127.0.0.1:');
  return `${canvaCompatibleUrl}/api/canva/oauth/callback`;
}

/**
 * Generate PKCE code verifier and challenge
 */
function generatePKCE(): { verifier: string; challenge: string } {
  // Generate a random 32-byte code verifier
  const verifier = crypto.randomBytes(32).toString('base64url');

  // Create SHA256 hash of verifier for challenge
  const challenge = crypto.createHash('sha256').update(verifier).digest('base64url');

  return { verifier, challenge };
}

export class CanvaService {
  /**
   * Build the OAuth authorization URL
   *
   * @param tenantId - Tenant ID to encode in state
   * @returns Authorization URL to redirect the user to
   */
  public buildOAuthUrl(tenantId: string): string {
    // Generate PKCE
    const { verifier, challenge } = generatePKCE();

    // Use base64url encoding for state to safely pass tenant ID
    const stateData = { tenantId };
    const state = Buffer.from(JSON.stringify(stateData)).toString('base64url');

    // Store verifier for later token exchange
    codeVerifiers.set(state, { verifier, createdAt: Date.now() });

    const clientId = getCanvaClientId();
    const redirectUri = buildCanvaRedirectUri();

    // Request design and folder read scopes
    // profile:read is required for /users/me/profile (display_name)
    const scopes = [
      'profile:read',
      'design:meta:read',
      'design:content:read',
      'folder:read',
      'asset:read',
    ];

    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      scope: scopes.join(' '),
      state,
      response_type: 'code',
      code_challenge: challenge,
      code_challenge_method: 'S256',
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
      logger.error(
        'Failed to parse Canva OAuth state',
        error instanceof Error ? error : new Error(String(error)),
        { state }
      );
      throw new Error('Invalid OAuth state parameter');
    }
  }

  /**
   * Exchange authorization code for tokens
   *
   * @param code - Authorization code from OAuth callback
   * @param state - State parameter for PKCE verifier lookup
   * @param tenantId - Tenant ID for storing credentials
   */
  public async exchangeCodeForTokens(code: string, state: string, tenantId: string): Promise<void> {
    const clientId = getCanvaClientId();
    const clientSecret = getCanvaClientSecret();
    const redirectUri = buildCanvaRedirectUri();

    // Get PKCE verifier from state
    const verifierData = codeVerifiers.get(state);
    if (!verifierData) {
      throw new Error('PKCE code verifier not found - OAuth state may have expired');
    }
    const { verifier } = verifierData;

    // Remove verifier after use (it's single-use)
    codeVerifiers.delete(state);

    // Build Basic auth header
    const credentials = `${clientId}:${clientSecret}`;
    const basicAuth = Buffer.from(credentials).toString('base64');

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
        code_verifier: verifier,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Canva token exchange failed', undefined, {
        status: response.status,
        error: errorText,
        tenant_id: tenantId,
      });
      throw new Error(`Canva token exchange failed: ${response.status} - ${errorText}`);
    }

    const tokenResponse = (await response.json()) as CanvaTokenResponse;

    // Get user info and profile (display_name is in a separate endpoint)
    const [userInfo, userProfile] = await Promise.all([
      this.getCurrentUser(tokenResponse.access_token),
      this.getUserProfile(tokenResponse.access_token),
    ]);

    // Store credentials
    await this.storeCredentials(tenantId, {
      accessToken: tokenResponse.access_token,
      refreshToken: tokenResponse.refresh_token,
      expiresIn: tokenResponse.expires_in,
      userId: userInfo.user_id,
      userDisplayName: userProfile.display_name,
    });

    await updateIntegrationStatus(tenantId, 'canva', true);
  }

  /**
   * Get current user info from Canva (/users/me)
   * Response format: { team_user: { user_id, team_id } }
   */
  private async getCurrentUser(accessToken: string): Promise<CanvaTeamUser> {
    const response = await fetch(`${CANVA_API_URL}/users/me`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to get Canva user info', undefined, {
        status: response.status,
        error: errorText,
      });
      throw new Error(`Failed to get Canva user info: ${response.status}`);
    }

    const data = (await response.json()) as CanvaUserInfoResponse;
    logger.info('Got Canva user info', { team_user: data.team_user });
    return data.team_user;
  }

  /**
   * Get current user profile from Canva (/users/me/profile)
   * Response format: { profile: { display_name } }
   */
  private async getUserProfile(accessToken: string): Promise<CanvaProfile> {
    const response = await fetch(`${CANVA_API_URL}/users/me/profile`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      // Profile endpoint might fail, return empty profile
      const errorText = await response.text();
      logger.warn('Failed to get Canva user profile, using default', {
        status: response.status,
        error: errorText,
      });
      return {};
    }

    const data = (await response.json()) as CanvaUserProfileResponse;
    logger.info('Got Canva user profile', { profile: data.profile });
    return data.profile;
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
      userId: string;
      userDisplayName?: string;
    }
  ): Promise<void> {
    // Calculate expiration time (expires_in is in seconds)
    const expiresAt = new Date(Date.now() + credentials.expiresIn * 1000).toISOString();

    // Store all credentials using unified config manager
    // Sensitive keys (tokens) auto-route to SSM, non-sensitive to DB
    await Promise.all([
      saveConfigValue(CANVA_ACCESS_TOKEN_KEY, credentials.accessToken, tenantId),
      saveConfigValue(CANVA_REFRESH_TOKEN_KEY, credentials.refreshToken, tenantId),
      saveConfigValue(CANVA_USER_ID_KEY, credentials.userId, tenantId),
      saveConfigValue(
        CANVA_USER_DISPLAY_NAME_KEY,
        credentials.userDisplayName || 'Unknown',
        tenantId
      ),
      saveConfigValue(CANVA_TOKEN_EXPIRES_AT_KEY, expiresAt, tenantId),
    ]);

    // Register connector installation
    await installConnector({
      tenantId,
      type: ConnectorType.Canva,
      externalId: credentials.userId,
      externalMetadata: {},
      updateMetadataOnExisting: false,
    });

    logger.info('Stored Canva credentials', {
      tenant_id: tenantId,
      user_id: credentials.userId,
      user_display_name: credentials.userDisplayName,
    });
  }

  /**
   * Reset backfill state (called on disconnect for fresh reconnect)
   */
  public async resetBackfillState(tenantId: string): Promise<void> {
    await Promise.all([
      saveConfigValue(CANVA_FULL_BACKFILL_COMPLETE_KEY, '', tenantId),
      saveConfigValue(CANVA_DESIGNS_SYNCED_UNTIL_KEY, '', tenantId),
    ]);
    logger.info('Reset Canva backfill state', { tenant_id: tenantId });
  }
}
