/**
 * Configuration Manager Types
 * Defines the contract that all configuration managers must implement
 */

export type ConfigKey = string;
export type TenantId = string;
export type ConfigValue = unknown;

/**
 * Common interface for all configuration managers
 * Ensures consistent API across database and SSM implementations
 */
export interface ConfigManager {
  /**
   * Get a configuration value for a specific tenant
   * @param key - The configuration key to retrieve
   * @param tenantId - The tenant/organization ID for scoping
   * @returns The configuration value or null if not found
   */
  getConfigValue(key: ConfigKey, tenantId: TenantId): Promise<ConfigValue>;

  /**
   * Save a configuration value for a specific tenant
   * @param key - The configuration key
   * @param value - The configuration value
   * @param tenantId - The tenant/organization ID for scoping
   * @returns True if saved successfully, false otherwise
   */
  saveConfigValue(key: ConfigKey, value: ConfigValue, tenantId: TenantId): Promise<boolean>;

  /**
   * Get all configuration values for a specific tenant
   * @param tenantId - The tenant/organization ID for scoping
   * @returns Object containing all key-value pairs for the tenant
   */
  getAllConfigValues(tenantId: TenantId): Promise<Record<ConfigKey, ConfigValue>>;

  /**
   * Delete a configuration value for a specific tenant (optional)
   * @param key - The configuration key to delete
   * @param tenantId - The tenant/organization ID for scoping
   * @returns True if deleted successfully, false otherwise
   */
  deleteConfigValue(key: ConfigKey, tenantId: TenantId): Promise<boolean>;
}

/**
 * Configuration storage backend types
 */
type ConfigBackend = 'database' | 'ssm';

/**
 * Configuration route mapping
 */
export interface ConfigRoute {
  key: ConfigKey;
  backend: ConfigBackend;
  sensitive: boolean;
}
