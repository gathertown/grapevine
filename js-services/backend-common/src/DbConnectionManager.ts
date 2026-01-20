/**
 * Database Connection Manager for Multi-Tenant Architecture
 * Manages per-tenant database connection pools
 */

import { Pool } from 'pg';
import { SSMClient } from './aws/SSMClient';
import { logger, LogContext } from './logger';

interface PoolStats {
  tenantId: string;
  totalCount: number;
  idleCount: number;
  waitingCount: number;
}

interface TenantDatabaseCredentials {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
}

export class DbConnectionManager {
  private pools: Map<string, Pool>;
  private ssmClient: SSMClient;

  constructor() {
    // Map to store connection pools per tenant
    // Key: tenantId, Value: Pool instance
    this.pools = new Map();

    // SSM client for retrieving tenant-specific credentials
    this.ssmClient = new SSMClient();
  }

  /**
   * Get database connection pool for a specific tenant
   * @param tenantId The internal tenant ID (t_*)
   */
  async get(tenantId: string): Promise<Pool | null> {
    return LogContext.run({ tenant_id: tenantId, operation: 'get-db-pool' }, async () => {
      if (!tenantId) {
        logger.warn('DbConnectionManager: No tenantId provided');
        return null;
      }

      // Check if we already have a pool for this tenant
      if (this.pools.has(tenantId)) {
        const existing = this.pools.get(tenantId);
        if (!existing) {
          return null;
        }
        return existing;
      }

      // Create a new pool for this tenant
      const pool = await this.createPoolForTenant(tenantId);

      if (pool) {
        this.pools.set(tenantId, pool);
        logger.info(`Created database pool for tenant: ${tenantId}`);
      }

      return pool;
    });
  }

  /**
   * Get tenant-specific database credentials from SSM
   * Following the same pattern as Python's tenant_db.py:
   * - Database name, user, password from SSM
   * - Host from PG_TENANT_DATABASE_HOST env var
   * - Port from PG_TENANT_DATABASE_PORT env var (default 5432)
   * - SSL mode from PG_TENANT_DATABASE_SSLMODE env var (default 'require')
   */
  private async getTenantDatabaseCredentials(
    tenantId: string
  ): Promise<TenantDatabaseCredentials | null> {
    return LogContext.run({ tenant_id: tenantId, operation: 'get-db-credentials' }, async () => {
      try {
        // Get host from environment variable (shared across all tenants)
        const host = process.env.PG_TENANT_DATABASE_HOST;
        if (!host) {
          logger.info(`PG_TENANT_DATABASE_HOST env var not set, tenant-specific DB not available`);
          return null;
        }

        // Get port from env var with default (matching Python's tenant_db.py)
        const port = parseInt(process.env.PG_TENANT_DATABASE_PORT || '5432', 10);

        // Fetch tenant-specific credentials from SSM in parallel
        const [dbName, dbUser, dbPass] = await Promise.all([
          this.ssmClient.getParameter(`/${tenantId}/credentials/postgresql/db_name`, true, true),
          this.ssmClient.getParameter(`/${tenantId}/credentials/postgresql/db_rw_user`, true, true),
          this.ssmClient.getParameter(`/${tenantId}/credentials/postgresql/db_rw_pass`, true, true),
        ]);

        // If we don't have all required credentials, return null
        if (!dbName || !dbUser || !dbPass) {
          logger.info(
            `Missing SSM credentials for tenant ${tenantId}: db_name=${!!dbName}, db_rw_user=${!!dbUser}, db_rw_pass=${!!dbPass}`
          );
          return null;
        }

        return {
          host,
          port,
          database: dbName,
          username: dbUser,
          password: dbPass,
        };
      } catch (error) {
        // SSM parameters might not exist yet if tenant is not fully provisioned
        logger.info(`Tenant database credentials not found in SSM for ${tenantId}`, {
          error: String(error),
        });
        return null;
      }
    });
  }

