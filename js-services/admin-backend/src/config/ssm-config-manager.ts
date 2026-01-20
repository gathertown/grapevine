/**
 * SSM Configuration Manager
 *
 * Stores sensitive configuration values in AWS Systems Manager Parameter Store with KMS encryption.
 * Use this for: API keys, tokens, secrets, passwords, webhook secrets.
 * Examples: OPENAI_API_KEY, GITHUB_TOKEN, SLACK_BOT_TOKEN
 *
 * Benefits: KMS encryption at rest, IAM access controls, audit logging, secure by default
 * All parameters stored as: /{tenant_id}/config/{key}
 * Implements the ConfigManager interface for consistency with database-based storage
 */

import { SSMClient } from '@corporate-context/backend-common';
import type { ConfigManager, ConfigKey, ConfigValue, TenantId } from './types.js';
import { SENSITIVE_KEYS, isSensitiveKey } from './configKeys.js';
import { logger, LogContext } from '../utils/logger.js';

type SSMClientType = InstanceType<typeof SSMClient>;

class SsmConfigManager implements ConfigManager {
  private ssmClient: SSMClientType;

  constructor() {
    this.ssmClient = new SSMClient();
  }

  /**
   * Maps configuration keys to their appropriate SSM parameter paths
   * Uses dedicated paths for API keys and signing secrets to match other services
   */
  private getParameterName(key: ConfigKey, tenantId: string): string {
    // Map signing secrets to dedicated paths
    const signingSecretMap: Record<string, string> = {
      GITHUB_WEBHOOK_SECRET: `/${tenantId}/signing-secret/github`,
      SLACK_SIGNING_SECRET: `/${tenantId}/signing-secret/slack`,
      NOTION_WEBHOOK_SECRET: `/${tenantId}/signing-secret/notion`,
      LINEAR_WEBHOOK_SECRET: `/${tenantId}/signing-secret/linear`,
      GATHER_WEBHOOK_SECRET: `/${tenantId}/signing-secret/gather`,
      TRELLO_WEBHOOK_SECRET: `/${tenantId}/signing-secret/trello`,
    };

    // Map API keys/tokens to dedicated paths
    const apiKeyMap: Record<string, string> = {
      GITHUB_TOKEN: `/${tenantId}/api-key/GITHUB_TOKEN`,
      SLACK_BOT_TOKEN: `/${tenantId}/api-key/SLACK_BOT_TOKEN`,
      NOTION_TOKEN: `/${tenantId}/api-key/NOTION_TOKEN`,
      LINEAR_API_KEY: `/${tenantId}/api-key/LINEAR_API_KEY`,
      GOOGLE_DRIVE_SERVICE_ACCOUNT: `/${tenantId}/api-key/GOOGLE_DRIVE_SERVICE_ACCOUNT`,
      GATHER_API_KEY: `/${tenantId}/api-key/GATHER_API_KEY`,
    };

    // Check if this key has a dedicated path
    if (signingSecretMap[key]) {
      return signingSecretMap[key];
    }
    if (apiKeyMap[key]) {
      return apiKeyMap[key];
    }

    if (isSensitiveKey(key)) {
      return `/${tenantId}/api-key/${key}`;
    } else {
      return `/${tenantId}/config/${key}`;
    }
  }

  /**
   * Get a sensitive configuration value from SSM Parameter Store
   * @param key - The configuration key to retrieve
   * @param tenantId - The tenant/organization ID for scoping
   * @returns The configuration value or null if not found
   */
  async getConfigValue(key: ConfigKey, tenantId: TenantId): Promise<ConfigValue> {
    return LogContext.run(
      { tenant_id: tenantId, configKey: key, operation: 'ssm-get-config' },
      async () => {
        if (!tenantId) {
          logger.error('No tenant ID available - cannot retrieve config from SSM');
          return null;
        }

        try {
          const parameterName = this.getParameterName(key, tenantId);
          const value = await this.ssmClient.getParameter(parameterName, true, true);

          if (value === null) {
            logger.debug(`Config parameter not found in SSM: ${parameterName}`, { parameterName });
            return null;
          }

          // Try to parse as JSON if it looks like JSON
          try {
            if (value.startsWith('{') || value.startsWith('[')) {
              return JSON.parse(value);
            }
          } catch {
            // Not JSON, return as string
          }

          return value;
        } catch (error) {
          logger.error(`Error getting config value from SSM: ${key}`, {
            error: (error as Error).message,
          });
          return null;
        }
      }
    );
  }

