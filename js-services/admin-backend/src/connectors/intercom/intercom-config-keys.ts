import { ConfigKey } from '../../config/types';

// Sensitive keys (stored in SSM Parameter Store with encryption)
export const INTERCOM_SENSITIVE_KEYS = [
  'INTERCOM_ACCESS_TOKEN',
] as const satisfies readonly ConfigKey[];

// Non-sensitive keys (stored in regular database)
export const INTERCOM_NON_SENSITIVE_KEYS = [
  'INTERCOM_TOKEN_TYPE',
] as const satisfies readonly ConfigKey[];
