/**
 * Canva Configuration Keys
 *
 * OAuth tokens are stored in SSM Parameter Store.
 * Non-sensitive metadata is stored in the tenant config table.
 *
 * Canva OAuth:
 * - Uses PKCE flow for authorization
 * - Access tokens expire after ~4 hours (14400 seconds)
 * - Refresh tokens can only be used once (they rotate)
 */

import type { ConfigKey } from '../../config/types.js';

// SSM keys (sensitive)
export const CANVA_ACCESS_TOKEN_KEY: ConfigKey = 'CANVA_ACCESS_TOKEN';
export const CANVA_REFRESH_TOKEN_KEY: ConfigKey = 'CANVA_REFRESH_TOKEN';

// DB config keys (non-sensitive)
export const CANVA_USER_ID_KEY: ConfigKey = 'CANVA_USER_ID';
export const CANVA_USER_DISPLAY_NAME_KEY: ConfigKey = 'CANVA_USER_DISPLAY_NAME';
export const CANVA_TOKEN_EXPIRES_AT_KEY: ConfigKey = 'CANVA_TOKEN_EXPIRES_AT';

// Sync state keys
export const CANVA_FULL_BACKFILL_COMPLETE_KEY: ConfigKey = 'CANVA_FULL_BACKFILL_COMPLETE';
export const CANVA_DESIGNS_SYNCED_UNTIL_KEY: ConfigKey = 'CANVA_DESIGNS_SYNCED_UNTIL';

/**
 * Sensitive keys stored in AWS SSM Parameter Store
 */
export const CANVA_SENSITIVE_KEYS: ConfigKey[] = [CANVA_ACCESS_TOKEN_KEY, CANVA_REFRESH_TOKEN_KEY];

/**
 * Non-sensitive keys stored in PostgreSQL config table
 */
export const CANVA_NON_SENSITIVE_KEYS: ConfigKey[] = [
  CANVA_USER_ID_KEY,
  CANVA_USER_DISPLAY_NAME_KEY,
  CANVA_TOKEN_EXPIRES_AT_KEY,
  CANVA_FULL_BACKFILL_COMPLETE_KEY,
  CANVA_DESIGNS_SYNCED_UNTIL_KEY,
];

/**
 * All Canva config keys for cleanup on disconnect
 */
export const CANVA_CONFIG_KEYS: ConfigKey[] = [
  ...CANVA_SENSITIVE_KEYS,
  ...CANVA_NON_SENSITIVE_KEYS,
];

/**
 * Check if Canva is fully configured
 */
export const isCanvaComplete = (config: Record<ConfigKey, unknown>): boolean => {
  return !!config[CANVA_ACCESS_TOKEN_KEY];
};
