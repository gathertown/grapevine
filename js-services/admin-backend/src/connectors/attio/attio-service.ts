import crypto from 'crypto';
import { SSMClient } from '@corporate-context/backend-common';
import { getConfigValue, saveConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { getBaseDomain, getFrontendUrl } from '../../utils/config.js';
import {
  ATTIO_ACCESS_TOKEN_KEY,
  ATTIO_WEBHOOK_ID_KEY,
  ATTIO_WORKSPACE_ID_KEY,
  ATTIO_WORKSPACE_SLUG_KEY,
} from './attio-config.js';

/**
 * Attio OAuth Configuration
 *
 * OAuth endpoints from Attio docs:
 * - Authorization: https://app.attio.com/authorize
 * - Token Exchange: https://app.attio.com/oauth/token
 *
 * Sources:
 * - OAuth Tutorial: https://docs.attio.com/rest-api/tutorials/connect-an-app-through-oauth
 * - Token Endpoint: https://docs.attio.com/docs/oauth/token
 */

/**
 * Token response from Attio OAuth
 * Note: Attio does NOT return refresh_token or expires_in
 * Source: https://docs.attio.com/docs/oauth/token
 */
type AttioTokenResponse = {
  access_token: string;
  token_type: 'Bearer';
};

/**
 * Webhook response from Attio API
 * Source: https://docs.attio.com/rest-api/endpoint-reference/webhooks
 *
 * Note: The 'secret' field is only returned when creating a webhook.
 * It is used for HMAC-SHA256 signature verification of incoming webhooks.
 */
type AttioWebhookResponse = {
  data: {
    id: {
      workspace_id: string;
      webhook_id: string;
    };
    target_url: string;
    status: 'active' | 'degraded' | 'inactive';
    subscriptions: Array<{
      event_type: string;
      filter: unknown;
    }>;
    created_at: string;
    secret: string; // Only returned on webhook creation
  };
};

// Attio OAuth endpoints
const AUTH_URL = 'https://app.attio.com/authorize';
const TOKEN_URL = 'https://app.attio.com/oauth/token';
const API_BASE_URL = 'https://api.attio.com/v2';

/**
 * Get Attio client ID from environment
 * Throws if not configured - this is called lazily when OAuth is actually initiated
 */
function getAttioClientId(): string {
  const value = process.env.ATTIO_CLIENT_ID;
  if (!value) {
    throw new Error('ATTIO_CLIENT_ID environment variable is required for Attio OAuth');
  }
  return value;
}

/**
 * Get Attio client secret from environment
 * Throws if not configured - this is called lazily when OAuth is actually initiated
 */
function getAttioClientSecret(): string {
  const value = process.env.ATTIO_CLIENT_SECRET;
  if (!value) {
    throw new Error('ATTIO_CLIENT_SECRET environment variable is required for Attio OAuth');
  }
  return value;
}

/**
 * Build Attio redirect URI from FRONTEND_URL
 * Follows the same pattern as Gong, Asana, Zendesk, etc.
 */
function buildAttioRedirectUri(): string {
  const frontendUrl = getFrontendUrl();
  return `${frontendUrl}/api/attio/oauth/callback`;
}

export class AttioService {
  /**
   * Build the OAuth authorization URL for Attio
   *
   * Authorization URL parameters (from docs):
   * - response_type: Must be "code"
   * - client_id: Your app's OAuth client ID
   * - redirect_uri: Must match configured redirect URI
   * - state: Recommended for CSRF protection
   *
   * Source: https://docs.attio.com/rest-api/tutorials/connect-an-app-through-oauth
   */
  public buildOAuthUrl(tenantId: string): string {
    const state = `${crypto.randomUUID()}_${tenantId}`;
    const clientId = getAttioClientId();
    const redirectUri = buildAttioRedirectUri();

    const params = new URLSearchParams({
      response_type: 'code',
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
   * Source: https://docs.attio.com/docs/oauth/token
   */
  public async exchangeCodeForTokens(code: string, tenantId: string): Promise<void> {
    const clientId = getAttioClientId();
    const clientSecret = getAttioClientSecret();
    const redirectUri = buildAttioRedirectUri();

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
      logger.error('Attio token exchange failed', {
        status: response.status,
        error: errorText,
        redirect_uri: redirectUri,
        tenant_id: tenantId,
      });
      throw new Error(`Attio token exchange failed: ${response.status} - ${errorText}`);
    }

    const tokenResponse = (await response.json()) as AttioTokenResponse;
    const workspaceInfo = await this.getWorkspaceInfo(tokenResponse.access_token);

    await this.storeTokensAndMetadata(tenantId, {
      accessToken: tokenResponse.access_token,
      workspaceId: workspaceInfo.workspaceId,
      workspaceName: workspaceInfo.workspaceName,
      workspaceSlug: workspaceInfo.workspaceSlug,
    });

    // Ensure webhook exists for real-time updates (cleans up any existing webhook first)
    await this.ensureWebhook(tokenResponse.access_token, tenantId);

    await updateIntegrationStatus(tenantId, 'attio', true);
  }

  /**
   * Ensure a webhook is configured, creating a new one and then cleaning up any existing.
   *
   * This prevents duplicate webhooks when re-authenticating. We create the new webhook
   * first and then delete the old one to ensure we don't lose real-time updates if
   * creation fails.
   */
  private async ensureWebhook(accessToken: string, tenantId: string): Promise<void> {
    // Get existing webhook ID before creating new one
    const existingWebhookId = await getConfigValue(ATTIO_WEBHOOK_ID_KEY, tenantId);

    // Create the new webhook first (fail-safe: we keep real-time updates if creation fails)
    const created = await this.createWebhook(accessToken, tenantId);

    // Only delete the old webhook if we successfully created a new one
    if (created && existingWebhookId && typeof existingWebhookId === 'string') {
      logger.info('Deleting old Attio webhook after successful new webhook creation', {
        tenant_id: tenantId,
        old_webhook_id: existingWebhookId,
      });
      await this.deleteWebhook(accessToken, existingWebhookId);
    }
  }

  /**
   * Get workspace info from Attio API
   * Uses /v2/self endpoint to get current workspace details
   */
  private async getWorkspaceInfo(
    accessToken: string
  ): Promise<{ workspaceId: string; workspaceName: string; workspaceSlug: string }> {
    const response = await fetch(`${API_BASE_URL}/self`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to get Attio workspace info', {
        status: response.status,
        error: errorText,
      });
      throw new Error(`Failed to get Attio workspace info: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    const workspaceId = data?.workspace_id;
    const workspaceName = data?.workspace_name || 'Unknown Workspace';
    const workspaceSlug = data?.workspace_slug;

    if (!workspaceId) {
      throw new Error('Attio /self response missing workspace_id');
    }

    if (!workspaceSlug) {
      throw new Error('Attio /self response missing workspace_slug');
    }

    return { workspaceId, workspaceName, workspaceSlug };
  }

  /**
   * Store tokens and metadata
   *
   * Note: Attio tokens do not expire per documentation, so we don't store expiry.
   * Source: https://attio.com/help/apps/other-apps/generating-an-api-key
   */
  private async storeTokensAndMetadata(
    tenantId: string,
    authData: {
      accessToken: string;
      workspaceId: string;
      workspaceName: string;
      workspaceSlug: string;
    }
  ): Promise<void> {
    await Promise.all([
      saveConfigValue(ATTIO_ACCESS_TOKEN_KEY, authData.accessToken, tenantId),
      saveConfigValue(ATTIO_WORKSPACE_ID_KEY, authData.workspaceId, tenantId),
      saveConfigValue(ATTIO_WORKSPACE_SLUG_KEY, authData.workspaceSlug, tenantId),
    ]);

    await installConnector({
      tenantId,
      type: ConnectorType.Attio,
      externalId: authData.workspaceId,
    });
  }

  /**
   * Create webhook for real-time Attio updates
   *
   * Subscribes to record, note, and task events for incremental sync.
   * Uses tenant-specific webhook URL pattern: https://{tenant_id}.ingest.{baseDomain}/webhooks/attio
   *
   * Source: https://docs.attio.com/rest-api/endpoint-reference/webhooks
   *
   * @returns true if webhook was created successfully, false otherwise
   */
  private async createWebhook(accessToken: string, tenantId: string): Promise<boolean> {
    const baseDomain = getBaseDomain();
    const webhookUrl = `https://${tenantId}.ingest.${baseDomain}/webhooks/attio`;

    // Subscribe to record, note, and task events
    const subscriptions = [
      { event_type: 'record.created', filter: null },
      { event_type: 'record.updated', filter: null },
      { event_type: 'record.deleted', filter: null },
      { event_type: 'note.created', filter: null },
      { event_type: 'note.updated', filter: null },
      { event_type: 'note.deleted', filter: null },
      { event_type: 'task.created', filter: null },
      { event_type: 'task.updated', filter: null },
      { event_type: 'task.deleted', filter: null },
    ];

    const response = await fetch(`${API_BASE_URL}/webhooks`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        data: {
          target_url: webhookUrl,
          subscriptions,
        },
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to create Attio webhook', {
        status: response.status,
        error: errorText,
        tenant_id: tenantId,
        webhook_url: webhookUrl,
      });
      // Don't throw - webhook creation failure shouldn't block OAuth completion
      // The periodic full sync will still work
      return false;
    }

    const webhookResponse = (await response.json()) as AttioWebhookResponse;
    const webhookId = webhookResponse.data.id.webhook_id;
    const webhookSecret = webhookResponse.data.secret;

    // Store webhook ID for later cleanup on disconnect
    await saveConfigValue(ATTIO_WEBHOOK_ID_KEY, webhookId, tenantId);

    // Store webhook secret for signature verification
    // The secret is only returned when creating the webhook, so we must capture it now
    if (webhookSecret) {
      const ssmClient = new SSMClient();
      const secretStored = await ssmClient.storeSigningSecret(tenantId, 'attio', webhookSecret);
      if (!secretStored) {
        logger.error('Failed to store Attio webhook signing secret', {
          tenant_id: tenantId,
          webhook_id: webhookId,
        });
        // Don't throw - webhook will work but signature verification will fail
        // Admin can re-authenticate to fix this
      }
    } else {
      logger.warn('Attio webhook response missing secret', {
        tenant_id: tenantId,
        webhook_id: webhookId,
      });
    }

    logger.info('Created Attio webhook', {
      tenant_id: tenantId,
      webhook_id: webhookId,
      webhook_url: webhookUrl,
      subscriptions: subscriptions.map((s) => s.event_type),
    });

    return true;
  }

  /**
   * Delete webhook when disconnecting Attio
   *
   * Called during connector disconnect to clean up webhook subscription.
   */
  public async deleteWebhook(accessToken: string, webhookId: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/webhooks/${webhookId}`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok && response.status !== 404) {
      const errorText = await response.text();
      logger.error('Failed to delete Attio webhook', {
        status: response.status,
        error: errorText,
        webhook_id: webhookId,
      });
      // Don't throw - best effort cleanup
      return;
    }

    logger.info('Deleted Attio webhook', { webhook_id: webhookId });
  }
}