  /**
   * Create a new database connection pool for a tenant
   * Retrieves tenant-specific database credentials from SSM
   */
  private async createPoolForTenant(tenantId: string): Promise<Pool | null> {
    return LogContext.run({ tenant_id: tenantId, operation: 'create-db-pool' }, async () => {
      try {
        // Get tenant-specific database credentials from SSM
        const dbCredentials = await this.getTenantDatabaseCredentials(tenantId);

        if (!dbCredentials) {
          logger.error(`No database credentials available for tenant: ${tenantId}`);
          return null;
        }

        // Build database URL from SSM credentials
        const { host, port, database, username, password } = dbCredentials;
        const sslmode = process.env.PG_TENANT_DATABASE_SSLMODE || 'require';

        // Build connection string without sslmode (we'll handle SSL in the Pool config)
        const databaseUrl = `postgresql://${username}:${password}@${host}:${port}/${database}`;
        logger.info(
          `Using tenant-specific database for ${tenantId} at ${host}:${port}/${database}`
        );

        // Determine SSL configuration based on sslmode
        const sslConfig =
          sslmode === 'require' || sslmode === 'prefer'
            ? { rejectUnauthorized: false } // For cloud databases, encrypt but don't verify certificate
            : false; // No SSL for 'disable' or any other value

        // Create pool for this tenant
        const pool = new Pool({
          connectionString: databaseUrl,
          ssl: sslConfig,
          max: 3, // Maximum number of connections in the pool
          min: 0, // Minimum number of connections in the pool
          connectionTimeoutMillis: 30000, // Return error after 30s if connection cannot be established
          idleTimeoutMillis: 30000, // Close idle connections after 30s
          maxUses: 7500, // Close connection after 7500 uses (optional, helps prevent stale connections)
        });

        // Handle pool errors
        pool.on('error', (err: Error) => {
          logger.error(`Database pool error for tenant ${tenantId}`, err, {
            tenant_id: tenantId,
            operation: 'db-pool-error',
          });
        });

        // Handle pool connect events
        pool.on('connect', () => {
          logger.info(`Database connected for tenant: ${tenantId}`, {
            tenant_id: tenantId,
            operation: 'db-pool-connect',
          });
        });

        return pool;
      } catch (error) {
        logger.error(`Error creating pool for tenant ${tenantId}`, error);
        return null;
      }
    });
  }

  /**
   * Get the number of active tenant pools
   */
  getActivePoolCount(): number {
    return this.pools.size;
  }

  /**
   * Get all tenant IDs that have active pools
   */
  getActiveTenants(): string[] {
    return Array.from(this.pools.keys());
  }

  /**
   * Close a specific tenant's database pool
   */
  async closePool(tenantId: string): Promise<void> {
    return LogContext.run({ tenant_id: tenantId, operation: 'close-db-pool' }, async () => {
      if (this.pools.has(tenantId)) {
        const pool = this.pools.get(tenantId);
        if (!pool) {
          return;
        }
        await pool.end();
        this.pools.delete(tenantId);
        logger.info(`Closed database pool for tenant: ${tenantId}`);
      }
    });
  }

  /**
   * Close all database connection pools
   * Should be called during application shutdown
   */
  async closeAll(): Promise<void> {
    return LogContext.run({ operation: 'close-all-db-pools' }, async () => {
      const closePromises = [];

      for (const [tenantId, pool] of this.pools) {
        closePromises.push(
          LogContext.run({ tenant_id: tenantId, operation: 'close-db-pool' }, async () => {
            return pool
              .end()
              .then(() => {
                logger.info(`Closed database pool for tenant: ${tenantId}`);
              })
              .catch((err) => {
                logger.error(`Error closing pool for tenant ${tenantId}`, { error: err.message });
              });
          })
        );
      }

      await Promise.all(closePromises);
      this.pools.clear();
      logger.info('All database connection pools closed');
    });
  }

  /**
   * Get pool statistics for monitoring
   */
  async getPoolStats(tenantId: string): Promise<PoolStats | null> {
    const pool = this.pools.get(tenantId);
    if (!pool) {
      return null;
    }

    return {
      tenantId,
      totalCount: pool.totalCount,
      idleCount: pool.idleCount,
      waitingCount: pool.waitingCount,
    };
  }

  /**
   * Get all pool statistics for monitoring
   */
  getAllPoolStats(): PoolStats[] {
    return Array.from(this.pools.entries()).map(([tenantId, pool]) => ({
      tenantId,
      totalCount: pool.totalCount,
      idleCount: pool.idleCount,
      waitingCount: pool.waitingCount,
    }));
  }
}
