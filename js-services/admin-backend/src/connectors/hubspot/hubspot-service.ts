import crypto from 'crypto';
import { Client } from '@hubspot/api-client';
import { saveConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { TokenResponseIF } from '@hubspot/api-client/lib/codegen/oauth/index.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';

type HubSpotConfig = {
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  scopes: string;
};

export class HubSpotService {
  private readonly client: Client;
  private readonly config: HubSpotConfig;

  constructor() {
    this.client = new Client();
    this.config = this.loadConfig();
  }

  public buildOAuthUrl(tenantId: string): string {
    const state = `${crypto.randomUUID()}_${tenantId}`;

    const authUrl = this.client.oauth.getAuthorizationUrl(
      this.config.clientId,
      this.config.redirectUri,
      this.config.scopes,
      undefined,
      state
    );

    logger.info('Generated HubSpot OAuth URL', {
      tenant_id: tenantId,
      redirect_uri: this.config.redirectUri,
    });

    return authUrl;
  }

  public async exchangeCodeForTokens(code: string, tenantId: string): Promise<void> {
    logger.info('Exchanging HubSpot authorization code', {
      tenant_id: tenantId,
    });

    const tokenResponse = await this.client.oauth.tokensApi.create(
      'authorization_code',
      code,
      this.config.redirectUri,
      this.config.clientId,
      this.config.clientSecret
    );

    const accessTokenMeta = await this.client.oauth.accessTokensApi.get(tokenResponse.accessToken);
    const portalId = accessTokenMeta.hubId;

    await this.storeTokensAndMetadata(tenantId, { ...tokenResponse, portalId });

    logger.info('HubSpot tokens and metadata saved successfully', {
      tenant_id: tenantId,
      portal_id: portalId,
    });

    // Update Notion CRM - HubSpot integration connected
    await updateIntegrationStatus(tenantId, 'hubspot', true);
  }

  private async storeTokensAndMetadata(
    tenantId: string,
    authData: TokenResponseIF & { portalId: number }
  ): Promise<void> {
    const expiresAt = new Date(Date.now() + authData.expiresIn * 1000).toISOString();

    await Promise.all([
      saveConfigValue('HUBSPOT_ACCESS_TOKEN', authData.accessToken, tenantId),
      saveConfigValue('HUBSPOT_REFRESH_TOKEN', authData.refreshToken, tenantId),
      saveConfigValue('HUBSPOT_TOKEN_EXPIRES_AT', expiresAt, tenantId),
      saveConfigValue('HUBSPOT_COMPLETE', 'true', tenantId),
      installConnector({
        tenantId,
        type: ConnectorType.HubSpot,
        externalId: authData.portalId.toString(),
      }),
    ]);
  }

  private loadConfig(): HubSpotConfig {
    const clientId = process.env.HUBSPOT_CLIENT_ID;
    const clientSecret = process.env.HUBSPOT_CLIENT_SECRET;
    const redirectUri = process.env.HUBSPOT_REDIRECT_URI;
    // TODO: The scopes here must match the scopes in the app-hsmeta.json file
    // Issues: This is hidden implementation, making it difficult for developer
    // to find and modify. We should expose a config option. And we should have
    // a single source of truth for scopes (not spread out between here and the
    // app-hsmeta.json file)
    const scopes =
      'oauth crm.objects.companies.read crm.objects.deals.read sales-email-read crm.objects.contacts.read tickets';
    if (!clientId) throw new Error('HUBSPOT_CLIENT_ID not configured');
    if (!clientSecret) throw new Error('HUBSPOT_CLIENT_SECRET not configured');
    if (!redirectUri) throw new Error('HUBSPOT_REDIRECT_URI not configured');
    return { clientId, clientSecret, redirectUri, scopes };
  }
}
