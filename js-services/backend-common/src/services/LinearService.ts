/**
 * Linear Token Management Service
 *
 * Handles Linear OAuth token refresh logic with dependency injection.
 * Can be used across services (admin-backend, slack-bot) by providing appropriate config managers.
 */

import { createLogger, LogContext } from '../logger';

const logger = createLogger('LinearService');

const LINEAR_TOKEN_URL = 'https://api.linear.app/oauth/token';
const LINEAR_TOKEN_REFRESH_BUFFER_HOURS = 1;
const LINEAR_HTTP_TIMEOUT_MS = 30000;

export type TenantId = string;
export type ConfigValue = unknown;

/**
 * Configuration manager interface for Linear service dependencies
 */
export interface ConfigManager {
  getConfigValue(key: string, tenantId: TenantId): Promise<ConfigValue>;
  saveConfigValue(key: string, value: ConfigValue, tenantId: TenantId): Promise<boolean>;
}

/**
 * Dependencies required by LinearService
 */
export interface LinearServiceDependencies {
  /** Config manager for sensitive values (LINEAR_ACCESS_TOKEN, LINEAR_REFRESH_TOKEN) */
  ssmConfigManager: ConfigManager;
  /** Config manager for non-sensitive values (LINEAR_TOKEN_EXPIRES_AT) */
  dbConfigManager: ConfigManager;
}

interface RefreshedTokenData {
  accessToken: string;
  refreshToken?: string;
  expiresAt: string;
}

export class LinearService {
  private ssmConfigManager: ConfigManager;
  private dbConfigManager: ConfigManager;

  constructor(dependencies: LinearServiceDependencies) {
    this.ssmConfigManager = dependencies.ssmConfigManager;
    this.dbConfigManager = dependencies.dbConfigManager;
  }

  /**
   * Get a valid Linear access token, refreshing if necessary.
   *
   * This is the recommended way to get a Linear access token - it ensures
   * the token is valid and not expired before returning it.
   *
   * @param tenantId - Tenant ID
   * @returns Valid access token or null if not configured
   */
  async getValidAccessToken(tenantId: TenantId): Promise<string | null> {
    return LogContext.run(
      { tenant_id: tenantId, operation: 'linear-get-valid-token' },
      async () => {
        try {
          // Fetch current token, refresh token, and expiry in parallel
          const [accessToken, refreshToken, expiresAt] = await Promise.all([
            this.ssmConfigManager.getConfigValue('LINEAR_ACCESS_TOKEN', tenantId),
            this.ssmConfigManager.getConfigValue('LINEAR_REFRESH_TOKEN', tenantId),
            this.dbConfigManager.getConfigValue('LINEAR_TOKEN_EXPIRES_AT', tenantId),
          ]);

          // No token configured
          if (!accessToken || typeof accessToken !== 'string') {
            return null;
          }

          // No refresh token - return current token (can't refresh)
          if (!refreshToken || typeof refreshToken !== 'string') {
            return accessToken;
          }

          // No expiry timestamp - refresh to update metadata
          if (!expiresAt || typeof expiresAt !== 'string') {
            logger.info('Found OAuth token without expiry, refreshing to update metadata', {
              tenant_id: tenantId,
            });
            const refreshedToken = await this.refreshToken(tenantId, refreshToken);
            return refreshedToken?.accessToken || accessToken;
          }

          // Check if token is expiring soon
          if (this.isTokenExpiringSoon(expiresAt)) {
            logger.info('Linear token expired or expiring soon; refreshing...', {
              tenant_id: tenantId,
              expires_at: expiresAt,
            });
            const refreshedToken = await this.refreshToken(tenantId, refreshToken);

            if (!refreshedToken) {
              // Re-read both token AND expiry to check if another process succeeded
              const [rereadToken, rereadExpiry] = await Promise.all([
                this.ssmConfigManager.getConfigValue('LINEAR_ACCESS_TOKEN', tenantId),
                this.dbConfigManager.getConfigValue('LINEAR_TOKEN_EXPIRES_AT', tenantId),
              ]);

              if (typeof rereadToken !== 'string') {
                return null;
              }

              // If token changed OR expiry is now valid, another process refreshed successfully
              if (
                rereadToken !== accessToken ||
                (typeof rereadExpiry === 'string' && !this.isTokenExpiringSoon(rereadExpiry))
              ) {
                logger.info('Another process refreshed the token successfully', {
                  tenant_id: tenantId,
                });
                return rereadToken;
              }

              // Token didn't change and still expired - refresh truly failed
              logger.error('Linear refresh permanently failed, returning null', {
                tenant_id: tenantId,
              });
              return null;
            }

            return refreshedToken.accessToken;
          }

          // Token is still valid
          return accessToken;
        } catch (error) {
          logger.error('Error getting valid Linear access token', {
            error: (error as Error).message,
            tenant_id: tenantId,
          });
          return null;
        }
      }
    );
  }

