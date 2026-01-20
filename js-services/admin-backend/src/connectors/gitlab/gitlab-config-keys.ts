import { ConfigKey } from '../../config/types';

// Sensitive keys (stored in SSM Parameter Store with encryption)
export const GITLAB_SENSITIVE_KEYS = [
  'GITLAB_ACCESS_TOKEN',
  'GITLAB_REFRESH_TOKEN',
  'GITLAB_CLIENT_ID',
  'GITLAB_CLIENT_SECRET',
] as const satisfies readonly ConfigKey[];

// Non-sensitive keys (stored in regular database)
export const GITLAB_NON_SENSITIVE_KEYS = [
  'GITLAB_TOKEN_TYPE',
  'GITLAB_INSTANCE_URL', // Base URL for self-hosted GitLab instances (e.g., https://gitlab.example.com)
] as const satisfies readonly ConfigKey[];
