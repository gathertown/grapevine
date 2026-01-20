/**
 * Database Middleware for Multi-Tenant Architecture
 * Injects tenant-specific database connection pools into request context
 */

import type { Request, Response, NextFunction } from 'express';

import { DbConnectionManager } from '@corporate-context/backend-common';

import { logger, LogContext } from '../utils/logger.js';

type DbConnectionManagerType = InstanceType<typeof DbConnectionManager>;

// Create a global instance of the connection manager
const dbManager = new DbConnectionManager();

/**
 * Database middleware that injects tenant-specific database pool
 * into the request context as req.db
 *
 * This middleware should be used after authentication middleware
 * so that req.user.tenantId is available
 */
export async function dbMiddleware(req: Request, res: Response, next: NextFunction): Promise<void> {
  return LogContext.run({ operation: 'db-middleware' }, async () => {
    try {
      // Check if we have user context from authentication with tenant ID
      if (req.user && req.user.tenantId) {
        // Get the database pool for this tenant
        const pool = await dbManager.get(req.user.tenantId);

        if (!pool) {
          logger.error(`Failed to get database pool for tenant: ${req.user.tenantId}`);
          res.status(500).json({
            error: 'Database connection unavailable',
            details: 'Could not establish database connection for your organization',
          });
          return;
        }

        // Inject the pool into the request context
        req.db = pool;

        // Add a query wrapper that logs the organization context
        const originalQuery = pool.query.bind(pool);
        (
          req.db as unknown as {
            query: (text: string, params?: unknown[]) => unknown;
          }
        ).query = function (text: string, params?: unknown[]) {
          logger.debug(`[DB Query] ${text.substring(0, 100)}${text.length > 100 ? '...' : ''}`, {
            query_preview: text.substring(0, 100),
          });
          return originalQuery(text, params);
        };

        logger.info(`Database pool injected for tenant: ${req.user.tenantId}`);
      } else if (req.user && !req.user.tenantId) {
        // User is authenticated but organization is not provisioned yet
        logger.info(`No tenant found for organization: ${req.user.organizationId}`);
        // Don't inject database pool, but continue - some endpoints may not need it
      } else {
        // No user context - this could be a public endpoint or authentication failed
        // We don't inject a database pool in this case
        logger.debug('No user context available - skipping database pool injection');
      }

      next();
    } catch (error) {
      logger.error('Database middleware error', { error: String(error) });
      res.status(500).json({
        error: 'Database middleware error',
        details: (error as Error).message,
      });
    }
  });
}

/**
 * Get the database connection manager instance
 * Useful for administrative operations or shutdown procedures
 */
export function getDbManager(): DbConnectionManagerType {
  return dbManager;
}

/**
 * Close all database connections
 * Should be called during application shutdown
 */
export async function closeAllConnections(): Promise<void> {
  return LogContext.run({ operation: 'close-all-db-connections' }, async () => {
    try {
      await dbManager.closeAll();
      logger.info('All database connections closed successfully');
    } catch (error) {
      logger.error('Error closing database connections', { error: String(error) });
      throw error;
    }
  });
}

/**
 * Get statistics for all active database pools
 * Useful for monitoring and debugging
 */
export function getAllPoolStats(): unknown {
  return dbManager.getAllPoolStats();
}
