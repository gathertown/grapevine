import { Pool } from 'pg';
import { FeatureKey } from './feature-definitions.js';

type TenantId = string;

interface FeatureStore {
  getTenantFeatures(tenantId: TenantId): Promise<Set<FeatureKey>>;
  enableFeatureForTenant(tenantId: TenantId, feature: FeatureKey): Promise<void>;
  disableFeatureForTenant(tenantId: TenantId, feature: FeatureKey): Promise<void>;
}

class InMemoryFeatureStore implements FeatureStore {
  #featureAllowlist: Map<TenantId, Set<FeatureKey>> = new Map();

  getTenantFeatures(tenantId: TenantId): Promise<Set<FeatureKey>> {
    return Promise.resolve(this.#featureAllowlist.get(tenantId) ?? new Set());
  }
  enableFeatureForTenant(tenantId: TenantId, feature: FeatureKey): Promise<void> {
    const tenantAllowlist = this.#featureAllowlist.get(tenantId) || new Set();
    tenantAllowlist.add(feature);
    this.#featureAllowlist.set(tenantId, tenantAllowlist);
    return Promise.resolve();
  }
  disableFeatureForTenant(tenantId: TenantId, feature: FeatureKey): Promise<void> {
    this.#featureAllowlist.get(tenantId)?.delete(feature);
    return Promise.resolve();
  }
}

class PsqlFeatureStore implements FeatureStore {
  constructor(private pool: Pool) {}

  async getTenantFeatures(tenantId: TenantId): Promise<Set<FeatureKey>> {
    const result = await this.pool.query(
      'SELECT feature_key FROM public.feature_allowlist WHERE tenant_id = $1',
      [tenantId]
    );

    const features = result.rows.map((row) => row.feature_key as FeatureKey);
    return new Set(features);
  }

  async disableFeatureForTenant(tenantId: TenantId, feature: FeatureKey): Promise<void> {
    await this.pool.query(
      'DELETE FROM public.feature_allowlist WHERE tenant_id = $1 AND feature_key = $2',
      [tenantId, feature]
    );
  }

  async enableFeatureForTenant(tenantId: TenantId, feature: FeatureKey): Promise<void> {
    await this.pool.query(
      `INSERT INTO public.feature_allowlist (tenant_id, feature_key, created_at, updated_at)
             VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
             ON CONFLICT (tenant_id, feature_key) DO NOTHING`,
      [tenantId, feature]
    );
  }
}

export { type FeatureStore, InMemoryFeatureStore, PsqlFeatureStore };
