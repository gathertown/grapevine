import { TenantMode } from '@corporate-context/shared-common';
import { useAllConfig } from '../api/config';

/**
 * Custom hook that determines if the tenant came from the dev platform flow.
 * Used for showing different onboarding UI flows, NOT for feature gating.
 *
 * For feature gating, use the feature flags system from api/features.ts
 *
 * @returns boolean - true if the tenant's mode is 'dev_platform', false otherwise
 *
 * @example
 * ```tsx
 * const isDevMode = useDevMode();
 *
 * if (isDevMode) {
 *   return <DevPlatformOnboarding />;
 * }
 * ```
 */
export const useDevMode = (): boolean => {
  const { data: configData } = useAllConfig();
  return configData?.TENANT_MODE === TenantMode.DevPlatform;
};
