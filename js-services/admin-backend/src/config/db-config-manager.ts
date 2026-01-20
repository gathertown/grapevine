/**
 * Database Configuration Manager
 *
 * Stores non-sensitive configuration values in PostgreSQL for fast access.
 * Use this for: company info, display preferences, job IDs, metadata.
 * Examples: COMPANY_NAME, SLACK_EXPORT_INFO
 *
 * Benefits: Fast queries, supports complex data types, easier debugging
 * Implements the ConfigManager interface for consistency with SSM-based storage
 */

import { Pool } from 'pg';
import type { ConfigManager, ConfigKey, ConfigValue, TenantId } from './types.js';
import { getDbManager } from '../middleware/db-middleware.js';
import { logger, LogContext } from '../utils/logger.js';

class DbConfigManager implements ConfigManager {
  /**
   * Get tenant-specific database connection
   */
  private async getTenantDb(tenantId: TenantId): Promise<Pool | null> {
    const dbManager = getDbManager();
    const pool = await dbManager.get(tenantId);
    if (!pool) {
      logger.error(`Failed to get database pool for tenant: ${tenantId}`);
      return null;
    }
    return pool;
  }

  /**
   * Get a configuration value from the database
   * @param key - The configuration key to retrieve
   * @param tenantId - The tenant/organization ID for scoping
   * @returns The configuration value or null if not found
   */
  async getConfigValue(key: ConfigKey, tenantId: TenantId): Promise<ConfigValue> {
    return LogContext.run(
      { tenant_id: tenantId, configKey: key, operation: 'db-get-config' },
      async () => {
        const dbConnection = await this.getTenantDb(tenantId);
        if (!dbConnection) {
          logger.error(
            `No database connection available for tenant ${tenantId} - skipping config get`
          );
          return null;
        }

        try {
          // Add timeout protection
          const timeoutPromise = new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('Database query timeout')), 10000)
          );

          const queryPromise = dbConnection.query('SELECT value FROM config WHERE key = $1', [key]);

          const result = await Promise.race([queryPromise, timeoutPromise]);

          if (result.rows.length > 0) {
            return result.rows[0].value;
          }
          return null;
        } catch (error) {
          logger.error('Error getting config value', { error: (error as Error).message });
          // If it's a connection error, log pool stats if available
          const errorMessage = (error as Error).message;
          if (errorMessage.includes('max clients') || errorMessage.includes('connection')) {
            logger.error('Pool stats', {
              total: (dbConnection as unknown as { totalCount: number }).totalCount,
              idle: (dbConnection as unknown as { idleCount: number }).idleCount,
              waiting: (dbConnection as unknown as { waitingCount: number }).waitingCount,
            });
          }
          return null;
        }
      }
    );
  }

  /**
   * Save a configuration value to the database
   * @param key - The configuration key
   * @param value - The configuration value
   * @param tenantId - The tenant/organization ID for scoping
   * @returns True if saved successfully, false otherwise
   */
  async saveConfigValue(key: ConfigKey, value: ConfigValue, tenantId: TenantId): Promise<boolean> {
    return LogContext.run(
      { tenant_id: tenantId, configKey: key, operation: 'db-save-config' },
      async () => {
        const dbConnection = await this.getTenantDb(tenantId);
        if (!dbConnection) {
          logger.error(
            `No database connection available for tenant ${tenantId} - skipping config save`
          );
          return false;
        }

        try {
          // Add timeout protection
          const timeoutPromise = new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('Database query timeout')), 10000)
          );

          // Atomic upsert using ON CONFLICT
          const upsertPromise = dbConnection.query(
            `INSERT INTO config (key, value, created_at, updated_at)
           VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
           ON CONFLICT (key)
           DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP`,
            [key, value]
          );
          await Promise.race([upsertPromise, timeoutPromise]);

          logger.info(`Config value saved to database: ${key} for tenant ${tenantId}`);
          return true;
        } catch (error) {
          logger.error('Error saving config value', { error: (error as Error).message });
          // If it's a connection error, log pool stats if available
          const errorMessage = (error as Error).message;
          if (errorMessage.includes('max clients') || errorMessage.includes('connection')) {
            logger.error('Pool stats', {
              total: (dbConnection as unknown as { totalCount: number }).totalCount,
              idle: (dbConnection as unknown as { idleCount: number }).idleCount,
              waiting: (dbConnection as unknown as { waitingCount: number }).waitingCount,
            });
          }
          return false;
        }
      }
    );
  }

  /**
   * Get all non-sensitive configuration values from the database for a tenant
   * @param tenantId - The tenant/organization ID for scoping
   * @returns Object containing all non-sensitive key-value pairs
   */
  async getAllConfigValues(tenantId: TenantId): Promise<Record<ConfigKey, ConfigValue>> {
    return LogContext.run({ tenant_id: tenantId, operation: 'db-get-all-configs' }, async () => {
      const dbConnection = await this.getTenantDb(tenantId);
      if (!dbConnection) {
        logger.error(
          `No database connection available for tenant ${tenantId} - skipping config get all`
        );
        return {};
      }

      try {
        const result = await dbConnection.query('SELECT key, value FROM config');

        const configData: Record<ConfigKey, ConfigValue> = {};
        for (const row of result.rows) {
          configData[row.key] = row.value;
        }

        return configData;
      } catch (error) {
        logger.error('Error fetching all config values from database', {
          error: (error as Error).message,
        });
        return {};
      }
    });
  }

  /**
   * Delete a configuration value from the database
   * @param key - The configuration key to delete
   * @param tenantId - The tenant/organization ID for scoping
   * @returns True if deleted successfully, false otherwise
   */
  async deleteConfigValue(key: ConfigKey, tenantId: TenantId): Promise<boolean> {
    return LogContext.run(
      { tenant_id: tenantId, configKey: key, operation: 'db-delete-config' },
      async () => {
        const dbConnection = await this.getTenantDb(tenantId);
        if (!dbConnection) {
          logger.error(
            `No database connection available for tenant ${tenantId} - skipping config delete`
          );
          return false;
        }

        try {
          // Add timeout protection
          const timeoutPromise = new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('Database query timeout')), 10000)
          );

          const deletePromise = dbConnection.query('DELETE FROM config WHERE key = $1', [key]);

          await Promise.race([deletePromise, timeoutPromise]);
          logger.info(`Config value deleted from database: ${key} for tenant ${tenantId}`);
          return true;
        } catch (error) {
          logger.error('Error deleting config value', { error: (error as Error).message });
          return false;
        }
      }
    );
  }
}

// Export singleton instance
export const dbConfigManager = new DbConfigManager();

// Export individual functions for backward compatibility
export const getConfigValue = (key: ConfigKey, tenantId: TenantId) =>
  dbConfigManager.getConfigValue(key, tenantId);
export const saveConfigValue = (key: ConfigKey, value: ConfigValue, tenantId: TenantId) =>
  dbConfigManager.saveConfigValue(key, value, tenantId);
export const getAllConfigValues = (tenantId: TenantId) =>
  dbConfigManager.getAllConfigValues(tenantId);
export const deleteConfigValue = (key: ConfigKey, tenantId: TenantId) =>
  dbConfigManager.deleteConfigValue(key, tenantId);
