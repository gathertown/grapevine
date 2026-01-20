/**
 * Utility functions for connector management
 */

import { logger } from '../utils/logger.js';
import { getControlDbPool } from '../control-db.js';
import { Connector, ConnectorType, ConnectorStatus } from '../types/connector.js';
import { ConnectorInstallationsRepository } from './connector-installations.js';

/**
 * Upsert a connector installation - create if it doesn't exist, update if it does.
 * This is a common pattern across all connector OAuth/configuration flows.
 *
 * Uses a single SQL transaction with INSERT ... ON CONFLICT to handle upserts atomically.
 *
 * @param params Configuration for the connector installation upsert
 * @returns The created or updated connector installation, or null if an error occurred
 */
export async function installConnector(params: {
  tenantId: string;
  type: ConnectorType;
  externalId: string;
  externalMetadata?: Record<string, unknown>;
  status?: ConnectorStatus;
  updateMetadataOnExisting?: boolean;
}): Promise<Connector | null> {
  const {
    tenantId,
    type,
    externalId,
    externalMetadata = {},
    status = 'active',
    updateMetadataOnExisting = false,
  } = params;

  const pool = getControlDbPool();
  if (!pool) {
    logger.error('Control database not available for connector upsert', {
      tenant_id: tenantId,
      type,
    });
    return null;
  }

  try {
    // Build the ON CONFLICT clause based on whether we should update metadata
    const updateClause = updateMetadataOnExisting
      ? 'status = EXCLUDED.status, external_metadata = EXCLUDED.external_metadata, updated_at = NOW()'
      : 'status = EXCLUDED.status, updated_at = NOW()';

    const result = await pool.query(
      `INSERT INTO connector_installations (tenant_id, type, external_id, external_metadata, status)
       VALUES ($1, $2, $3, $4, $5)
       ON CONFLICT (tenant_id, type, external_id)
       DO UPDATE SET ${updateClause}
       RETURNING id, tenant_id, type, external_id, external_metadata, status, created_at, updated_at`,
      [tenantId, type, externalId, JSON.stringify(externalMetadata), status]
    );

    const row = result.rows[0];
    const connector: Connector = {
      id: row.id as string,
      tenant_id: row.tenant_id as string,
      type: row.type as ConnectorType,
      external_id: row.external_id as string,
      external_metadata: (row.external_metadata as Record<string, unknown>) || {},
      status: row.status as ConnectorStatus,
      created_at: (row.created_at as Date).toISOString(),
      updated_at: (row.updated_at as Date).toISOString(),
    };

    const wasUpdate =
      new Date(connector.created_at).getTime() < new Date(connector.updated_at).getTime();
    logger.info(`${wasUpdate ? 'Updated' : 'Created'} ${type} connector installation`, {
      tenant_id: tenantId,
      connector_id: connector.id,
      type,
      was_update: wasUpdate,
    });

    return connector;
  } catch (error) {
    logger.error(`Failed to upsert ${type} connector record ${externalId}: ${error.message}`, {
      tenant_id: tenantId,
      type,
      external_id: externalId,
      error,
    });
    // Don't throw - we don't want to fail OAuth/configuration flows
    return null;
  }
}

/**
 * Mark a connector as disconnected for a given tenant and type.
 * This is a safe operation that logs errors but doesn't throw, so it won't fail disconnect flows.
 *
 * @param tenantId The tenant ID
 * @param type The connector type to mark as disconnected
 * @returns true if successfully marked as disconnected, false otherwise
 */
export async function uninstallConnector(tenantId: string, type: ConnectorType): Promise<boolean> {
  try {
    const connectorsRepo = new ConnectorInstallationsRepository();
    const existingConnectorInstallation = await connectorsRepo.getByTenantAndType(tenantId, type);

    if (existingConnectorInstallation) {
      await connectorsRepo.updateStatus(existingConnectorInstallation.id, 'disconnected');
      logger.info(`Marked ${type} connector as disconnected`, {
        tenant_id: tenantId,
        connector_id: existingConnectorInstallation.id,
      });
      return true;
    }

    logger.info(`No ${type} connector found to mark as disconnected`, {
      tenant_id: tenantId,
    });
    return false;
  } catch (error) {
    logger.error(`Failed to mark ${type} connector as disconnected`, {
      tenant_id: tenantId,
      error,
    });
    // Don't throw - we don't want to fail disconnect flows
    return false;
  }
}
