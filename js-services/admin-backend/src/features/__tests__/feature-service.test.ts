import { FeatureKeys } from '../feature-definitions';
import { FeatureService } from '../feature-service';
import { InMemoryFeatureStore } from '../feature-store';

describe('Feature allowlist service', () => {
  const tenantId = 'tenant-123';
  const feature = FeatureKeys.CONNECTOR_TRELLO;
  const dummyFeature = FeatureKeys.DUMMY_FEATURE;

  it('returns true when feature is enabled by environment default', async () => {
    process.env.GRAPEVINE_ENVIRONMENT = 'local';

    const service = new FeatureService(new InMemoryFeatureStore());
    const features = await service.getAllFeaturesForTenant(tenantId);

    expect(features[dummyFeature]).toBe(true);
  });

  it('returns false when feature is not enabled by env and tenant is not allowlisted', async () => {
    process.env.GRAPEVINE_ENVIRONMENT = 'production';

    const service = new FeatureService(new InMemoryFeatureStore());
    const features = await service.getAllFeaturesForTenant(tenantId);

    expect(features[dummyFeature]).toBe(false);
  });

  it('returns true when tenant is allowlisted even if environment denies it', async () => {
    process.env.GRAPEVINE_ENVIRONMENT = 'production';

    const store = new InMemoryFeatureStore();
    const service = new FeatureService(store);
    await store.enableFeatureForTenant(tenantId, dummyFeature);

    const features = await service.getAllFeaturesForTenant(tenantId);
    expect(features[dummyFeature]).toBe(true);
  });

  it('returns handles multiple features', async () => {
    process.env.GRAPEVINE_ENVIRONMENT = 'production';

    const store = new InMemoryFeatureStore();
    const service = new FeatureService(store);
    await store.enableFeatureForTenant(tenantId, feature);
    await store.enableFeatureForTenant(tenantId, dummyFeature);

    const features = await service.getAllFeaturesForTenant(tenantId);

    expect(features[feature]).toEqual(true);
    expect(features[dummyFeature]).toEqual(true); // true in spite of env
  });

  it('returns env features for unknown tenant', async () => {
    process.env.GRAPEVINE_ENVIRONMENT = 'production';

    const service = new FeatureService(new InMemoryFeatureStore());
    const features = await service.getAllFeaturesForTenant('unknown-tenant');

    expect(features[feature]).toEqual(false);
    expect(features[dummyFeature]).toEqual(false);
  });
});