  /**
   * Check if a Linear token is expiring soon (within configured buffer time)
   */
  isTokenExpiringSoon(expiresAtValue: string): boolean {
    try {
      const expiresAt = new Date(expiresAtValue);

      if (isNaN(expiresAt.getTime())) {
        return false;
      }

      const bufferTime = new Date(Date.now() + LINEAR_TOKEN_REFRESH_BUFFER_HOURS * 60 * 60 * 1000);
      return expiresAt <= bufferTime;
    } catch {
      return false;
    }
  }

  /**
   * Refresh Linear OAuth token and persist to SSM + database
   *
   * @param tenantId - Tenant ID
   * @param refreshToken - Current refresh token
   * @returns New token data or null if refresh failed
   */
  async refreshToken(tenantId: TenantId, refreshToken: string): Promise<RefreshedTokenData | null> {
    return LogContext.run({ tenant_id: tenantId, operation: 'linear-refresh-token' }, async () => {
      try {
        const clientId = process.env.LINEAR_CLIENT_ID;
        const clientSecret = process.env.LINEAR_CLIENT_SECRET;

        if (!clientId || !clientSecret) {
          logger.error('LINEAR_CLIENT_ID or LINEAR_CLIENT_SECRET not configured', {
            tenant_id: tenantId,
          });
          return null;
        }

        // Call Linear token endpoint
        const params = new URLSearchParams({
          grant_type: 'refresh_token',
          refresh_token: refreshToken,
          client_id: clientId,
          client_secret: clientSecret,
        });

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), LINEAR_HTTP_TIMEOUT_MS);

        try {
          const response = await fetch(LINEAR_TOKEN_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: params.toString(),
            signal: controller.signal,
          });

          if (!response.ok) {
            const errorText = await response.text();

            logger.error(`Failed to refresh Linear token ${errorText}`, {
              status: response.status,
              error: errorText,
              tenant_id: tenantId,
            });
            return null;
          }

          const tokens = await response.json();

          if (!tokens.access_token || !tokens.expires_in) {
            logger.error('Invalid token response from Linear', { tenant_id: tenantId });
            return null;
          }

          const expiresAt = new Date(Date.now() + tokens.expires_in * 1000);
          const expiresAtISO8601 = expiresAt.toISOString();

          // Save to SSM and DB in parallel
          await Promise.all([
            this.ssmConfigManager.saveConfigValue(
              'LINEAR_ACCESS_TOKEN',
              tokens.access_token,
              tenantId
            ),
            tokens.refresh_token
              ? this.ssmConfigManager.saveConfigValue(
                  'LINEAR_REFRESH_TOKEN',
                  tokens.refresh_token,
                  tenantId
                )
              : Promise.resolve(true),
            this.dbConfigManager.saveConfigValue(
              'LINEAR_TOKEN_EXPIRES_AT',
              expiresAtISO8601,
              tenantId
            ),
          ]);

          logger.info('Successfully refreshed Linear token', {
            tenant_id: tenantId,
            expires_at: expiresAtISO8601,
          });

          return {
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            expiresAt: expiresAtISO8601,
          };
        } finally {
          clearTimeout(timeoutId);
        }
      } catch (error) {
        logger.error('Error refreshing Linear token', {
          error: (error as Error).message,
          tenant_id: tenantId,
        });
        return null;
      }
    });
  }
}
