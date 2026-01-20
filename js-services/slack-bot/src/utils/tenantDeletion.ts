/**
 * Tenant deletion utility functions
 * Provides utilities to check if a tenant has been marked as deleted
 */

import { Pool } from 'pg';
import { logger } from './logger';
import { getOrCompute } from '@corporate-context/backend-common';

let controlDbPool: Pool | null = null;

// Redis cache TTL for deleted_at checks (10 minutes)
const DELETED_AT_CACHE_TTL_SECONDS = 600;

/**
 * Get or create the control database connection pool
 */
function getControlDbPool(): Pool | null {
  if (controlDbPool) {
    return controlDbPool;
  }

  const databaseUrl = process.env.CONTROL_DATABASE_URL;
  if (!databaseUrl) {
    logger.error(
      'Control database URL not configured. Set CONTROL_DATABASE_URL environment variable.'
    );
    return null;
  }

  const isLocalDb = databaseUrl.includes('localhost') || databaseUrl.includes('127.0.0.1');
  controlDbPool = new Pool({
    connectionString: databaseUrl,
    ssl: isLocalDb ? false : { rejectUnauthorized: false },
    max: 5,
    min: 1,
    connectionTimeoutMillis: 30000,
    idleTimeoutMillis: 30000,
    maxUses: 7500,
  });

  return controlDbPool;
}

/**
 * Check if a tenant is deleted
 * Uses Redis caching with 10-minute TTL to reduce database connection pool pressure.
 * Falls back to database if Redis is unavailable.
 *
 * @param tenantId - The tenant ID to check
 * @returns Promise<boolean> - True if tenant is deleted (deleted_at is not null), false otherwise
 */
export async function isTenantDeleted(tenantId: string): Promise<boolean> {
  const cacheKey = `tenant:deleted:${tenantId}`;

  const fetchFromDb = async (): Promise<boolean> => {
    const pool = getControlDbPool();
    if (!pool) {
      logger.error('Control database not available for tenant deletion check');
      return false;
    }

    try {
      const result = await pool.query('SELECT deleted_at FROM tenants WHERE id = $1', [tenantId]);

      if (result.rows.length === 0) {
        logger.warn(`Tenant ${tenantId} not found in control database`);
        return false;
      }

      const deletedAt = result.rows[0].deleted_at;
      const isDeleted = deletedAt !== null;

      if (isDeleted) {
        logger.warn(`Tenant ${tenantId} is marked as deleted (deleted at ${deletedAt})`);
      }

      return isDeleted;
    } catch (error) {
      logger.error(`Error checking tenant deletion status for ${tenantId}`, { error });
      return false;
    }
  };

  // Use cache helper to get or compute the value
  return await getOrCompute(
    cacheKey,
    fetchFromDb,
    (val) => (val ? '1' : '0'),
    (s) => s === '1',
    DELETED_AT_CACHE_TTL_SECONDS
  );
}

/**
 * Close the control database connection pool
 */
export async function closeControlDbPool(): Promise<void> {
  if (controlDbPool) {
    await controlDbPool.end();
    controlDbPool = null;
  }
}
