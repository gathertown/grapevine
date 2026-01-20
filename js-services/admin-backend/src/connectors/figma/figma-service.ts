/**
 * Figma OAuth Service
 *
 * Handles OAuth 2.0 authorization code flow for Figma.
 *
 * OAuth endpoints:
 * - Authorization: https://www.figma.com/oauth
 * - Token exchange: https://api.figma.com/v1/oauth/token
 * - Token refresh: https://api.figma.com/v1/oauth/refresh
 *
 * Token characteristics:
 * - Authorization codes expire in 30 seconds (exchange immediately!)
 * - Access tokens expire after 90 days
 * - Refresh tokens are long-lived
 *
 * Scopes:
 * - file_content:read - Read access to file content
 * - file_metadata:read - Read access to file metadata
 * - file_comments:read - Read access to file comments
 * - projects:read - List projects and files in projects (required for team access)
 * - webhooks:write - Create/manage webhooks for real-time updates
 * - webhooks:read - List existing webhooks (for deduplication)
 *
 * Sources:
 * - https://www.figma.com/developers/api#oauth2
 */

import crypto from 'crypto';
import { SSMClient } from '@corporate-context/backend-common';
import { saveConfigValue, getConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorInstallationsRepository } from '../../dal/connector-installations.js';
import { ConnectorType } from '../../types/connector.js';
import { getFrontendUrl, getGatekeeperUrl } from '../../utils/config.js';
import {
  FIGMA_ACCESS_TOKEN_KEY,
  FIGMA_REFRESH_TOKEN_KEY,
  FIGMA_USER_ID_KEY,
  FIGMA_USER_EMAIL_KEY,
  FIGMA_USER_HANDLE_KEY,
  FIGMA_TOKEN_EXPIRES_AT_KEY,
  FIGMA_WEBHOOK_PASSCODE_KEY,
} from './figma-config.js';

// Figma OAuth URLs
const OAUTH_AUTHORIZE_URL = 'https://www.figma.com/oauth';
const OAUTH_TOKEN_URL = 'https://api.figma.com/v1/oauth/token';
const OAUTH_REFRESH_URL = 'https://api.figma.com/v1/oauth/refresh';
const FIGMA_API_URL = 'https://api.figma.com/v1';
const FIGMA_API_V2_URL = 'https://api.figma.com/v2';

/**
 * Token response from Figma OAuth
 */
interface FigmaTokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user_id: string;
}

/**
 * User info from Figma /me endpoint
 */
interface FigmaUserInfo {
  id: string;
  email: string;
  handle: string;
  img_url: string;
}

/**
 * Webhook response from Figma API v2
 * See: https://developers.figma.com/docs/rest-api/webhooks-endpoints/
 */
interface FigmaWebhook {
  id: string;
  event_type: string;
  context: 'team' | 'file' | 'project';
  context_id: string;
  status: string;
  endpoint: string;
  description?: string;
}

/**
 * Figma webhook event types we want to subscribe to
 */
const FIGMA_WEBHOOK_EVENT_TYPES = ['FILE_UPDATE', 'FILE_DELETE', 'FILE_COMMENT'] as const;

/**
 * Get Figma client ID from environment
 */
function getFigmaClientId(): string {
  const value = process.env.FIGMA_CLIENT_ID;
  if (!value) {
    throw new Error('FIGMA_CLIENT_ID environment variable is required');
  }
  return value;
}

/**
 * Get Figma client secret from environment
 */
function getFigmaClientSecret(): string {
  const value = process.env.FIGMA_CLIENT_SECRET;
  if (!value) {
    throw new Error('FIGMA_CLIENT_SECRET environment variable is required');
  }
  return value;
}

/**
 * Build the OAuth redirect URI
 */
