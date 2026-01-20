/**
 * Repository for managing connector installations in the control database.
 */

import { Pool } from 'pg';
import { getControlDbPool } from '../control-db.js';
import { logger } from '../utils/logger.js';
import {
  Connector,
  ConnectorStatus,
  ConnectorType,
  CreateConnectorData,
} from '../types/connector.js';

export class ConnectorInstallationsRepository {
  private pool: Pool | null;

  constructor() {
    this.pool = getControlDbPool();
  }

  /**
   * Get connector by ID
   */
  async getById(id: string): Promise<Connector | null> {
    if (!this.pool) {
      logger.error('Control database not available');
      return null;
    }

    try {
      const result = await this.pool.query(
        `SELECT id, tenant_id, type, external_id, external_metadata,
                status, created_at, updated_at
         FROM connector_installations
         WHERE id = $1`,
        [id]
      );

      if (result.rows.length === 0) {
        return null;
      }

      return this.mapRow(result.rows[0]);
    } catch (error) {
      logger.error('Error getting connector by ID', { id, error });
      throw error;
    }
  }

  /**
   * Get all connectors for a tenant
   */
  async getByTenant(tenantId: string): Promise<Connector[]> {
    if (!this.pool) {
      logger.error('Control database not available');
      return [];
    }

    try {
      const result = await this.pool.query(
        `SELECT id, tenant_id, type, external_id, external_metadata,
                status, created_at, updated_at
         FROM connector_installations
         WHERE tenant_id = $1
         ORDER BY created_at DESC`,
        [tenantId]
      );

      return result.rows.map((row) => this.mapRow(row));
    } catch (error) {
      logger.error('Error getting connectors by tenant', { tenantId, error });
      throw error;
    }
  }

  /**
   * Get connector by tenant and type
   * Returns only active (non-disconnected) connectors, ordered by most recent first
   */
  async getByTenantAndType(tenantId: string, type: ConnectorType): Promise<Connector | null> {
    if (!this.pool) {
      logger.error('Control database not available');
      return null;
    }

    try {
      const result = await this.pool.query(
        `SELECT id, tenant_id, type, external_id, external_metadata,
                status, created_at, updated_at
         FROM connector_installations
         WHERE tenant_id = $1 AND type = $2 AND status != 'disconnected'
         ORDER BY created_at DESC
         LIMIT 1`,
        [tenantId, type]
      );

      if (result.rows.length === 0) {
        return null;
      }

      return this.mapRow(result.rows[0]);
    } catch (error) {
      logger.error('Error getting connector by tenant and type', { tenantId, type, error });
      throw error;
    }
  }

  /**
   * Get disconnected connector by tenant and type
   * Used to retrieve metadata from previously disconnected connectors (e.g., for reconnection scenarios)
   */
  async getDisconnectedByTenantAndType(
    tenantId: string,
    type: ConnectorType
  ): Promise<Connector | null> {
    if (!this.pool) {
      logger.error('Control database not available');
      return null;
    }

    try {
      const result = await this.pool.query(
        `SELECT id, tenant_id, type, external_id, external_metadata,
                status, created_at, updated_at
         FROM connector_installations
         WHERE tenant_id = $1 AND type = $2 AND status = 'disconnected'
         ORDER BY updated_at DESC
         LIMIT 1`,
        [tenantId, type]
      );

      if (result.rows.length === 0) {
        return null;
      }

      return this.mapRow(result.rows[0]);
    } catch (error) {
      logger.error('Error getting disconnected connector by tenant and type', {
        tenantId,
        type,
        error,
      });
      return null;
    }
  }

  /**
   * Get connector by tenant, type, and external ID (unique constraint)
   */
  async getByTenantTypeAndExternalId(
    tenantId: string,
    type: ConnectorType,
    externalId: string
  ): Promise<Connector | null> {
    if (!this.pool) {
      logger.error('Control database not available');
      return null;
    }

    try {
      const result = await this.pool.query(
        `SELECT id, tenant_id, type, external_id, external_metadata,
                status, created_at, updated_at
         FROM connector_installations
         WHERE tenant_id = $1 AND type = $2 AND external_id = $3`,
        [tenantId, type, externalId]
      );

      if (result.rows.length === 0) {
        return null;
      }

      return this.mapRow(result.rows[0]);
    } catch (error) {
      logger.error('Error getting connector by tenant, type, and external ID', {
        tenantId,
        type,
        externalId,
        error,
      });
      throw error;
    }
  }

