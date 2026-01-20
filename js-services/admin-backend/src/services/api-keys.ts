/**
 * API Keys Service
 *
 * Manages API key generation and storage for REST API authentication
 */

import { randomBytes } from 'crypto';
import { DbConnectionManager, SSMClient } from '@corporate-context/backend-common';
import { logger, LogContext } from '../utils/logger.js';

const dbManager = new DbConnectionManager();
const ssmClient = new SSMClient();

export interface APIKeyInfo {
  id: string;
  name: string;
  prefix: string;
  createdAt: string;
  lastUsedAt: string | null;
  createdBy: string | null;
}

/**
 * Generate a random API key with format: gv_{tenant_id}_{random_chars}
 */
function generateApiKey(tenantId: string): string {
  // Generate 16 random bytes and convert to hex (32 chars, only 0-9 and a-f)
  const randomString = randomBytes(16).toString('hex');

  return `gv_${tenantId}_${randomString}`;
}

/**
 * Extract the stored prefix (what we store in the database)
 * Format: gv_{tenant_id}_{key_id} where key_id is first 8 chars of random
 */
function extractStoredPrefix(apiKey: string): string {
  // Format: gv_{tenant_id}_{random_32_chars}
  // Store: gv_{full_tenant_id}_{first_8_of_random}
  const parts = apiKey.split('_');
  if (parts.length >= 3 && parts[1] && parts[2]) {
    const tenantId = parts[1]; // Full tenant ID, not truncated
    const keyId = parts[2].substring(0, 8);
    return `gv_${tenantId}_${keyId}`;
  }
  throw new Error('Invalid API key format');
}

/**
 * Extract the SSM key ID from API key or stored prefix (first 8 chars of random portion)
 */
function extractKeyId(apiKey: string): string {
  // Format: gv_{tenant_id}_{random_32_chars}
  // Extract first 8 chars of random portion for SSM lookup
  const parts = apiKey.split('_');
  if (parts.length >= 3 && parts[2]) {
    return parts[2].substring(0, 8);
  }
  throw new Error('Invalid API key format');
}

/**
 * Create a new API key for a tenant
 */
export async function createApiKey(
  tenantId: string,
  name: string,
  createdBy?: string
): Promise<{ apiKey: string; keyInfo: APIKeyInfo }> {
  return LogContext.run(
    {
      operation: 'create-api-key',
      tenantId,
      name,
    },
    async () => {
      const pool = await dbManager.get(tenantId);
      if (!pool) {
        throw new Error('Database connection unavailable');
      }

      // Generate API key with tenant_id embedded
      const apiKey = generateApiKey(tenantId);
      const storedPrefix = extractStoredPrefix(apiKey);
      const ssmKeyId = extractKeyId(apiKey);

      logger.debug('Generated API key components', {
        tenantId,
        storedPrefix,
        ssmKeyId,
        storedPrefixLength: storedPrefix.length,
      });

      try {
        // Insert metadata into database first to get the ID
        logger.debug('Inserting API key metadata into database', {
          tenantId,
          name,
          storedPrefix,
        });
        const result = await pool.query(
          `INSERT INTO api_keys (name, prefix, created_by)
           VALUES ($1, $2, $3)
           RETURNING id, name, prefix, created_at, last_used_at, created_by`,
          [name, storedPrefix, createdBy || null]
        );

        const row = result.rows[0];
        const dbId = row.id;

        // Store the actual key in SSM using the database ID
        logger.debug('Storing API key in SSM', { tenantId, dbId });
        const stored = await ssmClient.storeApiKey(tenantId, `gv_api_${dbId}`, apiKey);
        if (!stored) {
          // Rollback: delete from database if SSM storage fails
          await pool.query(`DELETE FROM api_keys WHERE id = $1`, [dbId]);
          throw new Error('Failed to store API key in SSM');
        }
        logger.debug('API key stored in SSM successfully', { tenantId, dbId });

        logger.info('API key created successfully', {
          tenantId,
          databaseId: dbId,
          name,
        });

        return {
          apiKey, // Return the full key only once
          keyInfo: {
            id: row.id,
            name: row.name,
            prefix: row.prefix,
            createdAt: row.created_at.toISOString(),
            lastUsedAt: row.last_used_at ? row.last_used_at.toISOString() : null,
            createdBy: row.created_by,
          },
        };
      } catch (error) {
        logger.error('Failed to create API key', {
          error: error instanceof Error ? error.message : JSON.stringify(error),
          errorStack: error instanceof Error ? error.stack : undefined,
          tenantId,
          name,
          storedPrefix,
          ssmKeyId,
        });
        throw error instanceof Error ? error : new Error('Failed to create API key');
      }
    }
  );
}

/**
 * List all API keys for a tenant
 */
export async function listApiKeys(tenantId: string): Promise<APIKeyInfo[]> {
  return LogContext.run(
    {
      operation: 'list-api-keys',
      tenantId,
    },
    async () => {
      const pool = await dbManager.get(tenantId);
      if (!pool) {
        throw new Error('Database connection unavailable');
      }

      try {
        const result = await pool.query(
          `SELECT id, name, prefix, created_at, last_used_at, created_by
           FROM api_keys
           ORDER BY created_at DESC`
        );

        return result.rows.map((row) => ({
          id: row.id,
          name: row.name,
          prefix: row.prefix,
          createdAt: row.created_at.toISOString(),
          lastUsedAt: row.last_used_at ? row.last_used_at.toISOString() : null,
          createdBy: row.created_by,
        }));
      } catch (error) {
        logger.error('Failed to list API keys', {
          error: error instanceof Error ? error.message : 'Unknown error',
          tenantId,
        });
        throw new Error('Failed to list API keys');
      }
    }
  );
}

/**
 * Delete an API key
 */
export async function deleteApiKey(tenantId: string, keyId: string): Promise<boolean> {
  return LogContext.run(
    {
      operation: 'delete-api-key',
      tenantId,
      keyId,
    },
    async () => {
      const pool = await dbManager.get(tenantId);
      if (!pool) {
        throw new Error('Database connection unavailable');
      }

      try {
        // Delete from database
        const result = await pool.query(`DELETE FROM api_keys WHERE id = $1`, [keyId]);

        const deleted = result.rowCount !== null && result.rowCount > 0;

        if (deleted) {
          await ssmClient.deleteParameter(`/${tenantId}/api-key/gv_api_${keyId}`);

          logger.info('API key deleted successfully', {
            tenantId,
            keyId,
          });
        } else {
          logger.warn('API key not found for deletion', {
            tenantId,
            keyId,
          });
        }

        return deleted;
      } catch (error) {
        logger.error('Failed to delete API key', {
          error: error instanceof Error ? error.message : 'Unknown error',
          tenantId,
          keyId,
        });
        throw new Error('Failed to delete API key');
      }
    }
  );
}
