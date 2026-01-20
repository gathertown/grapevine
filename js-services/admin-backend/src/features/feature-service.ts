import { ALL_FEATURE_KEYS, FeatureKey, isFeatureAllowedInEnv } from './feature-definitions';
import { FeatureStore } from './feature-store';

type TenantId = string;

class FeatureService {
  constructor(private featureStore: FeatureStore) {}

  async getAllFeaturesForTenant(tenantId: TenantId): Promise<Record<FeatureKey, boolean>> {
    const tenantFeatures = await this.featureStore.getTenantFeatures(tenantId);

    const featureEntries = ALL_FEATURE_KEYS.map(
      (feature) => [feature, isFeatureAllowedInEnv(feature) || tenantFeatures.has(feature)] as const
    );

    return Object.fromEntries(featureEntries) as Record<FeatureKey, boolean>;
  }
}

export { FeatureService };
