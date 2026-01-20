/**
 * Tenant Configuration Manager
 *
 * Provides tenant-specific configuration retrieval from database
 * Shared across services (slack-bot, admin-backend, etc.)
 */

import { Pool } from 'pg';
import { createLogger } from '../logger';

const logger = createLogger('tenant-config');

export type ConfigKey = string;
export type ConfigValue = string | boolean | null;

export interface TenantConfigManagerDependencies {
  getDbPool: (tenantId: string) => Promise<Pool | null>;
}

export class TenantConfigManager {
  private getDbPool: (tenantId: string) => Promise<Pool | null>;

  constructor(deps: TenantConfigManagerDependencies) {
    this.getDbPool = deps.getDbPool;
  }

  /**
   * Get a configuration value from the tenant-specific database
   */
  async getConfigValue(key: ConfigKey, tenantId: string): Promise<ConfigValue> {
    const pool = await this.getDbPool(tenantId);
    if (!pool) {
      logger.error('No database connection available for tenant', { tenantId });
      return null;
    }

    try {
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Database query timeout')), 10000)
      );

      const queryPromise = pool.query('SELECT value FROM config WHERE key = $1', [key]);
      const result = await Promise.race([queryPromise, timeoutPromise]);

      if (result.rows.length > 0) {
        return result.rows[0].value as ConfigValue;
      }
      return null;
    } catch (error) {
      logger.error('Error getting config value', {
        error: error instanceof Error ? error : new Error(String(error)),
        key,
        tenantId,
      });
      return null;
    }
  }

  /**
   * Set a configuration value in the tenant-specific database
   */
  async setConfigValue(key: ConfigKey, value: ConfigValue, tenantId: string): Promise<boolean> {
    const pool = await this.getDbPool(tenantId);
    if (!pool) {
      logger.error('No database connection available for tenant', { tenantId });
      return false;
    }

    try {
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Database query timeout')), 10000)
      );

      const queryPromise = pool.query(
        'INSERT INTO config (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = CURRENT_TIMESTAMP',
        [key, value]
      );
      await Promise.race([queryPromise, timeoutPromise]);

      return true;
    } catch (error) {
      logger.error('Error setting config value', {
        error: error instanceof Error ? error : new Error(String(error)),
        key,
        tenantId,
      });
      return false;
    }
  }
}
