/**
 * Pipedrive Configuration Keys
 *
 * OAuth tokens are stored in SSM Parameter Store.
 * Non-sensitive metadata is stored in the tenant config table.
 *
 * Pipedrive OAuth:
 * - Access tokens expire (typically 1 hour)
 * - Refresh tokens expire after 60 days of non-use
 * - api_domain is company-specific (e.g., https://company.pipedrive.com)
 */

import type { ConfigKey } from '../../config/types.js';

// SSM keys (sensitive)
export const PIPEDRIVE_ACCESS_TOKEN_KEY: ConfigKey = 'PIPEDRIVE_ACCESS_TOKEN';
export const PIPEDRIVE_REFRESH_TOKEN_KEY: ConfigKey = 'PIPEDRIVE_REFRESH_TOKEN';

// DB config keys (non-sensitive)
export const PIPEDRIVE_API_DOMAIN_KEY: ConfigKey = 'PIPEDRIVE_API_DOMAIN';
export const PIPEDRIVE_COMPANY_ID_KEY: ConfigKey = 'PIPEDRIVE_COMPANY_ID';
export const PIPEDRIVE_COMPANY_NAME_KEY: ConfigKey = 'PIPEDRIVE_COMPANY_NAME';
export const PIPEDRIVE_TOKEN_EXPIRES_AT_KEY: ConfigKey = 'PIPEDRIVE_TOKEN_EXPIRES_AT';

// Sync state keys
export const PIPEDRIVE_DEALS_SYNCED_UNTIL_KEY: ConfigKey = 'PIPEDRIVE_DEALS_SYNCED_UNTIL';
export const PIPEDRIVE_PERSONS_SYNCED_UNTIL_KEY: ConfigKey = 'PIPEDRIVE_PERSONS_SYNCED_UNTIL';
export const PIPEDRIVE_ORGS_SYNCED_UNTIL_KEY: ConfigKey = 'PIPEDRIVE_ORGS_SYNCED_UNTIL';
export const PIPEDRIVE_PRODUCTS_SYNCED_UNTIL_KEY: ConfigKey = 'PIPEDRIVE_PRODUCTS_SYNCED_UNTIL';
export const PIPEDRIVE_FULL_BACKFILL_COMPLETE_KEY: ConfigKey = 'PIPEDRIVE_FULL_BACKFILL_COMPLETE';

// Pagination cursor keys
export const PIPEDRIVE_DEALS_CURSOR_KEY: ConfigKey = 'PIPEDRIVE_DEALS_CURSOR';
export const PIPEDRIVE_PERSONS_CURSOR_KEY: ConfigKey = 'PIPEDRIVE_PERSONS_CURSOR';
export const PIPEDRIVE_ORGS_CURSOR_KEY: ConfigKey = 'PIPEDRIVE_ORGS_CURSOR';
export const PIPEDRIVE_PRODUCTS_CURSOR_KEY: ConfigKey = 'PIPEDRIVE_PRODUCTS_CURSOR';

/**
 * Sensitive keys stored in AWS SSM Parameter Store
 */
export const PIPEDRIVE_SENSITIVE_KEYS: ConfigKey[] = [
  PIPEDRIVE_ACCESS_TOKEN_KEY,
  PIPEDRIVE_REFRESH_TOKEN_KEY,
];

/**
 * Non-sensitive keys stored in PostgreSQL config table
 */
export const PIPEDRIVE_NON_SENSITIVE_KEYS: ConfigKey[] = [
  PIPEDRIVE_API_DOMAIN_KEY,
  PIPEDRIVE_COMPANY_ID_KEY,
  PIPEDRIVE_COMPANY_NAME_KEY,
  PIPEDRIVE_TOKEN_EXPIRES_AT_KEY,
  PIPEDRIVE_DEALS_SYNCED_UNTIL_KEY,
  PIPEDRIVE_PERSONS_SYNCED_UNTIL_KEY,
  PIPEDRIVE_ORGS_SYNCED_UNTIL_KEY,
  PIPEDRIVE_PRODUCTS_SYNCED_UNTIL_KEY,
  PIPEDRIVE_FULL_BACKFILL_COMPLETE_KEY,
  PIPEDRIVE_DEALS_CURSOR_KEY,
  PIPEDRIVE_PERSONS_CURSOR_KEY,
  PIPEDRIVE_ORGS_CURSOR_KEY,
  PIPEDRIVE_PRODUCTS_CURSOR_KEY,
];

/**
 * All Pipedrive config keys for cleanup on disconnect
 */
export const PIPEDRIVE_CONFIG_KEYS: ConfigKey[] = [
  ...PIPEDRIVE_SENSITIVE_KEYS,
  ...PIPEDRIVE_NON_SENSITIVE_KEYS,
];

/**
 * Check if Pipedrive is fully configured
 */
export const isPipedriveComplete = (config: Record<ConfigKey, unknown>): boolean => {
  return !!config[PIPEDRIVE_ACCESS_TOKEN_KEY];
};
