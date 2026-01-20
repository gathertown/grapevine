/**
 * Attio Configuration Keys
 *
 * Defines sensitive and non-sensitive configuration keys for Attio OAuth.
 *
 * Token characteristics (from Attio docs):
 * - API Keys: Tokens do not expire (https://attio.com/help/apps/other-apps/generating-an-api-key)
 * - OAuth: Token response only includes `access_token` and `token_type` - no `refresh_token`
 *   or `expires_in` documented (https://docs.attio.com/docs/oauth/token)
 */

import type { ConfigKey } from '../../config/types.js';

// Config key constants
export const ATTIO_ACCESS_TOKEN_KEY: ConfigKey = 'ATTIO_ACCESS_TOKEN';
export const ATTIO_WORKSPACE_ID_KEY: ConfigKey = 'ATTIO_WORKSPACE_ID';
export const ATTIO_WORKSPACE_SLUG_KEY: ConfigKey = 'ATTIO_WORKSPACE_SLUG';
export const ATTIO_WEBHOOK_ID_KEY: ConfigKey = 'ATTIO_WEBHOOK_ID';

/**
 * Sensitive keys stored in AWS SSM Parameter Store
 */
export const ATTIO_SENSITIVE_KEYS: ConfigKey[] = [
  ATTIO_ACCESS_TOKEN_KEY,
  // Note: Attio OAuth does not return refresh tokens per documentation
] as const;

/**
 * Non-sensitive keys stored in PostgreSQL
 */
export const ATTIO_NON_SENSITIVE_KEYS: ConfigKey[] = [
  ATTIO_WORKSPACE_ID_KEY,
  ATTIO_WORKSPACE_SLUG_KEY,
  ATTIO_WEBHOOK_ID_KEY,
] as const;

/**
 * All Attio configuration keys
 * Used for operations like disconnect that need to clean up all config
 */
export const ATTIO_CONFIG_KEYS = [...ATTIO_SENSITIVE_KEYS, ...ATTIO_NON_SENSITIVE_KEYS] as const;

/**
 * Check if Attio connector is complete/configured
 * Similar to other connectors, we check for the actual access token
 */
export const isAttioComplete = (config: Record<ConfigKey, unknown>): boolean => {
  return !!config[ATTIO_ACCESS_TOKEN_KEY];
};
