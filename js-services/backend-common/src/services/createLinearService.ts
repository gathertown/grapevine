/**
 * Factory for creating a configured LinearService instance
 *
 * Provides Linear token management with automatic refresh.
 * Uses SSMClient and TenantConfigManager as config managers.
 */

import { LinearService, type ConfigManager as LinearConfigManager } from './LinearService';
import { SSMClient } from '../aws/SSMClient';
import { TenantConfigManager } from './TenantConfigManager';

/**
 * SSM Config Manager adapter for LinearService
 * Wraps SSMClient to implement the LinearConfigManager interface
 */
class SSMConfigManagerAdapter implements LinearConfigManager {
  private ssmClient: SSMClient;

  constructor() {
    this.ssmClient = new SSMClient();
  }

  async getConfigValue(key: string, tenantId: string): Promise<unknown> {
    return this.ssmClient.getApiKey(tenantId, key);
  }

  async saveConfigValue(key: string, value: string, tenantId: string): Promise<boolean> {
    return this.ssmClient.storeApiKey(tenantId, key, value);
  }
}

/**
 * DB Config Manager adapter for LinearService
 * Wraps TenantConfigManager to implement the LinearConfigManager interface
 */
class DBConfigManagerAdapter implements LinearConfigManager {
  private tenantConfigManager: TenantConfigManager;

  constructor(tenantConfigManager: TenantConfigManager) {
    this.tenantConfigManager = tenantConfigManager;
  }

  async getConfigValue(key: string, tenantId: string): Promise<unknown> {
    return this.tenantConfigManager.getConfigValue(key, tenantId);
  }

  async saveConfigValue(key: string, value: string, tenantId: string): Promise<boolean> {
    return this.tenantConfigManager.setConfigValue(key, value, tenantId);
  }
}

/**
 * Create a configured LinearService instance
 *
 * @param tenantConfigManager - TenantConfigManager instance for DB config storage
 * @returns Configured LinearService instance
 */
export function createLinearService(tenantConfigManager: TenantConfigManager): LinearService {
  const ssmConfigManager = new SSMConfigManagerAdapter();
  const dbConfigManager = new DBConfigManagerAdapter(tenantConfigManager);

  return new LinearService({
    ssmConfigManager,
    dbConfigManager,
  });
}