  /**
   * Save a sensitive configuration value to SSM Parameter Store
   * @param key - The configuration key
   * @param value - The configuration value
   * @param tenantId - The tenant/organization ID for scoping
   * @returns True if saved successfully, false otherwise
   */
  async saveConfigValue(key: ConfigKey, value: ConfigValue, tenantId: TenantId): Promise<boolean> {
    return LogContext.run(
      { tenant_id: tenantId, configKey: key, operation: 'ssm-save-config' },
      async () => {
        if (!tenantId) {
          logger.error('No tenant ID available - cannot save config to SSM');
          return false;
        }

        try {
          const parameterName = this.getParameterName(key, tenantId);

          // Convert value to string for SSM storage
          let stringValue: string;
          if (typeof value === 'string') {
            stringValue = value;
          } else {
            stringValue = JSON.stringify(value);
          }

          const description = `Sensitive configuration parameter ${key} for tenant ${tenantId}`;
          const success = await this.ssmClient.putParameter(
            parameterName,
            stringValue,
            description,
            true // overwrite existing
          );

          if (success) {
            logger.info(`Sensitive config value saved to SSM: ${parameterName}`, { parameterName });
          } else {
            logger.error(`Failed to save sensitive config value to SSM: ${parameterName}`, {
              parameterName,
            });
          }

          return success;
        } catch (error) {
          logger.error(`Error saving config value to SSM: ${key}`, {
            error: (error as Error).message,
          });
          return false;
        }
      }
    );
  }

  /**
   * Get all sensitive configuration values from SSM Parameter Store for a tenant
   * @param tenantId - The tenant/organization ID for scoping
   * @returns Object containing all sensitive key-value pairs
   *
   * TODO: For better performance with many parameters, consider:
   * 1. Using AWS SDK's getParametersByPath() to fetch all at once
   * 2. Implementing pagination for large parameter sets
   * 3. Adding caching layer for frequently accessed configs
   */
  async getAllConfigValues(tenantId: TenantId): Promise<Record<ConfigKey, ConfigValue>> {
    return LogContext.run({ tenant_id: tenantId, operation: 'ssm-get-all-configs' }, async () => {
      if (!tenantId) {
        logger.error('No tenant ID available - cannot retrieve all configs from SSM');
        return {};
      }

      const configData: Record<ConfigKey, ConfigValue> = {};

      // Fetch all known sensitive config keys in parallel
      const promises = SENSITIVE_KEYS.map(async (key) => {
        const value = await this.getConfigValue(key, tenantId);
        if (value !== null) {
          configData[key] = value;
        }
      });

      try {
        await Promise.all(promises);
      } catch (error) {
        logger.error('Error fetching all sensitive config values from SSM', {
          error: (error as Error).message,
        });
        // Return partial results on error
      }

      return configData;
    });
  }

  /**
   * Delete a sensitive configuration value from SSM Parameter Store
   * @param key - The configuration key to delete
   * @param tenantId - The tenant/organization ID for scoping
   * @returns True if deleted successfully, false otherwise
   */
  async deleteConfigValue(key: ConfigKey, tenantId: TenantId): Promise<boolean> {
    return LogContext.run(
      { tenant_id: tenantId, configKey: key, operation: 'ssm-delete-config' },
      async () => {
        if (!tenantId) {
          logger.error('No tenant ID available - cannot delete config from SSM');
          return false;
        }

        try {
          const parameterName = this.getParameterName(key, tenantId);
          const success = await this.ssmClient.deleteParameter(parameterName);

          if (success) {
            logger.info(`Sensitive config value deleted from SSM: ${parameterName}`, {
              parameterName,
            });
          } else {
            logger.warn(`Failed to delete sensitive config value from SSM: ${parameterName}`, {
              parameterName,
            });
          }

          return success;
        } catch (error) {
          logger.error(`Error deleting config value from SSM: ${key}`, {
            error: (error as Error).message,
          });
          return false;
        }
      }
    );
  }
}

// Export singleton instance
export const ssmConfigManager = new SsmConfigManager();
