/**
 * Unified Configuration Manager
 *
 * Smart router that automatically directs config requests to the right storage backend.
 * Simply call getConfigValue() or saveConfigValue() - no need to know where data is stored!
 *
 * Routing Logic:
 * - Sensitive keys (API tokens, secrets) → SSM Parameter Store (encrypted)
 * - Non-sensitive keys (company info, metadata) → PostgreSQL (fast access)
 *
 * Benefits: Best of both worlds - security for secrets, performance for regular data
 * Single API regardless of backend - just import and use!
 */

import type { ConfigManager, ConfigKey, ConfigValue, TenantId } from './types.js';
import { isSensitiveKey } from './configKeys.js';
import { dbConfigManager } from './db-config-manager.js';
import { ssmConfigManager } from './ssm-config-manager.js';
import { logger } from '../utils/logger.js';
import { linearService } from '../services/linear-service.js';

class UnifiedConfigManager implements ConfigManager {
  /**
   * Get the appropriate config manager for a given key
   */
  private getManagerForKey(key: ConfigKey): ConfigManager {
    return isSensitiveKey(key) ? ssmConfigManager : dbConfigManager;
  }

  /**
   * Get a configuration value, automatically routing to appropriate backend
   * @param key - The configuration key to retrieve
   * @param tenantId - The tenant/organization ID for scoping
   * @returns The configuration value or null if not found
   */
  async getConfigValue(key: ConfigKey, tenantId: TenantId): Promise<ConfigValue> {
    const manager = this.getManagerForKey(key);
    return manager.getConfigValue(key, tenantId);
  }

  /**
   * Save a configuration value, automatically routing to appropriate backend
   * @param key - The configuration key
   * @param value - The configuration value
   * @param tenantId - The tenant/organization ID for scoping
   * @returns True if saved successfully, false otherwise
   */
  async saveConfigValue(key: ConfigKey, value: ConfigValue, tenantId: TenantId): Promise<boolean> {
    const manager = this.getManagerForKey(key);
    return manager.saveConfigValue(key, value, tenantId);
  }

  /**
   * Get all configuration values for a tenant from both backends
   * @param tenantId - The tenant/organization ID for scoping
   * @returns Object containing all key-value pairs from both SSM and database
   */
  async getAllConfigValues(tenantId: TenantId): Promise<Record<ConfigKey, ConfigValue>> {
    // Fetch from both backends in parallel
    const [ssmConfig, dbConfig] = await Promise.all([
      ssmConfigManager.getAllConfigValues(tenantId),
      dbConfigManager.getAllConfigValues(tenantId),
    ]);

    // Merge results (SSM takes precedence in case of conflicts, though there shouldn't be any)
    const mergedConfig = {
      ...dbConfig,
      ...ssmConfig,
    };

    // Check if LINEAR_ACCESS_TOKEN needs to be refreshed using the dedicated service
    // This handles checking expiry, refreshing if needed, and all error cases
    if (mergedConfig.LINEAR_ACCESS_TOKEN) {
      try {
        const validToken = await linearService.getValidAccessToken(tenantId);
        if (validToken) {
          mergedConfig.LINEAR_ACCESS_TOKEN = validToken;
        }
      } catch (error) {
        logger.error('Error checking/refreshing Linear access token', {
          error: (error as Error).message,
          tenant_id: tenantId,
        });
        // Continue with existing token - don't fail the entire config fetch
      }
    }

    return mergedConfig;
  }

  /**
   * Delete a configuration value, automatically routing to appropriate backend
   * @param key - The configuration key to delete
   * @param tenantId - The tenant/organization ID for scoping
   * @returns True if deleted successfully, false otherwise
   */
  async deleteConfigValue(key: ConfigKey, tenantId: TenantId): Promise<boolean> {
    const manager = this.getManagerForKey(key);
    return manager.deleteConfigValue(key, tenantId);
  }
}

// Export singleton instance
export const configManager = new UnifiedConfigManager();

// Export convenience functions with the same interface
export const getConfigValue = (key: ConfigKey, tenantId: TenantId) =>
  configManager.getConfigValue(key, tenantId);

export const saveConfigValue = (key: ConfigKey, value: ConfigValue, tenantId: TenantId) =>
  configManager.saveConfigValue(key, value, tenantId);

export const getAllConfigValues = (tenantId: TenantId) =>
  configManager.getAllConfigValues(tenantId);

export const deleteConfigValue = (key: ConfigKey, tenantId: TenantId) =>
  configManager.deleteConfigValue(key, tenantId);
