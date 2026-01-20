/**
 * Tenant Mode Enum
 * Defines valid mode values for tracking tenant type/origin
 */

export enum TenantMode {
  DevPlatform = 'dev_platform',
  QA = 'qa',
}

/**
 * Type guard to check if a value is a valid TenantMode
 */
export function isValidTenantMode(value: unknown): value is TenantMode {
  return typeof value === 'string' && Object.values(TenantMode).includes(value as TenantMode);
}