  /**
   * Create a new connector
   */
  async create(data: CreateConnectorData): Promise<Connector> {
    if (!this.pool) {
      throw new Error('Control database not available');
    }

    try {
      const result = await this.pool.query(
        `INSERT INTO connector_installations (tenant_id, type, external_id, external_metadata, status)
         VALUES ($1, $2, $3, $4, $5)
         RETURNING id, tenant_id, type, external_id, external_metadata,
                   status, created_at, updated_at`,
        [
          data.tenant_id,
          data.type,
          data.external_id,
          JSON.stringify(data.external_metadata || {}),
          data.status || 'pending',
        ]
      );

      return this.mapRow(result.rows[0]);
    } catch (error) {
      logger.error('Error creating connector', { data, error });
      throw error;
    }
  }

  /**
   * Update connector status
   */
  async updateStatus(id: string, status: ConnectorStatus): Promise<void> {
    if (!this.pool) {
      throw new Error('Control database not available');
    }

    try {
      await this.pool.query(
        `UPDATE connector_installations
         SET status = $1, updated_at = NOW()
         WHERE id = $2`,
        [status, id]
      );
    } catch (error) {
      logger.error('Error updating connector status', { id, status, error });
      throw error;
    }
  }

  /**
   * Update connector metadata
   */
  async updateMetadata(id: string, metadata: Record<string, unknown>): Promise<void> {
    if (!this.pool) {
      throw new Error('Control database not available');
    }

    try {
      await this.pool.query(
        `UPDATE connector_installations
         SET external_metadata = $1, updated_at = NOW()
         WHERE id = $2`,
        [JSON.stringify(metadata), id]
      );
    } catch (error) {
      logger.error('Error updating connector metadata', { id, error });
      throw error;
    }
  }

  /**
   * Delete a connector (hard delete)
   */
  async delete(id: string): Promise<void> {
    if (!this.pool) {
      throw new Error('Control database not available');
    }

    try {
      await this.pool.query('DELETE FROM connector_installations WHERE id = $1', [id]);
    } catch (error) {
      logger.error('Error deleting connector', { id, error });
      throw error;
    }
  }

  /**
   * Mark connector as disconnected (soft delete)
   */
  async markDisconnected(id: string): Promise<void> {
    await this.updateStatus(id, 'disconnected');
  }

  /**
   * Get connector by type and external ID (for webhook routing without tenant_id)
   * Returns only active (non-disconnected) connectors
   */
  async getByTypeAndExternalId(type: ConnectorType, externalId: string): Promise<Connector | null> {
    if (!this.pool) {
      logger.error('Control database not available');
      return null;
    }

    try {
      const result = await this.pool.query(
        `SELECT id, tenant_id, type, external_id, external_metadata,
                status, created_at, updated_at
         FROM connector_installations
         WHERE type = $1 AND external_id = $2 AND status != 'disconnected'`,
        [type, externalId]
      );

      if (result.rows.length === 0) {
        return null;
      }

      return this.mapRow(result.rows[0]);
    } catch (error) {
      logger.error('Error getting connector by type and external ID', { type, externalId, error });
      throw error;
    }
  }

  /**
   * Get all connectors of a specific type (for cron jobs)
   * Returns only active (non-disconnected) connectors
   */
  async getAllByType(type: ConnectorType): Promise<Connector[]> {
    if (!this.pool) {
      logger.error('Control database not available');
      return [];
    }

    try {
      const result = await this.pool.query(
        `SELECT id, tenant_id, type, external_id, external_metadata,
                status, created_at, updated_at
         FROM connector_installations
         WHERE type = $1 AND status != 'disconnected'`,
        [type]
      );
      return result.rows.map((row) => this.mapRow(row));
    } catch (error) {
      logger.error('Error getting all connectors by type', { type, error });
      throw error;
    }
  }

  /**
   * Map database row to Connector object
   */
  private mapRow(row: Record<string, unknown>): Connector {
    return {
      id: row.id as string,
      tenant_id: row.tenant_id as string,
      type: row.type as ConnectorType,
      external_id: row.external_id as string,
      external_metadata: (row.external_metadata as Record<string, unknown>) || {},
      status: row.status as ConnectorStatus,
      created_at: (row.created_at as Date).toISOString(),
      updated_at: (row.updated_at as Date).toISOString(),
    };
  }
}
