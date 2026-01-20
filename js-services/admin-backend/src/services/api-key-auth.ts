/**
 * API Key Authentication Service
 *
 * Handles API key verification for external REST API access
 */

import { timingSafeEqual } from 'crypto';
import { DbConnectionManager, SSMClient } from '@corporate-context/backend-common';
import { logger, LogContext } from '../utils/logger.js';

const dbManager = new DbConnectionManager();
const ssmClient = new SSMClient();

/**
 * Extract tenant ID from API key
 * Format: gv_{tenant_id}_{random_32_chars}
 */
function extractTenantId(apiKey: string): string | null {
  const parts = apiKey.split('_');
  if (parts.length >= 3 && parts[0] === 'gv' && parts[1]) {
    return parts[1];
  }
  return null;
}

/**
 * Extract the stored prefix (what we store in the database)
 * Format: gv_{tenant_id}_{key_id} where key_id is first 8 chars of random
 */
function extractStoredPrefix(apiKey: string): string | null {
  const parts = apiKey.split('_');
  if (parts.length >= 3 && parts[1] && parts[2]) {
    const tenantId = parts[1];
    const keyId = parts[2].substring(0, 8);
    return `gv_${tenantId}_${keyId}`;
  }
  return null;
}

/**
 * Verify an API key and return the tenant ID if valid
 *
 * @param apiKey - The API key to verify (format: gv_{tenant_id}_{random_32_chars})
 * @returns The tenant ID if the key is valid, null otherwise
 */
export async function verifyApiKey(apiKey: string): Promise<string | null> {
  return LogContext.run(
    {
      operation: 'verify-api-key',
    },
    async () => {
      try {
        // Extract tenant ID from the key
        const tenantId = extractTenantId(apiKey);
        if (!tenantId) {
          logger.debug('Invalid API key format - could not extract tenant ID');
          return null;
        }

        // Get database connection for this tenant
        const pool = await dbManager.get(tenantId);
        if (!pool) {
          logger.debug('Database connection unavailable for tenant', { tenantId });
          return null;
        }

        // Extract the stored prefix to look up in database
        const storedPrefix = extractStoredPrefix(apiKey);
        if (!storedPrefix) {
          logger.debug('Invalid API key format - could not extract prefix');
          return null;
        }

        // Look up the API key metadata by prefix
        const result = await pool.query(`SELECT id FROM api_keys WHERE prefix = $1`, [
          storedPrefix,
        ]);

        if (result.rows.length === 0) {
          logger.debug('API key prefix not found in database', { storedPrefix });
          return null;
        }

        const dbId = result.rows[0].id;

        // Fetch the actual key from SSM
        const storedKey = await ssmClient.getApiKey(tenantId, `gv_api_${dbId}`);
        if (!storedKey) {
          logger.warn('API key not found in SSM', { tenantId, dbId });
          return null;
        }

        // Use constant-time comparison to prevent timing attacks
        const providedKeyBuffer = Buffer.from(apiKey, 'utf8');
        const storedKeyBuffer = Buffer.from(storedKey, 'utf8');

        // Keys must be same length for timingSafeEqual
        if (providedKeyBuffer.length !== storedKeyBuffer.length) {
          logger.debug('API key length mismatch');
          return null;
        }

        const isValid = timingSafeEqual(providedKeyBuffer, storedKeyBuffer);

        if (!isValid) {
          logger.debug('API key comparison failed');
          return null;
        }

        // Update last_used_at timestamp
        await pool.query(`UPDATE api_keys SET last_used_at = NOW() WHERE id = $1`, [dbId]);

        logger.info('API key verified successfully', { tenantId, dbId });
        return tenantId;
      } catch (error) {
        logger.error('Error verifying API key', {
          error: error instanceof Error ? error.message : 'Unknown error',
        });
        return null;
      }
    }
  );
}
