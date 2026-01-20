import type { SelectOption } from '@gathertown/gather-design-system';

// PostHog configuration keys
export const POSTHOG_API_KEY_CONFIG_KEY = 'POSTHOG_PERSONAL_API_KEY';
export const POSTHOG_HOST_CONFIG_KEY = 'POSTHOG_HOST';

// Default PostHog hosts
export const POSTHOG_HOSTS: SelectOption[] = [
  { value: 'https://us.posthog.com', label: 'US Cloud (us.posthog.com)' },
  { value: 'https://eu.posthog.com', label: 'EU Cloud (eu.posthog.com)' },
  { value: 'custom', label: 'Self-hosted (enter custom URL)' },
];

export const DEFAULT_POSTHOG_HOST = 'https://us.posthog.com';