function buildFigmaRedirectUri(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/figma/oauth/callback`;
}

export class FigmaService {
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

    const clientId = getFigmaClientId();
    const redirectUri = buildFigmaRedirectUri();

    // Request user info, file content, metadata, comment, project read, and webhook access
    // Note: projects:read is required to access team projects via /v1/teams/:team_id/projects
    // Note: webhooks:write is required to create webhooks for real-time updates
    // Note: webhooks:read is required to list existing webhooks (for deduplication)
    const scopes = [
      'current_user:read',
      'file_content:read',
      'file_metadata:read',
      'file_comments:read',
      'projects:read',
      'webhooks:write',
      'webhooks:read',
    ];

    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      scope: scopes.join(' '),
      state,
      response_type: 'code',
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
        'Failed to parse Figma OAuth state',
        error instanceof Error ? error : new Error(String(error)),
        { state }
      );
      throw new Error('Invalid OAuth state parameter');
    }
  }

  /**
   * Exchange authorization code for tokens
   *
   * IMPORTANT: Figma auth codes expire in 30 seconds - call this immediately!
   *
   * @param code - Authorization code from OAuth callback
   * @param tenantId - Tenant ID for storing credentials
   */
  public async exchangeCodeForTokens(code: string, tenantId: string): Promise<void> {
    const clientId = getFigmaClientId();
    const clientSecret = getFigmaClientSecret();
    const redirectUri = buildFigmaRedirectUri();

    const response = await fetch(OAUTH_TOKEN_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri,
        code,
        grant_type: 'authorization_code',
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Figma token exchange failed', undefined, {
        status: response.status,
        error: errorText,
        tenant_id: tenantId,
      });
      throw new Error(`Figma token exchange failed: ${response.status} - ${errorText}`);
    }

    const tokenResponse = (await response.json()) as FigmaTokenResponse;

    // Get user info
    const userInfo = await this.getCurrentUser(tokenResponse.access_token);

    // Store credentials
    await this.storeCredentials(tenantId, {
      accessToken: tokenResponse.access_token,
      refreshToken: tokenResponse.refresh_token,
      expiresIn: tokenResponse.expires_in,
      userId: userInfo.id,
      userEmail: userInfo.email,
      userHandle: userInfo.handle,
    });

    await updateIntegrationStatus(tenantId, 'figma', true);
  }

  /**
   * Get current user info from Figma
   */
  private async getCurrentUser(accessToken: string): Promise<FigmaUserInfo> {
    const response = await fetch(`${FIGMA_API_URL}/me`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to get Figma user info', undefined, {
        status: response.status,
        error: errorText,
      });
      throw new Error(`Failed to get Figma user info: ${response.status}`);
    }

    return (await response.json()) as FigmaUserInfo;
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
      userEmail: string;
      userHandle: string;
    }
  ): Promise<void> {
    // Calculate expiration time (expires_in is in seconds)
    const expiresAt = new Date(Date.now() + credentials.expiresIn * 1000).toISOString();

    // Store all credentials using unified config manager
    // Sensitive keys (tokens) auto-route to SSM, non-sensitive to DB
    await Promise.all([
      saveConfigValue(FIGMA_ACCESS_TOKEN_KEY, credentials.accessToken, tenantId),
      saveConfigValue(FIGMA_REFRESH_TOKEN_KEY, credentials.refreshToken, tenantId),
      saveConfigValue(FIGMA_USER_ID_KEY, credentials.userId, tenantId),
      saveConfigValue(FIGMA_USER_EMAIL_KEY, credentials.userEmail, tenantId),
      saveConfigValue(FIGMA_USER_HANDLE_KEY, credentials.userHandle, tenantId),
      saveConfigValue(FIGMA_TOKEN_EXPIRES_AT_KEY, expiresAt, tenantId),
    ]);

    // Check for existing disconnected connector with team selection (reconnection scenario)
    // We need to preserve the selected_team_ids from the old connector
    const connectorRepo = new ConnectorInstallationsRepository();
    const existingDisconnected = await connectorRepo.getDisconnectedByTenantAndType(
      tenantId,
      ConnectorType.Figma
    );

    let preservedMetadata: Record<string, unknown> = {};
    if (existingDisconnected?.external_metadata?.selected_team_ids) {
      preservedMetadata = {
        selected_team_ids: existingDisconnected.external_metadata.selected_team_ids,
        synced_team_ids: existingDisconnected.external_metadata.synced_team_ids || [],
      };
      logger.info('Preserving team selection from previous connection', {
        tenant_id: tenantId,
        team_count: (existingDisconnected.external_metadata.selected_team_ids as string[]).length,
      });
    }

    // Register connector installation with preserved metadata
    await installConnector({
      tenantId,
      type: ConnectorType.Figma,
      externalId: credentials.userId,
      externalMetadata: preservedMetadata,
      updateMetadataOnExisting: Object.keys(preservedMetadata).length > 0,
    });

    logger.info('Stored Figma credentials', {
      tenant_id: tenantId,
      user_id: credentials.userId,
      user_email: credentials.userEmail,
      user_handle: credentials.userHandle,
    });
  }

  /**
   * Refresh access token using refresh token
   *
   * Figma access tokens are long-lived (90 days), but can be refreshed.
   */
  public async refreshAccessToken(tenantId: string): Promise<void> {
    const refreshToken = await getConfigValue(FIGMA_REFRESH_TOKEN_KEY, tenantId);

    if (!refreshToken || typeof refreshToken !== 'string') {
      throw new Error('No refresh token found for tenant');
    }

    const clientId = getFigmaClientId();
    const clientSecret = getFigmaClientSecret();

    const response = await fetch(OAUTH_REFRESH_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        refresh_token: refreshToken,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Figma token refresh failed', undefined, {
        status: response.status,
        error: errorText,
        tenant_id: tenantId,
      });
      throw new Error(`Figma token refresh failed: ${response.status}`);
    }

    const tokenResponse = (await response.json()) as FigmaTokenResponse;

    // Update stored tokens using unified config manager
    const expiresAt = new Date(Date.now() + tokenResponse.expires_in * 1000).toISOString();
    const savePromises = [
      saveConfigValue(FIGMA_ACCESS_TOKEN_KEY, tokenResponse.access_token, tenantId),
      saveConfigValue(FIGMA_TOKEN_EXPIRES_AT_KEY, expiresAt, tenantId),
    ];

    // Only update refresh token if a new one was provided
    if (tokenResponse.refresh_token) {
      savePromises.push(
        saveConfigValue(FIGMA_REFRESH_TOKEN_KEY, tokenResponse.refresh_token, tenantId)
      );
    }

    await Promise.all(savePromises);

    logger.info('Refreshed Figma access token', { tenant_id: tenantId });
  }

  /**
   * Generate a secure random passcode for webhook signatures
   */
  private generateWebhookPasscode(): string {
    return crypto.randomBytes(32).toString('hex');
  }

  /**
   * Get or create webhook passcode for a tenant
   *
   * The passcode is stored in SSM as a signing secret and used for HMAC verification
   */
  public async getOrCreateWebhookPasscode(tenantId: string): Promise<string> {
    // Check if we already have a passcode
    const existing = await getConfigValue(FIGMA_WEBHOOK_PASSCODE_KEY, tenantId);
    if (existing && typeof existing === 'string') {
      return existing;
    }

    // Generate new passcode
    const passcode = this.generateWebhookPasscode();
    await saveConfigValue(FIGMA_WEBHOOK_PASSCODE_KEY, passcode, tenantId);

    // Also store as signing secret for gatekeeper webhook verification
    const ssmClient = new SSMClient();
    await ssmClient.storeSigningSecret(tenantId, 'figma', passcode);

    logger.info('Generated new Figma webhook passcode', { tenant_id: tenantId });
    return passcode;
  }

  /**
   * Get the webhook endpoint URL for a team
   *
   * Uses the gatekeeper URL with tenant-specific routing.
   */
  public getWebhookEndpoint(tenantId: string): string {
    const baseUrl = getGatekeeperUrl();
    return `${baseUrl}/${tenantId}/webhooks/figma`;
  }

  /**
   * Register webhooks for a team
   *
   * Creates webhooks for FILE_UPDATE, FILE_DELETE, and FILE_COMMENT events.
   * Checks existing webhooks first to avoid duplicates - only creates if no webhook
   * exists for the same team + event_type + endpoint combination.
   *
   * @param tenantId - Tenant ID for credential lookup
   * @param teamId - Figma team ID to register webhooks for
   * @returns Array of webhook IDs (both existing and newly created)
   */
  public async registerWebhooksForTeam(tenantId: string, teamId: string): Promise<string[]> {
    const accessToken = await getConfigValue(FIGMA_ACCESS_TOKEN_KEY, tenantId);
    if (!accessToken || typeof accessToken !== 'string') {
      throw new Error('No Figma access token found for tenant');
    }

    const passcode = await this.getOrCreateWebhookPasscode(tenantId);
    const endpoint = this.getWebhookEndpoint(tenantId);
    const webhookIds: string[] = [];

    // Get existing webhooks for this team to avoid duplicates
    let existingWebhooks: FigmaWebhook[] = [];
    try {
      existingWebhooks = await this.listWebhooks(tenantId, teamId);
      logger.info('Found existing Figma webhooks for team', {
        tenant_id: tenantId,
        team_id: teamId,
        count: existingWebhooks.length,
      });
    } catch (error) {
      logger.warn('Failed to list existing webhooks, will create new ones', {
        tenant_id: tenantId,
        team_id: teamId,
        error: error instanceof Error ? error.message : String(error),
      });
    }

    for (const eventType of FIGMA_WEBHOOK_EVENT_TYPES) {
      // Check if webhook already exists for this team + event_type + endpoint (v2 uses context/context_id)
      const existingWebhook = existingWebhooks.find(
        (w) =>
          w.context === 'team' &&
          w.context_id === teamId &&
          w.event_type === eventType &&
          w.endpoint === endpoint
      );

      if (existingWebhook) {
        logger.info('Webhook already exists for team/event/endpoint', {
          tenant_id: tenantId,
          team_id: teamId,
          event_type: eventType,
          webhook_id: existingWebhook.id,
          endpoint,
        });
        webhookIds.push(existingWebhook.id);
        continue;
      }

      try {
        const webhook = await this.createWebhook(accessToken, {
          event_type: eventType,
          context: 'team',
          context_id: teamId,
          endpoint,
          passcode,
          description: `Grapevine ${eventType} webhook`,
        });

        webhookIds.push(webhook.id);
        logger.info('Created Figma webhook', {
          tenant_id: tenantId,
          team_id: teamId,
          webhook_id: webhook.id,
          event_type: eventType,
          endpoint,
        });
      } catch (error) {
        // Log error but continue with other event types
        // Note: logger.error signature is (message, error?, context?)
        logger.error(
          'Failed to create Figma webhook',
          error instanceof Error ? error : new Error(String(error)),
          {
            tenant_id: tenantId,
            team_id: teamId,
            event_type: eventType,
          }
        );
      }
    }

    return webhookIds;
  }

  /**
   * Create a single webhook using v2 API
   * See: https://developers.figma.com/docs/rest-api/webhooks-endpoints/
   */
  private async createWebhook(
    accessToken: string,
    config: {
      event_type: string;
      context: 'team' | 'file' | 'project';
      context_id: string;
      endpoint: string;
      passcode: string;
      description?: string;
    }
  ): Promise<FigmaWebhook> {
    const response = await fetch(`${FIGMA_API_V2_URL}/webhooks`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(config),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to create webhook: ${response.status} - ${errorText}`);
    }

    return (await response.json()) as FigmaWebhook;
  }

  /**
   * Delete a webhook by ID using v2 API
   */
  public async deleteWebhook(tenantId: string, webhookId: string): Promise<void> {
    const accessToken = await getConfigValue(FIGMA_ACCESS_TOKEN_KEY, tenantId);
    if (!accessToken || typeof accessToken !== 'string') {
      throw new Error('No Figma access token found for tenant');
    }

    const response = await fetch(`${FIGMA_API_V2_URL}/webhooks/${webhookId}`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok && response.status !== 404) {
      const errorText = await response.text();
      throw new Error(`Failed to delete webhook: ${response.status} - ${errorText}`);
    }

    logger.info('Deleted Figma webhook', {
      tenant_id: tenantId,
      webhook_id: webhookId,
    });
  }

  /**
   * Delete all webhooks for a team
   *
   * @param tenantId - Tenant ID for credential lookup
   * @param webhookIds - Array of webhook IDs to delete
   */
  public async deleteWebhooks(tenantId: string, webhookIds: string[]): Promise<void> {
    for (const webhookId of webhookIds) {
      try {
        await this.deleteWebhook(tenantId, webhookId);
      } catch (error) {
        logger.error(
          'Failed to delete Figma webhook',
          error instanceof Error ? error : new Error(String(error)),
          {
            tenant_id: tenantId,
            webhook_id: webhookId,
          }
        );
      }
    }
  }

  /**
   * List webhooks for a team using v2 API
   * See: https://developers.figma.com/docs/rest-api/webhooks-endpoints/
   * Note: v2 API requires context parameter
   */
  public async listWebhooks(tenantId: string, teamId: string): Promise<FigmaWebhook[]> {
    const accessToken = await getConfigValue(FIGMA_ACCESS_TOKEN_KEY, tenantId);
    if (!accessToken || typeof accessToken !== 'string') {
      throw new Error('No Figma access token found for tenant');
    }

    // Build URL with team context (required for v2 API)
    const url = new URL(`${FIGMA_API_V2_URL}/webhooks`);
    url.searchParams.set('context', 'team');
    url.searchParams.set('context_id', teamId);

    const response = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to list webhooks: ${response.status} - ${errorText}`);
    }

    const data = (await response.json()) as { webhooks: FigmaWebhook[] };
    return data.webhooks || [];
  }
}
