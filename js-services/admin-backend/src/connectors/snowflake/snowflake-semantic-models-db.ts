/**
 * Data Access Layer for Snowflake Semantic Models and Views
 *
 * This module provides database operations for the snowflake_semantic_models table
 * in tenant databases, supporting both:
 * - Semantic Models: YAML files stored in Snowflake stages (identified by stage_path)
 * - Semantic Views: Database objects (identified by database_name, schema_name, name)
 *
 * Note: This table is in tenant databases (not control DB) for better data isolation
 * and architectural consistency with other tenant-specific operational data.
 */

import type { Pool } from 'pg';
import { randomUUID } from 'crypto';
import { logger, LogContext } from '../../utils/logger';

export enum SemanticModelType {
  MODEL = 'model',
  VIEW = 'view',
}

export enum SemanticModelState {
  ENABLED = 'enabled',
  DISABLED = 'disabled',
  DELETED = 'deleted',
  ERROR = 'error',
}

export interface SemanticModel {
  id: string;
  name: string;
  type: SemanticModelType;
  // For semantic models (YAML files in stages)
  stage_path: string | null;
  // For semantic views (database objects)
  database_name: string | null;
  schema_name: string | null;
  // Common fields
  description: string | null;
  warehouse: string | null;
  state: SemanticModelState;
  status_description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateSemanticModelData {
  name: string;
  type: SemanticModelType;
  // For semantic models
  stage_path?: string;
  // For semantic views
  database_name?: string;
  schema_name?: string;
  // Common fields
  description?: string;
  warehouse?: string;
}

export interface UpdateSemanticModelData {
  name?: string;
  description?: string | null;
  warehouse?: string | null;
  state?: SemanticModelState;
}

/**
 * Get all semantic models for a tenant
 */
export async function getSemanticModelsByTenantId(pool: Pool): Promise<SemanticModel[]> {
  return LogContext.run({ operation: 'get-semantic-models-by-tenant' }, async () => {
    try {
      const result = await pool.query(
        `SELECT id, name, type, stage_path, database_name, schema_name, description, warehouse, state, status_description, created_at, updated_at
         FROM snowflake_semantic_models
         WHERE state != $1
         ORDER BY created_at DESC`,
        [SemanticModelState.DELETED]
      );

      return result.rows;
    } catch (error) {
      logger.error('Failed to get semantic models', { error });
      return [];
    }
  });
}

/**
 * Get a single semantic model by ID
 */
export async function getSemanticModelById(pool: Pool, id: string): Promise<SemanticModel | null> {
  return LogContext.run(
    { semantic_model_id: id, operation: 'get-semantic-model-by-id' },
    async () => {
      try {
        const result = await pool.query(
          `SELECT id, name, type, stage_path, database_name, schema_name, description, warehouse, state, status_description, created_at, updated_at
           FROM snowflake_semantic_models
           WHERE id = $1 AND state != $2`,
          [id, SemanticModelState.DELETED]
        );

        return result.rows.length > 0 ? result.rows[0] : null;
      } catch (error) {
        logger.error('Failed to get semantic model', { error, semanticModelId: id });
        return null;
      }
    }
  );
}

/**
 * Create a new semantic model
 */
export async function createSemanticModel(
  pool: Pool,
  data: CreateSemanticModelData
): Promise<SemanticModel | null> {
  return LogContext.run(
    {
      name: data.name,
      stage_path: data.stage_path,
      operation: 'create-semantic-model',
    },
    async () => {
      const id = randomUUID();
      const now = new Date().toISOString();

      // Validate required fields based on type
      if (data.type === SemanticModelType.MODEL && !data.stage_path) {
        logger.error('Semantic models require stage_path');
        throw new Error('MISSING_STAGE_PATH');
      }
      if (data.type === SemanticModelType.VIEW && (!data.database_name || !data.schema_name)) {
        logger.error('Semantic views require database_name and schema_name');
        throw new Error('MISSING_DATABASE_SCHEMA');
      }

      // Check for existing deleted model with same identifier
      try {
        let existingDeleted = null;
        if (data.type === SemanticModelType.MODEL) {
          const result = await pool.query(
            `SELECT id FROM snowflake_semantic_models
             WHERE type = $1 AND stage_path = $2 AND state = $3`,
            [SemanticModelType.MODEL, data.stage_path, SemanticModelState.DELETED]
          );
          existingDeleted = result.rows.length > 0 ? result.rows[0] : null;
        } else {
          const result = await pool.query(
            `SELECT id FROM snowflake_semantic_models
             WHERE type = $1 AND database_name = $2 AND schema_name = $3 AND name = $4 AND state = $5`,
            [
              SemanticModelType.VIEW,
              data.database_name,
              data.schema_name,
              data.name,
              SemanticModelState.DELETED,
            ]
          );
          existingDeleted = result.rows.length > 0 ? result.rows[0] : null;
        }

        // If a deleted model exists, reactivate it instead of creating new
        if (existingDeleted) {
          const updateResult = await pool.query(
            `UPDATE snowflake_semantic_models
             SET state = $1, name = $2, description = $3, warehouse = $4, status_description = $5, updated_at = $6
             WHERE id = $7
             RETURNING id, name, type, stage_path, database_name, schema_name, description, warehouse, state, status_description, created_at, updated_at`,
            [
              SemanticModelState.ENABLED,
              data.name,
              data.description || null,
              data.warehouse || null,
              null, // Clear status_description when reactivating
              now,
              existingDeleted.id,
            ]
          );

          return updateResult.rows[0];
        }
      } catch (checkError) {
        logger.error('Error checking for existing deleted model', { error: checkError });
        // Continue with normal create flow
      }

      try {
        const result = await pool.query(
          `INSERT INTO snowflake_semantic_models
           (id, name, type, stage_path, database_name, schema_name, description, warehouse, state, status_description, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
           RETURNING id, name, type, stage_path, database_name, schema_name, description, warehouse, state, status_description, created_at, updated_at`,
          [
            id,
            data.name,
            data.type,
            data.stage_path || null,
            data.database_name || null,
            data.schema_name || null,
            data.description || null,
            data.warehouse || null,
            SemanticModelState.ENABLED, // enabled by default
            null, // status_description starts as null
            now,
            now,
          ]
        );

        return result.rows[0];
      } catch (error: unknown) {
        // Check for unique constraint violation
        if (
          error &&
          typeof error === 'object' &&
          'code' in error &&
          error.code === '23505' &&
          'constraint' in error &&
          typeof error.constraint === 'string'
        ) {
          if (error.constraint.includes('model_unique')) {
            logger.warn('Semantic model with this stage path already exists', {
              stagePath: data.stage_path,
            });
            throw new Error('DUPLICATE_STAGE_PATH');
          }
          if (error.constraint.includes('view_unique')) {
            logger.warn('Semantic view with this name already exists', {
              databaseName: data.database_name,
              schemaName: data.schema_name,
              name: data.name,
            });
            throw new Error('DUPLICATE_VIEW_NAME');
          }
        }

        logger.error(`Failed to create semantic ${data.type}`, {
          error,
          name: data.name,
        });
        return null;
      }
    }
  );
}

/**
 * Update a semantic model
 */
export async function updateSemanticModel(
  pool: Pool,
  id: string,
  data: UpdateSemanticModelData
): Promise<SemanticModel | null> {
  return LogContext.run(
    {
      semantic_model_id: id,
      updated_fields: Object.keys(data),
      operation: 'update-semantic-model',
    },
    async () => {
      // Build dynamic update query
      const updates: string[] = [];
      const values: (string | boolean | null | undefined)[] = [];
      let paramIndex = 1;

      if (data.name !== undefined) {
        updates.push(`name = $${paramIndex++}`);
        values.push(data.name);
      }

      if (data.description !== undefined) {
        updates.push(`description = $${paramIndex++}`);
        values.push(data.description || null);
      }

      if (data.warehouse !== undefined) {
        updates.push(`warehouse = $${paramIndex++}`);
        values.push(data.warehouse);
      }

      if (data.state !== undefined) {
        updates.push(`state = $${paramIndex++}`);
        values.push(data.state);
      }

      if (updates.length === 0) {
        logger.warn('No fields to update', { semanticModelId: id });
        return null;
      }

      updates.push(`updated_at = $${paramIndex++}`);
      values.push(new Date().toISOString());

      // Add WHERE clause parameters
      values.push(id);

      const query = `
        UPDATE snowflake_semantic_models
        SET ${updates.join(', ')}
        WHERE id = $${paramIndex++}
        RETURNING id, name, type, stage_path, database_name, schema_name, description, warehouse, state, status_description, created_at, updated_at
      `;

      try {
        const result = await pool.query(query, values);

        if (result.rows.length === 0) {
          logger.warn('Semantic model not found for update', { semanticModelId: id });
          return null;
        }

        return result.rows[0];
      } catch (error) {
        logger.error('Failed to update semantic model', {
          error,
          semanticModelId: id,
        });
        return null;
      }
    }
  );
}

/**
 * Delete a semantic model (soft delete by setting state to DELETED)
 */
export async function deleteSemanticModel(pool: Pool, id: string): Promise<boolean> {
  return LogContext.run({ semantic_model_id: id, operation: 'delete-semantic-model' }, async () => {
    try {
      const result = await pool.query(
        `UPDATE snowflake_semantic_models
           SET state = $1, updated_at = $2
           WHERE id = $3 AND state != $1
           RETURNING id, name`,
        [SemanticModelState.DELETED, new Date().toISOString(), id]
      );

      if (result.rows.length === 0) {
        logger.warn('Semantic model not found for deletion or already deleted', {
          semanticModelId: id,
        });
        return false;
      }

      return true;
    } catch (error) {
      logger.error('Failed to delete semantic model', {
        error,
        semanticModelId: id,
      });
      return false;
    }
  });
}
